from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ragwarrant.artifacts import prepare_run_dir
from ragwarrant.cloud import docker_smoke_command_documented
from ragwarrant.end_to_end import RAGPolicy, run_pipeline
from ragwarrant.experiments.governance import governance_ablation_table
from ragwarrant.experiments.runner import run_suite
from ragwarrant.fixtures import candidate_policy_metrics, deterministic_split, governance_fixture
from ragwarrant.metrics import (
    apply_utilities,
    pareto_frontier,
    protected_regression_gate,
    rank_policies,
)
from ragwarrant.policy import policy_id
from ragwarrant.robustness import perturb_corpus, security_violation
from ragwarrant.utils.write_once import WriteOnceError


def test_no_overwrite_completed_run(tmp_path: Path) -> None:
    run_id, run_dir = prepare_run_dir(tmp_path, "fixed", suite="ragwarrant_reproduction_v1")
    (run_dir / "run_manifest.json").write_text('{"status":"completed"}', encoding="utf-8")
    assert run_id == "fixed"
    with pytest.raises(WriteOnceError):
        prepare_run_dir(tmp_path, "fixed", suite="ragwarrant_reproduction_v1")


def test_deterministic_split() -> None:
    a = deterministic_split(governance_fixture(1), seed=7)
    b = deterministic_split(governance_fixture(1), seed=7)
    assert a["split"].tolist() == b["split"].tolist()
    assert {"train", "validation", "test"} <= set(a["split"])


def test_policy_id_stability() -> None:
    policy = {"top_k": 5, "citation_required": True}
    assert policy_id(policy) == policy_id({"citation_required": True, "top_k": 5})


def test_pareto_frontier_known_case() -> None:
    frame = pd.DataFrame(
        [
            {"policy_id": "a", "raw_quality": 0.8, "protected_subset_score": 0.8, "cost": 0.2, "latency_p95": 0.2},
            {"policy_id": "b", "raw_quality": 0.7, "protected_subset_score": 0.7, "cost": 0.3, "latency_p95": 0.3},
        ]
    )
    out = pareto_frontier(frame)
    assert out.loc[out["policy_id"] == "a", "pareto_frontier"].item() is True
    assert out.loc[out["policy_id"] == "b", "pareto_frontier"].item() is False


def test_cost_aware_ranking_known_case() -> None:
    metrics = apply_utilities(candidate_policy_metrics(), lambda_cost=1.0, lambda_latency=0.0)
    assert rank_policies(metrics).iloc[0]["policy_id"] != "quality_only_search"


def test_regression_gate_blocks_harmful_policy() -> None:
    gated = protected_regression_gate(candidate_policy_metrics(), regression_threshold=-0.03)
    assert gated.loc[gated["policy_id"] == "quality_only_search", "promotion_blocked"].item() is True


def test_certificate_refuses_null_control(tmp_path: Path) -> None:
    result = run_suite(
        suite="ragwarrant_certificate_calibration_v1",
        config_path=Path("configs/experiments/ragwarrant_certificate_calibration_v1.yaml"),
        output_dir=tmp_path,
        run_id="calibration",
    )
    cert = json.loads((Path(result["run_dir"]) / "certificate.json").read_text(encoding="utf-8"))
    assert cert["status"] == "Inconclusive"


def test_fixture_end_to_end_pipeline_runs() -> None:
    a = run_pipeline(RAGPolicy(top_k=3, citation_required=False))
    b = run_pipeline(RAGPolicy(top_k=8, reranker_enabled=True, citation_required=True))
    assert a["cost"] != b["cost"]
    assert "latency_p95" in b


def test_robustness_perturbations_are_deterministic() -> None:
    corpus = {"a": "alpha beta", "b": "gamma delta"}
    assert perturb_corpus(corpus, family="ocr_corruption", seed=5) == perturb_corpus(
        corpus, family="ocr_corruption", seed=5
    )


def test_security_constraint_blocks_promotion() -> None:
    assert security_violation("SECRET_API_KEY_PLACEHOLDER leaked") is True


def test_report_generation(tmp_path: Path) -> None:
    result = run_suite(
        suite="ragwarrant_governance_ablation_v1",
        config_path=Path("configs/experiments/ragwarrant_governance_ablation_v1.yaml"),
        output_dir=tmp_path,
        run_id="gov",
    )
    report = Path(result["run_dir"]) / "report.md"
    assert "Claim Boundary" in report.read_text(encoding="utf-8")


def test_artifact_schema_validation(tmp_path: Path) -> None:
    result = run_suite(
        suite="ragwarrant_reproduction_v1",
        config_path=Path("configs/experiments/ragwarrant_reproduction_v1.yaml"),
        output_dir=tmp_path,
        run_id="repro",
    )
    required = [
        "run_manifest.json",
        "input_config.yaml",
        "dataset_manifest.json",
        "split_manifest.json",
        "policy_space.yaml",
        "candidate_policy_metrics.csv",
        "aggregate_metrics.json",
        "ranking.json",
        "winning_policy.json",
        "certificate.json",
        "statistical_analysis.json",
        "utility_sensitivity.json",
        "regression_report.json",
        "no_overwrite_audit.json",
        "report.md",
    ]
    assert all((Path(result["run_dir"]) / name).exists() for name in required)


def test_docker_smoke_command_documented() -> None:
    assert docker_smoke_command_documented(Path("."))


def test_governance_ablation_blocks_harmful_quality_only() -> None:
    table = governance_ablation_table(candidate_policy_metrics())
    quality_winner = table.loc[table["stage"] == "quality_only_search", "winner"].item()
    final_winner = table.loc[table["stage"] == "plus_certificate_and_audit_requirements", "winner"].item()
    assert quality_winner == "quality_only_search"
    assert final_winner == "ragwarrant_no_fork"


def test_all_smoke_suites_run(tmp_path: Path) -> None:
    suites = [
        "ragwarrant_reproduction_v1",
        "ragwarrant_end_to_end_v1",
        "ragwarrant_governance_ablation_v1",
        "ragwarrant_certificate_calibration_v1",
        "ragwarrant_robustness_v1",
        "ragwarrant_cloud_repro_v1",
    ]
    for suite in suites:
        result = run_suite(
            suite=suite,
            config_path=Path(f"configs/experiments/{suite}.yaml"),
            output_dir=tmp_path,
            run_id=suite,
        )
        assert Path(result["run_dir"], "run_manifest.json").exists()
