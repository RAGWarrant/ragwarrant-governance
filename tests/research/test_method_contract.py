from __future__ import annotations

import inspect
from dataclasses import replace

import numpy as np
import pytest

from ragwarrant.research.methods import (
    CorrectedPairedBootstrapGate,
    NaivePointEstimate,
    paired_bootstrap_lower_bound,
)
from ragwarrant.research.simulator import sha256_json
from ragwarrant.research.types import EvidenceRow, ObservedEvidence, PolicyConfig


def _policy(sample_bootstraps: int = 64) -> PolicyConfig:
    return PolicyConfig(
        quality_noninferiority_margin=0.02,
        group_quality_noninferiority_margin=0.03,
        max_safety_violation_probability=0.10,
        max_execution_failure_probability=0.10,
        max_insufficient_evidence_probability=0.10,
        cost_weight=1.0,
        latency_weight=0.1,
        confidence_level=0.95,
        bootstrap_resamples=sample_bootstraps,
        enabled_risks=(
            "overall_quality",
            "group_quality",
            "safety_violation_probability",
            "execution_failure_probability",
            "insufficient_evidence_probability",
        ),
        enabled_group_risks=(),
        group_ids=("g",),
    )


def _evidence(
    deltas_by_policy: dict[str, list[float]],
    events_by_policy: dict[str, tuple[int, int, int]] | None = None,
) -> ObservedEvidence:
    sample_size = len(next(iter(deltas_by_policy.values())))
    rows = []
    for policy_id, deltas in sorted(deltas_by_policy.items()):
        assert len(deltas) == sample_size
        safety, execution, insufficient = (events_by_policy or {}).get(policy_id, (0, 0, 0))
        for index, delta in enumerate(deltas):
            rows.append(
                EvidenceRow(
                    example_id=f"confirmatory-{index:06d}",
                    group_id="g",
                    policy_id=policy_id,
                    incumbent_quality=0.70,
                    candidate_quality=0.70 + delta,
                    quality_delta=delta,
                    safety_violation=safety if index == 0 else 0,
                    execution_failure=execution if index == 0 else 0,
                    insufficient_evidence=insufficient if index == 0 else 0,
                    cost=0.8 if policy_id == "safe" else 0.6,
                    latency=1.0,
                )
            )
    ordered = tuple(sorted(rows, key=lambda row: (row.example_id, row.policy_id)))
    digest = sha256_json([row.as_dict() for row in ordered])
    return ObservedEvidence("hand__n100", "confirmatory", 0, sample_size, ordered, digest)


def test_naive_point_estimate_certifies_all_eligible_and_selects_objective() -> None:
    evidence = _evidence({"safe": [0.02] * 100, "unsafe": [-0.04] * 100})
    decision = NaivePointEstimate().evaluate(evidence, _policy())
    assert decision.certified_policy_ids == ("safe",)
    assert decision.selected_policy_id == "safe"
    assert decision.decision == "PROMOTE"


def test_corrected_gate_uses_one_sided_bounds_and_fails_closed() -> None:
    evidence = _evidence({"safe": [0.08] * 100, "unsafe": [-0.08] * 100})
    decision = CorrectedPairedBootstrapGate().evaluate(evidence, _policy(), method_seed=44)
    assert decision.certified_policy_ids == ("safe",)
    assert decision.selected_policy_id == "safe"
    assert decision.diagnostics["evidence_hash"] == evidence.evidence_hash


def test_bootstrap_lower_bound_matches_explicit_replacement_sampling() -> None:
    values = np.asarray([-0.2, 0.0, 0.1, 0.5])
    seed = 938
    resamples = 50
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(resamples, len(values)))
    expected = float(np.quantile(values[indices].mean(axis=1), 0.05))
    actual = paired_bootstrap_lower_bound(values, 0.95, resamples, seed)
    assert actual == pytest.approx(expected)
    assert len({tuple(row) for row in indices}) > 1


def test_deployable_method_signatures_do_not_accept_population_truth() -> None:
    for method in (NaivePointEstimate(), CorrectedPairedBootstrapGate()):
        parameters = inspect.signature(method.evaluate).parameters
        assert "truth" not in parameters
        assert "population_truth" not in parameters


def test_malformed_or_empty_evidence_raises() -> None:
    empty = ObservedEvidence("empty__n1", "confirmatory", 0, 1, (), "bad")
    with pytest.raises(ValueError, match="contain rows"):
        NaivePointEstimate().evaluate(empty, _policy())


def test_development_evidence_is_rejected_by_deployable_method() -> None:
    evidence = _evidence({"safe": [0.02] * 10})
    development = ObservedEvidence(
        evidence.scenario_id,
        "development",
        evidence.trial_index,
        evidence.sample_size,
        evidence.rows,
        evidence.evidence_hash,
    )
    with pytest.raises(ValueError, match="confirmatory"):
        NaivePointEstimate().evaluate(development, _policy())


def test_stale_evidence_hash_is_rejected() -> None:
    evidence = _evidence({"safe": [0.02] * 10})
    stale = replace(evidence, evidence_hash="0" * 64)
    with pytest.raises(ValueError, match="hash does not match"):
        NaivePointEstimate().evaluate(stale, _policy())


def test_duplicate_policy_example_rows_are_rejected() -> None:
    evidence = _evidence({"safe": [0.02] * 10})
    duplicated_rows = evidence.rows[:-1] + (evidence.rows[0],)
    duplicated = replace(evidence, rows=duplicated_rows)
    with pytest.raises(ValueError, match="duplicate policy/example"):
        NaivePointEstimate().evaluate(duplicated, _policy())


def test_candidates_must_share_group_and_incumbent_pairing() -> None:
    evidence = _evidence({"safe": [0.02] * 10, "unsafe": [-0.04] * 10})
    changed = list(evidence.rows)
    index = next(
        index
        for index, row in enumerate(changed)
        if row.policy_id == "unsafe" and row.example_id == "confirmatory-000000"
    )
    changed[index] = replace(changed[index], incumbent_quality=0.69, candidate_quality=0.65)
    changed_tuple = tuple(changed)
    inconsistent = replace(
        evidence,
        rows=changed_tuple,
        evidence_hash=sha256_json([row.as_dict() for row in changed_tuple]),
    )
    with pytest.raises(ValueError, match="share paired"):
        NaivePointEstimate().evaluate(inconsistent, _policy())
