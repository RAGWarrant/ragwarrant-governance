from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from ragwarrant.experiments.runner import run_suite
from ragwarrant.validation_phase3 import (
    dataset_matrix_v2_result,
    dataset_matrix_v2_rows,
    platform_workflow_rows,
)


def _config(tmp_path: Path, suite: str) -> Path:
    path = tmp_path / f"{suite}.yaml"
    path.write_text(yaml.safe_dump({"suite": suite, "seed": 20260808}), encoding="utf-8")
    return path


def test_ragbench_acquisition_requires_revision_pin() -> None:
    ragbench = next(row for row in dataset_matrix_v2_rows() if row["dataset_id"] == "ragbench")
    assert ragbench["revision"]
    assert ragbench["license_identifier"] == "cc-by-4.0"


def test_crag_requires_manual_approval() -> None:
    crag = next(row for row in dataset_matrix_v2_rows() if row["dataset_id"] == "crag")
    assert crag["acquisition_approved"] is False
    assert crag["acquisition_status"] == "blocked_manual_approval_required"


def test_lit_ragbench_generator_eval_only_classification() -> None:
    lit = next(row for row in dataset_matrix_v2_rows() if row["dataset_id"] == "lit_ragbench")
    assert lit["generator_eval_supported"] is True
    assert lit["end_to_end_corpus_backed_eligible"] is False


def test_replay_only_dataset_not_marked_end_to_end() -> None:
    ragbench = next(row for row in dataset_matrix_v2_rows() if row["dataset_id"] == "ragbench")
    assert ragbench["replay_or_context_eval_only"] is True
    assert ragbench["end_to_end_corpus_backed_eligible"] is False


def test_dataset_matrix_ready_eval_only() -> None:
    assert dataset_matrix_v2_result(dataset_matrix_v2_rows()) == "DATASETS_READY_EVAL_ONLY"


def test_dataset_capability_matrix_created(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_dataset_acquisition_matrix_v2")
    result = run_suite(suite="ragwarrant_dataset_acquisition_matrix_v2", config_path=cfg, output_dir=tmp_path, run_id="data")
    assert result["status"] == "DATASETS_READY_EVAL_ONLY"
    assert (Path(result["run_dir"]) / "dataset_capability_matrix_v2.json").exists()


def test_seen_examples_excluded(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_dataset_acquisition_matrix_v2")
    result = run_suite(suite="ragwarrant_dataset_acquisition_matrix_v2", config_path=cfg, output_dir=tmp_path, run_id="data")
    report = Path(result["run_dir"]) / "freshness_overlap_report.json"
    assert report.exists()
    assert "seen_examples_excluded" in report.read_text(encoding="utf-8")


def test_selection_regret_parent_classification_preserved(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_selection_regret_audit_v2")
    result = run_suite(suite="ragwarrant_selection_regret_audit_v2", config_path=cfg, output_dir=tmp_path, run_id="regret")
    assert result["classification_by_corpus"]["multihop_rag"] == "SELECTION_CORRECT_HELDOUT_REVERSAL"


def test_selection_regret_cross_corpus_reported(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_selection_regret_audit_v2")
    result = run_suite(suite="ragwarrant_selection_regret_audit_v2", config_path=cfg, output_dir=tmp_path, run_id="regret")
    assert (Path(result["run_dir"]) / "selection_regret_cross_corpus_report.md").exists()


def test_natural_case_label_required(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_natural_governance_superiority_v1")
    result = run_suite(suite="ragwarrant_natural_governance_superiority_v1", config_path=cfg, output_dir=tmp_path, run_id="natural")
    assert result["natural_cases_found"] == 0
    assert result["diagnostic_cases_found"] > 0


def test_synthetic_case_not_counted_as_natural_superiority(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_natural_governance_superiority_v1")
    result = run_suite(suite="ragwarrant_natural_governance_superiority_v1", config_path=cfg, output_dir=tmp_path, run_id="natural")
    assert result["result"] == "GOVERNANCE_INCONCLUSIVE_NO_NATURAL_DIVERGENCE"


def test_multi_corpus_requires_additional_corpus(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_multi_corpus_validation_v2")
    result = run_suite(suite="ragwarrant_multi_corpus_validation_v2", config_path=cfg, output_dir=tmp_path, run_id="multi")
    assert result["result"] == "BLOCKED_NO_ADDITIONAL_CORPUS"


def test_dataset_balanced_analysis_reported(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_multi_corpus_validation_v2")
    result = run_suite(suite="ragwarrant_multi_corpus_validation_v2", config_path=cfg, output_dir=tmp_path, run_id="multi")
    assert (Path(result["run_dir"]) / "dataset_balanced_analysis.json").exists()


def test_generator_skipped_classification_v2(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_generative_llm_validation_v1")
    result = run_suite(suite="ragwarrant_generative_llm_validation_v1", config_path=cfg, output_dir=tmp_path, run_id="gen")
    assert result["status"] == "GENERATOR_REGIME_SKIPPED_NO_MODEL"


def test_prompt_hash_recorded_or_skipped_reason(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_generative_llm_validation_v1")
    result = run_suite(suite="ragwarrant_generative_llm_validation_v1", config_path=cfg, output_dir=tmp_path, run_id="gen")
    text = (Path(result["run_dir"]) / "prompt_manifest.json").read_text(encoding="utf-8")
    assert "No generative prompt executed" in text


def test_human_eval_annotations_required_for_complete_status(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_human_eval_validation_v1")
    result = run_suite(suite="ragwarrant_human_eval_validation_v1", config_path=cfg, output_dir=tmp_path, run_id="human")
    assert result["status"] == "HUMAN_EVAL_READY_NOT_RUN"
    assert result["annotation_count"] == 0


def test_human_eval_answer_key_private(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_human_eval_validation_v1")
    result = run_suite(suite="ragwarrant_human_eval_validation_v1", config_path=cfg, output_dir=tmp_path, run_id="human")
    assert (Path(result["run_dir"]) / "human_eval_answer_key_private.json").exists()


def test_official_integration_requires_actual_package_or_api(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_governance_platform_benchmarks_v1")
    result = run_suite(suite="ragwarrant_governance_platform_benchmarks_v1", config_path=cfg, output_dir=tmp_path, run_id="platform")
    assert result["official_integrations_run"] == []


def test_workflow_simulations_labeled_simulation() -> None:
    candidates = pd.DataFrame(
        [
            {"policy_id": "a", "raw_quality": 0.8, "confirmatory_utility": 0.7},
            {"policy_id": "b", "raw_quality": 0.9, "confirmatory_utility": 0.6},
        ]
    )
    rows = platform_workflow_rows(candidates)
    simulations = [row for row in rows if row["workflow"] != "ragwarrant_governed_selection"]
    assert all(row["label"] == "workflow_baseline_simulation" for row in simulations)


def test_no_external_platform_claim_without_integration(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_governance_platform_benchmarks_v1")
    result = run_suite(suite="ragwarrant_governance_platform_benchmarks_v1", config_path=cfg, output_dir=tmp_path, run_id="platform")
    manifest = (Path(result["run_dir"]) / "governance_platform_benchmarks_manifest.json").read_text(encoding="utf-8")
    assert "WORKFLOW_SIMULATIONS_ONLY" in manifest


def test_ragwarrant_compared_against_all_workflow_baselines(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_governance_platform_benchmarks_v1")
    result = run_suite(suite="ragwarrant_governance_platform_benchmarks_v1", config_path=cfg, output_dir=tmp_path, run_id="platform")
    assert len(result["workflow_simulations_run"]) >= 8
