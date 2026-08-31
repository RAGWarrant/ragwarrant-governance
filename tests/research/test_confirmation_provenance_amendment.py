from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any, Callable

import pytest

from ragwarrant.research import confirmation_provenance_amendment as provenance


ROOT = Path(__file__).resolve().parents[2]
FOCUS1_DIGEST = "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
V1_COMMIT = "bf3b3331b623afbdaed295919b3ac945c10692f6"
WORKSPACE_MATERIALIZATION_ENV = "RAGWARRANT_CONFIRMATION_MATERIALIZATION_ROOT"
FIXTURE_INVENTORY_PATH = "synthetic_confirmation/inventory.json"
FIXTURE_REGISTRY_PATH = (
    "synthetic_confirmation/registry/canonical_materialization_registry_v1.json"
)
ORIGINAL_OUTPUT_HASHES = {
    "candidate_results.csv": "c319641270e8629344211c379d209ba692043d559ec93de064ac1ff5daf68ba6",
    "confirmation_manifest.json": "1280d2ae69c69086ca89501aa80bb453dfb5090f8fcf6e5f963c004aab17f8b8",
    "confirmation_report.md": "0e3eb69e0e88dad8cebab40c9997ae0fbbbc873a801bf48e5960e25f9534663e",
    "cost_results.csv": "01794c07fda2dd314e70db03119c352389b519030a1dfb0ddf264fa884a4acf8",
    "design_results.csv": "61cf7d16ae15d0694a418a2eb6f8bf190c27390f321ddaa8beaa099489dac3fd",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_entry(repository_root: Path, relative_path: str) -> dict[str, Any]:
    path = repository_root.joinpath(*relative_path.split("/"))
    return {
        "path": relative_path,
        "size_bytes": path.stat().st_size,
        "sha256": _sha(path),
    }


def _candidate_csv_bytes(
    *,
    marginal_overrides: dict[str, object] | None = None,
    old_independence: str = "0.123",
    old_union: str = "0.456",
) -> bytes:
    marginal = {
        component: value
        for component, value in zip(
            provenance.REQUIRED_COMPONENT_IDS,
            ("0.8", "0.9", "1", "1", "1", "1", "1", "1"),
            strict=True,
        )
    }
    if marginal_overrides:
        for component, value in marginal_overrides.items():
            if value is None:
                marginal.pop(component, None)
            else:
                marginal[component] = value
    fields = (
        "protocol_id",
        "design_id",
        "core_n",
        "group_quota",
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
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerow(
        {
            "protocol_id": provenance.ORIGINAL_PROTOCOL_ID,
            "design_id": "TEST_DESIGN",
            "core_n": "100",
            "group_quota": "50",
            "dependence_condition": "medium",
            "safe_policy_id": "policy_000",
            "replicates": "100",
            "joint_certification_count": "75",
            "joint_certification_probability": "0.75",
            "joint_certification_wilson_low": "0.65",
            "joint_certification_wilson_high": "0.83",
            "mean_union_bound_lower_bound": old_union,
            "mean_independence_approximation": old_independence,
            "marginal_component_powers": json.dumps(
                marginal, sort_keys=True, separators=(",", ":")
            ),
        }
    )
    return stream.getvalue().encode("utf-8")


def _write_fixture_repository(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    input_bytes = {
        "inputs/protocol.json": b'{"protocol":"test"}\n',
        "inputs/config.yaml": b"profile: test\n",
        "inputs/runner.py": b"# frozen test runner\n",
    }
    for relative, payload in input_bytes.items():
        path = repository_root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    output_root = "outputs/confirmation"
    candidate_path = f"{output_root}/candidate_results.csv"
    candidate = repository_root.joinpath(*candidate_path.split("/"))
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(_candidate_csv_bytes())
    input_entries = [_file_entry(repository_root, name) for name in input_bytes]
    output_entries = [_file_entry(repository_root, candidate_path)]
    output_set_hash = provenance.output_set_digest(output_entries)
    protocol_hash = _sha(repository_root / "inputs/protocol.json")
    config_hash = _sha(repository_root / "inputs/config.yaml")
    runner_hash = _sha(repository_root / "inputs/runner.py")
    repository_identity = (
        "test/repository|v1="
        f"{V1_COMMIT}|focus1={FOCUS1_DIGEST}"
    )
    materialization_digest = provenance.canonical_json_sha256(
        {
            "canonical_repository_root_identity": repository_identity,
            "config_sha256": config_hash,
            "output_set_sha256": output_set_hash,
            "protocol_id": provenance.ORIGINAL_PROTOCOL_ID,
            "protocol_sha256": protocol_hash,
        }
    )
    inventory = {
        "schema_version": "ragwarrant_original_confirmation_materialization_inventory.v1",
        "amendment_id": provenance.AMENDMENT_ID,
        "amendment_type": provenance.AMENDMENT_TYPE,
        "original_protocol_id": provenance.ORIGINAL_PROTOCOL_ID,
        "focus1_digest": FOCUS1_DIGEST,
        "v1_frozen_commit": V1_COMMIT,
        "canonical_repository_root_identity": repository_identity,
        "canonical_protocol_path": "inputs/protocol.json",
        "canonical_config_path": "inputs/config.yaml",
        "canonical_runner_path": "inputs/runner.py",
        "canonical_output_root": output_root,
        "canonical_materialization_id": f"sjpcv1-{materialization_digest}",
        "canonical_materialization_digest": materialization_digest,
        "materialization_scope": provenance.MATERIALIZATION_SCOPE,
        "original_protocol_sha256": protocol_hash,
        "original_configuration_sha256": config_hash,
        "original_runner_sha256": runner_hash,
        "output_set_hash": {
            "algorithm": "test fixture canonical output-set SHA-256",
            "sha256": output_set_hash,
            "file_policy": "EXACT_DECLARED_FILE_SET_NO_EXTRA_FILES",
        },
        "original_inputs": input_entries,
        "original_outputs": output_entries,
    }
    inventory_path = repository_root.joinpath(*FIXTURE_INVENTORY_PATH.split("/"))
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return repository_root, inventory


def _use_synthetic_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep portable registration tests wholly inside their synthetic fixture."""

    monkeypatch.setattr(provenance, "DEFAULT_REGISTRY_PATH", FIXTURE_REGISTRY_PATH)


def _register_synthetic_materialization(
    repository_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> provenance.VerificationResult:
    _use_synthetic_registry(monkeypatch)
    return provenance.register_existing_materialization(
        repository_root,
        inventory_path=FIXTURE_INVENTORY_PATH,
        registry_path=FIXTURE_REGISTRY_PATH,
        enforce_frozen_identity=False,
    )


def _guard_synthetic_materialization(
    repository_root: Path,
    *,
    requested_output_root: str,
    generator: Callable[[], Any] | None,
) -> provenance.VerificationResult:
    return provenance.guard_original_protocol_materialization(
        repository_root,
        protocol_id=provenance.ORIGINAL_PROTOCOL_ID,
        requested_output_root=requested_output_root,
        generator=generator,
        inventory_path=FIXTURE_INVENTORY_PATH,
        registry_path=FIXTURE_REGISTRY_PATH,
        enforce_frozen_identity=False,
    )


def _rewrite_candidate(
    repository_root: Path,
    transform: Callable[[dict[str, str]], None],
) -> None:
    path = repository_root / "outputs/confirmation/candidate_results.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    transform(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_windows_and_posix_separators_normalize_identically() -> None:
    assert provenance.normalize_repository_relative_path("a\\b\\c.json") == "a/b/c.json"
    assert provenance.normalize_repository_relative_path("a/b/c.json") == "a/b/c.json"
    with pytest.raises(provenance.ProvenanceError) as caught:
        provenance.require_canonical_repository_relative_path("a\\b\\c.json")
    assert caught.value.status == provenance.CONFIRMATION_PROVENANCE_PATH_MISMATCH


def test_path_case_comparison_follows_explicit_host_contract() -> None:
    assert provenance.paths_equal_under_host_contract(
        "Folder/File.json", "folder/file.json", case_sensitive=False
    )
    assert not provenance.paths_equal_under_host_contract(
        "Folder/File.json", "folder/file.json", case_sensitive=True
    )
    expected = os.name == "nt"
    assert provenance.paths_equal_under_host_contract(
        "Folder/File.json", "folder/file.json"
    ) is expected


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.json",
        "inside/../outside.json",
        "/absolute.json",
        "C:/absolute.json",
        r"C:\\absolute.json",
        r"\\server\\share\\file.json",
        "file.json:alternate-stream",
        "inside//file.json",
    ],
)
def test_traversal_absolute_and_ads_paths_fail_closed(unsafe_path: str) -> None:
    with pytest.raises(provenance.ProvenanceError) as caught:
        provenance.normalize_repository_relative_path(unsafe_path)
    assert caught.value.status == provenance.CONFIRMATION_PROVENANCE_PATH_MISMATCH


def test_symlink_escape_is_rejected_when_platform_allows_symlink_creation(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    outside = tmp_path / "outside"
    repository_root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = repository_root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"platform forbids test symlink creation: {exc}")
    with pytest.raises(provenance.ProvenanceError) as caught:
        provenance.resolve_repository_path(
            repository_root, "link/secret.txt", must_exist=True
        )
    assert caught.value.status == provenance.CONFIRMATION_PROVENANCE_PATH_MISMATCH


def test_exact_output_set_verifies_and_extra_file_fails_closed(tmp_path: Path) -> None:
    repository_root, inventory = _write_fixture_repository(tmp_path)
    valid = provenance.verify_original_materialization(repository_root, inventory)
    assert valid.ok
    assert valid.status == provenance.CONFIRMATION_PROVENANCE_VERIFIED
    (repository_root / "outputs/confirmation/extra.txt").write_text(
        "unexpected", encoding="utf-8"
    )
    invalid = provenance.verify_original_materialization(repository_root, inventory)
    assert not invalid.ok
    assert invalid.status == provenance.CONFIRMATION_PROVENANCE_INCOMPLETE
    assert invalid.details["extra"] == ["outputs/confirmation/extra.txt"]


def test_missing_original_file_fails_closed(tmp_path: Path) -> None:
    repository_root, inventory = _write_fixture_repository(tmp_path)
    (repository_root / "outputs/confirmation/candidate_results.csv").unlink()
    result = provenance.verify_original_materialization(repository_root, inventory)
    assert not result.ok
    assert result.status == provenance.CONFIRMATION_PROVENANCE_INCOMPLETE


def test_modified_original_bytes_cause_hash_mismatch(tmp_path: Path) -> None:
    repository_root, inventory = _write_fixture_repository(tmp_path)
    path = repository_root / "outputs/confirmation/candidate_results.csv"
    original = path.read_bytes()
    modified = original.replace(b"0.75", b"0.74", 1)
    assert len(modified) == len(original)
    path.write_bytes(modified)
    result = provenance.verify_original_materialization(repository_root, inventory)
    assert not result.ok
    assert result.status == provenance.CONFIRMATION_PROVENANCE_HASH_MISMATCH


def test_canonical_source_entry_cannot_diverge_from_frozen_scalar_hash(
    tmp_path: Path,
) -> None:
    repository_root, inventory = _write_fixture_repository(tmp_path)
    protocol_path = repository_root / "inputs/protocol.json"
    protocol_path.write_bytes(protocol_path.read_bytes() + b" ")
    changed = _file_entry(repository_root, "inputs/protocol.json")
    for index, entry in enumerate(inventory["original_inputs"]):
        if entry["path"] == "inputs/protocol.json":
            inventory["original_inputs"][index] = changed
            break
    result = provenance.verify_original_materialization(repository_root, inventory)
    assert not result.ok
    assert result.status == provenance.CONFIRMATION_PROVENANCE_HASH_MISMATCH
    assert "frozen scalar hash" in result.message


def test_hardlinked_authoritative_output_is_rejected_when_supported(
    tmp_path: Path,
) -> None:
    repository_root, inventory = _write_fixture_repository(tmp_path)
    original = repository_root / "outputs/confirmation/candidate_results.csv"
    hardlink = repository_root / "hardlink-copy.csv"
    try:
        os.link(original, hardlink)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"platform/filesystem forbids hardlink creation: {exc}")
    result = provenance.verify_original_materialization(repository_root, inventory)
    assert not result.ok
    assert result.status == provenance.CONFIRMATION_PROVENANCE_PATH_MISMATCH
    assert "hard-linked" in result.message


def test_registry_is_exclusive_and_future_materialization_refuses_before_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, _ = _write_fixture_repository(tmp_path)
    first = _register_synthetic_materialization(repository_root, monkeypatch)
    assert first.ok
    registry = repository_root.joinpath(*FIXTURE_REGISTRY_PATH.split("/"))
    before = registry.read_bytes()
    second_registration = _register_synthetic_materialization(
        repository_root, monkeypatch
    )
    assert second_registration.ok
    assert registry.read_bytes() == before
    assert {path.name for path in repository_root.iterdir()} == {
        "inputs",
        "outputs",
        "synthetic_confirmation",
    }
    called = False

    def forbidden_generator() -> None:
        nonlocal called
        called = True
        raise AssertionError("evidence generation must be refused")

    refusal = _guard_synthetic_materialization(
        repository_root,
        requested_output_root="outputs/confirmation",
        generator=forbidden_generator,
    )
    assert not refusal.ok
    assert refusal.status == provenance.CONFIRMATION_DUPLICATE_MATERIALIZATION
    assert refusal.details["generator_called"] is False
    assert called is False


def test_registry_host_absolute_path_is_non_authoritative_after_workspace_move(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    first.mkdir()
    repository_root, _ = _write_fixture_repository(first)
    assert _register_synthetic_materialization(repository_root, monkeypatch).ok
    moved_root = tmp_path / "moved" / "repository"
    moved_root.parent.mkdir()
    repository_root.rename(moved_root)
    result = _register_synthetic_materialization(moved_root, monkeypatch)
    assert result.ok, result.as_dict()


def test_missing_or_duplicate_registry_fails_closed_before_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, _ = _write_fixture_repository(tmp_path)
    assert _register_synthetic_materialization(repository_root, monkeypatch).ok
    registry = repository_root.joinpath(*FIXTURE_REGISTRY_PATH.split("/"))
    registry.unlink()
    called = False

    def forbidden_generator() -> None:
        nonlocal called
        called = True

    missing = _guard_synthetic_materialization(
        repository_root,
        requested_output_root="outputs/confirmation",
        generator=forbidden_generator,
    )
    assert not missing.ok
    assert missing.status == provenance.CONFIRMATION_PROVENANCE_INCOMPLETE
    assert called is False
    assert _register_synthetic_materialization(repository_root, monkeypatch).ok
    duplicate = registry.with_name("canonical_materialization_registry_v2.json")
    duplicate.write_bytes(registry.read_bytes())
    duplicate_result = _guard_synthetic_materialization(
        repository_root,
        requested_output_root="outputs/confirmation",
        generator=forbidden_generator,
    )
    assert not duplicate_result.ok
    assert duplicate_result.status == provenance.CONFIRMATION_DUPLICATE_MATERIALIZATION
    assert called is False


@pytest.mark.parametrize(
    "alternate_root",
    ["outputs/alternate", "Outputs/confirmation", r"outputs\confirmation"],
)
def test_alternate_or_aliased_output_root_cannot_bypass_guard(
    tmp_path: Path,
    alternate_root: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, _ = _write_fixture_repository(tmp_path)
    assert _register_synthetic_materialization(repository_root, monkeypatch).ok
    called = False

    def forbidden_generator() -> None:
        nonlocal called
        called = True

    result = _guard_synthetic_materialization(
        repository_root,
        requested_output_root=alternate_root,
        generator=forbidden_generator,
    )
    assert not result.ok
    assert result.status == provenance.CONFIRMATION_PROVENANCE_PATH_MISMATCH
    assert called is False


def test_corrected_decimal_product_and_union_use_aggregate_marginals_only(
    tmp_path: Path,
) -> None:
    repository_root, inventory = _write_fixture_repository(tmp_path)
    rows = provenance.derive_corrected_diagnostics(
        repository_root,
        inventory,
        amendment_implementation_hash="a" * 64,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["component_count"] == len(provenance.REQUIRED_COMPONENT_IDS) == 8
    assert row["independence_joint_pass_point_estimate_from_marginals"] == "0.72"
    assert row["union_bound_joint_pass_lower_point_estimate_from_marginals"] == "0.7"
    assert row["direct_observed_joint_certification_rate"] == "0.75"
    assert row["direct_observed_joint_wilson_low"] == "0.65"
    assert row["direct_observed_joint_wilson_high"] == "0.83"
    assert row["components_share_observations"] is True
    assert "independence approximation" in row["explicit_claim_boundary"]
    assert not any(
        "wilson" in key.lower()
        for key in row
        if key.startswith("independence_") or key.startswith("union_bound_")
    )


def test_deprecated_values_are_never_silently_used_as_corrected_values(
    tmp_path: Path,
) -> None:
    repository_root, inventory = _write_fixture_repository(tmp_path)
    rows = provenance.derive_corrected_diagnostics(
        repository_root,
        inventory,
        amendment_implementation_hash="b" * 64,
    )
    row = rows[0]
    assert row["independence_joint_pass_point_estimate_from_marginals"] != "0.123"
    assert row["union_bound_joint_pass_lower_point_estimate_from_marginals"] != "0.456"
    assert row["direct_observed_joint_certification_rate"] == "0.75"
    mapping = provenance.deprecated_diagnostic_mapping(inventory)
    assert mapping["classification"] == "DEPRECATED_MISLABELED_SECONDARY_DIAGNOSTIC"
    assert mapping["primary_conclusion_depended_on_columns"] is False
    assert {item["original_column_name"] for item in mapping["columns"]} == {
        "mean_independence_approximation",
        "mean_union_bound_lower_bound",
    }


def test_missing_mandatory_component_is_explicitly_unavailable(
    tmp_path: Path,
) -> None:
    repository_root, inventory = _write_fixture_repository(tmp_path)
    missing = provenance.REQUIRED_COMPONENT_IDS[0]

    def remove_component(row: dict[str, str]) -> None:
        marginal = json.loads(row["marginal_component_powers"])
        marginal.pop(missing)
        row["marginal_component_powers"] = json.dumps(marginal, sort_keys=True)

    _rewrite_candidate(repository_root, remove_component)
    rows = provenance.derive_corrected_diagnostics(
        repository_root,
        inventory,
        amendment_implementation_hash="c" * 64,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["derivation_status"] == "UNAVAILABLE_MISSING_MANDATORY_COMPONENTS"
    assert row["missing_component_identifiers"] == [missing]
    assert row["independence_joint_pass_point_estimate_from_marginals"] is None
    assert row["union_bound_joint_pass_lower_point_estimate_from_marginals"] is None
    assert row["direct_observed_joint_certification_rate"] == "0.75"


def test_unexpected_component_fails_closed(tmp_path: Path) -> None:
    repository_root, inventory = _write_fixture_repository(tmp_path)

    def add_component(row: dict[str, str]) -> None:
        marginal = json.loads(row["marginal_component_powers"])
        marginal["unexpected_risk::__overall__"] = 1
        row["marginal_component_powers"] = json.dumps(marginal, sort_keys=True)

    _rewrite_candidate(repository_root, add_component)
    with pytest.raises(provenance.ProvenanceError) as caught:
        provenance.derive_corrected_diagnostics(
            repository_root,
            inventory,
            amendment_implementation_hash="d" * 64,
        )
    assert caught.value.status == provenance.CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH
    assert caught.value.details["extra"] == ["unexpected_risk::__overall__"]


@pytest.mark.parametrize(
    ("malformed_marginals", "expected_status"),
    [
        ("{", provenance.CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH),
        ("[]", provenance.CONFIRMATION_PROVENANCE_INCOMPLETE),
        ('"not-a-mapping"', provenance.CONFIRMATION_PROVENANCE_INCOMPLETE),
    ],
)
def test_malformed_marginal_component_input_fails_closed(
    tmp_path: Path,
    malformed_marginals: str,
    expected_status: str,
) -> None:
    repository_root, inventory = _write_fixture_repository(tmp_path)

    def corrupt_marginals(row: dict[str, str]) -> None:
        row["marginal_component_powers"] = malformed_marginals

    _rewrite_candidate(repository_root, corrupt_marginals)
    with pytest.raises(provenance.ProvenanceError) as caught:
        provenance.derive_corrected_diagnostics(
            repository_root,
            inventory,
            amendment_implementation_hash="e" * 64,
        )
    assert caught.value.status == expected_status


def test_module_has_no_simulator_evidence_identity_full_or_drand_dependency() -> None:
    source_path = ROOT / "src/ragwarrant/research/confirmation_provenance_amendment.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)
    assert not any(name.startswith("ragwarrant") for name in imported_modules)
    assert not any(
        name in imported_modules
        for name in ("requests", "urllib", "httpx", "drand", "public_beacon")
    )
    assert called_names.isdisjoint(
        {
            "simulate_joint_power",
            "simulate_trial",
            "generate_evidence",
            "enumerate_confirmation_schedule",
            "derive_confirmation_seed",
            "fetch_drand",
        }
    )


@pytest.mark.workspace_materialization
def test_original_materialization_and_frozen_hashes_verify_read_only() -> None:
    configured_root = os.environ.get(WORKSPACE_MATERIALIZATION_ENV)
    if not configured_root:
        pytest.skip(
            f"{WORKSPACE_MATERIALIZATION_ENV} is not set; skipping read-only "
            "workspace materialization integrity verification"
        )
    materialization_root = Path(configured_root).expanduser()
    if not materialization_root.is_absolute():
        pytest.fail(f"{WORKSPACE_MATERIALIZATION_ENV} must be an absolute path")
    if not materialization_root.is_dir():
        pytest.fail(
            f"{WORKSPACE_MATERIALIZATION_ENV} does not name an existing directory"
        )
    materialization_root = materialization_root.resolve(strict=True)
    if len(materialization_root.parents) < 3:
        pytest.fail(
            f"{WORKSPACE_MATERIALIZATION_ENV} must name the confirmation output "
            "directory inside a repository workspace"
        )
    review_root = materialization_root.parent
    workspace_root = materialization_root.parents[2]
    inventory = provenance.load_original_inventory(
        workspace_root, provenance.DEFAULT_INVENTORY_PATH
    )
    declared_materialization_root = provenance.resolve_repository_path(
        workspace_root,
        inventory["canonical_output_root"],
        must_exist=True,
    )
    if declared_materialization_root != materialization_root:
        pytest.fail(
            f"{WORKSPACE_MATERIALIZATION_ENV} does not match the inventory's "
            "canonical output root"
        )
    before = {
        entry["path"]: _sha(workspace_root.joinpath(*entry["path"].split("/")))
        for entry in inventory["original_outputs"]
    }
    actual_output_paths = {
        path.relative_to(workspace_root).as_posix()
        for path in materialization_root.rglob("*")
        if path.is_file()
    }
    declared_output_paths = {
        entry["path"] for entry in inventory["original_outputs"]
    }
    assert actual_output_paths == declared_output_paths
    actual_output_entries = [
        _file_entry(workspace_root, entry["path"])
        for entry in inventory["original_outputs"]
    ]
    assert actual_output_entries == inventory["original_outputs"]
    assert provenance.output_set_digest(actual_output_entries) == inventory[
        "output_set_hash"
    ]["sha256"]
    assert inventory["focus1_digest"] == FOCUS1_DIGEST
    assert inventory["v1_frozen_commit"] == V1_COMMIT
    assert inventory["output_set_hash"]["sha256"] == (
        "a6ff12e61dc800be65c089cdb7cbe8aca68339a53af08d6ac1bbc95db8a57493"
    )
    assert {Path(path).name: digest for path, digest in before.items()} == ORIGINAL_OUTPUT_HASHES
    focus1 = json.loads(
        (review_root / "FOCUS1_POST_COMMIT_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert focus1["benchmark_freeze_digest"] == FOCUS1_DIGEST
    v1 = json.loads(
        (review_root / "FOCUS2_V1_PRESERVATION_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    assert v1["v1_baseline_commit"] == V1_COMMIT
    for group in ("implementation_sha256", "result_artifact_sha256"):
        for relative_path, expected_hash in v1[group].items():
            assert _sha(workspace_root.joinpath(*relative_path.split("/"))) == expected_hash
    rows = provenance.derive_corrected_diagnostics(
        workspace_root,
        inventory,
        amendment_implementation_hash=_sha(
            workspace_root
            / "src/ragwarrant/research/confirmation_provenance_amendment.py"
        ),
    )
    assert len(rows) == 18
    after = {
        entry["path"]: _sha(workspace_root.joinpath(*entry["path"].split("/")))
        for entry in inventory["original_outputs"]
    }
    assert after == before
