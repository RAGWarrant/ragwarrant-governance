# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from ragwarrant.config import SuiteConfig
from ragwarrant.experiments.runner import run_suite
from ragwarrant.real_rag import (
    budget_parity_report,
    deterministic_fixture_scenario,
    issue_real_rag_certificate,
    leakage_report,
    select_primary_baseline,
)
from ragwarrant.utils.write_once import WriteOnceError


def _fixture_config(tmp_path: Path, *, suite: str = "ragwarrant_real_rag_reproduction_v1") -> Path:
    path = tmp_path / f"{suite}.yaml"
    payload = {
        "suite": suite,
        "suite_version": 1,
        "profile": "smoke",
        "evidence_mode": "historical_reproduction",
        "seed": 11,
        "seeds": [11, 29],
        "dataset": {
            "dataset_root": str(tmp_path / "missing_dataset"),
            "scenario_root": str(tmp_path / "missing_scenario"),
            "allow_fixture_fallback": True,
            "fixture_rows": 60,
            "near_duplicate_threshold": 0.99,
        },
        "policy_space": {"top_k": [3, 5], "citation_required": [False, True]},
        "primary_endpoint": {"superiority_margin": 0.01, "bootstrap_samples": 50},
        "budget": {"mode": "candidate_count", "amount": 64, "parity_tolerance": 0.0},
        "baselines": {
            "required": [
                "static_default_rag_policy",
                "best_single_policy_on_validation",
                "uniform_random_search",
                "greedy_coordinate_search",
                "greedy_regression_aware_search",
                "optuna_tpe",
                "ragwarrant_no_fork",
            ],
            "optional": ["retrieval_confidence_gating", "uncertainty_threshold_gating"],
            "diagnostic": ["oracle_upper_bound_diagnostic"],
        },
        "governance": {"protected_regression_threshold": -0.03, "minimum_group_size": 5},
        "certificate": {"supported_enabled": False, "bootstrap_samples": 50},
        "output": {"append_only": True},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    return path


def test_run_manifest_records_evidence_mode(tmp_path: Path) -> None:
    result = run_suite(
        suite="ragwarrant_end_to_end_public_v1",
        config_path=Path("configs/experiments/ragwarrant_end_to_end_public_v1_smoke.yaml"),
        output_dir=tmp_path,
        run_id="e2e-smoke",
    )
    manifest = json.loads((Path(result["run_dir"]) / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["evidence_mode"] == "end_to_end_smoke"


def test_completed_real_run_cannot_be_overwritten(tmp_path: Path) -> None:
    config = _fixture_config(tmp_path)
    run_suite(
        suite="ragwarrant_real_rag_reproduction_v1",
        config_path=config,
        output_dir=tmp_path,
        run_id="fixed-real-run",
    )
    with pytest.raises(WriteOnceError):
        run_suite(
            suite="ragwarrant_real_rag_reproduction_v1",
            config_path=config,
            output_dir=tmp_path,
            run_id="fixed-real-run",
        )


def test_exact_duplicate_groups_stay_in_one_split() -> None:
    train, validation, test = deterministic_fixture_scenario(40)
    report = leakage_report(train, validation, test, near_threshold=0.99)
    assert report["status"] == "pass"
    assert report["exact_duplicate_cross_split_count"] == 0


def test_cross_split_leakage_refuses_run() -> None:
    train = pd.DataFrame({"example_id": ["a"], "normalized_query": ["same query"]})
    validation = pd.DataFrame({"example_id": ["b"], "normalized_query": ["same query"]})
    test = pd.DataFrame({"example_id": ["c"], "normalized_query": ["different"]})
    report = leakage_report(train, validation, test)
    cert = issue_real_rag_certificate(
        cfg=SuiteConfig(
            suite="ragwarrant_real_rag_reproduction_v1",
            seed=1,
            dataset={},
            policy_space={},
            objectives={},
            baselines=[],
            certificate={"supported_enabled": False},
            output={},
            raw={"profile": "confirmatory", "certificate": {"supported_enabled": False}},
        ),
        profile="confirmatory",
        evidence_mode="offline_public_real_rag",
        leakage=report,
        budget={"pass": True},
        baseline_eligibility={"required_missing": []},
        primary_selection={"status": "selected"},
        stats={"paired_bootstrap_ci": {"mean_delta": 0.02, "ci_low": 0.01}, "dataset_balanced": {"mean_delta": 0.02}, "seed_level_win_tie_loss": {"wins": 3, "n": 3}},
        regression={"pass": True},
        sensitivity={"utility_fragile": False},
        no_overwrite_status="append_only_confirmed",
    )
    assert cert["status"] == "Refused"


def test_primary_baseline_selected_on_validation_only() -> None:
    frame = pd.DataFrame(
        [
            {"policy_id": "static_default_rag_policy", "validation_cost_adjusted_utility": 0.9, "diagnostic_only": False, "skipped": False},
            {"policy_id": "greedy_regression_aware_search", "validation_cost_adjusted_utility": 0.8, "diagnostic_only": False, "skipped": False},
            {"policy_id": "ragwarrant_no_fork", "validation_cost_adjusted_utility": 0.95, "diagnostic_only": False, "skipped": False},
            {"policy_id": "oracle_upper_bound_diagnostic", "validation_cost_adjusted_utility": 1.0, "diagnostic_only": True, "skipped": False},
        ]
    )
    assert select_primary_baseline(frame)["selected_primary_baseline"] == "static_default_rag_policy"


def test_no_fork_is_not_hardcoded_winner() -> None:
    frame = pd.DataFrame(
        [
            {"policy_id": "static_default_rag_policy", "validation_cost_adjusted_utility": 0.8, "diagnostic_only": False, "skipped": False},
            {"policy_id": "greedy_regression_aware_search", "validation_cost_adjusted_utility": 0.9, "diagnostic_only": False, "skipped": False},
            {"policy_id": "ragwarrant_no_fork", "validation_cost_adjusted_utility": 0.7, "diagnostic_only": False, "skipped": False},
        ]
    )
    assert select_primary_baseline(frame)["selected_primary_baseline"] == "greedy_regression_aware_search"


def test_budget_parity_equal_candidate_count(tmp_path: Path) -> None:
    cfg = SuiteConfig.from_path(_fixture_config(tmp_path))
    frame = pd.DataFrame(
        [
            {"policy_id": "a", "seed": 1, "evaluation_count": 64, "diagnostic_only": False},
            {"policy_id": "b", "seed": 1, "evaluation_count": 64, "diagnostic_only": False},
        ]
    )
    assert budget_parity_report(frame, cfg)["pass"] is True


def test_budget_overrun_refuses_or_disqualifies(tmp_path: Path) -> None:
    cfg = SuiteConfig.from_path(_fixture_config(tmp_path))
    frame = pd.DataFrame([{"policy_id": "a", "seed": 1, "evaluation_count": 65, "diagnostic_only": False}])
    assert budget_parity_report(frame, cfg)["pass"] is False


def test_supported_certificate_disabled(tmp_path: Path) -> None:
    cfg = SuiteConfig.from_path(_fixture_config(tmp_path))
    cert = issue_real_rag_certificate(
        cfg=cfg,
        profile="confirmatory",
        evidence_mode="offline_public_real_rag",
        leakage={"status": "pass"},
        budget={"pass": True},
        baseline_eligibility={"required_missing": []},
        primary_selection={"status": "selected"},
        stats={"paired_bootstrap_ci": {"mean_delta": 0.03, "ci_low": 0.02}, "dataset_balanced": {"mean_delta": 0.03}, "seed_level_win_tie_loss": {"wins": 5, "n": 5}},
        regression={"pass": True},
        sensitivity={"utility_fragile": False},
        no_overwrite_status="append_only_confirmed",
    )
    assert cert["status"] == "Candidate external signal"
    assert cert["supported_enabled"] is False


def test_real_rag_smoke_fixture_run_writes_required_artifacts(tmp_path: Path) -> None:
    config = _fixture_config(tmp_path)
    result = run_suite(
        suite="ragwarrant_real_rag_reproduction_v1",
        config_path=config,
        output_dir=tmp_path,
        run_id="real-smoke",
    )
    run_dir = Path(result["run_dir"])
    required = [
        "dataset_manifest.json",
        "dataset_availability_report.json",
        "normalization_report.json",
        "split_manifest.json",
        "leakage_report.json",
        "budget_parity_report.json",
        "baseline_eligibility.json",
        "primary_baseline_selection.json",
        "candidate_policy_metrics.csv",
        "per_query_metrics.csv",
        "statistical_analysis.json",
        "certificate.json",
        "report.md",
    ]
    assert all((run_dir / name).exists() for name in required)
    assert json.loads((run_dir / "certificate.json").read_text(encoding="utf-8"))["status"] in {"Inconclusive", "Refused"}


def test_end_to_end_smoke_certificate_is_inconclusive(tmp_path: Path) -> None:
    result = run_suite(
        suite="ragwarrant_end_to_end_public_v1",
        config_path=Path("configs/experiments/ragwarrant_end_to_end_public_v1_smoke.yaml"),
        output_dir=tmp_path,
        run_id="e2e",
    )
    cert = json.loads((Path(result["run_dir"]) / "certificate.json").read_text(encoding="utf-8"))
    assert cert["status"] == "Inconclusive"
    assert cert["evidence_mode"] == "end_to_end_smoke"
