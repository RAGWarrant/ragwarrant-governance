from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from ragwarrant.research.fixed_sample_warrant import (
    HOLM,
    PromotionWarrant,
    RiskTestResult,
    FrozenCandidateFamily,
)
from ragwarrant.research.focus2_reporting import OUTPUT_FILENAMES, write_focus2_outputs
from ragwarrant.research.types import public_research_artifact


def _artifact(procedure: str = HOLM) -> dict[str, object]:
    family = FrozenCandidateFamily(
        candidate_policy_ids=("policy_0001",),
        incumbent_policy_id="benchmark_incumbent_v1",
        enabled_risks=("overall_quality",),
        enabled_group_risks=(),
        group_ids=("group_a",),
        confirmatory_unit_count=64,
        quality_noninferiority_margin=0.02,
        group_quality_noninferiority_margin=0.03,
        binary_thresholds=(),
        quality_delta_bounds=(-0.25, 0.25),
        familywise_error_level=0.05,
        multiplicity_method=procedure,
        selection_objective="minimize_cost",
    )
    test = RiskTestResult(
        hypothesis_id="policy_0001::overall_quality::__overall__",
        policy_id="policy_0001",
        risk_id="overall_quality",
        group_id=None,
        null_hypothesis="mean_quality_delta <= -0.02",
        alternative_hypothesis="mean_quality_delta > -0.02",
        null_boundary=-0.02,
        support_bounds=(-0.25, 0.25),
        sample_count=64,
        observed_statistic=0.1,
        raw_p_value=0.001,
        adjusted_p_value=0.001,
        rejection_threshold=0.05,
        rejected=True,
        failure_reason=None,
    )
    return public_research_artifact(PromotionWarrant(
        decision="PROMOTE",
        decision_reason="fixture certification",
        family=family,
        evidence_hash="0" * 64,
        certified_policy_ids=("policy_0001",),
        selected_policy_id="policy_0001",
        risk_tests=(test,),
        candidate_summaries=(("policy_0001", {"mean_cost": 1.0, "mean_latency": 2.0}),),
    ).as_dict())


def _method_row(procedure: str = HOLM) -> dict[str, object]:
    return {
        "scenario_id": "fixture__n64",
        "base_scenario_id": "fixture",
        "family": "FIXTURE",
        "method_id": "fixed_sample_multi_risk_warrant_v1",
        "multiplicity_method": procedure,
        "observed_evidence_only": True,
        "truth_isolated": True,
        "benchmark_control_only": False,
        "research_only": True,
        "production_integrated": False,
        "trial_count": 1,
        "false_promotion_count": 0,
        "false_promotion_rate": 0.0,
        "false_promotion_rate_confidence_interval": "[0.0,0.7934506856227626]",
        "false_certification_count": 0,
        "false_certification_rate": 0.0,
        "false_block_count": 0,
        "false_block_rate": 0.0,
        "correct_promotion_count": 1,
        "correct_promotion_rate": 1.0,
        "correct_no_safe_candidate_block_count": 0,
        "correct_no_safe_candidate_block_rate": 0.0,
        "no_decision_count": 0,
        "no_decision_rate": 0.0,
        "mean_certified_set_size": 1.0,
        "mean_operational_regret_when_safe_selection_occurs": 0.0,
        "candidate_count": 1,
        "sample_size": 64,
        "enabled_risks": '["overall_quality"]',
        "scenario_truth_summary": "{}",
    }


def _result() -> dict[str, object]:
    return {
        "manifest": {
            "benchmark_id": "fixed_sample_multi_risk_warrant_benchmark_v1",
            "profile": "CI",
            "evidence_role": "developmental",
            "seed_schedule_version": 2,
            "full_profile_used": False,
            "full_evidence_generated": False,
            "full_results_inspected": False,
            "target_drand_round_selected": False,
            "truth_isolated_method_accessed_population_truth": False,
            "same_observed_evidence_object_shared_by_truth_isolated_methods": True,
            "candidate_families_frozen_before_confirmatory_evidence": True,
            "post_hoc_filtered": False,
            "scenario_results_aggregated_into_headline": False,
            "truth_access_method_ids": ["oracle_safe_objective"],
            "focus2_config_hash": (
                "7c7efdaa389c40a2ec17c1fcd63ca99c1c98abd85dc56ad2d105427fa38e7fdc"
            ),
            "focus2_config_file_sha256": (
                "74773244d4267d1a8d72c993234e4aebdc62141d4a155fb972e4ecd6f9279a53"
            ),
            "complete": True,
            "focus1_benchmark_freeze_digest": (
                "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
            ),
        },
        "config_snapshot": {"protocol_version": "false_promotion_benchmark_v1"},
        "focus2_config_snapshot": {"method_id": "fixed_sample_multi_risk_warrant_v1"},
        "scenario_truth_rows": [{"scenario_id": "fixture__n64", "policy_id": "candidate"}],
        "scenario_summary_rows": [{"scenario_id": "fixture__n64", "sample_size": 64}],
        "method_summary_rows": [_method_row(HOLM), _method_row("bonferroni")],
        "trial_summary_sample_rows": [
            {
                "scenario_id": "fixture__n64",
                "method_id": "fixed_sample_multi_risk_warrant_v1",
                "multiplicity_method": HOLM,
                "evidence_hash": "0" * 64,
            }
        ],
        "warrant_artifacts": {"holm": _artifact(HOLM), "bonferroni": _artifact("bonferroni")},
    }


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_writes_complete_atomic_research_local_output_contract(tmp_path: Path) -> None:
    root = tmp_path / "focus2"
    paths = write_focus2_outputs(_result(), root)

    assert {path.name for path in paths} == set(OUTPUT_FILENAMES)
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths)
    manifest = json.loads((root / "benchmark_manifest.json").read_text("utf-8"))
    assert manifest["complete"] is True
    assert manifest["full_profile_used"] is False
    assert manifest["full_evidence_generated"] is False
    assert manifest["target_drand_round_selected"] is False
    assert set(manifest["output_integrity"]) == set(OUTPUT_FILENAMES[1:])
    for name, expected in manifest["output_integrity"].items():
        assert expected == {
            "sha256": _digest(root / name),
            "size_bytes": (root / name).stat().st_size,
        }


def test_artifact_serialization_matches_research_schema() -> None:
    artifact = _artifact()
    schema = json.loads(
        Path("schemas/research/promotion_warrant_v1.schema.json").read_text("utf-8")
    )

    assert set(artifact) == set(schema["required"]) == set(schema["properties"])
    assert artifact["method"] == schema["properties"]["method"]["const"]
    assert artifact["method_id"] == schema["properties"]["method_id"]["const"]
    risk_test = artifact["risk_tests"][0]
    risk_schema = schema["$defs"]["risk_test"]
    assert set(risk_test) == set(risk_schema["required"]) == set(risk_schema["properties"])


def test_schema_requires_a_positive_confirmatory_unit_count() -> None:
    schema = json.loads(
        Path("schemas/research/promotion_warrant_v1.schema.json").read_text("utf-8")
    )
    assert schema["properties"]["confirmatory_unit_count"]["minimum"] == 1


def test_outputs_contain_no_private_paths_or_secret_markers(tmp_path: Path) -> None:
    paths = write_focus2_outputs(_result(), tmp_path / "focus2")
    combined = "\n".join(path.read_text("utf-8") for path in paths)
    assert str(Path.cwd().resolve()) not in combined
    assert str(tmp_path.resolve()) not in combined
    lowered = combined.lower()
    assert "api_key" not in lowered
    assert "authorization: bearer" not in lowered
    assert "drand_target_round" not in lowered
    assert "full_seed" not in lowered
    assert '"deployable": true' not in lowered


def test_writer_does_not_modify_historical_artifacts_or_results(tmp_path: Path) -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "README.md", "artifacts", "results"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    existing = [Path(path) for path in tracked if Path(path).is_file()]
    before = {path: _digest(path) for path in existing}
    write_focus2_outputs(_result(), tmp_path / "focus2")
    assert before == {path: _digest(path) for path in existing}


def test_writer_fails_closed_for_full_or_unrecognized_existing_output(tmp_path: Path) -> None:
    full_result = _result()
    full_result["manifest"]["profile"] = "FULL"
    full_result["manifest"]["evidence_role"] = "confirmatory"
    full_result["manifest"]["full_profile_used"] = True
    with pytest.raises(ValueError, match="CI or LOCAL"):
        write_focus2_outputs(full_result, tmp_path / "full")

    root = tmp_path / "owner-data"
    root.mkdir()
    owner_file = root / "preserve.txt"
    owner_file.write_bytes(b"preserve")
    with pytest.raises(ValueError, match="not an exact prior"):
        write_focus2_outputs(_result(), root)
    assert owner_file.read_bytes() == b"preserve"


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("full_profile_used", True),
        ("full_evidence_generated", True),
        ("full_results_inspected", True),
        ("target_drand_round_selected", True),
        ("truth_isolated_method_accessed_population_truth", True),
        ("candidate_families_frozen_before_confirmatory_evidence", False),
        ("same_observed_evidence_object_shared_by_truth_isolated_methods", False),
        ("post_hoc_filtered", True),
        ("scenario_results_aggregated_into_headline", True),
        ("focus2_config_hash", "0" * 64),
    ],
)
def test_writer_rejects_contradictory_manifest_provenance(
    tmp_path: Path, field: str, invalid: object
) -> None:
    result = _result()
    result["manifest"][field] = invalid

    with pytest.raises(ValueError, match=field):
        write_focus2_outputs(result, tmp_path / field)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("truth_isolated", False),
        ("observed_evidence_only", False),
        ("population_truth_accessed", True),
        ("full_profile_used", True),
        ("benchmark_freeze_digest", "0" * 64),
        ("multiplicity_method", "choose_after_results"),
        ("production_integrated", True),
    ],
)
def test_writer_rejects_invalid_warrant_provenance(
    tmp_path: Path, field: str, invalid: object
) -> None:
    result = copy.deepcopy(_result())
    result["warrant_artifacts"]["holm"][field] = invalid

    with pytest.raises(ValueError, match="promotion warrant"):
        write_focus2_outputs(result, tmp_path / field)


def test_writer_rejects_selected_policy_outside_certified_set(tmp_path: Path) -> None:
    result = copy.deepcopy(_result())
    result["warrant_artifacts"]["holm"]["selected_policy_id"] = "policy_9999"

    with pytest.raises(ValueError, match="selected policy must be certified"):
        write_focus2_outputs(result, tmp_path / "uncertified")
