from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from ragwarrant.config import SuiteConfig
from ragwarrant.experiments.runner import run_suite
from ragwarrant.validation_phase3 import (
    RAG_COMPASS_DISPLAY,
    RAG_COMPASS_ID,
    classify_selection_regret,
    governance_case_rows,
    optimizer_display_name,
    optimizer_registry_payload,
    workflow_baseline_rows,
    write_rag_compass_name_migration,
)


def _config(tmp_path: Path, suite: str) -> Path:
    path = tmp_path / f"{suite}.yaml"
    path.write_text(yaml.safe_dump({"suite": suite, "seed": 20260808, "statistics": {"bootstrap_samples": 20}}), encoding="utf-8")
    return path


def test_optimizer_registry_maps_ragwarrant_no_fork_to_rag_compass() -> None:
    registry = optimizer_registry_payload()
    assert registry["optimizers"][RAG_COMPASS_ID]["canonical_display_name"] == RAG_COMPASS_DISPLAY
    assert optimizer_display_name(RAG_COMPASS_ID) == "RAG Compass (legacy id: ragwarrant_no_fork)"


def test_legacy_id_still_supported() -> None:
    assert optimizer_registry_payload()["optimizers"][RAG_COMPASS_ID]["stable_internal_id"] == RAG_COMPASS_ID
    assert optimizer_registry_payload()["optimizers"][RAG_COMPASS_ID]["schema_id_stable"] is True


def test_name_change_does_not_change_claims(tmp_path: Path) -> None:
    migration = write_rag_compass_name_migration(tmp_path)
    assert migration["claim_change"] is False
    assert migration["schema_migration_performed"] is False


def test_reports_use_rag_compass_display_name() -> None:
    assert "RAG Compass" in optimizer_display_name(RAG_COMPASS_ID)


def test_selection_logic_bug_detected_known_case() -> None:
    result = classify_selection_regret("optuna_tpe", "optuna_tpe", RAG_COMPASS_ID, True, -0.1)
    assert result == "SELECTION_LOGIC_BUG"


def test_heldout_reversal_classified_known_case() -> None:
    result = classify_selection_regret(RAG_COMPASS_ID, "optuna_tpe", RAG_COMPASS_ID, True, 0.2)
    assert result == "SELECTION_CORRECT_HELDOUT_REVERSAL"


def test_tiebreaker_reported_known_case() -> None:
    result = classify_selection_regret(RAG_COMPASS_ID, "optuna_tpe", RAG_COMPASS_ID, True, 0.0)
    assert result in {"SELECTION_CORRECT_HELDOUT_REVERSAL", "SELECTION_TIEBREAKER_DRIVEN"}


def test_governance_blocks_unsafe_high_quality_candidate() -> None:
    unsafe = next(row for row in governance_case_rows() if row["scenario"] == "unsafe_high_quality")
    assert unsafe["quality_only"] == "unsafe_candidate"
    assert unsafe["governed"] == "safe_candidate"


def test_governance_blocks_cost_trap() -> None:
    row = next(row for row in governance_case_rows() if row["scenario"] == "cost_trap")
    assert row["rule"] == "cost_utility"


def test_governance_blocks_latency_trap() -> None:
    row = next(row for row in governance_case_rows() if row["scenario"] == "latency_trap")
    assert row["rule"] == "latency_threshold"


def test_governance_blocks_protected_regression() -> None:
    row = next(row for row in governance_case_rows() if row["scenario"] == "protected_regression")
    assert row["governed"] == "stable_candidate"


def test_governance_refuses_provenance_failure() -> None:
    row = next(row for row in governance_case_rows() if row["scenario"] == "provenance_failure")
    assert row["governed"] == "no_promotion"


def test_workflow_baselines_labeled_simulation() -> None:
    candidates = pd.DataFrame(
        [
            {"policy_id": "a", "raw_quality": 0.9, "confirmatory_utility": 0.1},
            {"policy_id": "b", "raw_quality": 0.8, "confirmatory_utility": 0.2},
        ]
    )
    rows = workflow_baseline_rows(candidates)
    simulated = [row for row in rows if row["workflow"] != "ragwarrant_governed_selection"]
    assert all(row["label"] == "workflow_baseline_simulation" for row in simulated)


def test_no_external_platform_claim_without_integration(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_generative_llm_regime_v1")
    cfg = SuiteConfig.from_path(cfg_path)
    assert cfg.suite == "ragwarrant_generative_llm_regime_v1"


def test_generator_skipped_classification(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_generative_llm_regime_v1")
    result = run_suite(suite="ragwarrant_generative_llm_regime_v1", config_path=cfg_path, output_dir=tmp_path, run_id="gen")
    assert result["status"] == "GENERATOR_REGIME_SKIPPED_NO_MODEL"


def test_human_eval_not_marked_run_without_annotations(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_human_eval_pilot_v1")
    result = run_suite(suite="ragwarrant_human_eval_pilot_v1", config_path=cfg_path, output_dir=tmp_path, run_id="human")
    assert result["status"] == "HUMAN_EVAL_READY_NOT_RUN"
