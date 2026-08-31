from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts.run_joint_power_confirmation import (
    DEFAULT_OUTPUT,
    load_confirmation_config,
    validate_execution_paths,
    verify_protocol_freeze,
)
from ragwarrant.research import joint_power_confirmation as confirmation
from ragwarrant.research.joint_power_confirmation import (
    ConfirmationIdentity,
    derive_confirmation_seed,
    enumerate_confirmation_schedule,
    planning_label,
    run_confirmation_cell,
    schedule_fingerprints,
)
from ragwarrant.research.stratified_joint_power import wilson_interval


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/research/stratified_joint_power_confirmation_v1.yaml"
EXECUTOR = ROOT / "src/ragwarrant/research/joint_power_confirmation.py"
RUNNER = ROOT / "scripts/run_joint_power_confirmation.py"
FOCUSED_TEST = Path(__file__).resolve()
WORKSPACE_MATERIALIZATION_ENV = "RAGWARRANT_CONFIRMATION_MATERIALIZATION_ROOT"
FOCUS1_DIGEST = "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
V1_COMMIT = "bf3b3331b623afbdaed295919b3ac945c10692f6"
ORIGINAL_FOCUSED_TEST_SHA256 = "a76ea9bfac13a433d81b72756dbe7d795f26f911d38c6e19e162f5a2e3f39fab"

PRESERVED_STRATIFIED_HASHES = {
    "configs/research/stratified_joint_warrant_power_v1.yaml": "087cbb7273c4d9869c0011b966cd0614606960046e5c2ba598a1893226a677b2",
    "docs/research/joint_warrant_power_planning.md": "40b681c180bb62b6ad2aa179543006facac5531b5f1ee81b7b2ec2db9fbee222",
    "docs/research/stratified_confirmatory_evidence_v1.md": "f043b8d96ca8223dd7cdee748f0ace80902fa769643ffdee337785686f0478cc",
    "scripts/run_stratified_joint_power_study.py": "8645a369633d86b3407eb2f8d424f2fd7d9e180e76e173c8189578241e2cdb4c",
    "src/ragwarrant/research/stratified_joint_power.py": "9101048d30a5cfc758fca029dc44ce21603d9406f9929ab02859d6f112e72f4d",
    "tests/research/test_stratified_joint_warrant_power.py": "6298e76086f3319083c6e2d8409907aee8158843cdfcacde9d8544d2220c0d19",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _portable_config(tmp_path: Path) -> Path:
    """Create a synthetic config rebinding only this portability-test hash."""

    loaded = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    loaded["frozen_executor"]["focused_tests_sha256"] = _sha(FOCUSED_TEST)
    path = tmp_path / "confirmation-portable-test.yaml"
    path.write_text(yaml.safe_dump(loaded, sort_keys=False), encoding="utf-8")
    return path


def _synthetic_protocol_freeze(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build a minimal test-only freeze without using scientific outputs."""

    protocol_json = tmp_path / "protocol.json"
    protocol_md = tmp_path / "protocol.md"
    protocol_json.write_text(
        json.dumps(
            {
                "protocol_id": confirmation.PROTOCOL_ID,
                "test_only": True,
                "evidence_collected": False,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    protocol_md.write_text(
        "# Synthetic protocol fixture\n\nTest-only; not scientific evidence.\n",
        encoding="utf-8",
    )
    freeze = {
        "schema_version": "ragwarrant_joint_power_confirmation_protocol_freeze.test.v1",
        "protocol_id": confirmation.PROTOCOL_ID,
        "frozen_before_execution": True,
        "protocol_json_sha256": _sha(protocol_json),
        "protocol_markdown_sha256": _sha(protocol_md),
        "tracked_config_sha256": _sha(CONFIG),
        "executor_sha256": _sha(EXECUTOR),
        "runner_sha256": _sha(RUNNER),
        "focused_tests_sha256": _sha(FOCUSED_TEST),
        "confirmation_output_existed_at_freeze": False,
    }
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(freeze, sort_keys=True) + "\n", encoding="utf-8")
    return protocol_json, protocol_md, freeze_path


def _workspace_materialization_root() -> Path:
    raw = os.environ.get(WORKSPACE_MATERIALIZATION_ENV)
    if not raw:
        pytest.skip(
            f"{WORKSPACE_MATERIALIZATION_ENV} is not set; "
            "skipping read-only workspace materialization integrity verification"
        )
    requested = Path(raw).expanduser()
    if not requested.is_absolute():
        pytest.fail(f"{WORKSPACE_MATERIALIZATION_ENV} must be an absolute path")
    if not requested.is_dir():
        pytest.fail(f"{WORKSPACE_MATERIALIZATION_ENV} does not name an existing directory")
    canonical = DEFAULT_OUTPUT.resolve(strict=True)
    resolved = requested.resolve(strict=True)
    if requested != canonical or resolved != canonical:
        pytest.fail(
            f"{WORKSPACE_MATERIALIZATION_ENV} must name the exact canonical "
            "confirmation materialization root without aliases"
        )
    return canonical


def test_confirmation_config_freezes_exact_two_by_three_by_1000_schedule(tmp_path: Path) -> None:
    # The committed config retains its historical test hash. A synthetic copy
    # binds the current portability-test bytes without changing frozen science.
    loaded = load_confirmation_config(_portable_config(tmp_path))
    assert loaded["focus1_digest"] == FOCUS1_DIGEST
    assert loaded["v1_baseline_commit"] == V1_COMMIT
    assert loaded["designs"] == [
        {"id": "COMPONENT_PLANNING_COMPARATOR", "core_n": 1383, "group_quota": 826},
        {"id": "SELECTED_JOINT_PLANNING_CANDIDATE", "core_n": 1720, "group_quota": 1028},
    ]
    assert loaded["dependence_conditions"] == {"low": 0.0, "medium": 0.5, "high": 0.9}
    assert loaded["replicates_per_design_dependence_cell"] == 1000
    assert loaded["total_replicates"] == 6000


def test_confirmation_runner_imports_as_a_standalone_cli() -> None:
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--protocol-freeze" in completed.stdout


def test_config_rejects_added_design_or_resized_schedule(tmp_path: Path) -> None:
    loaded = yaml.safe_load(_portable_config(tmp_path).read_text(encoding="utf-8"))
    loaded["designs"].append({"id": "POST_HOC", "core_n": 2000, "group_quota": 1200})
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(loaded, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="two-design"):
        load_confirmation_config(path)


def test_canonical_identity_and_sha256_seed_are_stable() -> None:
    identity = ConfirmationIdentity(
        "STRATIFIED_JOINT_POWER_CONFIRMATION_V1",
        "COMPONENT_PLANNING_COMPARATOR",
        "medium",
        21,
    )
    assert identity.canonical == (
        "STRATIFIED_JOINT_POWER_CONFIRMATION_V1|"
        "COMPONENT_PLANNING_COMPARATOR|medium|21"
    )
    expected = int.from_bytes(
        hashlib.sha256(
            json.dumps(
                [1554387201, identity.canonical],
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).digest()[:8],
        "big",
    )
    assert derive_confirmation_seed(identity) == expected
    assert derive_confirmation_seed(identity) == derive_confirmation_seed(identity)


def test_confirmation_schedule_is_disjoint_and_collision_free() -> None:
    identities = enumerate_confirmation_schedule()
    canonical = [item.canonical for item in identities]
    seeds = [derive_confirmation_seed(item) for item in identities]
    assert len(identities) == 6000
    assert len(set(canonical)) == 6000
    assert len(set(seeds)) == 6000
    assert all(value.startswith("STRATIFIED_JOINT_POWER_CONFIRMATION_V1|") for value in canonical)
    assert not any("|CI|" in value or "|LOCAL|" in value or "|FULL|" in value for value in canonical)
    assert schedule_fingerprints()["duplicate_seed_count"] == 0


def test_invalid_identity_fields_fail_closed() -> None:
    with pytest.raises(ValueError, match="protocol"):
        ConfirmationIdentity("other", confirmation.DESIGN_IDS[0], "low", 0)
    with pytest.raises(ValueError, match="design"):
        ConfirmationIdentity(confirmation.PROTOCOL_ID, "other", "low", 0)
    with pytest.raises(ValueError, match="dependence"):
        ConfirmationIdentity(confirmation.PROTOCOL_ID, confirmation.DESIGN_IDS[0], "other", 0)
    with pytest.raises(ValueError, match="replicate"):
        ConfirmationIdentity(confirmation.PROTOCOL_ID, confirmation.DESIGN_IDS[0], "low", 1000)


def test_wilson_target_labels_use_lower_bound_not_only_point_estimate() -> None:
    point_only_80 = next(
        count
        for count in range(800, 1001)
        if count / 1000 >= 0.80 and wilson_interval(count, 1000)[0] < 0.80
    )
    supports_80 = next(
        count for count in range(800, 1001) if wilson_interval(count, 1000)[0] >= 0.80
    )
    supports_90 = next(
        count for count in range(900, 1001) if wilson_interval(count, 1000)[0] >= 0.90
    )
    assert planning_label(799, 1000, 0.80) == "PLANNING_TARGET_NOT_SUPPORTED"
    assert planning_label(point_only_80, 1000, 0.80) == "PLANNING_POINT_ESTIMATE_ONLY"
    assert planning_label(supports_80, 1000, 0.80) == "PLANNING_SUPPORTS_80_PERCENT"
    assert planning_label(supports_90, 1000, 0.90) == "PLANNING_SUPPORTS_90_PERCENT"


def test_confirmation_executor_runs_exactly_1000_unique_identity_seeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[int] = []

    def fake_simulate_joint_power(**kwargs):
        received.append(kwargs["master_seed"])
        hit = int(kwargs["master_seed"] % 2 == 0)
        candidates = []
        for policy_id in kwargs["safe_policy_ids"]:
            candidates.append(
                {
                    "policy_id": policy_id,
                    "marginal_component_powers": {"overall_quality::__overall__": hit},
                    "union_bound_joint_lower_bound": float(hit),
                    "independence_approximation": float(hit),
                    "monte_carlo_joint_power": float(hit),
                }
            )
        return {
            "candidate_results": candidates,
            "at_least_one_safe_certification_probability": float(hit),
            "false_certification_probability": 0.0,
            "expected_certified_set_size": float(hit),
            "safe_selection_probability": float(hit),
            "unsafe_selection_probability": 0.0,
            "no_selection_probability": float(1 - hit),
        }

    monkeypatch.setattr(confirmation, "simulate_joint_power", fake_simulate_joint_power)
    row, candidates = run_confirmation_cell(
        design_id="COMPONENT_PLANNING_COMPARATOR",
        family=object(),
        policy=object(),
        core_n=1383,
        group_quotas={"majority": 826, "minority": 826},
        group_prevalence={"majority": 0.9, "minority": 0.1},
        safe_policy_ids=("policy_000", "policy_001", "policy_002"),
        binary_alternatives={
            "safety_violation_probability": 0.025,
            "execution_failure_probability": 0.015,
            "insufficient_evidence_probability": 0.05,
        },
        quality_slack=0.10,
        dependence_condition="low",
    )
    assert len(received) == 1000
    assert len(set(received)) == 1000
    assert row["replicates"] == 1000
    assert len(candidates) == 3
    expected_hits = sum(seed % 2 == 0 for seed in received)
    expected_rate = expected_hits / 1000
    assert row["at_least_one_safe_certification_count"] == expected_hits
    assert row["at_least_one_safe_certification_probability"] == expected_rate
    assert row["mean_certified_set_size"] == expected_rate
    assert row["operational_selection_probability"] == expected_rate
    assert row["safe_selection_probability"] == expected_rate
    assert row["no_selection_probability"] == 1.0 - expected_rate
    assert all(candidate["joint_certification_count"] == expected_hits for candidate in candidates)
    assert all(
        candidate["joint_certification_probability"] == expected_rate
        for candidate in candidates
    )


def test_protocol_freeze_hashes_are_enforced_with_synthetic_fixture(tmp_path: Path) -> None:
    protocol_json, protocol_md, freeze_path = _synthetic_protocol_freeze(tmp_path)
    freeze = verify_protocol_freeze(
        protocol_json,
        protocol_md,
        freeze_path,
        config_path=CONFIG,
        executor_path=EXECUTOR,
        runner_path=RUNNER,
        focused_test_path=FOCUSED_TEST,
    )
    assert freeze["frozen_before_execution"] is True
    assert freeze["confirmation_output_existed_at_freeze"] is False


def test_freeze_rejects_tampered_config_and_alternate_paths(tmp_path: Path) -> None:
    protocol_json, protocol_md, freeze_path = _synthetic_protocol_freeze(tmp_path)
    copied_config = tmp_path / "confirmation.yaml"
    copied_config.write_bytes(CONFIG.read_bytes() + b"\n# tampered\n")
    with pytest.raises(ValueError, match="tracked config hash changed"):
        verify_protocol_freeze(
            protocol_json,
            protocol_md,
            freeze_path,
            config_path=copied_config,
            executor_path=EXECUTOR,
            runner_path=RUNNER,
            focused_test_path=FOCUSED_TEST,
        )
    with pytest.raises(ValueError, match="canonical frozen path"):
        validate_execution_paths(
            copied_config,
            ROOT / "configs/research/stratified_joint_warrant_power_v1.yaml",
        )
    copied_parent = tmp_path / "parent.yaml"
    copied_parent.write_bytes(
        (ROOT / "configs/research/stratified_joint_warrant_power_v1.yaml").read_bytes()
    )
    with pytest.raises(ValueError, match="canonical frozen path"):
        validate_execution_paths(CONFIG, copied_parent)


def test_focus1_v1_and_prior_stratified_tracked_hashes_remain_unchanged() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert config["focus1_digest"] == FOCUS1_DIGEST
    assert config["v1_baseline_commit"] == V1_COMMIT
    assert config["frozen_executor"]["focused_tests_sha256"] == ORIGINAL_FOCUSED_TEST_SHA256
    for relative, expected in PRESERVED_STRATIFIED_HASHES.items():
        assert _sha(ROOT / relative) == expected


def test_operational_template_contains_only_owner_placeholders() -> None:
    text = (ROOT / "docs/research/operational_contract_template.md").read_text(encoding="utf-8")
    assert text.count("OWNER_OR_DEPLOYER_INPUT_REQUIRED") >= 14
    assert "does not freeze operational values" in text
    assert "execution authorization" in text


def test_protocol_config_prohibits_full_drand_workflows_and_evidence() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert config["execution_authorized"] is False
    assert config["evidence_collected"] is False
    assert config["full_executed"] is False
    assert config["drand_round_selected"] is False


@pytest.mark.workspace_materialization
def test_workspace_materialization_preserves_protocol_and_primary_results() -> None:
    materialization_root = _workspace_materialization_root()
    review_root = materialization_root.parent
    protocol_json = review_root / "JOINT_POWER_CONFIRMATION_PROTOCOL.json"
    protocol_md = review_root / "JOINT_POWER_CONFIRMATION_PROTOCOL.md"
    freeze_path = review_root / "JOINT_POWER_CONFIRMATION_PROTOCOL_FREEZE.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))

    assert _sha(protocol_json) == freeze["protocol_json_sha256"]
    assert _sha(protocol_md) == freeze["protocol_markdown_sha256"]
    assert _sha(CONFIG) == freeze["tracked_config_sha256"]
    assert _sha(EXECUTOR) == freeze["executor_sha256"]
    assert _sha(RUNNER) == freeze["runner_sha256"]
    assert freeze["focused_tests_sha256"] == ORIGINAL_FOCUSED_TEST_SHA256
    assert freeze["frozen_before_execution"] is True
    assert freeze["confirmation_output_existed_at_freeze"] is False

    protocol = json.loads(protocol_json.read_text(encoding="utf-8"))
    assert protocol["original_full_executed"] is False
    assert protocol["future_stratified_full_executed"] is False
    assert protocol["drand_round_selected"] is False

    manifest = json.loads(
        (materialization_root / "confirmation_manifest.json").read_text(encoding="utf-8")
    )
    for filename, expected in manifest["result_sha256"].items():
        assert _sha(materialization_root / filename) == expected

    with (materialization_root / "design_results.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    high = {row["design_id"]: row for row in rows if row["dependence_condition"] == "high"}
    comparator = high["COMPONENT_PLANNING_COMPARATOR"]
    selected = high["SELECTED_JOINT_PLANNING_CANDIDATE"]
    assert comparator["at_least_one_safe_certification_count"] == "770"
    assert comparator["at_least_one_safe_certification_probability"] == "0.77"
    assert comparator["at_least_one_safe_wilson_low"] == "0.7429132441380307"
    assert comparator["at_least_one_safe_wilson_high"] == "0.7950203062797695"
    assert selected["at_least_one_safe_certification_count"] == "903"
    assert selected["at_least_one_safe_certification_probability"] == "0.903"
    assert selected["at_least_one_safe_wilson_low"] == "0.8830847944509657"
    assert selected["at_least_one_safe_wilson_high"] == "0.9198308382096769"


@pytest.mark.workspace_materialization
def test_workspace_materialization_preserves_focus1_and_v1_manifests() -> None:
    materialization_root = _workspace_materialization_root()
    review_root = materialization_root.parent
    focus1 = json.loads(
        (review_root / "FOCUS1_POST_COMMIT_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert focus1["benchmark_freeze_digest"] == FOCUS1_DIGEST

    v1 = json.loads(
        (review_root / "FOCUS2_V1_PRESERVATION_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert v1["v1_baseline_commit"] == V1_COMMIT
    for relative, expected in v1["implementation_sha256"].items():
        assert _sha(ROOT / relative) == expected
    for relative, expected in v1["result_artifact_sha256"].items():
        assert _sha(ROOT / relative) == expected
