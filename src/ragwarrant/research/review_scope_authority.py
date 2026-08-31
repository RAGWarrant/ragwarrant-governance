"""Closed scientific-byte scope for review of PR A only.

This is deliberately not the complete Focus 1 or V1 authority verifier. It
binds the scientific-core candidate to reviewed hashes and rejects path-set
drift; the stacked integrity branch removes it and restores full authority.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any


SCOPE_ID = "PR_A_REVIEW_SCOPE_V1"
VERIFIED = "PR_A_REVIEW_SCOPE_VERIFIED"
INVALID_RECORD = "PR_A_REVIEW_SCOPE_INVALID_RECORD"
PATH_SET_MISMATCH = "PR_A_REVIEW_SCOPE_PATH_SET_MISMATCH"
FILE_MISSING = "PR_A_REVIEW_SCOPE_FILE_MISSING"
HASH_MISMATCH = "PR_A_REVIEW_SCOPE_HASH_MISMATCH"
AUTHORITY_RECORD_HASH_MISMATCH = "PR_A_REVIEW_SCOPE_AUTHORITY_RECORD_HASH_MISMATCH"
IMMUTABLE_SOURCE_UNAVAILABLE = "PR_A_REVIEW_SCOPE_IMMUTABLE_SOURCE_UNAVAILABLE"
FOCUS1_REFERENCE_MISMATCH = "PR_A_REVIEW_SCOPE_FOCUS1_REFERENCE_MISMATCH"
CLAIM_BOUNDARY = (
    "SCIENTIFIC_SUBSET_BYTE_EQUIVALENCE_TO_IMMUTABLE_OWNER_REVIEW_SOURCE"
)
SOURCE_COMMIT = "b67bb4df0716609e3d915ec8ab4574632d43f215"
FOCUS1_CHECKPOINT_COMMIT = "124836bcc2fba48373d7bd08f0087b23f2e41620"
ACCEPTED_FOCUS1_DIGEST = (
    "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
)
BASE_COMMIT = "b8534df6ac9a338c2f086fc0f49948032d1e48cc"
DEFAULT_RECORD = Path("configs/research/pr_a_review_scope_v1.json")
FOCUS1_AUTHORITY_RECORD_PATH = "configs/research/focus1_detached_authority_v1.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

# This small, closed review allowlist is intentionally code-reviewed rather
# than derived from the candidate-owned record or the current Git diff. The
# immutable owner-review commit supplies the expected bytes for every path.
IMMUTABLE_SCIENTIFIC_PATHS = (
    ".gitattributes",
    "configs/research/evidence_budget_planner_v1.yaml",
    "configs/research/false_promotion_benchmark_v1.yaml",
    "configs/research/fixed_sample_multi_risk_warrant_v1.yaml",
    "configs/research/fixed_sample_multi_risk_warrant_v2.yaml",
    "configs/research/fixed_sample_multi_risk_warrant_v2_iut_holm.yaml",
    "configs/research/stratified_joint_power_confirmation_v1.yaml",
    "configs/research/stratified_joint_warrant_power_v1.yaml",
    "docs/research/evidence_budget_planner.md",
    "docs/research/false_promotion_benchmark_protocol.md",
    "docs/research/false_promotion_benchmark_seed_schedule_v2_amendment.md",
    "docs/research/fixed_sample_multi_risk_warrant_v1_implementation.md",
    "docs/research/fixed_sample_multi_risk_warrant_v2.md",
    "docs/research/fixed_sample_multi_risk_warrant_v2_iut_holm.md",
    "docs/research/fixed_sample_promotion_warrant_design.md",
    "docs/research/focus2_platform_preflight_plan.md",
    "docs/research/joint_warrant_power_planning.md",
    "docs/research/operational_contract_template.md",
    "docs/research/stratified_confirmatory_design.md",
    "docs/research/stratified_confirmatory_evidence_v1.md",
    "docs/research/stratified_joint_power_confirmation_v1.md",
    "pyproject.toml",
    "schemas/research/promotion_warrant_v1.schema.json",
    "scripts/generate_seed_schedule_v2_manifest.py",
    "scripts/run_evidence_budget_study.py",
    "scripts/run_false_promotion_benchmark.py",
    "scripts/run_fixed_sample_warrant_benchmark.py",
    "scripts/run_fixed_sample_warrant_v2_benchmark.py",
    "scripts/run_focus2_power_feasibility_audit.py",
    "scripts/run_joint_power_confirmation.py",
    "scripts/run_stratified_joint_power_study.py",
    "src/ragwarrant/research/__init__.py",
    "src/ragwarrant/research/benchmark.py",
    "src/ragwarrant/research/evidence_budget_planner.py",
    "src/ragwarrant/research/fixed_sample_warrant.py",
    "src/ragwarrant/research/fixed_sample_warrant_v2.py",
    "src/ragwarrant/research/focus2_benchmark.py",
    "src/ragwarrant/research/focus2_power_diagnostics.py",
    "src/ragwarrant/research/focus2_reporting.py",
    "src/ragwarrant/research/focus2_v2_benchmark.py",
    "src/ragwarrant/research/focus2_v2_reporting.py",
    "src/ragwarrant/research/joint_power_confirmation.py",
    "src/ragwarrant/research/methods.py",
    "src/ragwarrant/research/reporting.py",
    "src/ragwarrant/research/seed_schedule.py",
    "src/ragwarrant/research/simulator.py",
    "src/ragwarrant/research/stratified_joint_power.py",
    "src/ragwarrant/research/types.py",
    "tests/research/test_benchmark_controls.py",
    "tests/research/test_benchmark_reproducibility.py",
    "tests/research/test_fixed_sample_warrant.py",
    "tests/research/test_fixed_sample_warrant_method.py",
    "tests/research/test_fixed_sample_warrant_v2.py",
    "tests/research/test_focus2_benchmark_integration.py",
    "tests/research/test_focus2_output_contract.py",
    "tests/research/test_method_contract.py",
    "tests/research/test_output_contract.py",
    "tests/research/test_seed_schedule_v2.py",
    "tests/research/test_simulator_truth.py",
)
APPROVED_SUPPORT_PATHS = (
    ".github/workflows/ci.yml",
    "configs/research/pr_a_review_scope_v1.json",
    "docs/migration/legacy_brand_exceptions.json",
    "src/ragwarrant/research/public_beacon.py",
    "src/ragwarrant/research/review_scope_authority.py",
    "tests/research/conftest.py",
    "tests/research/test_evidence_budget_planner.py",
    "tests/research/test_focus2_power_feasibility.py",
    "tests/research/test_focus2_v2_benchmark_integration.py",
    "tests/research/test_joint_power_confirmation.py",
    "tests/research/test_pr_a_review_scope.py",
    "tests/research/test_stratified_joint_warrant_power.py",
)


class ReviewScopeError(ValueError):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status


def _safe_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ReviewScopeError(INVALID_RECORD, "scope paths must be POSIX relative")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or any(part in ("", ".", "..") for part in path.parts)
        or value != path.as_posix()
    ):
        raise ReviewScopeError(INVALID_RECORD, "scope paths must be canonical")
    return path.as_posix()


def _unique_paths(values: object, label: str) -> list[str]:
    if not isinstance(values, list):
        raise ReviewScopeError(INVALID_RECORD, f"{label} must be a list")
    paths = [_safe_path(value) for value in values]
    if len(paths) != len(set(paths)):
        raise ReviewScopeError(INVALID_RECORD, f"{label} contains duplicates")
    return paths


def _reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ReviewScopeError(INVALID_RECORD, f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_record(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_pairs,
        )
    except (OSError, json.JSONDecodeError, ReviewScopeError) as exc:
        if isinstance(exc, ReviewScopeError):
            raise
        raise ReviewScopeError(INVALID_RECORD, "review-scope record is unreadable") from exc
    if not isinstance(value, dict):
        raise ReviewScopeError(INVALID_RECORD, "review-scope record must be an object")
    return value


def _validate_record(record: Mapping[str, Any]) -> tuple[list[str], dict[str, str], list[str]]:
    required = {
        "schema_version": "1.0",
        "scope_id": SCOPE_ID,
        "immutable_source_commit": SOURCE_COMMIT,
        "construction_base_commit": BASE_COMMIT,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    for key, expected in required.items():
        if record.get(key) != expected:
            raise ReviewScopeError(INVALID_RECORD, f"invalid review-scope {key}")
    if record.get("focus1_checkpoint_commit") != FOCUS1_CHECKPOINT_COMMIT:
        raise ReviewScopeError(
            FOCUS1_REFERENCE_MISMATCH,
            "Focus 1 checkpoint reference differs from the accepted checkpoint",
        )
    if record.get("focus1_digest_reference") != ACCEPTED_FOCUS1_DIGEST:
        raise ReviewScopeError(
            FOCUS1_REFERENCE_MISMATCH,
            "Focus 1 digest reference differs from the accepted digest",
        )
    support_paths = _unique_paths(record.get("split_support_paths"), "split_support_paths")
    if set(support_paths) != set(APPROVED_SUPPORT_PATHS):
        raise ReviewScopeError(PATH_SET_MISMATCH, "split support path set changed")
    hashes = record.get("scientific_sha256")
    if not isinstance(hashes, dict) or not hashes:
        raise ReviewScopeError(INVALID_RECORD, "scientific_sha256 must be a mapping")
    scientific: dict[str, str] = {}
    for raw_path, raw_digest in hashes.items():
        path = _safe_path(raw_path)
        if not isinstance(raw_digest, str) or _SHA256.fullmatch(raw_digest) is None:
            raise ReviewScopeError(INVALID_RECORD, f"invalid SHA-256 for {path}")
        if path in scientific:
            raise ReviewScopeError(INVALID_RECORD, f"duplicate scientific path {path}")
        scientific[path] = raw_digest
    if set(scientific) != set(IMMUTABLE_SCIENTIFIC_PATHS):
        raise ReviewScopeError(PATH_SET_MISMATCH, "scientific path set changed")
    if set(scientific) & set(support_paths):
        raise ReviewScopeError(INVALID_RECORD, "scientific and support paths overlap")
    expected_paths = sorted(set(IMMUTABLE_SCIENTIFIC_PATHS) | set(APPROVED_SUPPORT_PATHS))
    return expected_paths, scientific, support_paths


def _git_bytes(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "--no-replace-objects", *args],
            cwd=root,
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise ReviewScopeError(
            IMMUTABLE_SOURCE_UNAVAILABLE,
            "Git object access is unavailable",
        ) from exc
    if result.returncode != 0:
        raise ReviewScopeError(
            IMMUTABLE_SOURCE_UNAVAILABLE,
            "required immutable Git object is unavailable",
        )
    return result.stdout


def _verify_immutable_source(root: Path) -> None:
    if _git_bytes(root, "cat-file", "-t", SOURCE_COMMIT).strip() != b"commit":
        raise ReviewScopeError(
            IMMUTABLE_SOURCE_UNAVAILABLE,
            "owner-review source is not a commit",
        )


def _verify_focus1_reference(root: Path) -> None:
    """Bind PR A's reference metadata to the owner-review commit.

    The detached checkpoint object is intentionally not required in a clean
    PR A checkout. Complete checkpoint authority belongs to stacked PR B.
    """

    try:
        raw = _git_bytes(
            root,
            "cat-file",
            "blob",
            f"{SOURCE_COMMIT}:{FOCUS1_AUTHORITY_RECORD_PATH}",
        )
        authority = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ReviewScopeError) as exc:
        if isinstance(exc, ReviewScopeError) and exc.status == IMMUTABLE_SOURCE_UNAVAILABLE:
            raise
        raise ReviewScopeError(
            FOCUS1_REFERENCE_MISMATCH,
            "immutable owner-review Focus 1 reference is invalid",
        ) from exc
    if not isinstance(authority, dict) or (
        authority.get("authority_commit") != FOCUS1_CHECKPOINT_COMMIT
        or authority.get("accepted_digest") != ACCEPTED_FOCUS1_DIGEST
    ):
        raise ReviewScopeError(
            FOCUS1_REFERENCE_MISMATCH,
            "immutable owner-review Focus 1 reference differs from accepted values",
        )


def _immutable_scientific_hashes(root: Path) -> dict[str, str]:
    _verify_immutable_source(root)
    _verify_focus1_reference(root)
    return {
        path: hashlib.sha256(
            _git_bytes(root, "cat-file", "blob", f"{SOURCE_COMMIT}:{path}")
        ).hexdigest()
        for path in IMMUTABLE_SCIENTIFIC_PATHS
    }


def _git_changed_paths(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            [
                "git",
                "--no-replace-objects",
                "diff",
                "--name-only",
                "--no-renames",
                f"{BASE_COMMIT}..HEAD",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReviewScopeError(INVALID_RECORD, "construction base is unavailable") from exc
    return [line for line in result.stdout.splitlines() if line]


def verify_review_scope(
    repository_root: str | Path,
    *,
    record_path: str | Path = DEFAULT_RECORD,
    changed_paths: Iterable[str] | None = None,
) -> dict[str, object]:
    root = Path(repository_root).resolve()
    record_file = Path(record_path)
    if not record_file.is_absolute():
        record_file = root / record_file
    record = load_record(record_file)
    expected, scientific, support = _validate_record(record)
    immutable_hashes = _immutable_scientific_hashes(root)
    for relative_path, recorded_digest in scientific.items():
        if recorded_digest != immutable_hashes[relative_path]:
            raise ReviewScopeError(
                AUTHORITY_RECORD_HASH_MISMATCH,
                f"recorded hash differs from immutable owner-review blob: {relative_path}",
            )
    actual = [_safe_path(path) for path in (changed_paths or _git_changed_paths(root))]
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise ReviewScopeError(PATH_SET_MISMATCH, "candidate changed-path set differs from review scope")
    for relative_path in expected:
        target = root / relative_path
        if not target.is_file():
            raise ReviewScopeError(FILE_MISSING, f"required scope file is missing: {relative_path}")
    for relative_path, expected_digest in immutable_hashes.items():
        actual_digest = hashlib.sha256((root / relative_path).read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            raise ReviewScopeError(HASH_MISMATCH, f"scientific byte mismatch: {relative_path}")
    return {
        "status": VERIFIED,
        "scope_id": SCOPE_ID,
        "claim_boundary": CLAIM_BOUNDARY,
        "immutable_source_commit": SOURCE_COMMIT,
        "expected_hash_source": "RAW_GIT_BLOBS_AT_IMMUTABLE_OWNER_REVIEW_COMMIT",
        "focus1_checkpoint_reference": FOCUS1_CHECKPOINT_COMMIT,
        "focus1_digest_reference": ACCEPTED_FOCUS1_DIGEST,
        "focus1_reference_source": (
            "RAW_GIT_BLOB_AT_IMMUTABLE_OWNER_REVIEW_COMMIT:"
            f"{FOCUS1_AUTHORITY_RECORD_PATH}"
        ),
        "construction_base_commit": BASE_COMMIT,
        "expected_path_count": len(expected),
        "scientific_hash_count": len(scientific),
        "split_support_path_count": len(support),
        "complete_focus1_or_v1_authority": False,
        "complete_sealed_study_provenance": False,
    }


def main() -> int:
    try:
        result = verify_review_scope(Path.cwd())
    except ReviewScopeError as exc:
        print(json.dumps({"status": exc.status, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
