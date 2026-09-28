from __future__ import annotations

import csv
import copy
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pytest

from ragwarrant.research.fixed_sample_warrant import FOCUS1_FREEZE_DIGEST
from ragwarrant.research.fixed_sample_warrant_v2 import (
    METHOD_ID,
    VARIANT_A_ID,
    VARIANT_D_BONFERRONI_ID,
    VARIANT_D_ID,
)
from ragwarrant.research.focus2_v2_benchmark import (
    FROZEN_FOCUS1_CONFIG_PATH,
    FROZEN_V2_CONFIG_PATH,
    V1_SOURCE_SHA256,
    _diagnostic_retention_reason,
    load_v2_config,
    run_focus2_v2_benchmark,
)
from ragwarrant.research.focus2_v2_reporting import (
    OUTPUT_FILENAMES,
    write_focus2_v2_outputs,
)
from ragwarrant.research.simulator import load_config


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _tracked_hashes() -> dict[str, str]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    return {
        relative.decode("utf-8"): hashlib.sha256(
            (REPOSITORY_ROOT / relative.decode("utf-8")).read_bytes()
        ).hexdigest()
        for relative in tracked
        if relative and (REPOSITORY_ROOT / relative.decode("utf-8")).is_file()
    }


@pytest.fixture(scope="module")
def ci_result() -> dict[str, object]:
    return run_focus2_v2_benchmark(
        load_config(FROZEN_FOCUS1_CONFIG_PATH),
        load_v2_config(FROZEN_V2_CONFIG_PATH),
        profile="CI",
    )


def test_ci_v2_runs_the_frozen_five_variant_matrix(ci_result: dict[str, object]) -> None:
    manifest = ci_result["manifest"]
    assert manifest["trial_count_total"] == 384
    assert manifest["method_trial_row_count_total"] == 1_920
    assert manifest["scenario_method_summary_count"] == 80
    assert len(manifest["executed_method_variants"]) == 5
    variants = {
        item["variant_id"]: item for item in manifest["executed_method_variants"]
    }
    assert variants[VARIANT_A_ID]["method_id"] == "fixed_sample_multi_risk_warrant_v1"
    assert variants[VARIANT_D_ID]["method_id"] == METHOD_ID
    assert variants[VARIANT_D_BONFERRONI_ID]["multiplicity_method"] == "bonferroni"


def test_all_variants_share_one_evidence_trial_hash(ci_result: dict[str, object]) -> None:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in ci_result["trial_summary_sample_rows"]:
        grouped[str(row["evidence_trial_identity"])].append(row)
    assert grouped
    for rows in grouped.values():
        assert len(rows) == 5
        assert len({row["evidence_hash"] for row in rows}) == 1
        assert len({row["seed_fingerprint"] for row in rows}) == 1
        assert {row["variant_id"] for row in rows} == {
            "A_V1_BASELINE",
            "B_IUT_HOEFFDING",
            "C_FLAT_HB",
            "D_V2_COMBINED",
            "D_V2_BONFERRONI_COMPARISON",
        }


def test_v2_research_candidates_are_truth_isolated_and_full_drand_are_absent(
    ci_result: dict[str, object],
) -> None:
    manifest = ci_result["manifest"]
    assert manifest["focus1_benchmark_freeze_digest"] == FOCUS1_FREEZE_DIGEST
    assert manifest["truth_access_method_ids"] == []
    assert manifest["truth_isolated_method_accessed_population_truth"] is False
    assert manifest["research_candidate_method_ids"] == manifest["executed_method_ids"]
    assert manifest["benchmark_control_method_ids"] == []
    assert manifest["same_observed_evidence_object_shared_by_all_variants"] is True
    assert manifest["candidate_families_frozen_before_confirmatory_evidence"] is True
    assert manifest["full_profile_used"] is False
    assert manifest["full_evidence_generated"] is False
    assert manifest["full_results_inspected"] is False
    assert manifest["target_drand_round_selected"] is False


def test_method_summary_preserves_every_required_cell_metric(
    ci_result: dict[str, object],
) -> None:
    required = {
        "trial_count",
        "false_promotion_count",
        "false_promotion_rate",
        "false_promotion_rate_confidence_interval",
        "false_certification_count",
        "false_certification_rate",
        "false_block_count",
        "false_block_rate",
        "correct_promotion_count",
        "correct_promotion_rate",
        "correct_no_safe_candidate_block_count",
        "correct_no_safe_candidate_block_rate",
        "inconclusive_count",
        "inconclusive_rate",
        "mean_certified_set_size",
        "mean_operational_regret_when_safe_selection_occurs",
    }
    rows = ci_result["method_summary_rows"]
    assert len(rows) == 80
    assert all(required <= set(row) for row in rows)
    assert all(int(row["trial_count"]) == 24 for row in rows)


def test_power_diagnostics_record_candidate_iut_and_dominant_risk(
    ci_result: dict[str, object],
) -> None:
    rows = ci_result["power_diagnostics_sample_rows"]
    assert rows
    required = {
        "component_p_values",
        "candidate_iut_p_value",
        "adjusted_candidate_p_value",
        "candidate_rejection_threshold",
        "candidate_status",
        "first_or_dominant_risk_preventing_certification",
        "quality_test_implementation_used",
    }
    assert all(required <= set(row) for row in rows)
    iut_rows = [row for row in rows if row["multiplicity_scope"] == "candidate_iut"]
    assert iut_rows
    assert all(row["adjusted_candidate_p_value"] is not None for row in iut_rows)
    assert all(row["candidate_rejection_threshold"] is not None for row in iut_rows)


def test_false_event_diagnostics_survive_the_bounded_routine_sample() -> None:
    assert _diagnostic_retention_reason(1, 2, {}) == "bounded_routine_sample"
    assert _diagnostic_retention_reason(
        9, 2, {"false_promotion": 1, "false_certification": 0}
    ) == "false_promotion_or_certification_event"
    assert _diagnostic_retention_reason(
        9, 2, {"false_promotion": 0, "false_certification": 1}
    ) == "false_promotion_or_certification_event"
    assert _diagnostic_retention_reason(9, 2, {}) is None


def test_bottleneck_summary_is_per_scenario_candidate_and_risk(
    ci_result: dict[str, object],
) -> None:
    rows = ci_result["risk_bottleneck_summary_rows"]
    assert rows
    assert all(int(row["trial_count"]) == 24 for row in rows)
    assert all(0.0 <= float(row["component_pass_rate"]) <= 1.0 for row in rows)
    assert all(
        0.0 <= float(row["dominant_bottleneck_rate_when_not_certified"]) <= 1.0
        for row in rows
    )


def test_holm_weakly_dominates_bonferroni_on_identical_candidate_p_values(
    ci_result: dict[str, object],
) -> None:
    indexed = {
        (row["scenario_id"], row["variant_id"]): row
        for row in ci_result["method_summary_rows"]
    }
    scenario_ids = {row["scenario_id"] for row in ci_result["method_summary_rows"]}
    for scenario_id in scenario_ids:
        holm = indexed[(scenario_id, VARIANT_D_ID)]
        bonferroni = indexed[(scenario_id, VARIANT_D_BONFERRONI_ID)]
        assert float(holm["mean_certified_set_size"]) >= float(
            bonferroni["mean_certified_set_size"]
        )
        assert float(holm["false_block_rate"]) <= float(
            bonferroni["false_block_rate"]
        )


def test_full_and_unknown_profiles_fail_before_evidence_generation() -> None:
    config = load_config(FROZEN_FOCUS1_CONFIG_PATH)
    v2_config = load_v2_config(FROZEN_V2_CONFIG_PATH)
    with pytest.raises(ValueError, match="FULL is prohibited"):
        run_focus2_v2_benchmark(config, v2_config, profile="FULL")
    with pytest.raises(ValueError, match="unknown"):
        run_focus2_v2_benchmark(config, v2_config, profile="AFTER_LOOKING")


def test_variant_family_manipulation_fails_closed() -> None:
    config = load_config(FROZEN_FOCUS1_CONFIG_PATH)
    v2_config = load_v2_config(FROZEN_V2_CONFIG_PATH)
    v2_config["variants"] = list(v2_config["variants"])[1:]
    with pytest.raises(ValueError, match="prespecified ablation"):
        run_focus2_v2_benchmark(config, v2_config, profile="CI")


def test_output_package_is_complete_local_and_contains_no_private_paths(
    ci_result: dict[str, object], tmp_path: Path
) -> None:
    output = tmp_path / "focus2-v2-ci"
    written = write_focus2_v2_outputs(ci_result, output)
    assert {path.name for path in written} == set(OUTPUT_FILENAMES)
    manifest = json.loads((output / "benchmark_manifest.json").read_text("utf-8"))
    assert manifest["complete"] is True
    assert set(manifest["output_integrity"]) == set(OUTPUT_FILENAMES[1:])
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert "C:\\Users\\" not in text
        assert "FULL_MASTER_SEED" not in text
        assert '"deployable": true' not in text.lower()


def test_output_method_summary_is_not_heterogeneously_aggregated(
    ci_result: dict[str, object], tmp_path: Path
) -> None:
    output = tmp_path / "focus2-v2-ci"
    write_focus2_v2_outputs(ci_result, output)
    with (output / "method_summary.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 80
    assert len({(row["scenario_id"], row["variant_id"]) for row in rows}) == 80


def test_output_rejects_mislabeled_warrant_sample(
    ci_result: dict[str, object], tmp_path: Path
) -> None:
    tampered = copy.deepcopy(ci_result)
    samples = tampered["warrant_samples"]
    samples[VARIANT_D_ID]["method_id"] = "fixed_sample_multi_risk_warrant_v1"
    with pytest.raises(ValueError, match="invalid method_id"):
        write_focus2_v2_outputs(tampered, tmp_path / "tampered-warrant-sample")


def test_v1_baseline_and_historical_outputs_remain_untouched() -> None:
    source = REPOSITORY_ROOT / "src/ragwarrant/research/fixed_sample_warrant.py"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == V1_SOURCE_SHA256


def test_real_v2_cli_runs_from_tracked_inputs_without_tags_or_local_materialization(
    tmp_path: Path,
) -> None:
    output = tmp_path / "focus2-v2-cli"
    before = _tracked_hashes()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str((REPOSITORY_ROOT / "src").resolve())
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_fixed_sample_warrant_v2_benchmark.py",
            "--profile",
            "CI",
            "--output",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["status"] == "focus2_v2_developmental_benchmark_complete"
    manifest = json.loads((output / "benchmark_manifest.json").read_text("utf-8"))
    contracts = manifest["developmental_contracts"]
    assert contracts["focus1"]["status"] == "DEVELOPMENTAL_TRACKED_CONTRACT_VERIFIED"
    assert contracts["v1"]["status"] == "DEVELOPMENTAL_TRACKED_CONTRACT_VERIFIED"
    assert contracts["v1"]["remote_tag_required"] is False
    assert manifest["full_profile_used"] is False
    assert manifest["target_drand_round_selected"] is False
    public_text = "\n".join(
        path.read_text("utf-8") for path in output.iterdir() if path.is_file()
    ).lower()
    assert '"deployable": true' not in public_text
    assert "deployable," not in public_text
    assert _tracked_hashes() == before
