# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest

from ragwarrant.research.benchmark import score_decision, validate_method_decision, wilson_interval
from ragwarrant.research.methods import AlwaysBlock, method_capabilities, method_registry, oracle_safe_objective
from ragwarrant.research.simulator import generate_evidence, load_config, policy_config, scenario_truth
from ragwarrant.research.types import MethodDecision


CONFIG = Path("configs/research/false_promotion_benchmark_v1.yaml")


def _case(scenario_id: str):
    config = load_config(CONFIG)
    scenario = next(item for item in config["scenarios"] if item["scenario_id"] == scenario_id)
    policy = policy_config(config, scenario, "CI")
    truth = scenario_truth(config, scenario, 64, "CI")
    evidence = generate_evidence(config, scenario, 64, 0, "confirmatory", "CI")
    return policy, truth, evidence


def test_always_block_has_zero_false_promotion_and_can_false_block() -> None:
    policy, truth, evidence = _case("one_clearly_safe")
    decision = AlwaysBlock().evaluate(evidence, policy)
    score = score_decision(truth, decision, policy)
    assert score["false_promotion"] == 0
    assert score["false_certification"] == 0
    assert score["false_block"] == 1


def test_oracle_never_promotes_unsafe_and_is_non_deployable() -> None:
    policy, truth, _ = _case("all_unsafe_boundary")
    decision = oracle_safe_objective(truth, policy)
    score = score_decision(truth, decision, policy)
    assert decision.selected_policy_id is None
    assert score["false_promotion"] == 0
    assert not decision.deployable
    assert decision.uses_population_truth


def test_multiplicity_scores_any_unsafe_selection_or_certification() -> None:
    policy, truth, _ = _case("one_clearly_safe")
    decision = MethodDecision(
        method_id="constructed",
        selected_policy_id="inferior_quality",
        certified_policy_ids=("clearly_safe", "inferior_quality"),
        decision="PROMOTE",
        decision_reason="constructed invariant test",
        deployable=True,
        uses_population_truth=False,
    )
    score = score_decision(truth, decision, policy)
    assert score["false_promotion"] == 1
    assert score["false_certification"] == 1


def test_current_adapter_is_explicitly_unsupported_and_not_registered() -> None:
    capabilities = {item.method_id: item for item in method_capabilities()}
    current = capabilities["current_ragwarrant_adapter"]
    assert not current.supported
    assert current.status == "unsupported_in_benchmark_v1"
    assert "current_ragwarrant_adapter" not in method_registry()


def test_deployable_truth_access_is_rejected() -> None:
    _, truth, evidence = _case("one_clearly_safe")
    decision = MethodDecision(
        method_id="truth_spy",
        selected_policy_id=None,
        certified_policy_ids=(),
        decision="BLOCK",
        decision_reason="constructed invalid decision",
        deployable=True,
        uses_population_truth=True,
    )
    with pytest.raises(ValueError, match="accessed population truth"):
        validate_method_decision(
            decision,
            "truth_spy",
            tuple(candidate.policy_id for candidate in truth.confirmatory_candidates),
            evidence,
        )


def test_decision_flags_must_match_frozen_method_capability() -> None:
    _, truth, evidence = _case("one_clearly_safe")
    capability = next(
        item for item in method_capabilities() if item.method_id == "naive_point_estimate"
    )
    decision = MethodDecision(
        method_id="naive_point_estimate",
        selected_policy_id=None,
        certified_policy_ids=(),
        decision="BLOCK",
        decision_reason="constructed metadata drift",
        deployable=False,
        uses_population_truth=True,
        benchmark_control_only=False,
    )
    with pytest.raises(ValueError, match="frozen capability"):
        validate_method_decision(
            decision,
            "naive_point_estimate",
            tuple(candidate.policy_id for candidate in truth.confirmatory_candidates),
            evidence,
            capability,
        )


def test_wilson_interval_handles_boundary_counts() -> None:
    zero = wilson_interval(0, 24)
    full = wilson_interval(24, 24)
    assert zero[0] == 0.0 and 0.0 < zero[1] < 1.0
    assert full[1] == 1.0 and 0.0 < full[0] < 1.0
