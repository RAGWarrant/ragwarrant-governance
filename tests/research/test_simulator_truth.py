from __future__ import annotations

import copy
import math
from pathlib import Path

import numpy as np
import pytest

from ragwarrant.research.simulator import (
    generate_evidence,
    load_config,
    scenario_truth,
    validate_config,
)


CONFIG = Path("configs/research/false_promotion_benchmark_v1.yaml")


def _config() -> dict:
    return load_config(CONFIG)


def _scenario(config: dict, scenario_id: str) -> dict:
    return next(item for item in config["scenarios"] if item["scenario_id"] == scenario_id)


def test_truth_table_is_analytically_derived_from_config() -> None:
    config = _config()
    scenario = _scenario(config, "one_clearly_safe")
    truth = scenario_truth(config, scenario, 64, "CI")
    candidate = truth.confirmatory_candidate("clearly_safe")
    assert candidate.overall_quality_delta_vs_incumbent == pytest.approx(
        0.8 * 0.030 + 0.2 * 0.025
    )
    assert candidate.safety_violation_probability == pytest.approx(0.01)
    assert candidate.mean_cost == pytest.approx(0.82)
    assert candidate.truly_promotion_safe


def test_hidden_group_regression_is_classified_from_truth() -> None:
    config = _config()
    scenario = _scenario(config, "hidden_group_regression")
    truth = scenario_truth(config, scenario, 64, "CI")
    candidate = truth.confirmatory_candidate("average_pass_group_fail")
    assert candidate.overall_quality_delta_vs_incumbent > -0.02
    assert candidate.safety_violation_probability < 0.05
    assert candidate.overall_safe_but_subgroup_unsafe
    assert not candidate.truly_promotion_safe
    assert "group_quality:minority" in candidate.failed_truth_conditions
    assert "safety_violation_probability:minority" in candidate.failed_truth_conditions


def test_same_seed_is_identical_and_different_seed_changes_evidence() -> None:
    config = _config()
    scenario = _scenario(config, "dependent_candidates")
    first = generate_evidence(config, scenario, 64, 3, "confirmatory", "CI", master_seed=17)
    repeat = generate_evidence(config, scenario, 64, 3, "confirmatory", "CI", master_seed=17)
    different = generate_evidence(config, scenario, 64, 3, "confirmatory", "CI", master_seed=18)
    assert first == repeat
    assert first.evidence_hash != different.evidence_hash


def test_candidate_order_does_not_change_evidence_streams() -> None:
    config = _config()
    scenario = copy.deepcopy(_scenario(config, "one_clearly_safe"))
    first = generate_evidence(config, scenario, 64, 0, "confirmatory", "CI")
    scenario["candidates"].reverse()
    second = generate_evidence(config, scenario, 64, 0, "confirmatory", "CI")
    assert first.evidence_hash == second.evidence_hash
    assert first.rows == second.rows


def test_large_sample_approaches_declared_marginals_without_defining_truth() -> None:
    config = _config()
    scenario = copy.deepcopy(_scenario(config, "one_clearly_safe"))
    scenario["candidates"] = [
        candidate for candidate in scenario["candidates"] if candidate["policy_id"] == "clearly_safe"
    ]
    evidence = generate_evidence(
        config, scenario, 40_000, 0, "confirmatory", "CI", master_seed=991
    )
    rows = evidence.rows
    assert np.mean([row.quality_delta for row in rows]) == pytest.approx(0.029, abs=0.0025)
    assert np.mean([row.safety_violation for row in rows]) == pytest.approx(0.01, abs=0.0025)
    assert np.mean([row.execution_failure for row in rows]) == pytest.approx(0.005, abs=0.0020)
    assert np.mean([row.insufficient_evidence for row in rows]) == pytest.approx(0.03, abs=0.0035)
    assert np.mean([row.cost for row in rows]) == pytest.approx(0.82, abs=0.003)
    assert np.mean([row.latency for row in rows]) == pytest.approx(1.15, abs=0.006)


def test_development_and_confirmatory_streams_are_separate_with_frozen_ids() -> None:
    config = _config()
    scenario = _scenario(config, "development_confirmatory_shift")
    development = generate_evidence(config, scenario, 64, 0, "development", "CI")
    confirmatory = generate_evidence(config, scenario, 64, 0, "confirmatory", "CI")
    assert development.policy_ids == confirmatory.policy_ids
    assert development.evidence_hash != confirmatory.evidence_hash


def test_v1_scenario_matrix_and_truth_classifications_are_frozen() -> None:
    config = _config()
    expected = {
        "all_unsafe_boundary": ("ALL_UNSAFE_BOUNDARY", 4, 0),
        "one_clearly_safe": ("ONE_CLEARLY_SAFE", 4, 1),
        "many_candidates_k12": ("MANY_CANDIDATES_MULTIPLICITY", 12, 1),
        "many_candidates_k24": ("MANY_CANDIDATES_MULTIPLICITY", 24, 1),
        "dependent_candidates": ("DEPENDENT_CANDIDATES", 6, 2),
        "hidden_group_regression": ("HIDDEN_GROUP_REGRESSION", 4, 1),
        "development_confirmatory_shift": ("DEVELOPMENT_CONFIRMATORY_SHIFT", 4, 1),
        "multiple_safe_candidates": ("MULTIPLE_SAFE_CANDIDATES", 5, 3),
    }
    assert {scenario["scenario_id"] for scenario in config["scenarios"]} == set(expected)
    for scenario in config["scenarios"]:
        family, candidate_count, safe_count = expected[scenario["scenario_id"]]
        truth = scenario_truth(config, scenario, 64, "CI")
        assert scenario["sample_sizes"] == [64, 256]
        assert scenario["family"] == family
        assert len(truth.confirmatory_candidates) == candidate_count
        assert len(truth.safe_policy_ids) == safe_count


def test_candidates_share_example_group_and_incumbent_evidence() -> None:
    config = _config()
    scenario = _scenario(config, "dependent_candidates")
    evidence = generate_evidence(config, scenario, 256, 0, "confirmatory", "CI")
    truth = scenario_truth(config, scenario, 256, "CI")
    assert evidence.policy_ids == tuple(
        candidate.policy_id for candidate in truth.confirmatory_candidates
    )
    for example_id in {row.example_id for row in evidence.rows}:
        rows = [row for row in evidence.rows if row.example_id == example_id]
        assert len({row.group_id for row in rows}) == 1
        assert len({row.incumbent_quality for row in rows}) == 1


def test_dependent_scenario_produces_shared_variation_without_changing_marginals() -> None:
    config = _config()
    scenario = copy.deepcopy(_scenario(config, "dependent_candidates"))
    scenario["candidates"] = scenario["candidates"][:2]
    evidence = generate_evidence(
        config, scenario, 10_000, 1, "confirmatory", "CI", master_seed=73
    )
    first = evidence.rows_for("dependent_safe_01")
    second = evidence.rows_for("dependent_safe_02")
    correlation = np.corrcoef(
        [row.quality_delta for row in first], [row.quality_delta for row in second]
    )[0, 1]
    agreement = np.mean(
        [
            left.safety_violation == right.safety_violation
            for left, right in zip(first, second, strict=True)
        ]
    )
    assert correlation > 0.95
    assert agreement > 0.985
    assert np.mean([row.safety_violation for row in first]) == pytest.approx(0.02, abs=0.006)


@pytest.mark.parametrize(
    "mutator, match",
    [
        (lambda cfg: cfg["scenarios"].append(copy.deepcopy(cfg["scenarios"][0])), "duplicate scenario"),
        (
            lambda cfg: cfg["scenarios"][0]["candidates"].append(
                copy.deepcopy(cfg["scenarios"][0]["candidates"][0])
            ),
            "duplicate scenario .* candidate",
        ),
        (lambda cfg: cfg["profiles"]["CI"].update(replicate_count=0), "positive integer"),
        (lambda cfg: cfg["scenarios"][0].update(sample_sizes=[-1, 64]), "positive integers"),
        (lambda cfg: cfg["scenarios"][0].update(sample_sizes=[64, 64]), "duplicate sample sizes"),
        (
            lambda cfg: cfg["scenarios"][0]["groups"][0].update(prevalence=0.7),
            "sum to 1",
        ),
        (
            lambda cfg: cfg["scenarios"][0]["shared_outcome_fraction"].update(
                safety_violation_probability=1.1
            ),
            "between 0 and 1",
        ),
        (lambda cfg: cfg["scenarios"][0].pop("incumbent"), "missing incumbent"),
        (lambda cfg: cfg["policy"].update(quality_noninferiority_margin=-0.1), "nonnegative"),
        (lambda cfg: cfg["policy"].update(max_safety_violation_probability=math.nan), "finite"),
        (
            lambda cfg: cfg["scenarios"][0]["candidates"][0].update(policy_id="=FORMULA()"),
            "portable letters",
        ),
        (
            lambda cfg: cfg["policy"].update(max_safety_violation_probability=True),
            "finite number, not bool",
        ),
        (
            lambda cfg: cfg["scenarios"][0].update(
                enabled_risks=[
                    risk
                    for risk in cfg["scenarios"][0]["enabled_risks"]
                    if risk != "safety_violation_probability"
                ],
                enabled_group_risks=["safety_violation_probability"],
            ),
            "also be enabled overall",
        ),
    ],
)
def test_materially_invalid_config_fails_closed(mutator, match: str) -> None:
    config = _config()
    mutator(config)
    with pytest.raises(ValueError, match=match):
        validate_config(config)


def test_quality_support_violation_fails_without_clipping() -> None:
    config = _config()
    candidate = config["scenarios"][0]["candidates"][0]
    candidate["confirmatory"]["quality_delta_by_group"]["majority"] = 0.40
    with pytest.raises(ValueError, match="delta bounds"):
        validate_config(config)
