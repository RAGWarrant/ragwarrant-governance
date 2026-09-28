from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .public_beacon import (
    FULL_CONFIRMATION_STATUS,
    FULL_ENTROPY_AMENDMENT_ID,
    FULL_ENTROPY_PROTOCOL,
    RETIRED_FULL_SEED_STATUS,
    VerifiedFullEntropy,
    full_trial_seed_digest,
    require_active_full_execution,
)


SEED_SCHEDULE_VERSION = 2
AMENDMENT_ID = "FOCUS1-SEED-SCHEDULE-SEPARATION-001"
PROFILE_NAMES = ("CI", "LOCAL", "FULL")
CANONICAL_IDENTITY_FORMAT = (
    "v{seed_schedule_version}|{profile}|{scenario_id}|{sample_size}|{trial_index}"
)
DERIVATION_ALGORITHM = (
    "CI/LOCAL retain SHA-256 over canonical JSON development seed material; FULL "
    "uses SHA256(ASCII('RAGWARRANT_TRIAL_SEED_V2\\0') || 32-byte verified future-"
    "beacon master seed || UTF8(canonical trial identity))"
)
SEED_FINGERPRINT_ALGORITHM = (
    "SHA-256 namespace fingerprint over profile and canonical trial identity for "
    "static pre-reveal collision defense; FULL runtime fingerprints use the exact "
    "future-beacon trial-seed derivation"
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _positive_integer(value: object, label: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    minimum = 0 if allow_zero else 1
    if value < minimum:
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{label} must be {qualifier}")
    return value


def validate_seed_schedule_metadata(config: Mapping[str, Any]) -> None:
    if config.get("seed_schedule_version") != SEED_SCHEDULE_VERSION:
        raise ValueError(f"seed_schedule_version must be {SEED_SCHEDULE_VERSION}")
    if config.get("seed_schedule_amendment_id") != AMENDMENT_ID:
        raise ValueError(f"seed_schedule_amendment_id must be {AMENDMENT_ID}")
    profiles = config.get("profiles")
    if not isinstance(profiles, Mapping) or set(profiles) != set(PROFILE_NAMES):
        raise ValueError("profiles must contain exactly CI, LOCAL, and FULL")
    if config.get("full_entropy_protocol") != FULL_ENTROPY_PROTOCOL:
        raise ValueError(f"full_entropy_protocol must be {FULL_ENTROPY_PROTOCOL}")
    if config.get("full_entropy_amendment_id") != FULL_ENTROPY_AMENDMENT_ID:
        raise ValueError(
            f"full_entropy_amendment_id must be {FULL_ENTROPY_AMENDMENT_ID}"
        )
    if config.get("full_confirmation_status") != FULL_CONFIRMATION_STATUS:
        raise ValueError(f"full_confirmation_status must be {FULL_CONFIRMATION_STATUS}")
    if config.get("retired_full_seed_status") != RETIRED_FULL_SEED_STATUS:
        raise ValueError(f"retired_full_seed_status must be {RETIRED_FULL_SEED_STATUS}")
    if "full_seed_commitment_sha256" in config:
        raise ValueError("retired full_seed_commitment_sha256 must not remain configured")


def canonical_trial_identity(
    seed_schedule_version: int,
    profile: str,
    scenario_id: str,
    sample_size: int,
    trial_index: int,
) -> str:
    if seed_schedule_version != SEED_SCHEDULE_VERSION:
        raise ValueError(f"seed_schedule_version must be {SEED_SCHEDULE_VERSION}")
    if profile not in PROFILE_NAMES:
        raise ValueError(f"unknown profile: {profile}")
    if _SAFE_ID.fullmatch(scenario_id) is None:
        raise ValueError("scenario_id is not portable for canonical trial identity")
    _positive_integer(sample_size, "sample_size")
    _positive_integer(trial_index, "trial_index", allow_zero=True)
    return (
        f"v{seed_schedule_version}|{profile}|{scenario_id}|{sample_size}|"
        f"{trial_index}"
    )


def trial_seed_digest(master_seed: int, trial_identity: str) -> str:
    _positive_integer(master_seed, "profile master seed", allow_zero=True)
    payload = _canonical_json(
        ["ragwarrant-evidence-trial-seed-v2", master_seed, trial_identity]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def trial_seed(master_seed: int, trial_identity: str) -> int:
    return int(trial_seed_digest(master_seed, trial_identity), 16)


def _profile_seed_source_commitment(
    config: Mapping[str, Any],
    profile: str,
    development_master_seed: int | None = None,
) -> str:
    if profile not in PROFILE_NAMES:
        raise ValueError(f"unknown profile: {profile}")
    if profile == "FULL":
        payload = _canonical_json(
            ["ragwarrant-future-public-beacon-namespace-v1", FULL_ENTROPY_PROTOCOL]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    public_seed = (
        config.get("master_seed")
        if development_master_seed is None
        else development_master_seed
    )
    _positive_integer(public_seed, "development master seed", allow_zero=True)
    payload = _canonical_json(
        ["ragwarrant-public-development-seed-v2", profile, public_seed]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def schedule_seed_fingerprint(
    config: Mapping[str, Any],
    profile: str,
    trial_identity: str,
    *,
    development_master_seed: int | None = None,
) -> str:
    payload = _canonical_json(
        [
            "ragwarrant-schedule-seed-fingerprint-v2",
            _profile_seed_source_commitment(
                config, profile, development_master_seed
            ),
            trial_identity,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def enumerate_profile_trial_identities(
    config: Mapping[str, Any], profile: str
) -> tuple[str, ...]:
    validate_seed_schedule_metadata(config)
    if profile not in PROFILE_NAMES:
        raise ValueError(f"unknown profile: {profile}")
    replicate_count = _positive_integer(
        config["profiles"][profile].get("replicate_count"),
        f"profile {profile} replicate_count",
    )
    scenarios = config.get("scenarios")
    if not isinstance(scenarios, Sequence) or isinstance(scenarios, (str, bytes)):
        raise ValueError("scenarios must be a list")
    identities: list[str] = []
    for scenario in sorted(scenarios, key=lambda item: str(item["scenario_id"])):
        scenario_id = str(scenario["scenario_id"])
        sample_sizes = scenario.get("sample_sizes")
        if not isinstance(sample_sizes, Sequence) or isinstance(sample_sizes, (str, bytes)):
            raise ValueError(f"scenario {scenario_id} sample_sizes must be a list")
        for sample_size in sorted(int(value) for value in sample_sizes):
            for trial_index in range(replicate_count):
                identities.append(
                    canonical_trial_identity(
                        SEED_SCHEDULE_VERSION,
                        profile,
                        scenario_id,
                        sample_size,
                        trial_index,
                    )
                )
    return tuple(identities)


def build_seed_schedule_manifest(config: Mapping[str, Any]) -> dict[str, object]:
    validate_seed_schedule_metadata(config)
    identities_by_profile = {
        profile: enumerate_profile_trial_identities(config, profile)
        for profile in PROFILE_NAMES
    }
    identity_sets = {
        profile: set(identities) for profile, identities in identities_by_profile.items()
    }
    overlap_counts = {
        "CI_LOCAL": len(identity_sets["CI"] & identity_sets["LOCAL"]),
        "CI_FULL": len(identity_sets["CI"] & identity_sets["FULL"]),
        "LOCAL_FULL": len(identity_sets["LOCAL"] & identity_sets["FULL"]),
    }
    if any(overlap_counts.values()):
        raise ValueError(f"profile trial identity sets overlap: {overlap_counts}")

    fingerprints = [
        schedule_seed_fingerprint(config, profile, identity)
        for profile in PROFILE_NAMES
        for identity in identities_by_profile[profile]
    ]
    duplicate_seed_count = len(fingerprints) - len(set(fingerprints))
    if duplicate_seed_count:
        raise ValueError(
            f"configured schedule contains {duplicate_seed_count} duplicate seed fingerprints"
        )

    scenarios = sorted(config["scenarios"], key=lambda item: str(item["scenario_id"]))
    cells = [
        {"scenario_id": str(scenario["scenario_id"]), "sample_size": int(sample_size)}
        for scenario in scenarios
        for sample_size in sorted(scenario["sample_sizes"])
    ]
    identity_set_hashes = {
        profile: hashlib.sha256(
            _canonical_json(list(identities_by_profile[profile])).encode("utf-8")
        ).hexdigest()
        for profile in PROFILE_NAMES
    }
    complete_schedule_hash = hashlib.sha256(
        _canonical_json(
            {
                profile: list(identities_by_profile[profile])
                for profile in PROFILE_NAMES
            }
        ).encode("utf-8")
    ).hexdigest()
    return {
        "seed_schedule_version": SEED_SCHEDULE_VERSION,
        "amendment_id": AMENDMENT_ID,
        "derivation_algorithm": DERIVATION_ALGORITHM,
        "seed_fingerprint_algorithm": SEED_FINGERPRINT_ALGORITHM,
        "canonical_identity_format": CANONICAL_IDENTITY_FORMAT,
        "profile_names": list(PROFILE_NAMES),
        "scenario_count": len(scenarios),
        "sample_size_cell_count": len(cells),
        "sample_size_cells": cells,
        "configured_trial_counts": {
            profile: len(identities_by_profile[profile]) for profile in PROFILE_NAMES
        },
        "identity_set_hashes_by_profile": identity_set_hashes,
        "complete_schedule_hash": complete_schedule_hash,
        "overlap_counts": overlap_counts,
        "duplicate_seed_count": duplicate_seed_count,
        "full_entropy_protocol": FULL_ENTROPY_PROTOCOL,
        "full_entropy_amendment_id": FULL_ENTROPY_AMENDMENT_ID,
        "full_confirmation_status": FULL_CONFIRMATION_STATUS,
        "retired_full_seed_status": RETIRED_FULL_SEED_STATUS,
        "full_target_round_selected": False,
        "full_evidence_generated": False,
        "full_results_inspected": False,
        "schedule_enumeration_generated_evidence": False,
    }


def profile_master_seed_value(
    config: Mapping[str, Any],
    profile: str,
    seed_input: int | VerifiedFullEntropy | None,
) -> int:
    if profile not in PROFILE_NAMES:
        raise ValueError(f"unknown profile: {profile}")
    if profile == "FULL":
        if not isinstance(seed_input, VerifiedFullEntropy):
            raise ValueError("FULL requires a verified future-public-beacon entropy context")
        require_active_full_execution(seed_input)
        return int.from_bytes(seed_input._master_seed, "big")
    if isinstance(seed_input, VerifiedFullEntropy):
        raise ValueError("verified FULL entropy is not accepted for development profiles")
    value = config["master_seed"] if seed_input is None else seed_input
    _positive_integer(value, "profile master seed", allow_zero=True)
    return value


def validate_revealed_profile_seed_uniqueness(
    config: Mapping[str, Any], profile: str, master_seed: int | VerifiedFullEntropy
) -> None:
    identities = enumerate_profile_trial_identities(config, profile)
    if profile == "FULL":
        if not isinstance(master_seed, VerifiedFullEntropy):
            raise ValueError("FULL uniqueness validation requires verified beacon entropy")
        require_active_full_execution(master_seed)
        digests = [
            full_trial_seed_digest(master_seed._master_seed, identity)
            for identity in identities
        ]
    else:
        if isinstance(master_seed, VerifiedFullEntropy):
            raise ValueError("development uniqueness validation rejects FULL entropy")
        digests = [trial_seed_digest(master_seed, identity) for identity in identities]
    if len(digests) != len(set(digests)):
        raise ValueError(f"profile {profile} contains duplicate revealed trial seeds")
