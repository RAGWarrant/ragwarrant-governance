from __future__ import annotations

import inspect
import math
from dataclasses import replace

import pytest

from ragwarrant.research.fixed_sample_warrant import (
    BLOCKED_INVALID_EVIDENCE,
    FOCUS1_FREEZE_DIGEST,
    HOLM,
    INCONCLUSIVE,
    METHOD_ID,
    PROMOTE,
    FixedSampleMultiRiskWarrant,
    freeze_candidate_family,
)
from ragwarrant.research.simulator import sha256_json
from ragwarrant.research.types import EvidenceRow, ObservedEvidence, PolicyConfig


ALL_RISKS = (
    "overall_quality",
    "group_quality",
    "safety_violation_probability",
    "execution_failure_probability",
    "insufficient_evidence_probability",
)
BINARY_RISKS = (
    "safety_violation_probability",
    "execution_failure_probability",
    "insufficient_evidence_probability",
)


def _policy(
    *,
    enabled_risks: tuple[str, ...] = ALL_RISKS,
    enabled_group_risks: tuple[str, ...] = BINARY_RISKS,
    group_ids: tuple[str, ...] = ("g1", "g2"),
) -> PolicyConfig:
    return PolicyConfig(
        quality_noninferiority_margin=0.02,
        group_quality_noninferiority_margin=0.03,
        max_safety_violation_probability=0.10,
        max_execution_failure_probability=0.10,
        max_insufficient_evidence_probability=0.10,
        cost_weight=1.0,
        latency_weight=0.1,
        confidence_level=0.95,
        bootstrap_resamples=64,
        enabled_risks=enabled_risks,
        enabled_group_risks=enabled_group_risks,
        group_ids=group_ids,
    )


def _evidence(
    deltas_by_policy: dict[str, float],
    *,
    sample_size: int = 200,
    event_counts: dict[str, dict[str, int]] | None = None,
    objectives: dict[str, tuple[float, float]] | None = None,
    groups: tuple[str, ...] = ("g1", "g2"),
) -> ObservedEvidence:
    rows: list[EvidenceRow] = []
    for policy_id, delta in sorted(deltas_by_policy.items()):
        policy_events = (event_counts or {}).get(policy_id, {})
        cost, latency = (objectives or {}).get(policy_id, (1.0, 1.0))
        for index in range(sample_size):
            rows.append(
                EvidenceRow(
                    example_id=f"confirmatory-{index:06d}",
                    group_id=groups[index % len(groups)],
                    policy_id=policy_id,
                    incumbent_quality=0.70,
                    candidate_quality=0.70 + delta,
                    quality_delta=delta,
                    safety_violation=int(
                        index
                        < policy_events.get("safety_violation_probability", 0)
                    ),
                    execution_failure=int(
                        index
                        < policy_events.get("execution_failure_probability", 0)
                    ),
                    insufficient_evidence=int(
                        index
                        < policy_events.get("insufficient_evidence_probability", 0)
                    ),
                    cost=cost,
                    latency=latency,
                )
            )
    ordered = tuple(sorted(rows, key=lambda row: (row.example_id, row.policy_id)))
    return ObservedEvidence(
        scenario_id=f"hand__n{sample_size}",
        phase="confirmatory",
        trial_index=0,
        sample_size=sample_size,
        rows=ordered,
        evidence_hash=sha256_json([row.as_dict() for row in ordered]),
    )


def _method(
    evidence: ObservedEvidence,
    policy: PolicyConfig,
    *,
    candidate_policy_ids: tuple[str, ...] | None = None,
    multiplicity_method: str = HOLM,
    selection_objective: str = "minimize_cost",
) -> FixedSampleMultiRiskWarrant:
    family = freeze_candidate_family(
        candidate_policy_ids=candidate_policy_ids or evidence.policy_ids,
        incumbent_policy_id="incumbent",
        confirmatory_unit_count=evidence.sample_size,
        policy=policy,
        quality_delta_bounds=(-0.25, 0.25),
        familywise_error_level=0.05,
        multiplicity_method=multiplicity_method,
        selection_objective=selection_objective,
    )
    return FixedSampleMultiRiskWarrant(family)


def _rehash(evidence: ObservedEvidence, rows: tuple[EvidenceRow, ...]) -> ObservedEvidence:
    return replace(
        evidence,
        rows=rows,
        evidence_hash=sha256_json([row.as_dict() for row in rows]),
    )


def test_warrant_evaluates_the_complete_prespecified_hypothesis_family() -> None:
    policy = _policy()
    evidence = _evidence({"alpha": 0.20, "beta": 0.20})

    warrant = _method(evidence, policy).evaluate_warrant(evidence, policy)

    # Per candidate: one overall quality test, two group quality tests, three
    # overall binary tests, and three binary tests for each of two groups.
    assert len(warrant.risk_tests) == 2 * (1 + 2 + 3 + 3 * 2)
    assert len({test.hypothesis_id for test in warrant.risk_tests}) == 24
    assert {test.policy_id for test in warrant.risk_tests} == {"alpha", "beta"}
    assert {
        (test.risk_id, test.group_id) for test in warrant.risk_tests
    } == {
        ("overall_quality", None),
        ("group_quality", "g1"),
        ("group_quality", "g2"),
        *((risk, None) for risk in BINARY_RISKS),
        *((risk, group) for risk in BINARY_RISKS for group in ("g1", "g2")),
    }


def test_candidate_is_certified_only_when_every_risk_test_rejects() -> None:
    policy = _policy()
    evidence = _evidence(
        {"safe": 0.20, "unsafe_low_cost": 0.20},
        event_counts={
            "unsafe_low_cost": {"safety_violation_probability": 200},
        },
        objectives={"safe": (2.0, 2.0), "unsafe_low_cost": (0.1, 0.1)},
    )

    warrant = _method(evidence, policy).evaluate_warrant(evidence, policy)
    by_candidate = {
        policy_id: tuple(
            test for test in warrant.risk_tests if test.policy_id == policy_id
        )
        for policy_id in evidence.policy_ids
    }

    assert all(test.rejected for test in by_candidate["safe"])
    assert any(not test.rejected for test in by_candidate["unsafe_low_cost"])
    assert warrant.certified_policy_ids == ("safe",)
    assert warrant.selected_policy_id == "safe"
    assert warrant.decision == PROMOTE


def test_empty_certified_set_is_inconclusive() -> None:
    policy = _policy()
    evidence = _evidence({"boundary": -0.02})

    warrant = _method(evidence, policy).evaluate_warrant(evidence, policy)

    assert warrant.decision == INCONCLUSIVE
    assert warrant.certified_policy_ids == ()
    assert warrant.selected_policy_id is None


@pytest.mark.parametrize(
    ("objective", "expected"),
    [("minimize_cost", "low_cost"), ("minimize_latency", "low_latency")],
)
def test_operational_objective_is_applied_only_after_certification(
    objective: str, expected: str
) -> None:
    policy = _policy()
    evidence = _evidence(
        {"low_cost": 0.20, "low_latency": 0.20},
        objectives={"low_cost": (0.5, 3.0), "low_latency": (2.0, 0.5)},
    )

    warrant = _method(
        evidence, policy, selection_objective=objective
    ).evaluate_warrant(evidence, policy)

    assert warrant.certified_policy_ids == ("low_cost", "low_latency")
    assert warrant.selected_policy_id == expected


def test_operational_ties_are_broken_by_lexical_policy_id() -> None:
    policy = _policy()
    evidence = _evidence(
        {"alpha": 0.20, "zeta": 0.20},
        objectives={"alpha": (1.0, 1.0), "zeta": (1.0, 1.0)},
    )

    warrant = _method(evidence, policy).evaluate_warrant(evidence, policy)

    assert warrant.certified_policy_ids == ("alpha", "zeta")
    assert warrant.selected_policy_id == "alpha"


def test_missing_prespecified_group_remains_in_family_and_fails_closed() -> None:
    policy = _policy()
    evidence = _evidence({"candidate": 0.20}, groups=("g1",))

    warrant = _method(evidence, policy).evaluate_warrant(evidence, policy)
    missing = tuple(
        test for test in warrant.risk_tests if test.group_id == "g2"
    )

    assert len(missing) == 4
    assert all(test.sample_count == 0 for test in missing)
    assert all(test.raw_p_value == 1.0 for test in missing)
    assert all(test.failure_reason == "missing_group_evidence" for test in missing)
    assert warrant.decision == INCONCLUSIVE
    assert warrant.certified_policy_ids == ()


def test_missing_candidate_evidence_blocks_the_whole_warrant() -> None:
    policy = _policy()
    complete = _evidence({"alpha": 0.20, "beta": 0.20})
    alpha_only = tuple(row for row in complete.rows if row.policy_id == "alpha")
    incomplete = _rehash(complete, alpha_only)

    warrant = _method(
        complete, policy, candidate_policy_ids=("alpha", "beta")
    ).evaluate_warrant(incomplete, policy)

    assert warrant.decision == BLOCKED_INVALID_EVIDENCE
    assert warrant.selected_policy_id is None
    assert warrant.certified_policy_ids == ()
    assert warrant.risk_tests == ()
    assert "candidate IDs" in (warrant.invalid_evidence_reason or "")


def test_empty_observations_block_the_whole_warrant() -> None:
    policy = _policy()
    complete = _evidence({"candidate": 0.20})
    empty = replace(complete, rows=(), evidence_hash=sha256_json([]))

    warrant = _method(complete, policy).evaluate_warrant(empty, policy)

    assert warrant.decision == BLOCKED_INVALID_EVIDENCE
    assert warrant.certified_policy_ids == ()
    assert warrant.selected_policy_id is None
    assert warrant.risk_tests == ()


@pytest.mark.parametrize(("field", "value"), [("cost", math.nan), ("latency", math.inf)])
def test_nonfinite_continuous_evidence_blocks_the_whole_warrant(
    field: str, value: float
) -> None:
    policy = _policy()
    evidence = _evidence({"candidate": 0.20})
    rows = list(evidence.rows)
    rows[0] = replace(rows[0], **{field: value})
    # Canonical JSON intentionally cannot serialize NaN/Infinity. Keep the
    # prior hash: evidence validation rejects nonfinite values before checking
    # hash consistency, which is the fail-closed path under test.
    malformed = replace(evidence, rows=tuple(rows))

    warrant = _method(evidence, policy).evaluate_warrant(malformed, policy)

    assert warrant.decision == BLOCKED_INVALID_EVIDENCE
    assert warrant.selected_policy_id is None
    assert warrant.certified_policy_ids == ()
    assert "nonfinite" in (warrant.invalid_evidence_reason or "")


def test_duplicate_evidence_rows_block_the_whole_warrant() -> None:
    policy = _policy()
    evidence = _evidence({"candidate": 0.20})
    duplicated = _rehash(evidence, evidence.rows[:-1] + (evidence.rows[0],))

    warrant = _method(evidence, policy).evaluate_warrant(duplicated, policy)

    assert warrant.decision == BLOCKED_INVALID_EVIDENCE
    assert "duplicate policy/example" in (warrant.invalid_evidence_reason or "")


def test_frozen_family_rejects_duplicate_candidate_ids_and_unknown_risks() -> None:
    policy = _policy()
    evidence = _evidence({"candidate": 0.20})

    with pytest.raises(ValueError, match="duplicate policy IDs"):
        _method(
            evidence,
            policy,
            candidate_policy_ids=("candidate", "candidate"),
        )

    unknown_risk_policy = _policy(enabled_risks=ALL_RISKS + ("invented_risk",))
    with pytest.raises(ValueError, match="unknown enabled risks"):
        _method(evidence, unknown_risk_policy)


@pytest.mark.parametrize(
    ("argument", "value", "message"),
    [
        ("multiplicity_method", "choose_after_results", "unknown multiplicity method"),
        ("selection_objective", "maximize_hype", "unknown operational selection objective"),
    ],
)
def test_frozen_family_rejects_unknown_procedure_or_objective(
    argument: str, value: str, message: str
) -> None:
    policy = _policy()
    evidence = _evidence({"candidate": 0.20})

    with pytest.raises(ValueError, match=message):
        _method(evidence, policy, **{argument: value})  # type: ignore[arg-type]


def test_promotion_warrant_artifact_has_the_exact_public_fields() -> None:
    policy = _policy()
    evidence = _evidence({"candidate": 0.20})
    warrant = _method(evidence, policy).evaluate_warrant(evidence, policy)

    artifact = warrant.as_dict()

    assert set(artifact) == {
        "schema_version",
        "method",
        "method_id",
        "status",
        "decision",
        "decision_reason",
        "familywise_error_level",
        "multiplicity_method",
        "candidate_family_frozen",
        "family_hash",
        "incumbent_policy_id",
        "confirmatory_unit_count",
        "certified_policy_ids",
        "selected_policy_id",
        "selection_objective",
        "risk_tests",
        "enabled_risks",
        "operational_selection_objective",
        "diagnostics",
        "deployable",
        "uses_population_truth",
        "benchmark_freeze_digest",
        "seed_schedule_version",
        "full_profile_used",
        "population_truth_accessed",
        "research_only",
        "production_integrated",
    }
    assert artifact["method_id"] == METHOD_ID
    assert artifact["benchmark_freeze_digest"] == FOCUS1_FREEZE_DIGEST
    assert artifact["seed_schedule_version"] == 2
    assert artifact["full_profile_used"] is False
    assert artifact["population_truth_accessed"] is False
    assert artifact["production_integrated"] is False
    assert set(artifact["risk_tests"][0]) == {
        "hypothesis_id",
        "policy_id",
        "risk_id",
        "group_id",
        "null_hypothesis",
        "alternative_hypothesis",
        "null_boundary",
        "support_bounds",
        "sample_count",
        "observed_statistic",
        "raw_p_value",
        "adjusted_p_value",
        "rejection_threshold",
        "rejected",
        "failure_reason",
    }


def test_deployable_method_contract_has_no_population_truth_input() -> None:
    policy = _policy()
    evidence = _evidence({"candidate": 0.20})
    method = _method(evidence, policy)

    for callable_method in (method.evaluate, method.evaluate_warrant):
        parameters = inspect.signature(callable_method).parameters
        assert "truth" not in parameters
        assert "population_truth" not in parameters

    decision = method.evaluate(evidence, policy)
    artifact = decision.diagnostics["promotion_warrant"]
    assert decision.deployable is True
    assert decision.uses_population_truth is False
    assert decision.benchmark_control_only is False
    assert artifact["uses_population_truth"] is False
    assert artifact["population_truth_accessed"] is False


def test_finite_sample_evidence_does_not_encode_perfect_population_rejection() -> None:
    policy = _policy()
    # An all-zero finite binary-risk sample and strong observed quality can
    # occur with nonzero probability even when an unobserved population risk
    # exceeds its threshold. Population truth is intentionally not an input,
    # so the method must not be tested as if it could reject every unsafe
    # population deterministically.
    evidence = _evidence({"candidate": 0.20}, sample_size=200)

    warrant = _method(evidence, policy).evaluate_warrant(evidence, policy)

    assert warrant.decision == PROMOTE
    assert warrant.selected_policy_id == "candidate"


def test_invalid_warrant_maps_to_no_decision_without_certification() -> None:
    policy = _policy()
    evidence = _evidence({"candidate": 0.20})
    malformed = replace(evidence, phase="development")

    decision = _method(evidence, policy).evaluate(malformed, policy)

    assert decision.decision == "NO_DECISION"
    assert decision.selected_policy_id is None
    assert decision.certified_policy_ids == ()
    assert decision.diagnostics["promotion_warrant"]["decision"] == (
        BLOCKED_INVALID_EVIDENCE
    )
    assert "confirmatory" in decision.decision_reason
