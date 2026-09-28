# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def load_csv(path: str):
    with (ROOT / path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module", autouse=True)
def generate_behavioral_artifacts() -> None:
    from ragwarrant.behavioral_governance import run_experiment

    run_experiment(ROOT)


def test_behavioral_policy_definitions_exist() -> None:
    policies = load_json("artifacts/behavioral_policies/policy_definitions.json")
    policy_ids = {row["policy_id"] for row in policies}
    assert "low_retrieval_single_endpoint" in policy_ids
    assert "expanded_retrieval_multi_endpoint" in policy_ids
    assert "adaptive_routing_on_insufficient_evidence" in policy_ids
    assert "governed_selection" in policy_ids


def test_low_retrieval_uses_fewer_endpoints_than_expanded() -> None:
    rows = load_csv("artifacts/behavioral_governance/policy_summary_metrics.csv")
    by_policy = {row["policy_id"]: row for row in rows}
    assert float(by_policy["low_retrieval_single_endpoint"]["mean_api_calls"]) < float(
        by_policy["expanded_retrieval_multi_endpoint"]["mean_api_calls"]
    )
    assert float(by_policy["low_retrieval_single_endpoint"]["mean_measured_cost_units"]) < float(
        by_policy["expanded_retrieval_multi_endpoint"]["mean_measured_cost_units"]
    )


def test_adaptive_routing_changes_api_calls_by_query() -> None:
    rows = load_csv("artifacts/behavioral_governance/per_query_policy_results.csv")
    calls = {
        int(row["api_call_count"])
        for row in rows
        if row["policy_id"] == "adaptive_routing_on_insufficient_evidence" and row["split"] == "confirmatory_test"
    }
    assert calls == {1, 2}


def test_cost_and_latency_minimizers_use_measured_metrics() -> None:
    policies = load_json("artifacts/behavioral_policies/policy_definitions.json")
    by_policy = {row["policy_id"]: row for row in policies}
    assert "measured cost" in by_policy["measured_cost_minimizer_at_quality_floor"]["endpoint_selection_rule"]
    assert "p95 latency" in by_policy["measured_latency_minimizer_at_quality_floor"]["endpoint_selection_rule"]


def test_quality_only_ignores_cost_latency() -> None:
    policies = load_json("artifacts/behavioral_policies/policy_definitions.json")
    quality_only = [row for row in policies if row["policy_id"] == "quality_only_best_on_validation"][0]
    assert quality_only["cost_rule"] == "ignored"
    assert quality_only["latency_rule"] == "ignored"


def test_constrained_optimizer_and_pareto_outputs_exist() -> None:
    constrained = load_json("artifacts/baselines/constrained_optimizer_result.json")
    frontier = load_json("artifacts/baselines/pareto_frontier_analysis.json")
    assert constrained["winner"] == "low_retrieval_single_endpoint"
    assert "low_retrieval_single_endpoint" in frontier["frontier"]


def test_behavioral_distinction_matrix_nontrivial() -> None:
    rows = load_csv("artifacts/behavioral_policies/behavioral_distinction_matrix.csv")
    assert any(abs(float(row["api_call_count_difference"])) >= 1.0 for row in rows)
    assert any(abs(float(row["measured_cost_difference"])) >= 0.5 for row in rows)


def test_quality_measure_has_required_components() -> None:
    result = load_json("artifacts/quality_measurement/quality_measurement_result.json")
    weights = result["weights"]
    assert "answer_correctness_score_from_parent_raw_quality" in weights
    assert "evidence_support_score" in weights
    assert "abstention_score" in weights
    assert result["result_class"] == "QUALITY_MEASURE_PROXY_PLUS_EVIDENCE"


def test_primary_outcome_reports_operational_endpoint() -> None:
    stats = load_json("artifacts/behavioral_governance/primary_outcome_statistics.json")
    assert stats["primary_result_class"] == "GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_QUALITY"
    assert stats["governed_winner"] == "low_retrieval_single_endpoint"
    assert stats["quality_only_winner"] == "optuna_tpe"
    assert stats["cost_delta"]["ci_high"] < 0
    assert stats["quality_delta"]["ci_low"] >= -stats["quality_noninferiority_margin"]


def test_repeat_labels_frozen_resplit_not_independent() -> None:
    repeat = load_json("artifacts/behavioral_governance_repeat/repeat_manifest.json")
    assert repeat["repeat_type"] == "frozen_observation_resplit"
    assert repeat["result_class"] == "BEHAVIORAL_GOVERNANCE_DIRECTIONAL_REPEAT"


def test_no_raw_query_text_in_behavioral_artifacts() -> None:
    artifact_roots = [
        ROOT / "artifacts/behavioral_policies",
        ROOT / "artifacts/quality_measurement",
        ROOT / "artifacts/behavioral_governance",
        ROOT / "artifacts/baselines",
        ROOT / "artifacts/behavioral_governance_repeat",
        ROOT / "results/behavioral_governance",
    ]
    forbidden = ["query_text,", '"query_text"', "raw_query", "raw_response", "api_response", "source_snippet"]
    for root in artifact_roots:
        for path in root.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                assert not any(token in text for token in forbidden), path
