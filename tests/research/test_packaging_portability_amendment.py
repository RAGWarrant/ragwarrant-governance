from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "src/ragwarrant/research/packaging_portability_amendment.py"
SCRIPT_PATH = ROOT / "scripts/verify_packaging_portability.py"


def _load_module() -> ModuleType:
    name = "_test_packaging_portability_amendment"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


portability = _load_module()
REAL_FOCUS1_VERIFIER = portability.verify_focus1_checkpoint_authority


def _focus1_checkpoint_object_exists() -> bool:
    completed = subprocess.run(
        [
            "git",
            "cat-file",
            "-e",
            f"{portability.FOCUS1_CHECKPOINT_COMMIT}^{{commit}}",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


@pytest.fixture(autouse=True)
def _isolate_non_focus_authorities(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep packaging-unit fixtures synthetic; Focus 1 has dedicated real tests."""

    monkeypatch.setattr(portability, "AUTHORIZED_REPLACEMENT_SHA256", {})
    monkeypatch.setattr(
        portability,
        "verify_historical_focus1_authority",
        lambda root: {
            "status": portability.HISTORICAL_FOCUS1_AUTHORITY_VERIFIED,
            "checkpoint_commit": portability.FOCUS1_CHECKPOINT_COMMIT,
            "frozen_path_count": 36,
            "expected_digest": portability.FOCUS1_DIGEST,
            "observed_digest": portability.FOCUS1_DIGEST,
            "manifest": {"benchmark_freeze_digest": portability.FOCUS1_DIGEST},
        },
    )
    monkeypatch.setattr(
        portability,
        "verify_pr_b_declared_compatibility_delta",
        lambda root: {
            "status": portability.PR_B_DECLARED_COMPATIBILITY_DELTA_VERIFIED,
            "complete_historical_byte_equivalence_claimed": False,
        },
    )


def _write(root: Path, relative_path: str, content: bytes) -> Path:
    path = root.joinpath(*relative_path.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(repository_root: Path) -> dict[str, object]:
    bindings: list[dict[str, object]] = []
    for path in sorted(portability.REQUIRED_REBINDING_PATHS):
        tracked = repository_root.joinpath(*path.split("/"))
        authority = portability.AUTHORIZED_REBINDING_METADATA[path]
        bindings.append(
            {
                "prior_path": authority["prior_path"],
                "prior_sha256": (
                    authority["prior_sha256"]
                    if authority["prior_path"] is not None
                    else "NEW_FILE"
                ),
                "new_path": path,
                "new_sha256": _sha(tracked),
                "amendment_id": portability.INTEGRITY_AMENDMENT_ID,
                "change_category": authority["change_category"],
                "reason": "Synthetic test binding for the portability contract.",
                "scientific_impact": "NONE",
                "result_impact": "NONE",
            }
        )
    return {
        "schema_version": portability.SCHEMA_VERSION,
        "amendment_id": portability.AMENDMENT_ID,
        "amendment_type": portability.AMENDMENT_TYPE,
        "frozen_authorities": {
            "focus1_digest": portability.FOCUS1_DIGEST,
            "v1_hash": portability.V1_FROZEN_COMMIT,
            "original_confirmation_output_set_sha256": (
                portability.ORIGINAL_OUTPUT_SET_SHA256
            ),
        },
        "frozen_yaml_files": [
            {"path": path, "sha256": digest}
            for path, digest in portability.FROZEN_YAML_SHA256.items()
        ],
        "gitattributes_rules": dict(portability.REQUIRED_GITATTRIBUTES_RULES),
        "hash_rebindings": bindings,
        "declarations": {
            "scientific_input_changed": False,
            "scenario_changed": False,
            "truth_changed": False,
            "threshold_or_margin_changed": False,
            "method_changed": False,
            "seed_changed": False,
            "result_changed": False,
            "original_confirmation_output_changed": False,
            "simulation_rerun": False,
            "amendment_scope": "GIT_WHITESPACE_POLICY_AND_TEST_PORTABILITY_ONLY",
            "test_hashes_rebound_additively": True,
            "frozen_yaml_bytes_and_hashes_unchanged": True,
        },
    }


def _integrity_record(parent_record_path: Path) -> dict[str, object]:
    parent = json.loads(parent_record_path.read_text(encoding="utf-8"))
    return {
        "schema_version": "ragwarrant_packaging_integrity_amendment.v2",
        "amendment_id": portability.INTEGRITY_AMENDMENT_ID,
        "amendment_type": portability.INTEGRITY_AMENDMENT_TYPE,
        "parent_amendment_id": portability.AMENDMENT_ID,
        "parent_record": {
            "path": portability.DEFAULT_RECORD_PATH,
            "sha256": _sha(parent_record_path),
        },
        "focus1_authority": {
            "checkpoint_commit": portability.FOCUS1_CHECKPOINT_COMMIT,
            "accepted_digest": portability.FOCUS1_DIGEST,
        },
        "authorized_rebinding_paths": sorted(portability.REQUIRED_REBINDING_PATHS),
        "authorized_rebindings_sha256": hashlib.sha256(
            json.dumps(
                parent["hash_rebindings"],
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest(),
        "authority_json_paths": [
            ".local_data/research_review/confirmation_amendment/ORIGINAL_MATERIALIZATION_INVENTORY.json",
            ".local_data/research_review/confirmation_amendment/confirmation_provenance_amendment_v1.json",
        ],
        "trust_boundary": {
            "verifier_self_attestation": False,
            "reviewed_git_commit_and_ci_required": True,
            "global_external_copy_integrity_claimed": False,
        },
        "declarations": {
            "scientific_input_changed": False,
            "result_changed": False,
            "original_confirmation_output_changed": False,
            "simulation_rerun": False,
            "full_executed": False,
            "drand_accessed": False,
        },
    }


def _write_synthetic_repository(tmp_path: Path) -> tuple[Path, Path]:
    repository_root = tmp_path / "repository"
    repository_root.mkdir(parents=True)
    whitespace_rules: list[str] = []
    preserved_paths = {
        **portability.FROZEN_YAML_SHA256,
        **portability.PRESERVED_BLANK_EOF_INPUT_SHA256,
    }
    for relative_path in preserved_paths:
        _write(repository_root, relative_path, (ROOT / relative_path).read_bytes())
        whitespace_rules.append(
            f"{relative_path} {portability.REQUIRED_WHITESPACE_ATTRIBUTE}"
        )
    _write(
        repository_root,
        ".gitattributes",
        ("\n".join(whitespace_rules) + "\n").encode(),
    )
    for path in portability.REQUIRED_REBINDING_PATHS - {
        ".gitattributes",
        *preserved_paths,
    }:
        _write(repository_root, path, f"synthetic tracked file: {path}\n".encode())
    record_path = _write(
        repository_root,
        portability.DEFAULT_RECORD_PATH,
        (json.dumps(_record(repository_root), sort_keys=True, indent=2) + "\n").encode(),
    )
    _write(
        repository_root,
        portability.INTEGRITY_RECORD_PATH,
        (
            json.dumps(
                _integrity_record(record_path), sort_keys=True, indent=2
            )
            + "\n"
        ).encode(),
    )
    subprocess.run(["git", "init", "-q"], cwd=repository_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "synthetic@example.invalid"],
        cwd=repository_root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Synthetic Test"],
        cwd=repository_root,
        check=True,
    )
    subprocess.run(["git", "add", "--all"], cwd=repository_root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "synthetic"],
        cwd=repository_root,
        check=True,
    )
    return repository_root, record_path


def _rewrite_record(record_path: Path, mutate: object) -> None:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    mutate(record)
    record_path.write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    repository_root = record_path.parents[2]
    integrity_path = repository_root.joinpath(
        *portability.INTEGRITY_RECORD_PATH.split("/")
    )
    integrity_path.write_text(
        json.dumps(_integrity_record(record_path), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def test_portable_synthetic_repository_verifies_without_workspace_materialization(
    tmp_path: Path,
) -> None:
    repository_root, _ = _write_synthetic_repository(tmp_path)
    result = portability.verify_packaging_portability(repository_root)
    assert result.ok, result.as_dict()
    assert result.status == portability.PACKAGING_PORTABILITY_VERIFIED
    assert result.details["workspace_materialization"] == {
        "status": "NOT_REQUESTED",
        "bytes_unchanged": None,
    }
    assert result.details["simulation_rerun"] is False


def test_frozen_authority_mismatch_fails_closed(tmp_path: Path) -> None:
    repository_root, record_path = _write_synthetic_repository(tmp_path)

    def mutate(record: dict[str, object]) -> None:
        authorities = record["frozen_authorities"]
        assert isinstance(authorities, dict)
        authorities["focus1_digest"] = "0" * 64

    _rewrite_record(record_path, mutate)
    result = portability.verify_packaging_portability(repository_root)
    assert not result.ok
    assert result.status == portability.PACKAGING_PORTABILITY_HASH_MISMATCH


def test_frozen_yaml_byte_change_is_detected(tmp_path: Path) -> None:
    repository_root, _ = _write_synthetic_repository(tmp_path)
    yaml_path = repository_root / next(iter(portability.FROZEN_YAML_SHA256))
    yaml_path.write_bytes(yaml_path.read_bytes() + b"changed")
    result = portability.verify_packaging_portability(repository_root)
    assert not result.ok
    assert result.status == portability.PACKAGING_PORTABILITY_HASH_MISMATCH


def test_preserved_confirmation_input_byte_change_is_detected(tmp_path: Path) -> None:
    repository_root, _ = _write_synthetic_repository(tmp_path)
    preserved_path = repository_root / next(
        iter(portability.PRESERVED_BLANK_EOF_INPUT_SHA256)
    )
    preserved_path.write_bytes(preserved_path.read_bytes() + b"changed")
    result = portability.verify_packaging_portability(repository_root)
    assert not result.ok
    assert result.status == portability.PACKAGING_PORTABILITY_HASH_MISMATCH


def test_broad_or_unrelated_whitespace_override_is_rejected(tmp_path: Path) -> None:
    repository_root, record_path = _write_synthetic_repository(tmp_path)
    attributes = repository_root / ".gitattributes"
    attributes.write_text(
        attributes.read_text(encoding="utf-8") + "*.py whitespace=-blank-at-eof\n",
        encoding="utf-8",
    )

    def mutate(record: dict[str, object]) -> None:
        for binding in record["hash_rebindings"]:
            if binding["new_path"] == ".gitattributes":
                binding["new_sha256"] = _sha(attributes)

    _rewrite_record(record_path, mutate)
    result = portability.verify_packaging_portability(repository_root)
    assert not result.ok
    assert result.status == portability.PACKAGING_PORTABILITY_POLICY_MISMATCH


def test_replacement_hash_mismatch_is_detected(tmp_path: Path) -> None:
    repository_root, _ = _write_synthetic_repository(tmp_path)
    target = repository_root / "pyproject.toml"
    target.write_text("tampered\n", encoding="utf-8")
    result = portability.verify_packaging_portability(repository_root)
    assert not result.ok
    assert result.status == portability.PACKAGING_PORTABILITY_HASH_MISMATCH


def test_record_rejects_traversal_and_duplicate_json_keys(tmp_path: Path) -> None:
    repository_root, record_path = _write_synthetic_repository(tmp_path)
    def traversal(record: dict[str, object]) -> None:
        record["hash_rebindings"][0]["new_path"] = "tests/../escape.py"

    _rewrite_record(record_path, traversal)
    result = portability.verify_packaging_portability(repository_root)
    assert not result.ok
    assert result.status == portability.AUTHORITY_PATH_TRAVERSAL_REJECTED

    record_path.write_text(
        '{"schema_version":"one","schema_version":"two"}', encoding="utf-8"
    )
    result = portability.verify_packaging_portability(repository_root)
    assert not result.ok
    assert result.status == portability.PACKAGING_PORTABILITY_INCOMPLETE


LEGACY_TEST_HASHES = {
    "tests/research/test_joint_power_confirmation.py": (
        "a76ea9bfac13a433d81b72756dbe7d795f26f911d38c6e19e162f5a2e3f39fab"
    ),
    "tests/research/test_confirmation_provenance_amendment.py": (
        "14d5fbebba40b2773a3cb710c0686fda9fedb0b42d5c53c023f396d489bb9a8c"
    ),
}


def _aggregate_output_hash(entries: list[dict[str, object]]) -> str:
    payload = json.dumps(
        sorted(entries, key=lambda entry: str(entry["path"])),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_fake_workspace(
    tmp_path: Path,
) -> tuple[Path, Path, list[dict[str, object]], str]:
    repository_root = tmp_path / "workspace"
    materialization_root = repository_root / "workspace_outputs" / "confirmation_v1"
    materialization_root.mkdir(parents=True)
    (repository_root / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    implementation = repository_root / (
        "src/ragwarrant/research/confirmation_provenance_amendment.py"
    )
    implementation.parent.mkdir(parents=True)
    implementation.write_text("# synthetic repository marker only\n", encoding="utf-8")

    output_file = materialization_root / "synthetic.bin"
    output_file.write_bytes(b"synthetic-test-only")
    output_entry = {
        "path": "workspace_outputs/confirmation_v1/synthetic.bin",
        "size_bytes": output_file.stat().st_size,
        "sha256": _sha(output_file),
    }
    output_set_sha256 = _aggregate_output_hash([output_entry])

    unchanged_path = _write(
        repository_root, "tracked/unchanged.txt", b"preserved test fixture\n"
    )
    unchanged_entry = {
        "path": "tracked/unchanged.txt",
        "size_bytes": unchanged_path.stat().st_size,
        "sha256": _sha(unchanged_path),
    }
    rebindings: list[dict[str, object]] = []
    legacy_entries: dict[str, dict[str, object]] = {}
    for path, prior_hash in LEGACY_TEST_HASHES.items():
        current = _write(repository_root, path, f"portable replacement {path}\n".encode())
        legacy_entries[path] = {
            "path": path,
            "size_bytes": 1,
            "sha256": prior_hash,
        }
        rebindings.append(
            {
                "prior_path": path,
                "prior_sha256": prior_hash,
                "new_path": path,
                "new_sha256": _sha(current),
                "change_category": "TEST_PORTABILITY",
                "reason": "Synthetic old-to-new accepted test hash binding.",
                "scientific_impact": "NONE",
                "result_impact": "NONE",
            }
        )

    amendment_root = materialization_root.parent / "confirmation_amendment"
    amendment_root.mkdir()
    inventory = {
        "focus1_digest": portability.FOCUS1_DIGEST,
        "v1_frozen_commit": portability.V1_FROZEN_COMMIT,
        "canonical_output_root": "workspace_outputs/confirmation_v1",
        "canonical_materialization_id": "synthetic-materialization-v1",
        "materialization_scope": "AUTHORITATIVE_WITHIN_DECLARED_REPOSITORY_WORKSPACE",
        "output_set_hash": {
            "sha256": output_set_sha256,
            "file_policy": "EXACT_DECLARED_FILE_SET_NO_EXTRA_FILES",
        },
        "original_inputs": [unchanged_entry, legacy_entries[next(iter(LEGACY_TEST_HASHES))]],
        "original_outputs": [output_entry],
    }
    inventory_path = amendment_root / "ORIGINAL_MATERIALIZATION_INVENTORY.json"
    inventory_path.write_text(json.dumps(inventory, sort_keys=True), encoding="utf-8")

    freeze = {
        "focus1_digest": portability.FOCUS1_DIGEST,
        "v1_frozen_commit": portability.V1_FROZEN_COMMIT,
        "original_output_set_sha256": output_set_sha256,
        "materialization_scope": "AUTHORITATIVE_WITHIN_DECLARED_REPOSITORY_WORKSPACE",
        "simulation_rerun": False,
        "scientific_design_inputs_changed": False,
        "frozen_files": [
            unchanged_entry,
            legacy_entries["tests/research/test_confirmation_provenance_amendment.py"],
        ],
    }
    freeze_path = amendment_root / "AMENDMENT_IMPLEMENTATION_FREEZE_REVIEWED.json"
    freeze_path.write_text(json.dumps(freeze, sort_keys=True), encoding="utf-8")

    registry = {
        "focus1_digest": portability.FOCUS1_DIGEST,
        "v1_frozen_commit": portability.V1_FROZEN_COMMIT,
        "source_output_set_sha256": output_set_sha256,
        "canonical_output_root": "workspace_outputs/confirmation_v1",
        "canonical_materialization_id": "synthetic-materialization-v1",
        "materialization_scope": "AUTHORITATIVE_WITHIN_DECLARED_REPOSITORY_WORKSPACE",
        "registry_state": "IMPORTED_EXISTING_ORIGINAL",
        "simulation_executed_by_amendment": False,
        "source_inventory_path": (
            "workspace_outputs/confirmation_amendment/"
            "ORIGINAL_MATERIALIZATION_INVENTORY.json"
        ),
        "source_inventory_sha256": _sha(inventory_path),
    }
    registry_path = amendment_root / "canonical_materialization_registry_v1.json"
    registry_path.write_text(json.dumps(registry, sort_keys=True), encoding="utf-8")

    provenance = {
        "source_output_set_sha256": output_set_sha256,
        "source_inventory": {
            "path": registry["source_inventory_path"],
            "sha256": _sha(inventory_path),
        },
        "reviewed_implementation_freeze": {
            "path": (
                "workspace_outputs/confirmation_amendment/"
                "AMENDMENT_IMPLEMENTATION_FREEZE_REVIEWED.json"
            ),
            "size_bytes": freeze_path.stat().st_size,
            "sha256": _sha(freeze_path),
        },
        "registry": {
            "path": (
                "workspace_outputs/confirmation_amendment/"
                "canonical_materialization_registry_v1.json"
            ),
            "size_bytes": registry_path.stat().st_size,
            "sha256": _sha(registry_path),
        },
    }
    (amendment_root / "confirmation_provenance_amendment_v1.json").write_text(
        json.dumps(provenance, sort_keys=True), encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=repository_root, check=True)
    return repository_root, materialization_root, rebindings, output_set_sha256


def test_explicit_workspace_materialization_verification_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, materialization_root, rebindings, output_set_sha256 = _write_fake_workspace(
        tmp_path
    )
    monkeypatch.setattr(
        portability,
        "ORIGINAL_OUTPUT_SET_SHA256",
        output_set_sha256,
    )
    before = (materialization_root / "synthetic.bin").read_bytes()
    details = portability.verify_workspace_materialization_read_only(
        materialization_root,
        repository_root=materialization_root.parents[1],
        hash_rebindings=rebindings,
    )
    after = (materialization_root / "synthetic.bin").read_bytes()
    assert details["status"] == "CONFIRMATION_PROVENANCE_VERIFIED"
    assert details["bytes_unchanged"] is True
    assert before == after
    assert sorted(details["additively_rebound_inputs"]) == sorted(LEGACY_TEST_HASHES)


def test_workspace_changed_test_without_additive_binding_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, materialization_root, rebindings, output_set_sha256 = _write_fake_workspace(
        tmp_path
    )
    monkeypatch.setattr(
        portability,
        "ORIGINAL_OUTPUT_SET_SHA256",
        output_set_sha256,
    )
    with pytest.raises(portability.PortabilityVerificationError) as caught:
        portability.verify_workspace_materialization_read_only(
            materialization_root,
            repository_root=materialization_root.parents[1],
            hash_rebindings=rebindings[1:],
        )
    assert caught.value.status == portability.PACKAGING_PORTABILITY_WORKSPACE_MISMATCH


def test_cli_emits_machine_readable_result() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--repository-root",
            str(ROOT),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    if _focus1_checkpoint_object_exists():
        assert completed.returncode == 0, completed.stderr
        assert payload["status"] == portability.PACKAGING_PORTABILITY_VERIFIED
        assert payload["ok"] is True
    else:
        assert completed.returncode == 1, completed.stderr
        assert payload["status"] == portability.FOCUS1_AUTHORITY_CHECKPOINT_MISSING
        assert payload["ok"] is False


def _append_rebinding(
    record_path: Path,
    repository_root: Path,
    path: str,
    *,
    category: str = "PORTABILITY_VERIFIER_TESTS",
) -> None:
    target = repository_root.joinpath(*path.split("/"))
    wildcard = any(character in path for character in "*?[]")
    if not target.exists() and not wildcard:
        _write(repository_root, path, b"synthetic additional authority target\n")

    def mutate(record: dict[str, object]) -> None:
        bindings = record["hash_rebindings"]
        assert isinstance(bindings, list)
        bindings.append(
            {
                "prior_path": None,
                "prior_sha256": "NEW_FILE",
                "new_path": path,
                "new_sha256": "0" * 64 if wildcard else _sha(target),
                "amendment_id": portability.INTEGRITY_AMENDMENT_ID,
                "change_category": category,
                "reason": "Synthetic unauthorized authority entry.",
                "scientific_impact": "NONE",
                "result_impact": "NONE",
            }
        )

    _rewrite_record(record_path, mutate)


def test_exact_closed_rebinding_set_rejects_extra_and_missing(
    tmp_path: Path,
) -> None:
    repository_root, record_path = _write_synthetic_repository(tmp_path)
    _append_rebinding(record_path, repository_root, "tests/research/unapproved.py")
    result = portability.verify_packaging_portability(repository_root)
    assert result.status == portability.PACKAGING_REBINDING_EXTRA_AUTHORITY_ENTRY

    repository_root, record_path = _write_synthetic_repository(tmp_path / "missing")

    def remove(record: dict[str, object]) -> None:
        record["hash_rebindings"] = record["hash_rebindings"][1:]

    _rewrite_record(record_path, remove)
    result = portability.verify_packaging_portability(repository_root)
    assert result.status == portability.PACKAGING_PORTABILITY_INCOMPLETE


def test_duplicate_alias_wildcard_and_unknown_category_fail_closed(
    tmp_path: Path,
) -> None:
    repository_root, record_path = _write_synthetic_repository(tmp_path)

    def duplicate(record: dict[str, object]) -> None:
        record["hash_rebindings"].append(dict(record["hash_rebindings"][0]))

    _rewrite_record(record_path, duplicate)
    result = portability.verify_packaging_portability(repository_root)
    assert not result.ok

    repository_root, record_path = _write_synthetic_repository(tmp_path / "alias")
    _append_rebinding(record_path, repository_root, "PyProject.toml")
    result = portability.verify_packaging_portability(repository_root)
    assert result.status == portability.AUTHORITY_PATH_ALIAS_REJECTED

    repository_root, record_path = _write_synthetic_repository(tmp_path / "wildcard")
    _append_rebinding(record_path, repository_root, "tests/research/*.py")
    result = portability.verify_packaging_portability(repository_root)
    assert result.status == portability.PACKAGING_REBINDING_EXTRA_AUTHORITY_ENTRY

    repository_root, record_path = _write_synthetic_repository(tmp_path / "category")

    def category(record: dict[str, object]) -> None:
        record["hash_rebindings"][0]["change_category"] = "UNKNOWN_CATEGORY"

    _rewrite_record(record_path, category)
    result = portability.verify_packaging_portability(repository_root)
    assert result.status == portability.PACKAGING_PORTABILITY_POLICY_MISMATCH


def test_scientific_rebinding_and_mutable_self_agreement_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root, record_path = _write_synthetic_repository(tmp_path)
    scientific = "configs/research/false_promotion_benchmark_v1.yaml"
    _append_rebinding(record_path, repository_root, scientific)
    result = portability.verify_packaging_portability(repository_root)
    assert result.status == portability.PACKAGING_REBINDING_UNAUTHORIZED_PATH

    repository_root, record_path = _write_synthetic_repository(tmp_path / "self")
    target = repository_root / "pyproject.toml"
    target.write_text("[project]\nname='altered-authority-and-file'\n", encoding="utf-8")

    def mutate(record: dict[str, object]) -> None:
        for entry in record["hash_rebindings"]:
            if entry["new_path"] == "pyproject.toml":
                entry["new_sha256"] = _sha(target)

    _rewrite_record(record_path, mutate)
    monkeypatch.setattr(
        portability,
        "AUTHORIZED_REPLACEMENT_SHA256",
        {
            "pyproject.toml": (
                "30e47dc1ae5f43011ad79293120b01f1d68fa325ddadaedfea1f3c8d2822ab35"
            )
        },
    )
    result = portability.verify_packaging_portability(repository_root)
    assert result.status == portability.PACKAGING_PORTABILITY_HASH_MISMATCH


def test_rebinding_prior_authority_and_amendment_id_are_exact(tmp_path: Path) -> None:
    repository_root, record_path = _write_synthetic_repository(tmp_path)

    def mutate(record: dict[str, object]) -> None:
        for entry in record["hash_rebindings"]:
            if entry["new_path"] == "pyproject.toml":
                entry["prior_sha256"] = "0" * 64

    _rewrite_record(record_path, mutate)
    result = portability.verify_packaging_portability(repository_root)
    assert result.status == portability.PACKAGING_PORTABILITY_HASH_MISMATCH

    repository_root, record_path = _write_synthetic_repository(tmp_path / "id")

    def wrong_id(record: dict[str, object]) -> None:
        record["hash_rebindings"][0]["amendment_id"] = "UNAUTHORIZED"

    _rewrite_record(record_path, wrong_id)
    result = portability.verify_packaging_portability(repository_root)
    assert result.status == portability.PACKAGING_PORTABILITY_POLICY_MISMATCH


def test_new_file_identity_integrity_boundary_and_record_path_are_exact(
    tmp_path: Path,
) -> None:
    repository_root, record_path = _write_synthetic_repository(tmp_path)

    def malformed_new(record: dict[str, object]) -> None:
        for entry in record["hash_rebindings"]:
            if entry["prior_path"] is None:
                entry["prior_sha256"] = None
                break

    _rewrite_record(record_path, malformed_new)
    result = portability.verify_packaging_portability(repository_root)
    assert result.status == portability.PACKAGING_PORTABILITY_INCOMPLETE

    repository_root, record_path = _write_synthetic_repository(tmp_path / "trust")
    integrity_path = repository_root.joinpath(
        *portability.INTEGRITY_RECORD_PATH.split("/")
    )
    integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
    integrity["trust_boundary"]["verifier_self_attestation"] = True
    integrity_path.write_text(json.dumps(integrity), encoding="utf-8")
    result = portability.verify_packaging_portability(repository_root)
    assert result.status == portability.PACKAGING_PORTABILITY_POLICY_MISMATCH

    repository_root, record_path = _write_synthetic_repository(tmp_path / "alias")
    alternate = _write(
        repository_root,
        "configs/research/alternate_portability_record.json",
        record_path.read_bytes(),
    )
    result = portability.verify_packaging_portability(
        repository_root,
        record_path=alternate.relative_to(repository_root).as_posix(),
    )
    assert result.status == portability.AUTHORITY_PATH_ALIAS_REJECTED


def _create_focus1_checkpoint_repository(tmp_path: Path) -> tuple[Path, str]:
    repository_root = tmp_path / "focus1-checkpoint"
    repository_root.mkdir()
    generator_path = "scripts/generate_benchmark_freeze_manifest.py"
    generator = subprocess.run(
        [
            "git",
            "cat-file",
            "blob",
            f"{portability.FOCUS1_CHECKPOINT_COMMIT}:{generator_path}",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    frozen_paths = portability._checkpoint_frozen_paths(generator)
    for path in frozen_paths:
        raw = subprocess.run(
            [
                "git",
                "cat-file",
                "blob",
                f"{portability.FOCUS1_CHECKPOINT_COMMIT}:{path}",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        _write(repository_root, path, raw)
    subprocess.run(["git", "init", "-q"], cwd=repository_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "focus1@example.invalid"],
        cwd=repository_root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Focus1 Authority Test"],
        cwd=repository_root,
        check=True,
    )
    subprocess.run(["git", "add", "--all"], cwd=repository_root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "accepted checkpoint bytes"],
        cwd=repository_root,
        check=True,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repository_root, commit


def test_real_checkpoint_blobs_reproduce_accepted_focus1_digest() -> None:
    if not _focus1_checkpoint_object_exists():
        pytest.skip(
            "strict raw-checkpoint verification requires a full-history checkout; "
            "portable accepted-inventory verification remains mandatory"
        )
    authority = portability.verify_historical_focus1_authority(ROOT)
    assert authority["status"] == portability.HISTORICAL_FOCUS1_AUTHORITY_VERIFIED
    assert authority["expected_digest"] == portability.FOCUS1_DIGEST
    assert authority["observed_digest"] == portability.FOCUS1_DIGEST
    assert authority["frozen_path_count"] == 36


def test_portable_focus1_authority_does_not_require_checkpoint_object(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    repository_root = _copy_portable_focus1_tree(tmp_path)

    def forbidden_git_blob(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("portable authority must not access checkpoint Git blobs")

    monkeypatch.setattr(portability, "_git_blob", forbidden_git_blob)
    authority = portability.verify_focus1_portable_authority(repository_root)
    assert authority["status"] == portability.FOCUS1_AUTHORITY_VERIFIED
    assert authority["authority_source"] == "CHECKPOINT_DERIVED_ACCEPTED_INVENTORY"
    assert authority["observed_digest"] == portability.FOCUS1_DIGEST


def _copy_portable_focus1_tree(tmp_path: Path) -> Path:
    repository_root = tmp_path / "portable-focus1"
    for relative_path in portability.FOCUS1_CHECKPOINT_INPUT_SHA256:
        destination = repository_root.joinpath(*relative_path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            portability._git_blob(
                ROOT, portability.IMMUTABLE_OWNER_REVIEW_COMMIT, relative_path
            )
        )
    return repository_root


def test_portable_focus1_inventory_tamper_fails_digest_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tampered_inventory = dict(portability.FOCUS1_CHECKPOINT_INPUT_SHA256)
    first_path = next(iter(tampered_inventory))
    tampered_inventory[first_path] = "0" * 64
    monkeypatch.setattr(
        portability,
        "FOCUS1_CHECKPOINT_INPUT_SHA256",
        tampered_inventory,
    )
    with pytest.raises(portability.PortabilityVerificationError) as caught:
        portability.verify_focus1_portable_authority(ROOT)
    assert caught.value.status == portability.FOCUS1_AUTHORITY_DIGEST_MISMATCH


def test_portable_focus1_candidate_tamper_fails_blob_authority(
    tmp_path: Path,
) -> None:
    repository_root = _copy_portable_focus1_tree(tmp_path)
    relative_path = next(iter(portability.FOCUS1_CHECKPOINT_INPUT_SHA256))
    target = repository_root.joinpath(*relative_path.split("/"))
    target.write_bytes(target.read_bytes() + b"tampered")
    with pytest.raises(portability.PortabilityVerificationError) as caught:
        portability.verify_focus1_portable_authority(repository_root)
    assert caught.value.status == portability.FOCUS1_AUTHORITY_BLOB_MISMATCH


def test_portable_focus1_missing_path_fails_path_set_authority(
    tmp_path: Path,
) -> None:
    repository_root = _copy_portable_focus1_tree(tmp_path)
    relative_path = next(iter(portability.FOCUS1_CHECKPOINT_INPUT_SHA256))
    repository_root.joinpath(*relative_path.split("/")).unlink()
    with pytest.raises(portability.PortabilityVerificationError) as caught:
        portability.verify_focus1_portable_authority(repository_root)
    assert caught.value.status == portability.FOCUS1_AUTHORITY_PATH_SET_MISMATCH


def test_focus1_tamper_missing_and_extra_paths_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root, checkpoint = _create_focus1_checkpoint_repository(tmp_path)
    monkeypatch.setattr(portability, "FOCUS1_CHECKPOINT_COMMIT", checkpoint)
    target = repository_root / "docs/research/false_promotion_benchmark_protocol.md"
    target.write_bytes(target.read_bytes() + b"tampered")
    subprocess.run(["git", "add", "--all"], cwd=repository_root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "tampered candidate commit"],
        cwd=repository_root,
        check=True,
    )
    with pytest.raises(portability.PortabilityVerificationError) as caught:
        REAL_FOCUS1_VERIFIER(repository_root)
    assert (
        caught.value.status
        == portability.FOCUS1_AUTHORITY_CANDIDATE_BLOB_MISMATCH
    )

    subprocess.run(
        ["git", "switch", "--detach", checkpoint],
        cwd=repository_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "rm", "-q", "--", str(target.relative_to(repository_root))],
        cwd=repository_root,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "missing candidate path"],
        cwd=repository_root,
        check=True,
    )
    with pytest.raises(portability.PortabilityVerificationError) as caught:
        REAL_FOCUS1_VERIFIER(repository_root)
    assert (
        caught.value.status
        == portability.FOCUS1_AUTHORITY_CANDIDATE_PATH_SET_MISMATCH
    )

    subprocess.run(
        ["git", "switch", "--detach", checkpoint],
        cwd=repository_root,
        check=True,
        capture_output=True,
    )
    generator = subprocess.run(
        ["git", "show", f"{checkpoint}:scripts/generate_benchmark_freeze_manifest.py"],
        cwd=repository_root,
        check=True,
        capture_output=True,
    ).stdout
    frozen_paths = portability._checkpoint_frozen_paths(generator)
    with pytest.raises(portability.PortabilityVerificationError) as caught:
        REAL_FOCUS1_VERIFIER(
            repository_root,
            observed_paths=(*frozen_paths, "extra/focus1.py"),
        )
    assert (
        caught.value.status
        == portability.FOCUS1_AUTHORITY_CANDIDATE_PATH_SET_MISMATCH
    )


def test_focus1_manifest_or_accepted_digest_tampering_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root, checkpoint = _create_focus1_checkpoint_repository(tmp_path)
    monkeypatch.setattr(portability, "FOCUS1_CHECKPOINT_COMMIT", checkpoint)
    monkeypatch.setattr(portability, "FOCUS1_DIGEST", "0" * 64)
    with pytest.raises(portability.PortabilityVerificationError) as caught:
        REAL_FOCUS1_VERIFIER(repository_root)
    assert (
        caught.value.status
        == portability.FOCUS1_AUTHORITY_CHECKPOINT_DIGEST_MISMATCH
    )


def test_focus1_expected_bytes_ignore_git_filters_and_worktree_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root, checkpoint = _create_focus1_checkpoint_repository(tmp_path)
    monkeypatch.setattr(portability, "FOCUS1_CHECKPOINT_COMMIT", checkpoint)
    subprocess.run(
        ["git", "config", "core.autocrlf", "true"],
        cwd=repository_root,
        check=True,
    )
    authority = REAL_FOCUS1_VERIFIER(repository_root)
    assert authority["observed_digest"] == portability.FOCUS1_DIGEST


def test_authority_path_syntax_and_reparse_classification() -> None:
    for value in ("../authority.json", "/authority.json", "C:/authority.json", "//server/share/a.json"):
        with pytest.raises(portability.PortabilityVerificationError):
            portability._canonical_relative_path(value, "authority")
    fake_mount = type(
        "FakeStat",
        (),
        {
            "st_mode": stat.S_IFDIR,
            "st_file_attributes": portability._REPARSE_POINT_ATTRIBUTE,
            "st_reparse_tag": portability._IO_REPARSE_TAG_MOUNT_POINT,
        },
    )()
    fake_other = type(
        "FakeStat",
        (),
        {
            "st_mode": stat.S_IFREG,
            "st_file_attributes": portability._REPARSE_POINT_ATTRIBUTE,
            "st_reparse_tag": 1,
        },
    )()
    assert portability._link_or_reparse_status(fake_mount) == portability.AUTHORITY_PATH_JUNCTION_REJECTED
    assert portability._link_or_reparse_status(fake_other) == portability.AUTHORITY_PATH_REPARSE_POINT_REJECTED


def _make_symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"platform denied synthetic symlink creation: {exc}")


@pytest.mark.parametrize(
    "authority_name",
    [
        "ORIGINAL_MATERIALIZATION_INVENTORY.json",
        "confirmation_provenance_amendment_v1.json",
    ],
)
def test_workspace_authority_json_symlink_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authority_name: str,
) -> None:
    repository_root, materialization_root, rebindings, output_set_sha256 = (
        _write_fake_workspace(tmp_path)
    )
    monkeypatch.setattr(portability, "ORIGINAL_OUTPUT_SET_SHA256", output_set_sha256)
    authority = materialization_root.parent / "confirmation_amendment" / authority_name
    outside = tmp_path / f"outside-{authority_name}"
    outside.write_bytes(authority.read_bytes())
    authority.unlink()
    _make_symlink_or_skip(authority, outside)
    with pytest.raises(portability.PortabilityVerificationError) as caught:
        portability.verify_workspace_materialization_read_only(
            materialization_root,
            repository_root=repository_root,
            hash_rebindings=rebindings,
        )
    assert caught.value.status == portability.AUTHORITY_PATH_SYMLINK_REJECTED


def test_repository_root_alias_and_inside_resolving_symlink_are_rejected(
    tmp_path: Path,
) -> None:
    repository_root, _ = _write_synthetic_repository(tmp_path)
    alias = tmp_path / "repository-alias"
    _make_symlink_or_skip(alias, repository_root, directory=True)
    result = portability.verify_packaging_portability(alias)
    assert result.status == portability.AUTHORITY_PATH_SYMLINK_REJECTED


def test_materialization_cannot_be_verified_against_a_different_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_a, _, _, _ = _write_fake_workspace(tmp_path / "a")
    _, materialization_b, rebindings_b, output_hash_b = _write_fake_workspace(
        tmp_path / "b"
    )
    monkeypatch.setattr(portability, "ORIGINAL_OUTPUT_SET_SHA256", output_hash_b)
    with pytest.raises(portability.PortabilityVerificationError) as caught:
        portability.verify_workspace_materialization_read_only(
            materialization_b,
            repository_root=repository_a,
            hash_rebindings=rebindings_b,
        )
    assert caught.value.status == portability.AUTHORITY_PATH_OUTSIDE_REPOSITORY


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_windows_junction_root_alias_is_rejected(tmp_path: Path) -> None:
    repository_root, _ = _write_synthetic_repository(tmp_path)
    alias = tmp_path / "repository-junction"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(alias), str(repository_root)],
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        pytest.skip(f"platform denied synthetic junction creation: {created.stderr}")
    try:
        result = portability.verify_packaging_portability(alias)
        assert result.status == portability.AUTHORITY_PATH_JUNCTION_REJECTED
    finally:
        os.rmdir(alias)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_windows_materialization_and_authority_parent_junctions_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root, materialization_root, rebindings, output_hash = (
        _write_fake_workspace(tmp_path)
    )
    monkeypatch.setattr(portability, "ORIGINAL_OUTPUT_SET_SHA256", output_hash)

    materialization_alias = materialization_root.parent / "confirmation_alias"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(materialization_alias), str(materialization_root)],
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        pytest.skip(f"platform denied synthetic junction creation: {created.stderr}")
    try:
        with pytest.raises(portability.PortabilityVerificationError) as caught:
            portability.verify_workspace_materialization_read_only(
                materialization_alias,
                repository_root=repository_root,
                hash_rebindings=rebindings,
            )
        assert caught.value.status == portability.AUTHORITY_PATH_JUNCTION_REJECTED
    finally:
        os.rmdir(materialization_alias)

    authority_parent = materialization_root.parent / "confirmation_amendment"
    authority_target = materialization_root.parent / "confirmation_amendment_target"
    authority_parent.rename(authority_target)
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(authority_parent), str(authority_target)],
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        authority_target.rename(authority_parent)
        pytest.skip(f"platform denied authority-parent junction creation: {created.stderr}")
    try:
        with pytest.raises(portability.PortabilityVerificationError) as caught:
            portability.verify_workspace_materialization_read_only(
                materialization_root,
                repository_root=repository_root,
                hash_rebindings=rebindings,
            )
        assert caught.value.status == portability.AUTHORITY_PATH_JUNCTION_REJECTED
    finally:
        os.rmdir(authority_parent)


def test_authority_change_during_single_read_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root, record_path = _write_synthetic_repository(tmp_path)
    original = portability._metadata_identity
    calls = 0

    def changed(file_stat: os.stat_result) -> tuple[int, int, int, int]:
        nonlocal calls
        calls += 1
        identity = original(file_stat)
        return (*identity[:-1], identity[-1] + (1 if calls == 4 else 0))

    monkeypatch.setattr(portability, "_metadata_identity", changed)
    with pytest.raises(portability.PortabilityVerificationError) as caught:
        portability._read_repository_file_once(
            repository_root,
            record_path.relative_to(repository_root).as_posix(),
        )
    assert caught.value.status == portability.AUTHORITY_PATH_CHANGED_DURING_READ


def test_verifier_has_no_simulator_full_drand_network_or_generator_dependency() -> None:
    forbidden_import_roots = {
        "requests",
        "urllib",
        "httpx",
        "drand",
        "public_beacon",
    }
    forbidden_calls = {
        "simulate_joint_power",
        "simulate_trial",
        "generate_evidence",
        "run_benchmark",
        "fetch_drand",
        "urlopen",
        "request",
    }
    for path in (MODULE_PATH, SCRIPT_PATH):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add((node.module or "").split(".")[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
        assert imports.isdisjoint(forbidden_import_roots)
        assert calls.isdisjoint(forbidden_calls)
