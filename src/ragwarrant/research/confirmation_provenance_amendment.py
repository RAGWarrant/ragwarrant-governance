"""Workspace-local provenance binding for the preserved confirmation run.

This module intentionally does not import the confirmation simulator or any
evidence-generation code.  It verifies and registers one already-existing
materialization, derives secondary diagnostics from its aggregate CSV, and
guards the approved amendment entry point against a second materialization of
the original protocol ID.

The registry is authoritative only inside the declared repository workspace.
It cannot prevent copies outside that workspace or direct invocation of a
historical, unguarded runner.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import stat
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Iterable, Mapping, Sequence


AMENDMENT_ID = "STRATIFIED-JOINT-POWER-CONFIRMATION-PROVENANCE-001"
AMENDMENT_TYPE = "PROVENANCE_BINDING_AND_DERIVED_DIAGNOSTIC_CORRECTION"
ORIGINAL_PROTOCOL_ID = "STRATIFIED_JOINT_POWER_CONFIRMATION_V1"
MATERIALIZATION_SCOPE = "AUTHORITATIVE_WITHIN_DECLARED_REPOSITORY_WORKSPACE"
FOCUS1_DIGEST = "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
V1_FROZEN_COMMIT = "bf3b3331b623afbdaed295919b3ac945c10692f6"
CANONICAL_PROTOCOL_PATH = (
    ".local_data/research_review/JOINT_POWER_CONFIRMATION_PROTOCOL.json"
)
CANONICAL_CONFIG_PATH = "configs/research/stratified_joint_power_confirmation_v1.yaml"
CANONICAL_RUNNER_PATH = "scripts/run_joint_power_confirmation.py"
CANONICAL_OUTPUT_ROOT = ".local_data/research_review/joint_power_confirmation_v1"
ORIGINAL_PROTOCOL_SHA256 = (
    "d0a245b5329aa6adeaa27363c6226aa6756152b814bc597e7f9c33daf9eb1c4c"
)
ORIGINAL_CONFIGURATION_SHA256 = (
    "9d1c3420efd243dd6d67053333dad5c1642f9554a7dac2943dfcf4bcda392275"
)
ORIGINAL_RUNNER_SHA256 = (
    "a33d423771353d7daf69fdda631ee64fbde6c600714335bff726e724ed3696a6"
)
ORIGINAL_OUTPUT_SET_SHA256 = (
    "a6ff12e61dc800be65c089cdb7cbe8aca68339a53af08d6ac1bbc95db8a57493"
)

DEFAULT_INVENTORY_PATH = (
    ".local_data/research_review/confirmation_amendment/"
    "ORIGINAL_MATERIALIZATION_INVENTORY.json"
)
DEFAULT_AMENDMENT_ROOT = ".local_data/research_review/confirmation_amendment"
DEFAULT_IMPLEMENTATION_PATH = (
    "src/ragwarrant/research/confirmation_provenance_amendment.py"
)
DEFAULT_REVIEWED_FREEZE_PATH = (
    f"{DEFAULT_AMENDMENT_ROOT}/AMENDMENT_IMPLEMENTATION_FREEZE_REVIEWED.json"
)
DEFAULT_REGISTRY_PATH = (
    f"{DEFAULT_AMENDMENT_ROOT}/canonical_materialization_registry_v1.json"
)
DEFAULT_PROVENANCE_PATH = (
    f"{DEFAULT_AMENDMENT_ROOT}/confirmation_provenance_amendment_v1.json"
)
DEFAULT_PROVENANCE_MARKDOWN_PATH = (
    f"{DEFAULT_AMENDMENT_ROOT}/confirmation_provenance_amendment_v1.md"
)
DEFAULT_CORRECTED_CSV_PATH = (
    f"{DEFAULT_AMENDMENT_ROOT}/corrected_derived_diagnostics_v1.csv"
)
DEFAULT_CORRECTED_JSON_PATH = (
    f"{DEFAULT_AMENDMENT_ROOT}/corrected_derived_diagnostics_v1.json"
)
DEFAULT_DEPRECATED_MAPPING_PATH = (
    f"{DEFAULT_AMENDMENT_ROOT}/deprecated_diagnostic_mapping_v1.json"
)

CONFIRMATION_PROVENANCE_VERIFIED = "CONFIRMATION_PROVENANCE_VERIFIED"
CONFIRMATION_PROVENANCE_HASH_MISMATCH = "CONFIRMATION_PROVENANCE_HASH_MISMATCH"
CONFIRMATION_PROVENANCE_PATH_MISMATCH = "CONFIRMATION_PROVENANCE_PATH_MISMATCH"
CONFIRMATION_DUPLICATE_MATERIALIZATION = "CONFIRMATION_DUPLICATE_MATERIALIZATION"
CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH = (
    "CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH"
)
CONFIRMATION_PROVENANCE_INCOMPLETE = "CONFIRMATION_PROVENANCE_INCOMPLETE"

REQUIRED_COMPONENT_IDS = (
    "execution_failure_probability::__overall__",
    "group_quality::majority",
    "group_quality::minority",
    "insufficient_evidence_probability::__overall__",
    "overall_quality::__overall__",
    "safety_violation_probability::__overall__",
    "safety_violation_probability::majority",
    "safety_violation_probability::minority",
)

DEPRECATED_DIAGNOSTIC_COLUMNS = {
    "mean_independence_approximation": {
        "actual_formula": (
            "Mean across planning replicates of the per-replicate indicator "
            "that every mandatory component p-value was at or below alpha_floor, "
            "where alpha_floor = familywise_error_level / candidate_count."
        ),
        "actual_semantic_meaning": (
            "A secondary Monte Carlo proportion of candidates passing every mandatory "
            "component at the per-candidate Bonferroni floor. It is not the direct Holm "
            "certification outcome and is not a product of aggregate marginal pass rates."
        ),
        "why_name_is_incorrect": (
            "An independence approximation from aggregate marginals is the product "
            "of their pass-rate estimates; the preserved column does not calculate it."
        ),
    },
    "mean_union_bound_lower_bound": {
        "actual_formula": (
            "Mean across planning replicates of the per-replicate indicator that every "
            "mandatory component p-value was at or below alpha_floor, where alpha_floor "
            "= familywise_error_level / candidate_count. With Boolean component hits, "
            "the per-replicate product and union expression both equal this indicator."
        ),
        "actual_semantic_meaning": (
            "A secondary Monte Carlo proportion of candidates passing every mandatory "
            "component at the per-candidate Bonferroni floor. It is distinct from direct "
            "Holm certification and from an aggregate-marginal union-bound diagnostic."
        ),
        "why_name_is_incorrect": (
            "The aggregate-marginal union diagnostic is max(0, sum(q_i) - (k - 1)); "
            "the preserved column does not calculate that quantity."
        ),
    },
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_REPARSE_POINT_ATTRIBUTE = 0x400


@dataclass(frozen=True)
class VerificationResult:
    """Machine-readable result returned by amendment verification functions."""

    status: str
    ok: bool
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ok": self.ok,
            "message": self.message,
            "details": dict(self.details),
        }


class ProvenanceError(ValueError):
    """Fail-closed error carrying one of the required provenance statuses."""

    def __init__(
        self,
        status: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.details = dict(details or {})

    def as_result(self) -> VerificationResult:
        return VerificationResult(
            status=self.status,
            ok=False,
            message=str(self),
            details=self.details,
        )


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value using the amendment's stable encoding."""

    try:
        rendered = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_INCOMPLETE,
            f"Value is not canonical-JSON compatible: {exc}",
        ) from exc
    return rendered.encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_repository_relative_path(value: str) -> str:
    """Normalize separators while rejecting unsafe or ambiguous path syntax.

    This function makes ``a\\b`` and ``a/b`` normalize identically.  Security-
    sensitive authoritative records additionally use
    :func:`require_canonical_repository_relative_path`, which requires the
    normalized POSIX spelling to have been supplied verbatim.
    """

    if not isinstance(value, str) or not value:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_PATH_MISMATCH,
            "Repository-relative path must be a non-empty string.",
        )
    if "\x00" in value:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_PATH_MISMATCH,
            "Repository-relative path contains a NUL byte.",
        )
    windows_path = PureWindowsPath(value)
    normalized = value.replace("\\", "/")
    if windows_path.drive or windows_path.root or normalized.startswith("/"):
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_PATH_MISMATCH,
            f"Absolute, drive-qualified, UNC, or device path is forbidden: {value!r}.",
        )
    raw_parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_PATH_MISMATCH,
            f"Empty, dot, or traversal path component is forbidden: {value!r}.",
        )
    for part in raw_parts:
        if ":" in part:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                f"Colon/alternate-data-stream syntax is forbidden: {value!r}.",
            )
        if part.endswith((".", " ")):
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                f"Trailing dot or space is forbidden: {value!r}.",
            )
        base_name = part.split(".", 1)[0].upper()
        if base_name in _WINDOWS_RESERVED_NAMES:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                f"Reserved Windows path component is forbidden: {part!r}.",
            )
    return PurePosixPath(*raw_parts).as_posix()


def require_canonical_repository_relative_path(value: str) -> str:
    normalized = normalize_repository_relative_path(value)
    if value != normalized:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_PATH_MISMATCH,
            f"Authoritative path must use exact repository-relative POSIX spelling: {value!r}.",
            details={"canonical_path": normalized},
        )
    return normalized


def paths_equal_under_host_contract(
    first: str,
    second: str,
    *,
    case_sensitive: bool | None = None,
) -> bool:
    """Compare normalized paths under an explicit or host-derived case contract."""

    first_normalized = normalize_repository_relative_path(first)
    second_normalized = normalize_repository_relative_path(second)
    sensitive = (os.name != "nt") if case_sensitive is None else case_sensitive
    if sensitive:
        return first_normalized == second_normalized
    return first_normalized.casefold() == second_normalized.casefold()


def _is_reparse_point(file_stat: os.stat_result) -> bool:
    return bool(
        getattr(file_stat, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE
    )


def _validate_existing_path_chain(repository_root: Path, relative_path: str) -> None:
    current = repository_root
    for component in PurePosixPath(relative_path).parts:
        if not current.exists():
            return
        try:
            names = {entry.name for entry in os.scandir(current)}
        except OSError as exc:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                f"Cannot inspect canonical path parent {current}: {exc}",
            ) from exc
        if component not in names:
            # This rejects case aliases on case-insensitive hosts as well as stale paths.
            case_aliases = [name for name in names if name.casefold() == component.casefold()]
            if case_aliases:
                raise ProvenanceError(
                    CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                    f"Path case does not match the repository entry: {relative_path!r}.",
                    details={"actual_component": sorted(case_aliases)[0]},
                )
            return
        current = current / component
        try:
            file_stat = os.lstat(current)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(file_stat.st_mode) or _is_reparse_point(file_stat):
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                f"Symlink, junction, or reparse-point path is forbidden: {relative_path!r}.",
            )


def resolve_repository_path(
    repository_root: Path,
    relative_path: str,
    *,
    must_exist: bool,
) -> Path:
    canonical = require_canonical_repository_relative_path(relative_path)
    root = repository_root.resolve(strict=True)
    root_stat = os.lstat(root)
    if stat.S_ISLNK(root_stat.st_mode) or _is_reparse_point(root_stat):
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_PATH_MISMATCH,
            "Declared repository root may not be a symlink, junction, or reparse point.",
        )
    _validate_existing_path_chain(root, canonical)
    candidate = root.joinpath(*PurePosixPath(canonical).parts)
    try:
        resolved = candidate.resolve(strict=must_exist)
    except FileNotFoundError as exc:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_INCOMPLETE,
            f"Required provenance path is missing: {canonical}.",
            details={"path": canonical},
        ) from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_PATH_MISMATCH,
            f"Path escapes the declared repository workspace: {canonical!r}.",
        ) from exc
    return resolved


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_INCOMPLETE,
            f"{label} must be a JSON object.",
        )
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_INCOMPLETE,
            f"{label} must be a lowercase SHA-256 digest.",
        )
    return value


def load_original_inventory(
    repository_root: Path,
    inventory_path: str,
    *,
    enforce_frozen_identity: bool = True,
) -> dict[str, Any]:
    resolved = resolve_repository_path(repository_root, inventory_path, must_exist=True)
    try:
        parsed = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_INCOMPLETE,
            f"Original materialization inventory is unreadable: {exc}",
        ) from exc
    inventory = dict(_require_mapping(parsed, "Original materialization inventory"))
    required = {
        "schema_version",
        "amendment_id",
        "amendment_type",
        "original_protocol_id",
        "focus1_digest",
        "v1_frozen_commit",
        "canonical_repository_root_identity",
        "canonical_protocol_path",
        "canonical_config_path",
        "canonical_runner_path",
        "canonical_output_root",
        "canonical_materialization_id",
        "canonical_materialization_digest",
        "materialization_scope",
        "original_protocol_sha256",
        "original_configuration_sha256",
        "original_runner_sha256",
        "output_set_hash",
        "original_inputs",
        "original_outputs",
    }
    missing = sorted(required - inventory.keys())
    if missing:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_INCOMPLETE,
            "Original materialization inventory lacks required fields.",
            details={"missing_fields": missing},
        )
    expected_scalars = {
        "amendment_id": AMENDMENT_ID,
        "amendment_type": AMENDMENT_TYPE,
        "original_protocol_id": ORIGINAL_PROTOCOL_ID,
        "focus1_digest": FOCUS1_DIGEST,
        "v1_frozen_commit": V1_FROZEN_COMMIT,
        "materialization_scope": MATERIALIZATION_SCOPE,
    }
    if enforce_frozen_identity:
        expected_scalars.update(
            {
                "canonical_protocol_path": CANONICAL_PROTOCOL_PATH,
                "canonical_config_path": CANONICAL_CONFIG_PATH,
                "canonical_runner_path": CANONICAL_RUNNER_PATH,
                "canonical_output_root": CANONICAL_OUTPUT_ROOT,
                "original_protocol_sha256": ORIGINAL_PROTOCOL_SHA256,
                "original_configuration_sha256": ORIGINAL_CONFIGURATION_SHA256,
                "original_runner_sha256": ORIGINAL_RUNNER_SHA256,
            }
        )
    for key, expected in expected_scalars.items():
        if inventory.get(key) != expected:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_INCOMPLETE,
                f"Inventory {key} does not match the amendment contract.",
                details={"expected": expected, "actual": inventory.get(key)},
            )
    for path_key in (
        "canonical_protocol_path",
        "canonical_config_path",
        "canonical_runner_path",
        "canonical_output_root",
    ):
        require_canonical_repository_relative_path(str(inventory[path_key]))
    for sha_key in (
        "focus1_digest",
        "v1_frozen_commit",
        "original_protocol_sha256",
        "original_configuration_sha256",
        "original_runner_sha256",
        "canonical_materialization_digest",
    ):
        value = inventory[sha_key]
        if sha_key == "v1_frozen_commit":
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
                raise ProvenanceError(
                    CONFIRMATION_PROVENANCE_INCOMPLETE,
                    "v1_frozen_commit must be a lowercase Git SHA-1.",
                )
        else:
            _require_sha256(value, sha_key)
    output_hash = _require_mapping(inventory["output_set_hash"], "output_set_hash")
    _require_sha256(output_hash.get("sha256"), "output_set_hash.sha256")
    if enforce_frozen_identity and output_hash.get("sha256") != ORIGINAL_OUTPUT_SET_SHA256:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_HASH_MISMATCH,
            "Inventory output-set hash differs from the frozen original materialization.",
        )
    if output_hash.get("file_policy") != "EXACT_DECLARED_FILE_SET_NO_EXTRA_FILES":
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_INCOMPLETE,
            "Output-set policy must be EXACT_DECLARED_FILE_SET_NO_EXTRA_FILES.",
        )
    for collection_name in ("original_inputs", "original_outputs"):
        entries = inventory[collection_name]
        if not isinstance(entries, list) or not entries:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_INCOMPLETE,
                f"{collection_name} must be a non-empty array.",
            )
        seen: set[str] = set()
        for position, raw_entry in enumerate(entries):
            entry = _require_mapping(raw_entry, f"{collection_name}[{position}]")
            if set(entry) != {"path", "size_bytes", "sha256"}:
                raise ProvenanceError(
                    CONFIRMATION_PROVENANCE_INCOMPLETE,
                    f"{collection_name}[{position}] has an unexpected schema.",
                )
            path = require_canonical_repository_relative_path(str(entry["path"]))
            if path in seen:
                raise ProvenanceError(
                    CONFIRMATION_PROVENANCE_INCOMPLETE,
                    f"Duplicate path in {collection_name}: {path}.",
                )
            seen.add(path)
            if not isinstance(entry["size_bytes"], int) or entry["size_bytes"] < 0:
                raise ProvenanceError(
                    CONFIRMATION_PROVENANCE_INCOMPLETE,
                    f"Invalid size for {path}.",
                )
            _require_sha256(entry["sha256"], f"{path}.sha256")
    return inventory


def _materialization_digest(inventory: Mapping[str, Any]) -> str:
    identity = {
        "canonical_repository_root_identity": inventory[
            "canonical_repository_root_identity"
        ],
        "config_sha256": inventory["original_configuration_sha256"],
        "output_set_sha256": inventory["output_set_hash"]["sha256"],
        "protocol_id": inventory["original_protocol_id"],
        "protocol_sha256": inventory["original_protocol_sha256"],
    }
    return canonical_json_sha256(identity)


def _verify_file_entry(
    repository_root: Path,
    entry: Mapping[str, Any],
    *,
    reject_hardlinks: bool,
) -> dict[str, Any]:
    relative_path = str(entry["path"])
    resolved = resolve_repository_path(repository_root, relative_path, must_exist=True)
    if not resolved.is_file():
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_INCOMPLETE,
            f"Recorded path is not a regular file: {relative_path}.",
        )
    file_stat = resolved.stat()
    if reject_hardlinks and getattr(file_stat, "st_nlink", 1) != 1:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_PATH_MISMATCH,
            f"Authoritative output may not be hard-linked: {relative_path}.",
            details={"link_count": file_stat.st_nlink},
        )
    actual_size = file_stat.st_size
    if actual_size != entry["size_bytes"]:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_HASH_MISMATCH,
            f"Recorded file size changed: {relative_path}.",
            details={"expected": entry["size_bytes"], "actual": actual_size},
        )
    actual_hash = sha256_file(resolved)
    if actual_hash != entry["sha256"]:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_HASH_MISMATCH,
            f"Recorded file hash changed: {relative_path}.",
            details={"expected": entry["sha256"], "actual": actual_hash},
        )
    return {
        "path": relative_path,
        "size_bytes": actual_size,
        "sha256": actual_hash,
    }


def output_set_digest(entries: Iterable[Mapping[str, Any]]) -> str:
    normalized = sorted(
        (
            {
                "path": require_canonical_repository_relative_path(str(entry["path"])),
                "size_bytes": int(entry["size_bytes"]),
                "sha256": _require_sha256(entry["sha256"], "output sha256"),
            }
            for entry in entries
        ),
        key=lambda item: item["path"],
    )
    return canonical_json_sha256(normalized)


def verify_original_materialization(
    repository_root: Path,
    inventory: Mapping[str, Any],
) -> VerificationResult:
    try:
        verified_inputs = [
            _verify_file_entry(repository_root, entry, reject_hardlinks=False)
            for entry in inventory["original_inputs"]
        ]
        verified_outputs = [
            _verify_file_entry(repository_root, entry, reject_hardlinks=True)
            for entry in inventory["original_outputs"]
        ]
        verified_input_by_path = {entry["path"]: entry for entry in verified_inputs}
        canonical_source_bindings = {
            str(inventory["canonical_protocol_path"]): str(
                inventory["original_protocol_sha256"]
            ),
            str(inventory["canonical_config_path"]): str(
                inventory["original_configuration_sha256"]
            ),
            str(inventory["canonical_runner_path"]): str(
                inventory["original_runner_sha256"]
            ),
        }
        for canonical_path, frozen_hash in canonical_source_bindings.items():
            source_entry = verified_input_by_path.get(canonical_path)
            if source_entry is None:
                raise ProvenanceError(
                    CONFIRMATION_PROVENANCE_INCOMPLETE,
                    f"Canonical source is absent from original_inputs: {canonical_path}.",
                )
            if source_entry["sha256"] != frozen_hash:
                raise ProvenanceError(
                    CONFIRMATION_PROVENANCE_HASH_MISMATCH,
                    f"Canonical source entry is not linked to its frozen scalar hash: {canonical_path}.",
                    details={
                        "entry_sha256": source_entry["sha256"],
                        "frozen_sha256": frozen_hash,
                    },
                )
        output_root = resolve_repository_path(
            repository_root,
            str(inventory["canonical_output_root"]),
            must_exist=True,
        )
        if not output_root.is_dir():
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                "Canonical output root is not a directory.",
            )
        actual_children = {
            child.relative_to(repository_root.resolve(strict=True)).as_posix()
            for child in output_root.iterdir()
        }
        declared_children = {entry["path"] for entry in inventory["original_outputs"]}
        if actual_children != declared_children:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_INCOMPLETE,
                "Canonical output root does not contain the exact declared file set.",
                details={
                    "missing": sorted(declared_children - actual_children),
                    "extra": sorted(actual_children - declared_children),
                },
            )
        actual_output_hash = output_set_digest(verified_outputs)
        expected_output_hash = inventory["output_set_hash"]["sha256"]
        if actual_output_hash != expected_output_hash:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_HASH_MISMATCH,
                "Aggregate output-set hash does not match the inventory.",
                details={"expected": expected_output_hash, "actual": actual_output_hash},
            )
        digest = _materialization_digest(inventory)
        if digest != inventory["canonical_materialization_digest"]:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_HASH_MISMATCH,
                "Canonical materialization digest does not match its declared inputs.",
            )
        if inventory["canonical_materialization_id"] != f"sjpcv1-{digest}":
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_HASH_MISMATCH,
                "Canonical materialization ID does not match its deterministic digest.",
            )
        return VerificationResult(
            status=CONFIRMATION_PROVENANCE_VERIFIED,
            ok=True,
            message="Original confirmation materialization matches its inventory.",
            details={
                "verified_input_count": len(verified_inputs),
                "verified_output_count": len(verified_outputs),
                "output_set_sha256": actual_output_hash,
                "canonical_materialization_id": inventory[
                    "canonical_materialization_id"
                ],
            },
        )
    except ProvenanceError as exc:
        return exc.as_result()


def _registry_record(
    inventory: Mapping[str, Any],
    repository_root: Path,
    inventory_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": "ragwarrant_confirmation_materialization_registry.v1",
        "registry_state": "IMPORTED_EXISTING_ORIGINAL",
        "amendment_id": AMENDMENT_ID,
        "original_protocol_id": ORIGINAL_PROTOCOL_ID,
        "canonical_repository_root_identity": inventory[
            "canonical_repository_root_identity"
        ],
        "canonical_protocol_path": inventory["canonical_protocol_path"],
        "canonical_config_path": inventory["canonical_config_path"],
        "canonical_runner_path": inventory["canonical_runner_path"],
        "canonical_output_root": inventory["canonical_output_root"],
        "canonical_materialization_id": inventory["canonical_materialization_id"],
        "materialization_scope": MATERIALIZATION_SCOPE,
        "source_protocol_sha256": inventory["original_protocol_sha256"],
        "source_config_sha256": inventory["original_configuration_sha256"],
        "source_runner_sha256": inventory["original_runner_sha256"],
        "source_output_set_sha256": inventory["output_set_hash"]["sha256"],
        "source_inventory_path": inventory_path,
        "source_inventory_sha256": sha256_file(
            resolve_repository_path(repository_root, inventory_path, must_exist=True)
        ),
        "focus1_digest": FOCUS1_DIGEST,
        "v1_frozen_commit": V1_FROZEN_COMMIT,
        "imported_existing_materialization": True,
        "simulation_executed_by_amendment": False,
        "host_absolute_repository_path_non_authoritative": repository_root.resolve(
            strict=True
        ).as_posix(),
        "claim_boundary": (
            "Workspace-local registry for the approved amendment entry point only; "
            "it does not prevent external copies or direct use of historical runners."
        ),
    }


def _exclusive_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("Exclusive provenance write made no progress.")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _load_json_file(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_INCOMPLETE,
            f"{label} is unreadable: {exc}",
        ) from exc


def verify_reviewed_implementation_freeze(
    repository_root: Path,
    *,
    freeze_path: str = DEFAULT_REVIEWED_FREEZE_PATH,
) -> VerificationResult:
    """Verify the post-review implementation freeze before provenance activation."""

    try:
        resolved = resolve_repository_path(repository_root, freeze_path, must_exist=True)
        freeze = _require_mapping(
            _load_json_file(resolved, "Reviewed amendment implementation freeze"),
            "Reviewed amendment implementation freeze",
        )
        expected_scalars = {
            "schema_version": (
                "ragwarrant_confirmation_provenance_amendment_reviewed_freeze.v1"
            ),
            "amendment_id": AMENDMENT_ID,
            "amendment_type": AMENDMENT_TYPE,
            "original_protocol_id": ORIGINAL_PROTOCOL_ID,
            "focus1_digest": FOCUS1_DIGEST,
            "v1_frozen_commit": V1_FROZEN_COMMIT,
            "original_output_set_sha256": ORIGINAL_OUTPUT_SET_SHA256,
            "materialization_scope": MATERIALIZATION_SCOPE,
            "review_defects_resolved_before_final_activation": True,
            "simulation_rerun": False,
            "scientific_design_inputs_changed": False,
        }
        for key, expected in expected_scalars.items():
            if freeze.get(key) != expected:
                raise ProvenanceError(
                    CONFIRMATION_PROVENANCE_HASH_MISMATCH,
                    f"Reviewed implementation freeze field {key} differs from the contract.",
                )
        frozen_files = freeze.get("frozen_files")
        if not isinstance(frozen_files, list) or not frozen_files:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_INCOMPLETE,
                "Reviewed implementation freeze has no file bindings.",
            )
        by_path: dict[str, Mapping[str, Any]] = {}
        for raw_entry in frozen_files:
            entry = _require_mapping(raw_entry, "reviewed freeze file entry")
            if set(entry) != {"path", "size_bytes", "sha256"}:
                raise ProvenanceError(
                    CONFIRMATION_PROVENANCE_INCOMPLETE,
                    "Reviewed implementation freeze contains a malformed file entry.",
                )
            path = require_canonical_repository_relative_path(str(entry["path"]))
            if path in by_path:
                raise ProvenanceError(
                    CONFIRMATION_PROVENANCE_INCOMPLETE,
                    f"Reviewed implementation freeze repeats path {path}.",
                )
            by_path[path] = entry
            _verify_file_entry(repository_root, entry, reject_hardlinks=True)
        required_paths = {
            DEFAULT_INVENTORY_PATH,
            DEFAULT_IMPLEMENTATION_PATH,
            "scripts/verify_confirmation_provenance.py",
            "tests/research/test_confirmation_provenance_amendment.py",
            "docs/research/confirmation_provenance_amendment_v1.md",
        }
        missing = sorted(required_paths - by_path.keys())
        if missing:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_INCOMPLETE,
                "Reviewed implementation freeze omits required amendment files.",
                details={"missing_paths": missing},
            )
        return VerificationResult(
            status=CONFIRMATION_PROVENANCE_VERIFIED,
            ok=True,
            message="Reviewed amendment implementation freeze matches current bytes.",
            details={
                "freeze_path": freeze_path,
                "verified_file_count": len(by_path),
                "freeze_sha256": sha256_file(resolved),
            },
        )
    except ProvenanceError as exc:
        return exc.as_result()


def _verify_registry(
    repository_root: Path,
    inventory: Mapping[str, Any],
    registry_path: str,
    inventory_path: str,
) -> VerificationResult:
    try:
        resolved = resolve_repository_path(repository_root, registry_path, must_exist=True)
        actual = _load_json_file(resolved, "Canonical materialization registry")
        expected = _registry_record(inventory, repository_root, inventory_path)
        metadata_key = "host_absolute_repository_path_non_authoritative"
        actual_authoritative = dict(_require_mapping(actual, "Canonical materialization registry"))
        expected_authoritative = dict(expected)
        actual_host_metadata = actual_authoritative.pop(metadata_key, None)
        expected_authoritative.pop(metadata_key, None)
        if not isinstance(actual_host_metadata, str) or not actual_host_metadata:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_INCOMPLETE,
                "Canonical registry lacks non-authoritative host execution metadata.",
            )
        if actual_authoritative != expected_authoritative:
            raise ProvenanceError(
                CONFIRMATION_DUPLICATE_MATERIALIZATION,
                "Canonical registry differs from the sole approved materialization.",
            )
        registry_dir = resolved.parent
        registry_candidates = sorted(
            child.name
            for child in registry_dir.iterdir()
            if child.name.startswith("canonical_materialization_registry")
            and child.suffix == ".json"
        )
        if registry_candidates != [resolved.name]:
            raise ProvenanceError(
                CONFIRMATION_DUPLICATE_MATERIALIZATION,
                "More than one canonical materialization registry is present.",
                details={"registry_candidates": registry_candidates},
            )
        return VerificationResult(
            status=CONFIRMATION_PROVENANCE_VERIFIED,
            ok=True,
            message="Canonical materialization registry matches the imported original.",
            details={"registry_path": registry_path},
        )
    except ProvenanceError as exc:
        return exc.as_result()


def register_existing_materialization(
    repository_root: Path,
    *,
    inventory_path: str = DEFAULT_INVENTORY_PATH,
    registry_path: str = DEFAULT_REGISTRY_PATH,
    enforce_frozen_identity: bool = True,
) -> VerificationResult:
    """Atomically register the already-existing original without running evidence."""

    try:
        if enforce_frozen_identity:
            freeze_result = verify_reviewed_implementation_freeze(repository_root)
            if not freeze_result.ok:
                return freeze_result
        inventory = load_original_inventory(
            repository_root,
            inventory_path,
            enforce_frozen_identity=enforce_frozen_identity,
        )
        original_result = verify_original_materialization(repository_root, inventory)
        if not original_result.ok:
            return original_result
        canonical_registry = require_canonical_repository_relative_path(registry_path)
        if canonical_registry != DEFAULT_REGISTRY_PATH:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                "The original protocol has one fixed workspace-local registry path.",
            )
        resolved = resolve_repository_path(
            repository_root, canonical_registry, must_exist=False
        )
        record = _registry_record(inventory, repository_root, inventory_path)
        payload = json.dumps(
            record,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8") + b"\n"
        if resolved.exists():
            return _verify_registry(
                repository_root, inventory, canonical_registry, inventory_path
            )
        try:
            _exclusive_write(resolved, payload)
        except FileExistsError:
            return _verify_registry(
                repository_root, inventory, canonical_registry, inventory_path
            )
        return _verify_registry(
            repository_root, inventory, canonical_registry, inventory_path
        )
    except ProvenanceError as exc:
        return exc.as_result()


def guard_original_protocol_materialization(
    repository_root: Path,
    *,
    protocol_id: str,
    requested_output_root: str,
    generator: Callable[[], Any] | None = None,
    inventory_path: str = DEFAULT_INVENTORY_PATH,
    registry_path: str = DEFAULT_REGISTRY_PATH,
    enforce_frozen_identity: bool = True,
) -> VerificationResult:
    """Refuse any future materialization of the preserved protocol before callback.

    ``generator`` exists only so callers and tests can prove refusal occurs before
    evidence generation.  This function never invokes it.
    """

    del generator
    try:
        if protocol_id != ORIGINAL_PROTOCOL_ID:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_INCOMPLETE,
                f"Unknown confirmation protocol ID: {protocol_id!r}.",
            )
        canonical_request = require_canonical_repository_relative_path(
            requested_output_root
        )
        inventory = load_original_inventory(
            repository_root,
            inventory_path,
            enforce_frozen_identity=enforce_frozen_identity,
        )
        if canonical_request != inventory["canonical_output_root"]:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                "Alternate output roots cannot reuse the original protocol ID.",
                details={
                    "requested": canonical_request,
                    "canonical": inventory["canonical_output_root"],
                },
            )
        original_result = verify_original_materialization(repository_root, inventory)
        if not original_result.ok:
            return original_result
        registry_result = _verify_registry(
            repository_root, inventory, registry_path, inventory_path
        )
        if not registry_result.ok:
            return registry_result
        return VerificationResult(
            status=CONFIRMATION_DUPLICATE_MATERIALIZATION,
            ok=False,
            message=(
                "The original protocol ID is already bound to its sole authoritative "
                "workspace-local materialization; use a new protocol version and ID."
            ),
            details={
                "canonical_materialization_id": inventory[
                    "canonical_materialization_id"
                ],
                "generator_called": False,
            },
        )
    except ProvenanceError as exc:
        return exc.as_result()


def _decimal_probability(value: Any, label: str) -> Decimal:
    if isinstance(value, bool):
        raise ProvenanceError(
            CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
            f"{label} must be numeric, not Boolean.",
        )
    try:
        probability = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProvenanceError(
            CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
            f"{label} is not a finite decimal probability.",
        ) from exc
    if not probability.is_finite() or probability < 0 or probability > 1:
        raise ProvenanceError(
            CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
            f"{label} must lie in [0, 1].",
        )
    return probability


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    if value == 1:
        return "1"
    return format(value.normalize(), "f")


def derive_marginal_diagnostics(
    marginal_component_pass_rates: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive aggregate-marginal diagnostics without shrinking the component set.

    A missing mandatory component produces an explicit unavailable result.  An
    unknown extra component remains a malformed-family error because silently
    accepting it would change the declared candidate/risk aggregation level.
    """

    if not isinstance(marginal_component_pass_rates, Mapping):
        raise ProvenanceError(
            CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
            "Marginal component pass rates must be a mapping.",
        )
    actual_components = set(marginal_component_pass_rates)
    required_components = set(REQUIRED_COMPONENT_IDS)
    extra = sorted(actual_components - required_components)
    if extra:
        raise ProvenanceError(
            CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
            "Marginal component pass rates contain unknown components.",
            details={"extra": extra},
        )
    rates = {
        component: _decimal_probability(
            marginal_component_pass_rates[component], component
        )
        for component in REQUIRED_COMPONENT_IDS
        if component in marginal_component_pass_rates
    }
    missing = [
        component for component in REQUIRED_COMPONENT_IDS if component not in rates
    ]
    common: dict[str, Any] = {
        "component_count": len(REQUIRED_COMPONENT_IDS),
        "component_identifiers": list(REQUIRED_COMPONENT_IDS),
        "marginal_component_pass_rates": {
            component: _decimal_text(rates[component])
            for component in REQUIRED_COMPONENT_IDS
            if component in rates
        },
        "missing_component_identifiers": missing,
    }
    if missing:
        return {
            **common,
            "independence_joint_pass_point_estimate_from_marginals": None,
            "union_bound_joint_pass_lower_point_estimate_from_marginals": None,
            "derivation_status": "UNAVAILABLE_MISSING_MANDATORY_COMPONENTS",
        }
    with localcontext() as context:
        context.prec = 50
        independence = Decimal(1)
        for component in REQUIRED_COMPONENT_IDS:
            independence *= rates[component]
        union_lower = sum(rates.values(), Decimal(0)) - Decimal(
            len(REQUIRED_COMPONENT_IDS) - 1
        )
        if union_lower < 0:
            union_lower = Decimal(0)
        # These clamps address only impossible last-bit excursions.
        independence = min(Decimal(1), max(Decimal(0), independence))
        union_lower = min(Decimal(1), max(Decimal(0), union_lower))
    return {
        **common,
        "independence_joint_pass_point_estimate_from_marginals": _decimal_text(
            independence
        ),
        "union_bound_joint_pass_lower_point_estimate_from_marginals": _decimal_text(
            union_lower
        ),
        "derivation_status": "DERIVED_FROM_PRESERVED_AGGREGATE_MARGINALS",
    }


def _candidate_results_path(inventory: Mapping[str, Any]) -> str:
    candidates = [
        entry["path"]
        for entry in inventory["original_outputs"]
        if PurePosixPath(entry["path"]).name == "candidate_results.csv"
    ]
    if len(candidates) != 1:
        raise ProvenanceError(
            CONFIRMATION_PROVENANCE_INCOMPLETE,
            "Inventory must contain exactly one candidate_results.csv output.",
        )
    return candidates[0]


def derive_corrected_diagnostics(
    repository_root: Path,
    inventory: Mapping[str, Any],
    *,
    amendment_implementation_hash: str,
) -> list[dict[str, Any]]:
    """Derive corrected plug-in diagnostics from preserved aggregate marginals."""

    _require_sha256(amendment_implementation_hash, "amendment_implementation_hash")
    candidate_path = _candidate_results_path(inventory)
    resolved = resolve_repository_path(repository_root, candidate_path, must_exist=True)
    expected_headers = {
        "protocol_id",
        "design_id",
        "dependence_condition",
        "safe_policy_id",
        "replicates",
        "joint_certification_count",
        "joint_certification_probability",
        "joint_certification_wilson_low",
        "joint_certification_wilson_high",
        "mean_union_bound_lower_bound",
        "mean_independence_approximation",
        "marginal_component_powers",
    }
    rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    try:
        with resolved.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = set(reader.fieldnames or [])
            if not expected_headers.issubset(headers):
                missing = sorted(expected_headers - headers)
                raise ProvenanceError(
                    CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
                    "candidate_results.csv lacks required columns.",
                    details={"missing_columns": missing},
                )
            for row_number, source in enumerate(reader, start=2):
                if source["protocol_id"] != ORIGINAL_PROTOCOL_ID:
                    raise ProvenanceError(
                        CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
                        f"Unexpected protocol ID at candidate row {row_number}.",
                    )
                key = (
                    source["design_id"],
                    source["dependence_condition"],
                    source["safe_policy_id"],
                )
                if key in seen_keys:
                    raise ProvenanceError(
                        CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
                        f"Duplicate candidate diagnostic cell: {key!r}.",
                    )
                seen_keys.add(key)
                try:
                    marginal_raw = json.loads(
                        source["marginal_component_powers"],
                        parse_float=Decimal,
                        parse_int=Decimal,
                    )
                except (json.JSONDecodeError, TypeError) as exc:
                    raise ProvenanceError(
                        CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
                        f"Malformed marginal component powers at row {row_number}.",
                    ) from exc
                marginal_mapping = _require_mapping(
                    marginal_raw, f"marginal_component_powers row {row_number}"
                )
                derived = derive_marginal_diagnostics(marginal_mapping)
                try:
                    replicates = int(source["replicates"])
                    joint_count = int(source["joint_certification_count"])
                except (TypeError, ValueError) as exc:
                    raise ProvenanceError(
                        CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
                        f"Invalid direct joint counts at row {row_number}.",
                    ) from exc
                if replicates <= 0 or not (0 <= joint_count <= replicates):
                    raise ProvenanceError(
                        CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
                        f"Out-of-range direct joint counts at row {row_number}.",
                    )
                joint_rate = _decimal_probability(
                    source["joint_certification_probability"],
                    f"joint certification probability row {row_number}",
                )
                expected_joint_rate = Decimal(joint_count) / Decimal(replicates)
                if joint_rate != expected_joint_rate:
                    raise ProvenanceError(
                        CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
                        f"Direct joint count/rate mismatch at row {row_number}.",
                    )
                wilson_low = _decimal_probability(
                    source["joint_certification_wilson_low"],
                    f"Wilson low row {row_number}",
                )
                wilson_high = _decimal_probability(
                    source["joint_certification_wilson_high"],
                    f"Wilson high row {row_number}",
                )
                if wilson_low > joint_rate or joint_rate > wilson_high:
                    raise ProvenanceError(
                        CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
                        f"Direct Wilson interval does not contain its rate at row {row_number}.",
                    )
                rows.append(
                    {
                        "original_protocol_id": ORIGINAL_PROTOCOL_ID,
                        "amendment_id": AMENDMENT_ID,
                        "design_id": source["design_id"],
                        "dependence_condition": source["dependence_condition"],
                        "candidate_id": source["safe_policy_id"],
                        "component_count": derived["component_count"],
                        "component_identifiers": derived[
                            "component_identifiers"
                        ],
                        "marginal_component_pass_rates": derived[
                            "marginal_component_pass_rates"
                        ],
                        "missing_component_identifiers": derived[
                            "missing_component_identifiers"
                        ],
                        "direct_observed_joint_certification_count": joint_count,
                        "direct_observed_joint_certification_rate": _decimal_text(
                            joint_rate
                        ),
                        "direct_observed_joint_wilson_low": _decimal_text(wilson_low),
                        "direct_observed_joint_wilson_high": _decimal_text(wilson_high),
                        "independence_joint_pass_point_estimate_from_marginals": (
                            derived[
                                "independence_joint_pass_point_estimate_from_marginals"
                            ]
                        ),
                        "union_bound_joint_pass_lower_point_estimate_from_marginals": (
                            derived[
                                "union_bound_joint_pass_lower_point_estimate_from_marginals"
                            ]
                        ),
                        "source_marginal_column": "marginal_component_powers",
                        "source_candidate_results_sha256": next(
                            entry["sha256"]
                            for entry in inventory["original_outputs"]
                            if entry["path"] == candidate_path
                        ),
                        "source_output_set_hash": inventory["output_set_hash"]["sha256"],
                        "amendment_implementation_hash": amendment_implementation_hash,
                        "components_share_observations": True,
                        "derivation_status": derived["derivation_status"],
                        "explicit_claim_boundary": (
                            "Direct simulated joint certification remains authoritative; "
                            "the product is an independence approximation and the union "
                            "quantity is a lower-bound plug-in diagnostic. Neither receives "
                            "a Wilson interval or constitutes guaranteed planning power."
                        ),
                    }
                )
    except UnicodeError as exc:
        raise ProvenanceError(
            CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
            f"candidate_results.csv is not valid UTF-8: {exc}",
        ) from exc
    if not rows:
        raise ProvenanceError(
            CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
            "candidate_results.csv contains no diagnostic rows.",
        )
    return rows


def deprecated_diagnostic_mapping(inventory: Mapping[str, Any]) -> dict[str, Any]:
    candidate_path = _candidate_results_path(inventory)
    candidate_hash = next(
        entry["sha256"]
        for entry in inventory["original_outputs"]
        if entry["path"] == candidate_path
    )
    return {
        "schema_version": "ragwarrant_deprecated_confirmation_diagnostics.v1",
        "amendment_id": AMENDMENT_ID,
        "original_protocol_id": ORIGINAL_PROTOCOL_ID,
        "classification": "DEPRECATED_MISLABELED_SECONDARY_DIAGNOSTIC",
        "original_files_containing_columns": [candidate_path],
        "original_file_sha256": {candidate_path: candidate_hash},
        "primary_conclusion_depended_on_columns": False,
        "primary_outcomes": (
            "Direct Monte Carlo joint-certification counts, proportions, and Wilson "
            "intervals remain authoritative and unchanged."
        ),
        "columns": [
            {"original_column_name": name, **details}
            for name, details in DEPRECATED_DIAGNOSTIC_COLUMNS.items()
        ],
    }


_CORRECTED_CSV_FIELDS = (
    "original_protocol_id",
    "amendment_id",
    "design_id",
    "dependence_condition",
    "candidate_id",
    "component_count",
    "component_identifiers",
    "marginal_component_pass_rates",
    "missing_component_identifiers",
    "direct_observed_joint_certification_count",
    "direct_observed_joint_certification_rate",
    "direct_observed_joint_wilson_low",
    "direct_observed_joint_wilson_high",
    "independence_joint_pass_point_estimate_from_marginals",
    "union_bound_joint_pass_lower_point_estimate_from_marginals",
    "source_marginal_column",
    "source_candidate_results_sha256",
    "source_output_set_hash",
    "amendment_implementation_hash",
    "components_share_observations",
    "derivation_status",
    "explicit_claim_boundary",
)


def corrected_diagnostics_csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=_CORRECTED_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for source in rows:
        rendered = dict(source)
        rendered["component_identifiers"] = json.dumps(
            rendered["component_identifiers"], separators=(",", ":"), ensure_ascii=True
        )
        rendered["marginal_component_pass_rates"] = json.dumps(
            rendered["marginal_component_pass_rates"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        rendered["missing_component_identifiers"] = json.dumps(
            rendered["missing_component_identifiers"],
            separators=(",", ":"),
            ensure_ascii=True,
        )
        rendered["components_share_observations"] = str(
            bool(rendered["components_share_observations"])
        ).lower()
        writer.writerow({field: rendered[field] for field in _CORRECTED_CSV_FIELDS})
    return stream.getvalue().encode("utf-8")


def corrected_diagnostics_json_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    payload = {
        "schema_version": "ragwarrant_corrected_confirmation_diagnostics.v1",
        "amendment_id": AMENDMENT_ID,
        "original_protocol_id": ORIGINAL_PROTOCOL_ID,
        "row_count": len(rows),
        "rows": list(rows),
    }
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def _artifact_entry(repository_root: Path, relative_path: str) -> dict[str, Any]:
    resolved = resolve_repository_path(repository_root, relative_path, must_exist=True)
    return {
        "path": relative_path,
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def _provenance_markdown(inventory: Mapping[str, Any]) -> bytes:
    text = f"""# Confirmation provenance and diagnostic amendment v1

Amendment ID: `{AMENDMENT_ID}`
Amendment type: `{AMENDMENT_TYPE}`
Original protocol: `{ORIGINAL_PROTOCOL_ID}`

The package was blocked because the original materialization lacked a canonical,
workspace-local provenance binding and two secondary CSV columns were labeled as
aggregate independence/union diagnostics even though their preserved calculations
were per-replicate all-component pass indicators at the Bonferroni alpha floor
(`familywise_error_level / candidate_count`), distinct from direct Holm certification.

No simulation was rerun. The original outputs remain byte-identical. Primary direct
Monte Carlo joint-certification counts, probabilities, and Wilson intervals remain
valid and authoritative. The original mislabeled columns remain preserved as
historical output and are classified as
`DEPRECATED_MISLABELED_SECONDARY_DIAGNOSTIC`. Corrected plug-in diagnostics appear
only in new amendment artifacts.

No design point, seed, sample size, quota, scenario, dependence condition, threshold,
risk, estimand, method, or interpretation rule changed.

The sole canonical output root is
`{inventory['canonical_output_root']}` and the materialization scope is
`{MATERIALIZATION_SCOPE}`. This scope does not prevent arbitrary copies outside the
declared repository workspace or direct invocation of an unguarded historical runner.

The corrected product is labeled an independence approximation. The corrected union
formula is a lower-bound plug-in diagnostic. Neither is an observed joint proportion,
neither receives a Wilson interval, and neither replaces the direct simulated joint
certification result.
"""
    return text.encode("utf-8")


def write_new_amendment_artifacts(
    repository_root: Path,
    *,
    amendment_implementation_path: str = DEFAULT_IMPLEMENTATION_PATH,
    inventory_path: str = DEFAULT_INVENTORY_PATH,
    registry_path: str = DEFAULT_REGISTRY_PATH,
    provenance_path: str = DEFAULT_PROVENANCE_PATH,
    provenance_markdown_path: str = DEFAULT_PROVENANCE_MARKDOWN_PATH,
    corrected_csv_path: str = DEFAULT_CORRECTED_CSV_PATH,
    corrected_json_path: str = DEFAULT_CORRECTED_JSON_PATH,
    deprecated_mapping_path: str = DEFAULT_DEPRECATED_MAPPING_PATH,
    reviewed_freeze_path: str = DEFAULT_REVIEWED_FREEZE_PATH,
) -> VerificationResult:
    """Create amendment-only artifacts exclusively; never overwrite any file."""

    try:
        destinations = (
            provenance_path,
            provenance_markdown_path,
            corrected_csv_path,
            corrected_json_path,
            deprecated_mapping_path,
        )
        for destination in destinations:
            resolved_destination = resolve_repository_path(
                repository_root, destination, must_exist=False
            )
            if resolved_destination.exists():
                raise ProvenanceError(
                    CONFIRMATION_DUPLICATE_MATERIALIZATION,
                    f"Amendment artifact already exists and will not be overwritten: {destination}.",
                )
        freeze_result = verify_reviewed_implementation_freeze(
            repository_root, freeze_path=reviewed_freeze_path
        )
        if not freeze_result.ok:
            return freeze_result
        inventory = load_original_inventory(repository_root, inventory_path)
        original_result = verify_original_materialization(repository_root, inventory)
        if not original_result.ok:
            return original_result
        implementation = resolve_repository_path(
            repository_root, amendment_implementation_path, must_exist=True
        )
        if amendment_implementation_path != DEFAULT_IMPLEMENTATION_PATH:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                "Amendment implementation must use its canonical repository path.",
            )
        implementation_hash = sha256_file(implementation)
        rows = derive_corrected_diagnostics(
            repository_root,
            inventory,
            amendment_implementation_hash=implementation_hash,
        )
        registry_result = register_existing_materialization(
            repository_root,
            inventory_path=inventory_path,
            registry_path=registry_path,
        )
        if not registry_result.ok:
            return registry_result
        mapping = deprecated_diagnostic_mapping(inventory)
        mapping_bytes = json.dumps(
            mapping,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8") + b"\n"
        csv_bytes = corrected_diagnostics_csv_bytes(rows)
        json_bytes = corrected_diagnostics_json_bytes(rows)
        markdown_bytes = _provenance_markdown(inventory)
        payload_by_path = (
            (deprecated_mapping_path, mapping_bytes),
            (corrected_csv_path, csv_bytes),
            (corrected_json_path, json_bytes),
            (provenance_markdown_path, markdown_bytes),
        )
        written: list[Path] = []
        try:
            for relative_path, payload in payload_by_path:
                destination = resolve_repository_path(
                    repository_root, relative_path, must_exist=False
                )
                _exclusive_write(destination, payload)
                written.append(destination)
            amendment_artifacts = [
                _artifact_entry(repository_root, relative_path)
                for relative_path, _ in payload_by_path
            ]
            registry_entry = _artifact_entry(repository_root, registry_path)
            provenance = {
                "schema_version": "ragwarrant_confirmation_provenance_amendment.v1",
                "amendment_id": AMENDMENT_ID,
                "amendment_type": AMENDMENT_TYPE,
                "original_protocol_id": ORIGINAL_PROTOCOL_ID,
                "original_protocol_remains_immutable": True,
                "simulation_rerun": False,
                "scientific_design_inputs_changed": False,
                "primary_joint_results_changed": False,
                "original_mislabeled_fields_preserved": True,
                "corrected_diagnostics_only_in_new_amendment_artifacts": True,
                "canonical_repository_root_identity": inventory[
                    "canonical_repository_root_identity"
                ],
                "canonical_protocol_path": inventory["canonical_protocol_path"],
                "canonical_config_path": inventory["canonical_config_path"],
                "canonical_runner_path": inventory["canonical_runner_path"],
                "canonical_output_root": inventory["canonical_output_root"],
                "canonical_materialization_id": inventory[
                    "canonical_materialization_id"
                ],
                "materialization_scope": MATERIALIZATION_SCOPE,
                "source_inventory": {
                    "path": inventory_path,
                    "sha256": sha256_file(
                        resolve_repository_path(
                            repository_root, inventory_path, must_exist=True
                        )
                    ),
                },
                "reviewed_implementation_freeze": _artifact_entry(
                    repository_root, reviewed_freeze_path
                ),
                "source_protocol_sha256": inventory["original_protocol_sha256"],
                "source_config_sha256": inventory[
                    "original_configuration_sha256"
                ],
                "source_runner_sha256": inventory["original_runner_sha256"],
                "source_output_set_sha256": inventory["output_set_hash"]["sha256"],
                "amendment_implementation": {
                    "path": amendment_implementation_path,
                    "sha256": implementation_hash,
                },
                "registry": registry_entry,
                "amendment_artifacts": amendment_artifacts,
                "deprecated_diagnostics": sorted(DEPRECATED_DIAGNOSTIC_COLUMNS),
                "corrected_diagnostics_derive_only_from_preserved_aggregate_marginals": True,
                "direct_monte_carlo_joint_results_remain_authoritative": True,
                "claim_boundary": (
                    "This is a workspace-local provenance binding and secondary "
                    "diagnostic correction. It does not prevent external copies, "
                    "change primary outcomes, or establish a statistical guarantee."
                ),
            }
            provenance_bytes = json.dumps(
                provenance,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8") + b"\n"
            provenance_destination = resolve_repository_path(
                repository_root, provenance_path, must_exist=False
            )
            _exclusive_write(provenance_destination, provenance_bytes)
            written.append(provenance_destination)
        except Exception:
            # Fail closed. Never delete a partially written provenance artifact;
            # the next invocation will refuse rather than silently reconstruct it.
            raise
        return VerificationResult(
            status=CONFIRMATION_PROVENANCE_VERIFIED,
            ok=True,
            message="New provenance amendment artifacts were created without rerunning simulation.",
            details={
                "corrected_row_count": len(rows),
                "source_output_set_sha256": inventory["output_set_hash"]["sha256"],
                "simulation_rerun": False,
                "artifact_paths": [provenance_path, *destinations[1:]],
            },
        )
    except ProvenanceError as exc:
        return exc.as_result()
    except FileExistsError as exc:
        return VerificationResult(
            status=CONFIRMATION_DUPLICATE_MATERIALIZATION,
            ok=False,
            message=f"Exclusive amendment artifact creation refused an existing path: {exc}",
        )


def _parse_corrected_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != _CORRECTED_CSV_FIELDS:
            raise ProvenanceError(
                CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
                "Corrected diagnostics CSV schema differs from the amendment contract.",
            )
        return list(reader)


def _rows_as_csv_comparable(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    payload = corrected_diagnostics_csv_bytes(rows).decode("utf-8")
    return list(csv.DictReader(io.StringIO(payload)))


def verify_confirmation_provenance(
    repository_root: Path,
    *,
    provenance_path: str = DEFAULT_PROVENANCE_PATH,
    inventory_path: str = DEFAULT_INVENTORY_PATH,
    registry_path: str = DEFAULT_REGISTRY_PATH,
    reviewed_freeze_path: str = DEFAULT_REVIEWED_FREEZE_PATH,
) -> VerificationResult:
    """Read-only verification of original hashes, registry, and derivations."""

    try:
        freeze_result = verify_reviewed_implementation_freeze(
            repository_root, freeze_path=reviewed_freeze_path
        )
        if not freeze_result.ok:
            return freeze_result
        inventory = load_original_inventory(repository_root, inventory_path)
        original_result = verify_original_materialization(repository_root, inventory)
        if not original_result.ok:
            return original_result
        registry_result = _verify_registry(
            repository_root, inventory, registry_path, inventory_path
        )
        if not registry_result.ok:
            return registry_result
        resolved_provenance = resolve_repository_path(
            repository_root, provenance_path, must_exist=True
        )
        provenance_raw = _load_json_file(
            resolved_provenance, "Confirmation provenance amendment record"
        )
        provenance = _require_mapping(
            provenance_raw, "Confirmation provenance amendment record"
        )
        required_provenance = {
            "schema_version",
            "amendment_id",
            "amendment_type",
            "original_protocol_id",
            "canonical_repository_root_identity",
            "canonical_protocol_path",
            "canonical_config_path",
            "canonical_runner_path",
            "canonical_output_root",
            "canonical_materialization_id",
            "materialization_scope",
            "source_inventory",
            "reviewed_implementation_freeze",
            "source_protocol_sha256",
            "source_config_sha256",
            "source_runner_sha256",
            "source_output_set_sha256",
            "amendment_implementation",
            "registry",
            "amendment_artifacts",
        }
        missing = sorted(required_provenance - provenance.keys())
        if missing:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_INCOMPLETE,
                "Provenance amendment lacks required fields.",
                details={"missing_fields": missing},
            )
        expected_values = {
            "schema_version": "ragwarrant_confirmation_provenance_amendment.v1",
            "amendment_id": AMENDMENT_ID,
            "amendment_type": AMENDMENT_TYPE,
            "original_protocol_id": ORIGINAL_PROTOCOL_ID,
            "canonical_repository_root_identity": inventory[
                "canonical_repository_root_identity"
            ],
            "canonical_protocol_path": inventory["canonical_protocol_path"],
            "canonical_config_path": inventory["canonical_config_path"],
            "canonical_runner_path": inventory["canonical_runner_path"],
            "canonical_output_root": inventory["canonical_output_root"],
            "canonical_materialization_id": inventory[
                "canonical_materialization_id"
            ],
            "materialization_scope": MATERIALIZATION_SCOPE,
            "source_protocol_sha256": inventory["original_protocol_sha256"],
            "source_config_sha256": inventory["original_configuration_sha256"],
            "source_runner_sha256": inventory["original_runner_sha256"],
            "source_output_set_sha256": inventory["output_set_hash"]["sha256"],
        }
        for key, expected in expected_values.items():
            if provenance.get(key) != expected:
                raise ProvenanceError(
                    CONFIRMATION_PROVENANCE_HASH_MISMATCH,
                    f"Provenance field {key} no longer matches its frozen source.",
                )
        expected_flags = {
            "original_protocol_remains_immutable": True,
            "simulation_rerun": False,
            "scientific_design_inputs_changed": False,
            "primary_joint_results_changed": False,
            "original_mislabeled_fields_preserved": True,
            "corrected_diagnostics_only_in_new_amendment_artifacts": True,
            "corrected_diagnostics_derive_only_from_preserved_aggregate_marginals": True,
            "direct_monte_carlo_joint_results_remain_authoritative": True,
        }
        for key, expected in expected_flags.items():
            if provenance.get(key) is not expected:
                raise ProvenanceError(
                    CONFIRMATION_PROVENANCE_HASH_MISMATCH,
                    f"Provenance semantic flag {key} differs from the amendment contract.",
                )
        source_inventory = _require_mapping(
            provenance["source_inventory"], "source_inventory"
        )
        if source_inventory.get("path") != inventory_path:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                "Provenance record points to a different source inventory.",
            )
        inventory_hash = sha256_file(
            resolve_repository_path(repository_root, inventory_path, must_exist=True)
        )
        if source_inventory.get("sha256") != inventory_hash:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_HASH_MISMATCH,
                "Source inventory hash differs from the provenance record.",
            )
        freeze_declaration = _require_mapping(
            provenance["reviewed_implementation_freeze"],
            "reviewed_implementation_freeze",
        )
        if freeze_declaration.get("path") != reviewed_freeze_path:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                "Provenance record points to a different reviewed implementation freeze.",
            )
        _verify_file_entry(
            repository_root, freeze_declaration, reject_hardlinks=True
        )
        implementation = _require_mapping(
            provenance["amendment_implementation"], "amendment_implementation"
        )
        implementation_path = require_canonical_repository_relative_path(
            str(implementation.get("path", ""))
        )
        if implementation_path != DEFAULT_IMPLEMENTATION_PATH:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                "Provenance record points to a noncanonical amendment implementation.",
            )
        implementation_actual_hash = sha256_file(
            resolve_repository_path(
                repository_root, implementation_path, must_exist=True
            )
        )
        if implementation.get("sha256") != implementation_actual_hash:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_HASH_MISMATCH,
                "Amendment implementation hash differs from the provenance record.",
            )
        declared_artifacts = provenance["amendment_artifacts"]
        if not isinstance(declared_artifacts, list) or not declared_artifacts:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_INCOMPLETE,
                "Provenance record has no declared amendment artifacts.",
            )
        for artifact in declared_artifacts:
            _verify_file_entry(repository_root, artifact, reject_hardlinks=True)
        registry_declaration = _require_mapping(provenance["registry"], "registry")
        if registry_declaration.get("path") != registry_path:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_PATH_MISMATCH,
                "Provenance record points to a different registry path.",
            )
        _verify_file_entry(repository_root, registry_declaration, reject_hardlinks=True)
        rows = derive_corrected_diagnostics(
            repository_root,
            inventory,
            amendment_implementation_hash=implementation_actual_hash,
        )
        artifact_paths = {entry["path"]: entry for entry in declared_artifacts}
        required_artifact_paths = {
            DEFAULT_CORRECTED_CSV_PATH,
            DEFAULT_CORRECTED_JSON_PATH,
            DEFAULT_DEPRECATED_MAPPING_PATH,
            DEFAULT_PROVENANCE_MARKDOWN_PATH,
        }
        if set(artifact_paths) != required_artifact_paths:
            raise ProvenanceError(
                CONFIRMATION_PROVENANCE_INCOMPLETE,
                "Provenance record does not declare the exact amendment artifact set.",
                details={
                    "missing": sorted(required_artifact_paths - set(artifact_paths)),
                    "extra": sorted(set(artifact_paths) - required_artifact_paths),
                },
            )
        actual_csv = _parse_corrected_csv(
            resolve_repository_path(
                repository_root, DEFAULT_CORRECTED_CSV_PATH, must_exist=True
            )
        )
        expected_csv = _rows_as_csv_comparable(rows)
        if actual_csv != expected_csv:
            raise ProvenanceError(
                CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
                "Corrected CSV does not reproduce from the preserved aggregate marginals.",
            )
        actual_json = _load_json_file(
            resolve_repository_path(
                repository_root, DEFAULT_CORRECTED_JSON_PATH, must_exist=True
            ),
            "Corrected diagnostics JSON",
        )
        expected_json = json.loads(corrected_diagnostics_json_bytes(rows))
        if actual_json != expected_json:
            raise ProvenanceError(
                CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
                "Corrected JSON does not reproduce from the preserved aggregate marginals.",
            )
        actual_mapping = _load_json_file(
            resolve_repository_path(
                repository_root, DEFAULT_DEPRECATED_MAPPING_PATH, must_exist=True
            ),
            "Deprecated diagnostic mapping",
        )
        if actual_mapping != deprecated_diagnostic_mapping(inventory):
            raise ProvenanceError(
                CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH,
                "Deprecated diagnostic mapping differs from the amendment contract.",
            )
        return VerificationResult(
            status=CONFIRMATION_PROVENANCE_VERIFIED,
            ok=True,
            message="Confirmation provenance and corrected diagnostics verified read-only.",
            details={
                "canonical_materialization_id": inventory[
                    "canonical_materialization_id"
                ],
                "canonical_output_root": inventory["canonical_output_root"],
                "output_set_sha256": inventory["output_set_hash"]["sha256"],
                "corrected_diagnostic_rows": len(rows),
                "simulation_rerun": False,
            },
        )
    except ProvenanceError as exc:
        return exc.as_result()


__all__ = [
    "AMENDMENT_ID",
    "AMENDMENT_TYPE",
    "CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH",
    "CONFIRMATION_DUPLICATE_MATERIALIZATION",
    "CONFIRMATION_PROVENANCE_HASH_MISMATCH",
    "CONFIRMATION_PROVENANCE_INCOMPLETE",
    "CONFIRMATION_PROVENANCE_PATH_MISMATCH",
    "CONFIRMATION_PROVENANCE_VERIFIED",
    "DEFAULT_AMENDMENT_ROOT",
    "DEFAULT_CORRECTED_CSV_PATH",
    "DEFAULT_CORRECTED_JSON_PATH",
    "DEFAULT_DEPRECATED_MAPPING_PATH",
    "DEFAULT_INVENTORY_PATH",
    "DEFAULT_PROVENANCE_PATH",
    "DEFAULT_REVIEWED_FREEZE_PATH",
    "DEFAULT_REGISTRY_PATH",
    "DEPRECATED_DIAGNOSTIC_COLUMNS",
    "FOCUS1_DIGEST",
    "MATERIALIZATION_SCOPE",
    "ORIGINAL_PROTOCOL_ID",
    "ProvenanceError",
    "REQUIRED_COMPONENT_IDS",
    "V1_FROZEN_COMMIT",
    "VerificationResult",
    "canonical_json_bytes",
    "canonical_json_sha256",
    "corrected_diagnostics_csv_bytes",
    "corrected_diagnostics_json_bytes",
    "deprecated_diagnostic_mapping",
    "derive_corrected_diagnostics",
    "derive_marginal_diagnostics",
    "guard_original_protocol_materialization",
    "load_original_inventory",
    "normalize_repository_relative_path",
    "output_set_digest",
    "paths_equal_under_host_contract",
    "register_existing_materialization",
    "require_canonical_repository_relative_path",
    "resolve_repository_path",
    "sha256_file",
    "verify_confirmation_provenance",
    "verify_original_materialization",
    "verify_reviewed_implementation_freeze",
    "write_new_amendment_artifacts",
]
