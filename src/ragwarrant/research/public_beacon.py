"""Fail-closed FULL boundary for the scientific-core review branch.

PR A needs stable seed-schedule constants and freeze-manifest hashing, but it
does not contain or authorize beacon retrieval, round selection, OIDC checks,
or sealed FULL execution. The stacked integrity branch contains the integrity
implementation from the immutable review construction reference commit; that
branch remains subject to separate owner and security review.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any


FULL_ENTROPY_PROTOCOL = "DRAND_QUICKNET_FUTURE_ROUND_V1"
FULL_ENTROPY_AMENDMENT_ID = "FOCUS1-FULL-ENTROPY-DRAND-001"
FULL_CONFIRMATION_STATUS = "PENDING_FUTURE_PUBLIC_BEACON_SEAL"
RETIRED_FULL_SEED_STATUS = (
    "FULL_SECRET_SEED_COMMITMENT_RETIRED_AGENT_ACCESSIBLE_CUSTODY"
)
TRIAL_SEED_DOMAIN = b"RAGWARRANT_TRIAL_SEED_V2\x00"

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_FULL_DISABLED = (
    "PR A scientific review scope requires verified future-public-beacon "
    "entropy and does not authorize FULL execution"
)


class VerifiedFullEntropy:
    """Unconstructable marker retained for scientific API compatibility."""

    __slots__ = ("_master_seed", "_public_provenance")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "VerifiedFullEntropy can only be created by the stacked integrity "
            "implementation from a validated public-beacon receipt"
        )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_HEX.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def full_trial_seed_digest(full_master_seed: bytes, canonical_identity: str) -> str:
    """Retain the pure frozen seed derivation without exposing entropy creation."""

    if not isinstance(full_master_seed, bytes) or len(full_master_seed) != 32:
        raise ValueError("full_master_seed must contain exactly 32 bytes")
    if not isinstance(canonical_identity, str) or not canonical_identity.startswith(
        "v2|FULL|"
    ):
        raise ValueError("FULL trial identity must use the v2 FULL namespace")
    return hashlib.sha256(
        TRIAL_SEED_DOMAIN + full_master_seed + canonical_identity.encode("utf-8")
    ).hexdigest()


def require_active_full_execution(_entropy: VerifiedFullEntropy) -> None:
    """Reject every FULL execution attempt in PR A before evidence generation."""

    raise ValueError(_FULL_DISABLED)


@contextmanager
def _authorized_full_execution(
    _entropy: VerifiedFullEntropy,
) -> Iterator[dict[str, object]]:
    """Reject before OIDC, subprocess, network, RNG, or output activity."""

    raise ValueError(_FULL_DISABLED)
    yield {}  # pragma: no cover - keeps a context-manager shape without a live path


def benchmark_freeze_digest(manifest: Mapping[str, Any]) -> str:
    """Compute the preserved Focus 1 manifest digest."""

    keys = (
        "schema_version",
        "benchmark_protocol_version",
        "seed_schedule_version",
        "full_entropy_protocol",
        "protocol_version",
        "scenario_version",
        "method_interface_version",
        "estimands",
        "candidate_truth_definition",
        "event_definitions",
        "estimator_definitions",
        "enabled_risk_definitions",
        "input_hashes",
    )
    try:
        payload = {key: manifest[key] for key in keys}
    except KeyError as exc:
        raise ValueError(f"freeze manifest is missing {exc.args[0]}") from None
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def verify_benchmark_freeze_manifest(
    manifest: Mapping[str, Any], repository_root: str | Path
) -> str:
    """Verify declared input bytes without providing detached authority."""

    root = Path(repository_root).resolve()
    input_hashes = manifest.get("input_hashes")
    if not isinstance(input_hashes, Mapping) or not input_hashes:
        raise ValueError("freeze manifest input_hashes must be a nonempty mapping")
    for relative_path, expected in input_hashes.items():
        if not isinstance(relative_path, str):
            raise ValueError("freeze manifest paths must be strings")
        expected_digest = _require_sha256(expected, f"input hash for {relative_path}")
        source = (root / relative_path).resolve()
        try:
            source.relative_to(root)
        except ValueError:
            raise ValueError("freeze manifest path escapes repository root") from None
        if not source.is_file():
            raise ValueError(f"frozen input is missing: {relative_path}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected_digest:
            raise ValueError(f"frozen input hash mismatch: {relative_path}")
    digest = benchmark_freeze_digest(manifest)
    if manifest.get("benchmark_freeze_digest") != digest:
        raise ValueError("benchmark freeze digest does not match manifest contents")
    return digest


__all__ = [
    "FULL_CONFIRMATION_STATUS",
    "FULL_ENTROPY_AMENDMENT_ID",
    "FULL_ENTROPY_PROTOCOL",
    "RETIRED_FULL_SEED_STATUS",
    "VerifiedFullEntropy",
    "benchmark_freeze_digest",
    "full_trial_seed_digest",
    "require_active_full_execution",
    "verify_benchmark_freeze_manifest",
]
