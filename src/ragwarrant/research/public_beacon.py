from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FULL_ENTROPY_PROTOCOL = "DRAND_QUICKNET_FUTURE_ROUND_V1"
FULL_ENTROPY_AMENDMENT_ID = "FOCUS1-FULL-ENTROPY-DRAND-001"
FULL_CONFIRMATION_STATUS = "PENDING_FUTURE_PUBLIC_BEACON_SEAL"
RETIRED_FULL_SEED_STATUS = (
    "FULL_SECRET_SEED_COMMITMENT_RETIRED_AGENT_ACCESSIBLE_CUSTODY"
)
SEAL_SCHEMA_VERSION = "1.0"
EXECUTION_RECEIPT_SCHEMA_VERSION = "1.0"
FULL_SEED_DERIVATION = "RAGWARRANT_FULL_MASTER_SEED_V1"
FULL_SEED_DOMAIN = b"RAGWARRANT_FULL_MASTER_SEED_V1\x00"
TRIAL_SEED_DOMAIN = b"RAGWARRANT_TRIAL_SEED_V2\x00"
MINIMUM_SEAL_LEAD_SECONDS = 30 * 60

QUICKNET_BEACON_ID = "quicknet"
QUICKNET_CHAIN_HASH = (
    "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
)
QUICKNET_PUBLIC_KEY = (
    "83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183c"
    "8c4b450b6a0a6c3ac6a5776a2d1064510d1fec758c921cc22b0e17e63aaf4b"
    "cb5ed66304de9cf809bd274ca73bab4af5a6e9c76a4bc09e76eae8991ef5ece45a"
)
QUICKNET_GENESIS_TIME = 1_692_803_367
QUICKNET_PERIOD_SECONDS = 3
QUICKNET_SCHEME = "bls-unchained-g1-rfc9380"
QUICKNET_RELAYS = (
    f"https://api.drand.sh/{QUICKNET_CHAIN_HASH}",
    f"https://drand.cloudflare.com/{QUICKNET_CHAIN_HASH}",
)
DRAND_CLIENT_PACKAGE = "drand-client"
DRAND_CLIENT_VERSION = "1.4.2"
DRAND_CLIENT_INTEGRITY = (
    "sha512-jeNJmrVplfgIA/GVndxxJ5mo8y63BS2pEdNhk1siU4pQ+z/"
    "BnxsqRnxjH9ag1ip887s12SEgo0MTZPbQNz27NA=="
)

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SIGNATURE_HEX = re.compile(r"^[0-9a-f]+$")
_VERIFIED_ENTROPY_TOKEN = object()
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_RECEIPT_SIGNATURE_VERIFIER = (
    _REPOSITORY_ROOT / ".github/drand-verifier/verify_receipt_signature.mjs"
)
_DRAND_CLIENT_PACKAGE = (
    _REPOSITORY_ROOT / ".github/drand-verifier/node_modules/drand-client/package.json"
)
_GITHUB_OIDC_VERIFIER = (
    _REPOSITORY_ROOT / ".github/drand-verifier/verify_github_oidc.mjs"
)


@dataclass(frozen=True)
class QuicknetParameters:
    beacon_id: str = QUICKNET_BEACON_ID
    chain_hash: str = QUICKNET_CHAIN_HASH
    public_key: str = QUICKNET_PUBLIC_KEY
    genesis_time: int = QUICKNET_GENESIS_TIME
    period_seconds: int = QUICKNET_PERIOD_SECONDS
    scheme: str = QUICKNET_SCHEME

    def as_dict(self) -> dict[str, object]:
        return {
            "beacon_id": self.beacon_id,
            "chain_hash": self.chain_hash,
            "public_key": self.public_key,
            "genesis_time": self.genesis_time,
            "period_seconds": self.period_seconds,
            "scheme": self.scheme,
        }


PINNED_QUICKNET = QuicknetParameters()


class VerifiedFullEntropy:
    __slots__ = ("_master_seed", "_public_provenance")

    def __init__(
        self,
        master_seed: bytes,
        public_provenance: Mapping[str, object],
        *,
        _token: object | None = None,
    ) -> None:
        if _token is not _VERIFIED_ENTROPY_TOKEN:
            raise TypeError(
                "VerifiedFullEntropy can only be created from a validated public-beacon receipt"
            )
        if len(master_seed) != 32:
            raise ValueError("FULL master seed must contain exactly 32 bytes")
        self._master_seed = master_seed
        self._public_provenance = dict(public_provenance)

    def __repr__(self) -> str:
        return (
            "<VerifiedFullEntropy beacon_verified=True "
            "master_seed_persisted=False seed_redacted=True>"
        )

    def public_provenance(self) -> dict[str, object]:
        return dict(self._public_provenance)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_HEX.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_commit(value: object, label: str = "subject_commit") -> str:
    if not isinstance(value, str) or _COMMIT_SHA.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase 40-character Git commit SHA")
    return value


def _require_positive_round(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("target_round must be a positive integer")
    if value > (2**64 - 1):
        raise ValueError("target_round exceeds uint64")
    return value


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 UTC timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise ValueError(f"{label} must be an ISO-8601 UTC timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be an ISO-8601 UTC timestamp")
    return parsed.astimezone(timezone.utc)


def _verify_receipt_bls_signature(receipt: Mapping[str, Any]) -> None:
    if not _RECEIPT_SIGNATURE_VERIFIER.is_file() or not _DRAND_CLIENT_PACKAGE.is_file():
        raise ValueError(
            "pinned drand verifier is unavailable; install the frozen workflow dependency"
        )
    package = json.loads(_DRAND_CLIENT_PACKAGE.read_text(encoding="utf-8"))
    if package.get("name") != DRAND_CLIENT_PACKAGE or package.get("version") != DRAND_CLIENT_VERSION:
        raise ValueError("installed drand-client does not match the frozen verifier version")
    with tempfile.TemporaryDirectory(prefix="ragwarrant-receipt-bls-") as temporary:
        receipt_path = Path(temporary) / "receipt.json"
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        try:
            subprocess.run(
                ["node", str(_RECEIPT_SIGNATURE_VERIFIER), str(receipt_path)],
                cwd=_REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError("beacon receipt BLS signature verification failed") from exc


def verify_github_actions_execution_context(
    provenance: Mapping[str, Any],
) -> dict[str, str | bool]:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("FULL execution is restricted to the frozen GitHub Actions workflow")
    if not os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL") or not os.environ.get(
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN"
    ):
        raise ValueError("FULL execution requires a GitHub Actions OIDC capability")
    if not _GITHUB_OIDC_VERIFIER.is_file():
        raise ValueError("frozen GitHub OIDC verifier is missing")
    subject = _require_commit(provenance.get("subject_commit"))
    seal_sha = _require_sha256(provenance.get("seal_sha256"), "seal_sha256")
    try:
        result = subprocess.run(
            ["node", str(_GITHUB_OIDC_VERIFIER), subject, seal_sha],
            cwd=_REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        attestation = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise ValueError("GitHub Actions OIDC execution verification failed") from exc
    if attestation.get("github_oidc_execution_verified") is not True:
        raise ValueError("GitHub Actions OIDC verifier did not authorize FULL")
    if attestation.get("sha") != subject:
        raise ValueError("GitHub Actions OIDC attestation commit mismatch")
    return dict(attestation)


def _build_full_execution_gate():
    active: ContextVar[tuple[VerifiedFullEntropy, object] | None] = ContextVar(
        "ragwarrant_active_full_execution", default=None
    )

    @contextmanager
    def authorize(entropy: VerifiedFullEntropy):
        attestation = verify_github_actions_execution_context(
            entropy.public_provenance()
        )
        reset_token = active.set((entropy, object()))
        try:
            yield attestation
        finally:
            active.reset(reset_token)

    def require(entropy: VerifiedFullEntropy) -> None:
        current = active.get()
        if current is None or current[0] is not entropy:
            raise ValueError(
                "FULL entropy requires the active frozen GitHub Actions execution gate"
            )

    return authorize, require


_authorized_full_execution, require_active_full_execution = (
    _build_full_execution_gate()
)


def _utc_text(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def quicknet_round_timestamp(round_number: int) -> int:
    round_number = _require_positive_round(round_number)
    return QUICKNET_GENESIS_TIME + (round_number - 1) * QUICKNET_PERIOD_SECONDS


def first_quicknet_round_at_or_after(target_timestamp: int) -> int:
    if isinstance(target_timestamp, bool) or not isinstance(target_timestamp, int):
        raise ValueError("target_timestamp must be an integer Unix timestamp")
    if target_timestamp <= QUICKNET_GENESIS_TIME:
        return 1
    delta = target_timestamp - QUICKNET_GENESIS_TIME
    return (delta + QUICKNET_PERIOD_SECONDS - 1) // QUICKNET_PERIOD_SECONDS + 1


def select_future_quicknet_round(
    workflow_start_timestamp: int,
    minimum_lead_seconds: int = MINIMUM_SEAL_LEAD_SECONDS,
) -> tuple[int, int]:
    if (
        isinstance(workflow_start_timestamp, bool)
        or not isinstance(workflow_start_timestamp, int)
    ):
        raise ValueError("workflow_start_timestamp must be an integer Unix timestamp")
    if minimum_lead_seconds < MINIMUM_SEAL_LEAD_SECONDS:
        raise ValueError("minimum seal lead must be at least 30 minutes")
    target_timestamp = workflow_start_timestamp + minimum_lead_seconds
    round_number = first_quicknet_round_at_or_after(target_timestamp)
    scheduled_timestamp = quicknet_round_timestamp(round_number)
    if scheduled_timestamp < target_timestamp:
        raise AssertionError("selected round precedes the required target timestamp")
    return round_number, scheduled_timestamp


def build_seal_manifest(
    *,
    subject_commit: str,
    benchmark_freeze_digest: str,
    workflow_start_timestamp: int,
    seed_schedule_version: int = 2,
) -> dict[str, object]:
    subject_commit = _require_commit(subject_commit)
    benchmark_freeze_digest = _require_sha256(
        benchmark_freeze_digest, "benchmark_freeze_digest"
    )
    if seed_schedule_version != 2:
        raise ValueError("seed_schedule_version must be 2")
    target_round, target_timestamp = select_future_quicknet_round(
        workflow_start_timestamp
    )
    return {
        "schema_version": SEAL_SCHEMA_VERSION,
        "entropy_protocol": FULL_ENTROPY_PROTOCOL,
        "amendment_id": FULL_ENTROPY_AMENDMENT_ID,
        "seal_status": "SEALED_PENDING_BEACON",
        "subject_commit": subject_commit,
        "benchmark_freeze_digest": benchmark_freeze_digest,
        "seed_schedule_version": seed_schedule_version,
        "seal_workflow_started_at_utc": _utc_text(workflow_start_timestamp),
        "drand": {
            **PINNED_QUICKNET.as_dict(),
            "target_round": target_round,
            "target_round_timestamp_utc": _utc_text(target_timestamp),
        },
        "seed_derivation": FULL_SEED_DERIVATION,
        "canonical_trial_identity_format": (
            "v2|<PROFILE>|<SCENARIO_ID>|<SAMPLE_SIZE>|<TRIAL_INDEX>"
        ),
        "no_fallback_round": True,
        "automatic_result_publication": True,
        "full_executed": False,
    }


def canonical_seal_branch(subject_commit: str) -> str:
    return f"ragwarrant-full-seal-{_require_commit(subject_commit)}"


def canonical_frozen_subject_branch(subject_commit: str) -> str:
    return f"ragwarrant-full-subject-{_require_commit(subject_commit)}"


def sealed_round_for_retry(
    seal: Mapping[str, Any], requested_round: int | None = None
) -> int:
    validate_seal_manifest(seal)
    sealed_round = int(seal["drand"]["target_round"])
    if requested_round is not None and requested_round != sealed_round:
        raise ValueError("retry round must equal the original sealed round")
    return sealed_round


def validate_seal_manifest(seal: Mapping[str, Any]) -> None:
    if seal.get("schema_version") != SEAL_SCHEMA_VERSION:
        raise ValueError("unsupported seal schema_version")
    if seal.get("entropy_protocol") != FULL_ENTROPY_PROTOCOL:
        raise ValueError("seal entropy_protocol does not match the frozen protocol")
    if seal.get("amendment_id") != FULL_ENTROPY_AMENDMENT_ID:
        raise ValueError("seal amendment_id does not match the frozen protocol")
    if seal.get("seal_status") != "SEALED_PENDING_BEACON":
        raise ValueError("seal_status must be SEALED_PENDING_BEACON")
    _require_commit(seal.get("subject_commit"))
    _require_sha256(seal.get("benchmark_freeze_digest"), "benchmark_freeze_digest")
    if seal.get("seed_schedule_version") != 2:
        raise ValueError("seal seed_schedule_version must be 2")
    if seal.get("seed_derivation") != FULL_SEED_DERIVATION:
        raise ValueError("seal seed derivation is not recognized")
    if seal.get("no_fallback_round") is not True:
        raise ValueError("seal must prohibit fallback rounds")
    if seal.get("automatic_result_publication") is not True:
        raise ValueError("seal must require automatic result publication")
    if seal.get("full_executed") is not False:
        raise ValueError("an original seal cannot claim FULL execution")
    drand = seal.get("drand")
    if not isinstance(drand, Mapping):
        raise ValueError("seal drand parameters are missing")
    for key, expected in PINNED_QUICKNET.as_dict().items():
        if drand.get(key) != expected:
            raise ValueError(f"seal drand {key} does not match pinned Quicknet")
    target_round = _require_positive_round(drand.get("target_round"))
    scheduled = _parse_utc(
        drand.get("target_round_timestamp_utc"), "target_round_timestamp_utc"
    )
    if int(scheduled.timestamp()) != quicknet_round_timestamp(target_round):
        raise ValueError("sealed round timestamp does not match pinned Quicknet schedule")
    started = _parse_utc(
        seal.get("seal_workflow_started_at_utc"), "seal_workflow_started_at_utc"
    )
    expected_round, expected_timestamp = select_future_quicknet_round(
        int(started.timestamp())
    )
    if target_round != expected_round or int(scheduled.timestamp()) != expected_timestamp:
        raise ValueError(
            "seal must use the first Quicknet round at least 30 minutes after workflow start"
        )


def derive_full_master_seed(
    *,
    target_round: int,
    verified_beacon_randomness: str,
    benchmark_freeze_digest: str,
    focus2_freeze_commit_sha: str,
) -> bytes:
    target_round = _require_positive_round(target_round)
    randomness = _require_sha256(
        verified_beacon_randomness, "verified_beacon_randomness"
    )
    freeze_digest = _require_sha256(
        benchmark_freeze_digest, "benchmark_freeze_digest"
    )
    commit = _require_commit(focus2_freeze_commit_sha, "focus2_freeze_commit_sha")
    payload = b"".join(
        (
            FULL_SEED_DOMAIN,
            bytes.fromhex(QUICKNET_CHAIN_HASH),
            target_round.to_bytes(8, "big", signed=False),
            bytes.fromhex(randomness),
            bytes.fromhex(freeze_digest),
            bytes.fromhex(commit),
        )
    )
    return hashlib.sha256(payload).digest()


def full_trial_seed_digest(full_master_seed: bytes, canonical_identity: str) -> str:
    if not isinstance(full_master_seed, bytes) or len(full_master_seed) != 32:
        raise ValueError("full_master_seed must contain exactly 32 bytes")
    if not isinstance(canonical_identity, str) or not canonical_identity.startswith(
        "v2|FULL|"
    ):
        raise ValueError("FULL trial identity must use the v2 FULL namespace")
    return hashlib.sha256(
        TRIAL_SEED_DOMAIN + full_master_seed + canonical_identity.encode("utf-8")
    ).hexdigest()


def _validate_verified_receipt(
    seal: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    current_timestamp: int,
) -> dict[str, object]:
    validate_seal_manifest(seal)
    if receipt.get("schema_version") != EXECUTION_RECEIPT_SCHEMA_VERSION:
        raise ValueError("unsupported beacon receipt schema_version")
    if receipt.get("entropy_protocol") != FULL_ENTROPY_PROTOCOL:
        raise ValueError("beacon receipt entropy protocol mismatch")
    if receipt.get("verification_status") != "VERIFIED":
        raise ValueError("FULL requires a cryptographically verified beacon receipt")
    if receipt.get("signature_verified") is not True:
        raise ValueError("FULL requires a verified beacon signature")
    if receipt.get("subject_commit") != seal.get("subject_commit"):
        raise ValueError("beacon receipt subject commit differs from the seal")
    if receipt.get("benchmark_freeze_digest") != seal.get("benchmark_freeze_digest"):
        raise ValueError("beacon receipt benchmark digest differs from the seal")
    if receipt.get("seal_sha256") != hashlib.sha256(
        (_canonical_json(seal) + "\n").encode("utf-8")
    ).hexdigest():
        raise ValueError("beacon receipt does not bind the exact canonical seal")
    verifier = receipt.get("verifier")
    if not isinstance(verifier, Mapping):
        raise ValueError("beacon verifier metadata is missing")
    expected_verifier = {
        "package": DRAND_CLIENT_PACKAGE,
        "version": DRAND_CLIENT_VERSION,
        "integrity": DRAND_CLIENT_INTEGRITY,
        "beacon_verification_disabled": False,
    }
    for key, expected in expected_verifier.items():
        if verifier.get(key) != expected:
            raise ValueError(f"beacon verifier {key} does not match the pinned verifier")
    drand = receipt.get("drand")
    sealed_drand = seal["drand"]
    if not isinstance(drand, Mapping) or not isinstance(sealed_drand, Mapping):
        raise ValueError("beacon receipt drand data is missing")
    for key, expected in PINNED_QUICKNET.as_dict().items():
        if drand.get(key) != expected:
            raise ValueError(f"beacon receipt drand {key} does not match Quicknet")
    target_round = _require_positive_round(drand.get("round"))
    if target_round != sealed_drand.get("target_round"):
        raise ValueError("beacon receipt round differs from the sealed round")
    target_timestamp = quicknet_round_timestamp(target_round)
    if current_timestamp < target_timestamp:
        raise ValueError("FULL cannot execute before the sealed round")
    randomness = _require_sha256(drand.get("randomness"), "beacon randomness")
    signature = drand.get("signature")
    if (
        not isinstance(signature, str)
        or len(signature) % 2 != 0
        or _SIGNATURE_HEX.fullmatch(signature) is None
    ):
        raise ValueError("beacon signature must be nonempty lowercase hexadecimal")
    if hashlib.sha256(bytes.fromhex(signature)).hexdigest() != randomness:
        raise ValueError("beacon randomness does not equal SHA-256(signature)")
    relays = receipt.get("relay_verifications")
    if not isinstance(relays, list) or len(relays) < 2:
        raise ValueError("at least two relay verification records are required")
    relay_urls: set[str] = set()
    for relay in relays:
        if not isinstance(relay, Mapping):
            raise ValueError("relay verification record must be an object")
        url = relay.get("relay_url")
        if url not in QUICKNET_RELAYS or url in relay_urls:
            raise ValueError("relay verification URLs must be distinct pinned relays")
        relay_urls.add(str(url))
        if relay.get("signature_verified") is not True:
            raise ValueError("each accepted relay response must be signature verified")
        if relay.get("round") != target_round:
            raise ValueError("relay response round differs from the sealed round")
        _require_sha256(relay.get("response_sha256"), "relay response_sha256")
    publication = receipt.get("seal_publication")
    if not isinstance(publication, Mapping):
        raise ValueError("GitHub seal publication metadata is missing")
    if publication.get("schema_version") != "1.0":
        raise ValueError("unsupported seal publication schema_version")
    if publication.get("subject_commit") != seal.get("subject_commit"):
        raise ValueError("seal publication subject differs from the seal")
    if publication.get("seal_sha256") != receipt.get("seal_sha256"):
        raise ValueError("seal publication does not bind the exact seal bytes")
    _require_commit(publication.get("seal_commit_sha"), "seal_commit_sha")
    expected_branch = canonical_seal_branch(str(seal["subject_commit"]))
    if publication.get("canonical_seal_branch") != expected_branch:
        raise ValueError("seal publication canonical branch mismatch")
    if publication.get("canonical_seal_ref") != (
        f"refs/heads/{expected_branch}"
    ):
        raise ValueError("receipt does not reference the canonical seal branch")
    if publication.get("frozen_subject_ref") != (
        f"refs/heads/{canonical_frozen_subject_branch(str(seal['subject_commit']))}"
    ):
        raise ValueError("receipt does not bind the immutable frozen subject ref")
    run_id = publication.get("seal_workflow_run_id")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        raise ValueError("seal publication workflow run ID is invalid")
    if not isinstance(publication.get("draft_pr_url"), str):
        raise ValueError("receipt must identify the public draft seal PR")
    published_at = _parse_utc(
        publication.get("github_created_at_utc"), "github_created_at_utc"
    )
    if int(published_at.timestamp()) >= target_timestamp:
        raise ValueError("seal draft PR was not public before the target round")
    _verify_receipt_bls_signature(receipt)
    return {
        "target_round": target_round,
        "randomness": randomness,
        "signature": signature,
        "seal_sha256": receipt["seal_sha256"],
        "verifier": dict(verifier),
        "relay_verifications": [dict(item) for item in relays],
        "seal_publication": dict(publication),
    }


def verified_full_entropy_from_receipt(
    seal: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    current_timestamp: int,
    expected_subject_commit: str,
    expected_benchmark_freeze_digest: str,
) -> VerifiedFullEntropy:
    expected_subject_commit = _require_commit(expected_subject_commit)
    expected_benchmark_freeze_digest = _require_sha256(
        expected_benchmark_freeze_digest, "expected_benchmark_freeze_digest"
    )
    if seal.get("subject_commit") != expected_subject_commit:
        raise ValueError("executed commit differs from the sealed frozen commit")
    if seal.get("benchmark_freeze_digest") != expected_benchmark_freeze_digest:
        raise ValueError("executed benchmark digest differs from the sealed digest")
    provenance = _validate_verified_receipt(
        seal, receipt, current_timestamp=current_timestamp
    )
    master_seed = derive_full_master_seed(
        target_round=int(provenance["target_round"]),
        verified_beacon_randomness=str(provenance["randomness"]),
        benchmark_freeze_digest=expected_benchmark_freeze_digest,
        focus2_freeze_commit_sha=expected_subject_commit,
    )
    return VerifiedFullEntropy(
        master_seed,
        {
            "entropy_protocol": FULL_ENTROPY_PROTOCOL,
            "amendment_id": FULL_ENTROPY_AMENDMENT_ID,
            "subject_commit": expected_subject_commit,
            "benchmark_freeze_digest": expected_benchmark_freeze_digest,
            "drand": {
                **PINNED_QUICKNET.as_dict(),
                "round": provenance["target_round"],
                "randomness": provenance["randomness"],
                "signature": provenance["signature"],
            },
            "verifier": provenance["verifier"],
            "relay_verifications": provenance["relay_verifications"],
            "seal_publication": provenance["seal_publication"],
            "seal_sha256": provenance["seal_sha256"],
            "beacon_signature_verified": True,
            "full_master_seed_persisted": False,
        },
        _token=_VERIFIED_ENTROPY_TOKEN,
    )


def build_execution_closure(
    seal: Mapping[str, Any],
    execution_manifest: Mapping[str, Any] | None,
    *,
    workflow_conclusion: str,
    workflow_run_url: str,
    output_hashes_verified: bool = False,
) -> dict[str, object]:
    validate_seal_manifest(seal)
    sealed_drand = seal["drand"]
    expected_seal_hash = hashlib.sha256(
        (_canonical_json(seal) + "\n").encode("utf-8")
    ).hexdigest()
    completed = (
        workflow_conclusion == "success"
        and isinstance(execution_manifest, Mapping)
        and execution_manifest.get("schema_version") == "1.0"
        and execution_manifest.get("execution_status") == "COMPLETED"
        and execution_manifest.get("entropy_protocol") == FULL_ENTROPY_PROTOCOL
        and execution_manifest.get("subject_commit") == seal.get("subject_commit")
        and execution_manifest.get("benchmark_freeze_digest")
        == seal.get("benchmark_freeze_digest")
        and execution_manifest.get("seed_schedule_version") == 2
        and execution_manifest.get("seal_sha256") == expected_seal_hash
        and isinstance(execution_manifest.get("drand"), Mapping)
        and execution_manifest["drand"].get("round")
        == sealed_drand.get("target_round")
        and execution_manifest.get("full_master_seed_persisted") is False
        and execution_manifest.get("scientific_results_publication_required") is True
        and isinstance(execution_manifest.get("output_hashes"), Mapping)
        and bool(execution_manifest.get("output_hashes"))
        and output_hashes_verified
    )
    return {
        "schema_version": "1.0",
        "closure_status": "COMPLETED" if completed else "ABORTED_OR_INCOMPLETE",
        "subject_commit": seal["subject_commit"],
        "benchmark_freeze_digest": seal["benchmark_freeze_digest"],
        "sealed_round": seal["drand"]["target_round"],
        "workflow_conclusion": workflow_conclusion,
        "workflow_run_url": workflow_run_url,
        "same_seal_required_for_resume": True,
        "fallback_round_permitted": False,
        "publication_independent_of_scientific_direction": True,
        "execution_manifest_present": execution_manifest is not None,
        "output_hashes_verified": output_hashes_verified,
    }


def benchmark_freeze_digest(manifest: Mapping[str, Any]) -> str:
    payload = {
        key: manifest[key]
        for key in (
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
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def verify_benchmark_freeze_manifest(
    manifest: Mapping[str, Any], repository_root: str | Path
) -> str:
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
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != expected_digest:
            raise ValueError(f"frozen input hash mismatch: {relative_path}")
    actual_freeze_digest = benchmark_freeze_digest(manifest)
    if manifest.get("benchmark_freeze_digest") != actual_freeze_digest:
        raise ValueError("benchmark freeze digest does not match manifest contents")
    return actual_freeze_digest
