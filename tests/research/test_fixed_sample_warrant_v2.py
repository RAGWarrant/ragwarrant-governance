# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import ast
import hashlib
import math
from pathlib import Path

import numpy as np
import pytest

import ragwarrant.research.fixed_sample_warrant as v1
import ragwarrant.research.fixed_sample_warrant_v2 as v2
from ragwarrant.research.fixed_sample_warrant import HOLM, freeze_candidate_family
from ragwarrant.research.simulator import sha256_json
from ragwarrant.research.types import EvidenceRow, ObservedEvidence, PolicyConfig


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FROZEN_FOCUS1_DIGEST = (
    "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
)
FROZEN_V1_SOURCE_SHA256 = (
    "87e88342354346d0dceb29f45946e846b68f6b1fbaa42a946d5a53822ef4e8ad"
)


def _policy(
    *,
    enabled_risks: tuple[str, ...] = (
        "overall_quality",
        "group_quality",
        "safety_violation_probability",
        "execution_failure_probability",
        "insufficient_evidence_probability",
    ),
    enabled_group_risks: tuple[str, ...] = (),
    group_ids: tuple[str, ...] = ("g1", "g2"),
) -> PolicyConfig:
    return PolicyConfig(
        quality_noninferiority_margin=0.02,
        group_quality_noninferiority_margin=0.03,
        max_safety_violation_probability=0.05,
        max_execution_failure_probability=0.03,
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
    sample_size: int = 256,
    event_counts: dict[str, dict[str, int]] | None = None,
    groups: tuple[str, ...] = ("g1", "g2"),
) -> ObservedEvidence:
    rows: list[EvidenceRow] = []
    for policy_id, delta in sorted(deltas_by_policy.items()):
        counts = (event_counts or {}).get(policy_id, {})
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
                        index < counts.get("safety_violation_probability", 0)
                    ),
                    execution_failure=int(
                        index < counts.get("execution_failure_probability", 0)
                    ),
                    insufficient_evidence=int(
                        index < counts.get("insufficient_evidence_probability", 0)
                    ),
                    cost=1.0 if policy_id == "a" else 1.1,
                    latency=1.0,
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
    specification: v2.VariantSpecification,
) -> v2.FixedSampleMultiRiskWarrantV2:
    family = freeze_candidate_family(
        candidate_policy_ids=evidence.policy_ids,
        incumbent_policy_id="incumbent",
        confirmatory_unit_count=evidence.sample_size,
        policy=policy,
        quality_delta_bounds=(-0.25, 0.25),
        familywise_error_level=0.05,
        multiplicity_method=specification.multiplicity_method,
        selection_objective="minimize_cost",
    )
    return v2.FixedSampleMultiRiskWarrantV2(family, specification)


def _spec(variant_id: str) -> v2.VariantSpecification:
    return next(item for item in v2.PRESPECIFIED_V2_VARIANTS if item.variant_id == variant_id)


def test_hand_calculated_candidate_iut_p_value_is_component_maximum() -> None:
    values = (0.001, 0.20, 0.04, 0.013)
    assert v2.candidate_iut_p_value(values) == 0.20


def test_candidate_iut_rejects_empty_or_invalid_component_family() -> None:
    with pytest.raises(ValueError, match="every enabled"):
        v2.candidate_iut_p_value(())
    with pytest.raises(ValueError, match="between zero and one"):
        v2.candidate_iut_p_value((0.01, 1.01))


def test_hb_matches_independent_primary_reference_cases() -> None:
    assert v2.hoeffding_bentkus_p_value(0.2, 10, 0.5) == pytest.approx(
        0.14551915228366851806640625, rel=1e-14
    )
    assert v2.hoeffding_bentkus_p_value(0.4, 64, 0.54) == pytest.approx(
        0.05906749111367093416871071778, rel=1e-13
    )


def test_hb_endpoints_and_ceiling_convention_are_deterministic() -> None:
    assert v2.hoeffding_bentkus_p_value(0.0, 10, 0.5) == pytest.approx(0.5**10)
    assert v2.hoeffding_bentkus_p_value(1.0, 10, 0.5) == 1.0
    exact = v2.hoeffding_bentkus_p_value(0.2, 10, 0.5)
    just_above = v2.hoeffding_bentkus_p_value(math.nextafter(0.2, math.inf), 10, 0.5)
    just_below = v2.hoeffding_bentkus_p_value(math.nextafter(0.2, 0.0), 10, 0.5)
    assert just_above >= exact
    assert just_below == pytest.approx(exact)


def test_hb_is_numerically_stable_immediately_below_null_threshold() -> None:
    empirical_risk = 0.029999999999
    threshold = 0.03
    divergence = v2.binary_relative_entropy(empirical_risk, threshold)
    p_value = v2.hoeffding_bentkus_p_value(empirical_risk, 256, threshold)
    assert divergence >= 0.0
    assert 0.0 <= p_value <= 1.0


def test_hb_quality_labels_use_the_least_favourable_closed_null() -> None:
    for deltas in ((), (0.0,)):
        result = v2._hb_quality_test(
            policy_id="a",
            risk_id="overall_quality",
            group_id=None,
            deltas=deltas,
            margin=0.02,
            bounds=(-0.25, 0.25),
        )
        assert result.null_hypothesis == "mean_quality_delta <= -0.02"
        assert result.alternative_hypothesis == "mean_quality_delta > -0.02"


@pytest.mark.parametrize(
    ("risk", "count", "threshold"),
    [(-0.1, 10, 0.5), (1.1, 10, 0.5), (0.2, 0, 0.5), (0.2, 10, 0.0), (0.2, 10, 1.0)],
)
def test_hb_fails_closed_on_invalid_inputs(
    risk: float, count: int, threshold: float
) -> None:
    with pytest.raises(ValueError):
        v2.hoeffding_bentkus_p_value(risk, count, threshold)


def test_quality_transform_matches_frozen_support_and_noninferiority() -> None:
    losses, threshold = v2.transform_quality_deltas_to_losses(
        (-0.25, -0.02, 0.25), 0.02, -0.25, 0.25
    )
    assert losses == pytest.approx((1.0, 0.54, 0.0))
    assert threshold == pytest.approx(0.54)
    for delta in (-0.10, -0.02, 0.00, 0.10):
        transformed, tau = v2.transform_quality_deltas_to_losses(
            (delta,), 0.02, -0.25, 0.25
        )
        assert (delta >= -0.02) == (transformed[0] <= tau)


def test_quality_transform_verifies_prompt_special_case_without_using_it() -> None:
    losses, threshold = v2.transform_quality_deltas_to_losses(
        (-1.0, 0.0, 1.0), 0.02, -1.0, 1.0
    )
    assert losses == pytest.approx((1.0, 0.5, 0.0))
    assert threshold == pytest.approx((1.0 + 0.02) / 2.0)


def test_hb_p_values_are_super_uniform_in_prespecified_null_simulation() -> None:
    repetitions = 10_000
    level = 0.05
    threshold = 0.20
    sample_count = 40
    rng = np.random.default_rng(20260830)
    event_counts = rng.binomial(sample_count, threshold, size=repetitions)
    p_values = np.asarray(
        [
            v2.hoeffding_bentkus_p_value(count / sample_count, sample_count, threshold)
            for count in event_counts
        ]
    )
    rejection_rate = float(np.mean(p_values <= level))
    six_sigma_tolerance = 6.0 * math.sqrt(level * (1.0 - level) / repetitions)
    assert rejection_rate <= level + six_sigma_tolerance


def test_candidate_cannot_certify_when_one_enabled_component_is_not_significant() -> None:
    policy = _policy(
        enabled_risks=("execution_failure_probability",), group_ids=("g1",)
    )
    evidence = _evidence(
        {"a": 0.0, "b": 0.0},
        event_counts={"b": {"execution_failure_probability": 30}},
        groups=("g1",),
    )
    warrant = _method(evidence, policy, _spec(v2.VARIANT_B_ID)).evaluate_warrant(
        evidence, policy
    )
    candidate_b = next(item for item in warrant.candidate_tests if item.policy_id == "b")
    assert candidate_b.candidate_iut_p_value > 0.05
    assert not candidate_b.rejected
    assert "b" not in warrant.certified_policy_ids


def test_iut_holm_receives_only_complete_candidate_level_family(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = _policy(
        enabled_risks=("overall_quality", "execution_failure_probability"),
        group_ids=("g1",),
    )
    evidence = _evidence({"a": 0.20, "b": 0.20}, groups=("g1",))
    observed_families: list[tuple[str, ...]] = []
    original = v2.apply_multiplicity

    def capture(p_values: object, alpha: float, method: str) -> object:
        supplied = dict(p_values)  # type: ignore[arg-type]
        observed_families.append(tuple(sorted(supplied)))
        return original(supplied, alpha, method)

    monkeypatch.setattr(v2, "apply_multiplicity", capture)
    _method(evidence, policy, _spec(v2.VARIANT_B_ID)).evaluate_warrant(evidence, policy)
    assert observed_families == [("a", "b")]


def test_flat_hb_variant_applies_holm_to_component_family() -> None:
    policy = _policy(
        enabled_risks=("overall_quality", "execution_failure_probability"),
        group_ids=("g1",),
    )
    evidence = _evidence({"a": 0.20, "b": 0.20}, groups=("g1",))
    warrant = _method(evidence, policy, _spec(v2.VARIANT_C_ID)).evaluate_warrant(
        evidence, policy
    )
    assert all(item.adjusted_candidate_p_value is None for item in warrant.candidate_tests)
    assert len(warrant.component_tests) == 4


def test_constructed_iut_holm_case_controls_candidate_family() -> None:
    candidate_p_values = {
        "unsafe_a": v2.candidate_iut_p_value((0.001, 0.40)),
        "safe_b": v2.candidate_iut_p_value((0.001, 0.006)),
        "safe_c": v2.candidate_iut_p_value((0.010, 0.011)),
    }
    result = v1.holm_step_down_adjust(candidate_p_values, 0.05)
    assert result.rejected_hypothesis_ids == ("safe_b", "safe_c")
    assert "unsafe_a" not in result.rejected_hypothesis_ids


def test_iut_diagnostics_separate_component_threshold_from_candidate_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy(enabled_risks=("overall_quality",), group_ids=("g1",))
    evidence = _evidence({"a": 0.20, "b": 0.20}, groups=("g1",))
    method = _method(evidence, policy, _spec(v2.VARIANT_B_ID))
    components = tuple(
        v2.ComponentTestResult(
            hypothesis_id=f"{policy_id}::overall_quality::overall",
            policy_id=policy_id,
            risk_id="overall_quality",
            group_id=None,
            null_hypothesis="mean_quality_delta <= -0.02",
            alternative_hypothesis="mean_quality_delta > -0.02",
            null_boundary=-0.02,
            support_bounds=(-0.25, 0.25),
            sample_count=evidence.sample_size,
            observed_statistic=0.20,
            raw_p_value=p_value,
            test_implementation=v2.PAIRED_HOEFFDING,
        )
        for policy_id, p_value in (("a", 0.030), ("b", 0.031))
    )
    monkeypatch.setattr(method, "_component_tests", lambda _: components)
    warrant = method.evaluate_warrant(evidence, policy)
    candidates = {item.policy_id: item for item in warrant.candidate_tests}
    component_b = next(item for item in warrant.component_tests if item.policy_id == "b")
    assert candidates["b"].rejected is False
    assert candidates["b"].rejection_threshold == pytest.approx(0.05)
    assert component_b.passed_certification_threshold is True


def test_unsafe_candidate_is_not_deterministically_blocked_in_every_sample() -> None:
    # A population event risk can exceed the threshold while a finite sample
    # happens to contain zero events. The method sees evidence, never truth.
    assert v1.exact_binomial_lower_tail(0, 256, 0.03) < 0.05


def test_v2_reuses_binary_test_behavior_and_v1_source_is_byte_frozen() -> None:
    assert v2._binary_test is v1._binary_test
    source = REPOSITORY_ROOT / "src/ragwarrant/research/fixed_sample_warrant.py"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == FROZEN_V1_SOURCE_SHA256


def test_variant_a_is_not_reimplemented_in_v2() -> None:
    assert all(
        item.variant_id != v2.VARIANT_A_ID for item in v2.PRESPECIFIED_V2_VARIANTS
    )
    policy = _policy(enabled_risks=("execution_failure_probability",), group_ids=("g1",))
    evidence = _evidence({"a": 0.0}, groups=("g1",))
    family = freeze_candidate_family(
        candidate_policy_ids=evidence.policy_ids,
        incumbent_policy_id="incumbent",
        confirmatory_unit_count=evidence.sample_size,
        policy=policy,
        quality_delta_bounds=(-0.25, 0.25),
        familywise_error_level=0.05,
        multiplicity_method=HOLM,
        selection_objective="minimize_cost",
    )
    a_spec = v2.VariantSpecification(
        v2.VARIANT_A_ID,
        v1.METHOD_ID,
        v2.FLAT_WHOLE_FAMILY,
        HOLM,
        v2.PAIRED_HOEFFDING,
    )
    with pytest.raises(ValueError, match="exact v1"):
        v2.FixedSampleMultiRiskWarrantV2(family, a_spec)


def test_focus1_digest_and_full_drand_prohibitions_are_fixed() -> None:
    assert v1.FOCUS1_FREEZE_DIGEST == FROZEN_FOCUS1_DIGEST
    assert v2.FOCUS1_FREEZE_DIGEST == FROZEN_FOCUS1_DIGEST
    config = (
        REPOSITORY_ROOT / "configs/research/fixed_sample_multi_risk_warrant_v2.yaml"
    ).read_text(encoding="utf-8")
    assert "full_profile_permitted: false" in config
    assert "target_drand_round_selected: false" in config


def test_tests_do_not_assert_v2_outperforms_v1() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        names = {
            child.id for child in ast.walk(node.test) if isinstance(child, ast.Name)
        }
        assert not {"v1_rate", "v2_rate"}.issubset(names)
