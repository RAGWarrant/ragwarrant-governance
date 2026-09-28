# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

"""Additive Focus 2 v2 intersection-union fixed-sample warrant.

V1 remains the exact committed baseline.  This module reuses its frozen family,
binary tests, paired-Hoeffding test, and multiplicity implementations without
editing them.  It has no population-truth or artifact-write access.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from .fixed_sample_warrant import (
    BLOCKED_INVALID_EVIDENCE,
    BONFERRONI,
    HOLM,
    INCONCLUSIVE,
    PROMOTE,
    FOCUS1_FREEZE_DIGEST,
    SEED_SCHEDULE_VERSION,
    FixedSampleMultiRiskWarrant,
    FrozenCandidateFamily,
    _binary_test,
    _hypothesis_id,
    _log_binomial_probability,
    _logsumexp,
    _mean,
    _quality_test,
    _finite_real,
    _positive_count,
    _probability,
    apply_multiplicity,
)
from .methods import RISK_EVIDENCE_FIELDS
from .simulator import sha256_json
from .types import BINARY_RISKS, MethodDecision, ObservedEvidence, PolicyConfig


METHOD_ID = "fixed_sample_multi_risk_warrant_v2"
VARIANT_A_ID = "A_V1_BASELINE"
VARIANT_B_ID = "B_IUT_HOEFFDING"
VARIANT_C_ID = "C_FLAT_HB"
VARIANT_D_ID = "D_V2_COMBINED"
VARIANT_D_BONFERRONI_ID = "D_V2_BONFERRONI_COMPARISON"

FLAT_WHOLE_FAMILY = "flat_whole_family"
CANDIDATE_IUT = "candidate_iut"
PAIRED_HOEFFDING = "paired_hoeffding"
HOEFFDING_BENTKUS_QUALITY = "hoeffding_bentkus_quality"
SUPPORTED_MULTIPLICITY_SCOPES = (FLAT_WHOLE_FAMILY, CANDIDATE_IUT)
SUPPORTED_QUALITY_TESTS = (PAIRED_HOEFFDING, HOEFFDING_BENTKUS_QUALITY)
MIN_POSITIVE_FLOAT = math.ulp(0.0)
LOG_MIN_POSITIVE_FLOAT = math.log(MIN_POSITIVE_FLOAT)


@dataclass(frozen=True)
class VariantSpecification:
    variant_id: str
    method_id: str
    multiplicity_scope: str
    multiplicity_method: str
    quality_test: str

    def __post_init__(self) -> None:
        for name, value in (("variant_id", self.variant_id), ("method_id", self.method_id)):
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be a non-empty canonical string")
        if self.multiplicity_scope not in SUPPORTED_MULTIPLICITY_SCOPES:
            raise ValueError("unknown multiplicity scope")
        if self.multiplicity_method not in {HOLM, BONFERRONI}:
            raise ValueError("unknown multiplicity method")
        if self.quality_test not in SUPPORTED_QUALITY_TESTS:
            raise ValueError("unknown quality test")

    def as_dict(self) -> dict[str, str]:
        return {
            "variant_id": self.variant_id,
            "method_id": self.method_id,
            "multiplicity_scope": self.multiplicity_scope,
            "multiplicity_method": self.multiplicity_method,
            "quality_test": self.quality_test,
        }


PRESPECIFIED_V2_VARIANTS = (
    VariantSpecification(
        VARIANT_B_ID,
        "fixed_sample_multi_risk_warrant_v2_iut_hoeffding_ablation",
        CANDIDATE_IUT,
        HOLM,
        PAIRED_HOEFFDING,
    ),
    VariantSpecification(
        VARIANT_C_ID,
        "fixed_sample_multi_risk_warrant_v2_flat_hb_ablation",
        FLAT_WHOLE_FAMILY,
        HOLM,
        HOEFFDING_BENTKUS_QUALITY,
    ),
    VariantSpecification(
        VARIANT_D_ID,
        METHOD_ID,
        CANDIDATE_IUT,
        HOLM,
        HOEFFDING_BENTKUS_QUALITY,
    ),
    VariantSpecification(
        VARIANT_D_BONFERRONI_ID,
        "fixed_sample_multi_risk_warrant_v2_bonferroni_comparison",
        CANDIDATE_IUT,
        BONFERRONI,
        HOEFFDING_BENTKUS_QUALITY,
    ),
)


@dataclass(frozen=True)
class ComponentTestResult:
    hypothesis_id: str
    policy_id: str
    risk_id: str
    group_id: str | None
    null_hypothesis: str
    alternative_hypothesis: str
    null_boundary: float
    support_bounds: tuple[float, float] | None
    sample_count: int
    observed_statistic: float | None
    raw_p_value: float
    test_implementation: str
    failure_reason: str | None = None
    multiplicity_adjusted_p_value: float | None = None
    certification_threshold: float | None = None
    passed_certification_threshold: bool | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "policy_id": self.policy_id,
            "risk_id": self.risk_id,
            "group_id": self.group_id,
            "null_hypothesis": self.null_hypothesis,
            "alternative_hypothesis": self.alternative_hypothesis,
            "null_boundary": self.null_boundary,
            "support_bounds": (
                list(self.support_bounds) if self.support_bounds is not None else None
            ),
            "sample_count": self.sample_count,
            "observed_statistic": self.observed_statistic,
            "raw_p_value": self.raw_p_value,
            "test_implementation": self.test_implementation,
            "failure_reason": self.failure_reason,
            "multiplicity_adjusted_p_value": self.multiplicity_adjusted_p_value,
            "certification_threshold": self.certification_threshold,
            "passed_certification_threshold": self.passed_certification_threshold,
        }


@dataclass(frozen=True)
class CandidateTestResult:
    policy_id: str
    component_hypothesis_ids: tuple[str, ...]
    candidate_iut_p_value: float
    adjusted_candidate_p_value: float | None
    rejection_threshold: float | None
    rejected: bool
    dominant_component_hypothesis_id: str
    dominant_risk_id: str
    dominant_group_id: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "component_hypothesis_ids": list(self.component_hypothesis_ids),
            "candidate_iut_p_value": self.candidate_iut_p_value,
            "adjusted_candidate_p_value": self.adjusted_candidate_p_value,
            "rejection_threshold": self.rejection_threshold,
            "rejected": self.rejected,
            "dominant_component_hypothesis_id": self.dominant_component_hypothesis_id,
            "dominant_risk_id": self.dominant_risk_id,
            "dominant_group_id": self.dominant_group_id,
        }


@dataclass(frozen=True)
class V2PromotionWarrant:
    specification: VariantSpecification
    decision: str
    decision_reason: str
    family: FrozenCandidateFamily
    evidence_hash: str
    certified_policy_ids: tuple[str, ...]
    selected_policy_id: str | None
    component_tests: tuple[ComponentTestResult, ...]
    candidate_tests: tuple[CandidateTestResult, ...]
    candidate_summaries: tuple[tuple[str, Mapping[str, float]], ...]
    invalid_evidence_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        primary = (
            "mean_cost"
            if self.family.selection_objective == "minimize_cost"
            else "mean_latency"
        )
        secondary = "mean_latency" if primary == "mean_cost" else "mean_cost"
        selected_summary = dict(self.candidate_summaries).get(
            self.selected_policy_id or ""
        )
        return {
            "schema_version": "2.0",
            "method": self.specification.method_id,
            "method_id": self.specification.method_id,
            "variant_id": self.specification.variant_id,
            "status": "COMPLETED",
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "familywise_error_level": self.family.familywise_error_level,
            "multiplicity_scope": self.specification.multiplicity_scope,
            "multiplicity_method": self.specification.multiplicity_method,
            "quality_test": self.specification.quality_test,
            "candidate_family_frozen": True,
            "family_hash": self.family.family_hash,
            "candidate_family_size": len(self.family.candidate_policy_ids),
            "incumbent_policy_id": self.family.incumbent_policy_id,
            "confirmatory_unit_count": self.family.confirmatory_unit_count,
            "certified_policy_ids": list(self.certified_policy_ids),
            "selected_policy_id": self.selected_policy_id,
            "component_tests": [test.as_dict() for test in self.component_tests],
            "candidate_tests": [test.as_dict() for test in self.candidate_tests],
            "enabled_risks": list(self.family.enabled_risks),
            "operational_selection_objective": {
                "primary": primary,
                "secondary": secondary,
                "tertiary": "lexical_policy_id",
                "selected_value": (
                    selected_summary.get(primary)
                    if selected_summary is not None
                    else None
                ),
            },
            "diagnostics": {
                "evidence_hash": self.evidence_hash,
                "component_hypothesis_count": len(self.component_tests),
                "candidate_hypothesis_count": len(self.candidate_tests),
                "candidate_summaries": {
                    policy_id: dict(values)
                    for policy_id, values in self.candidate_summaries
                },
                "invalid_evidence_reason": self.invalid_evidence_reason,
                "family_definition": self.family.as_dict(),
                "variant_specification": self.specification.as_dict(),
                "candidate_iut_definition": "max_enabled_component_raw_p_values",
                "boundary_convention": (
                    "truth equality is safe; p-values use least-favourable closure boundaries"
                ),
                "development_evidence_used_for_certification": False,
                "post_hoc_filtered": False,
            },
            "deployable": True,
            "uses_population_truth": False,
            "benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST,
            "seed_schedule_version": SEED_SCHEDULE_VERSION,
            "full_profile_used": False,
            "population_truth_accessed": False,
            "research_only": True,
            "production_integrated": False,
        }

    def to_method_decision(self) -> MethodDecision:
        return MethodDecision(
            method_id=self.specification.method_id,
            selected_policy_id=self.selected_policy_id,
            certified_policy_ids=self.certified_policy_ids,
            decision=PROMOTE if self.decision == PROMOTE else "NO_DECISION",
            decision_reason=self.decision_reason,
            deployable=True,
            uses_population_truth=False,
            benchmark_control_only=False,
            diagnostics={
                "evidence_hash": self.evidence_hash,
                "variant_id": self.specification.variant_id,
                "multiplicity_scope": self.specification.multiplicity_scope,
                "multiplicity_method": self.specification.multiplicity_method,
                "quality_test": self.specification.quality_test,
                "familywise_error_level": self.family.familywise_error_level,
                "family_hash": self.family.family_hash,
                "promotion_warrant": self.as_dict(),
            },
        )


def _safe_exp_probability(log_probability: float) -> float:
    if not math.isfinite(log_probability):
        if log_probability == -math.inf:
            return MIN_POSITIVE_FLOAT
        raise ValueError("log probability must be finite or negative infinity")
    if log_probability >= 0.0:
        return 1.0
    if log_probability <= LOG_MIN_POSITIVE_FLOAT:
        return MIN_POSITIVE_FLOAT
    return math.exp(log_probability)


def binary_relative_entropy(value: float, reference: float) -> float:
    """Return Bernoulli KL with explicit, finite endpoint conventions."""

    x = _probability(value, "value")
    q = _probability(reference, "reference")
    if q in {0.0, 1.0}:
        raise ValueError("reference must be strictly between zero and one")
    if x == q:
        return 0.0
    if x == 0.0:
        return -math.log1p(-q)
    if x == 1.0:
        return -math.log(q)
    delta = x - q
    terms = (
        x * math.log1p(delta / q),
        (1.0 - x) * math.log1p(-delta / (1.0 - q)),
    )
    result = math.fsum(terms)
    if not math.isfinite(result):
        raise ValueError("binary relative entropy calculation failed")
    if result < 0.0:
        roundoff_tolerance = 16.0 * math.ulp(max(abs(terms[0]), abs(terms[1])))
        if result >= -roundoff_tolerance:
            return 0.0
        raise ValueError("binary relative entropy calculation failed")
    return result


def _log_binomial_lower_tail(
    event_count: int, sample_count: int, probability: float
) -> float:
    n = _positive_count(sample_count, "sample_count")
    if isinstance(event_count, bool) or not isinstance(event_count, int):
        raise ValueError("event_count must be an integer")
    if event_count < 0:
        return -math.inf
    if event_count >= n:
        return 0.0
    q = _probability(probability, "probability")
    if q in {0.0, 1.0}:
        raise ValueError("probability must be strictly between zero and one")
    return _logsumexp(
        _log_binomial_probability(n, index, q)
        for index in range(event_count + 1)
    )


def hoeffding_bentkus_p_value(
    empirical_risk: float, sample_count: int, risk_threshold: float
) -> float:
    """LTT Proposition 2.2 p-value for independent bounded [0,1] losses."""

    r_hat = _probability(empirical_risk, "empirical_risk")
    n = _positive_count(sample_count, "sample_count")
    threshold = _probability(risk_threshold, "risk_threshold")
    if threshold in {0.0, 1.0}:
        raise ValueError("risk_threshold must be strictly between zero and one")

    clipped_mean = min(r_hat, threshold)
    log_hoeffding = -n * binary_relative_entropy(clipped_mean, threshold)
    cutoff = min(n, math.ceil(n * r_hat))
    log_bentkus = 1.0 + _log_binomial_lower_tail(cutoff, n, threshold)
    p_value = min(
        1.0,
        _safe_exp_probability(log_hoeffding),
        _safe_exp_probability(log_bentkus),
    )
    if not math.isfinite(p_value):
        raise ValueError("Hoeffding-Bentkus p-value is nonfinite")
    return p_value


def transform_quality_deltas_to_losses(
    deltas: Iterable[float],
    noninferiority_margin: float,
    lower_bound: float,
    upper_bound: float,
) -> tuple[tuple[float, ...], float]:
    """Transform bounded paired deltas to the equivalent [0,1] LTT loss."""

    margin = _finite_real(noninferiority_margin, "noninferiority_margin")
    if margin < 0.0:
        raise ValueError("noninferiority_margin must be nonnegative")
    lower = _finite_real(lower_bound, "lower_bound")
    upper = _finite_real(upper_bound, "upper_bound")
    if lower >= upper:
        raise ValueError("lower_bound must be strictly less than upper_bound")
    try:
        values = tuple(_finite_real(value, "quality delta") for value in deltas)
    except TypeError as exc:
        raise ValueError("quality deltas must be a non-empty iterable") from exc
    if not values:
        raise ValueError("quality deltas must be non-empty")
    if any(value < lower or value > upper for value in values):
        raise ValueError("quality delta lies outside the prespecified support")
    width = upper - lower
    threshold = (upper + margin) / width
    if not 0.0 < threshold < 1.0:
        raise ValueError("transformed noninferiority threshold must lie in (0,1)")
    losses = tuple((upper - value) / width for value in values)
    if any(not 0.0 <= value <= 1.0 for value in losses):
        raise ValueError("quality loss transformation left [0,1]")
    return losses, threshold


def hoeffding_bentkus_quality_p_value(
    deltas: Iterable[float],
    noninferiority_margin: float,
    lower_bound: float,
    upper_bound: float,
) -> float:
    losses, threshold = transform_quality_deltas_to_losses(
        deltas, noninferiority_margin, lower_bound, upper_bound
    )
    return hoeffding_bentkus_p_value(
        math.fsum(losses) / len(losses), len(losses), threshold
    )


def candidate_iut_p_value(component_p_values: Iterable[float]) -> float:
    try:
        values = tuple(
            _probability(value, "component p-value") for value in component_p_values
        )
    except TypeError as exc:
        raise ValueError("component p-values must be a non-empty iterable") from exc
    if not values:
        raise ValueError("candidate IUT requires every enabled component p-value")
    return max(values)


def _from_v1_pending(test: Any, implementation: str) -> ComponentTestResult:
    return ComponentTestResult(
        hypothesis_id=test.hypothesis_id,
        policy_id=test.policy_id,
        risk_id=test.risk_id,
        group_id=test.group_id,
        null_hypothesis=test.null_hypothesis,
        alternative_hypothesis=test.alternative_hypothesis,
        null_boundary=test.null_boundary,
        support_bounds=test.support_bounds,
        sample_count=test.sample_count,
        observed_statistic=test.observed_statistic,
        raw_p_value=test.raw_p_value,
        test_implementation=implementation,
        failure_reason=test.failure_reason,
    )


def _hb_quality_test(
    *,
    policy_id: str,
    risk_id: str,
    group_id: str | None,
    deltas: tuple[float, ...],
    margin: float,
    bounds: tuple[float, float],
) -> ComponentTestResult:
    hypothesis_id = _hypothesis_id(policy_id, risk_id, group_id)
    if not deltas:
        return ComponentTestResult(
            hypothesis_id=hypothesis_id,
            policy_id=policy_id,
            risk_id=risk_id,
            group_id=group_id,
            null_hypothesis=f"mean_quality_delta <= {-margin}",
            alternative_hypothesis=f"mean_quality_delta > {-margin}",
            null_boundary=-margin,
            support_bounds=bounds,
            sample_count=0,
            observed_statistic=None,
            raw_p_value=1.0,
            test_implementation=HOEFFDING_BENTKUS_QUALITY,
            failure_reason="missing_group_evidence",
        )
    return ComponentTestResult(
        hypothesis_id=hypothesis_id,
        policy_id=policy_id,
        risk_id=risk_id,
        group_id=group_id,
        null_hypothesis=f"mean_quality_delta <= {-margin}",
        alternative_hypothesis=f"mean_quality_delta > {-margin}",
        null_boundary=-margin,
        support_bounds=bounds,
        sample_count=len(deltas),
        observed_statistic=_mean(deltas),
        raw_p_value=hoeffding_bentkus_quality_p_value(
            deltas, margin, bounds[0], bounds[1]
        ),
        test_implementation=HOEFFDING_BENTKUS_QUALITY,
    )


class FixedSampleMultiRiskWarrantV2:
    """Truth-isolated v2 warrant for one prespecified ablation specification."""

    def __init__(
        self, family: FrozenCandidateFamily, specification: VariantSpecification
    ) -> None:
        if specification.variant_id == VARIANT_A_ID:
            raise ValueError("variant A must call the exact v1 implementation")
        if family.multiplicity_method != specification.multiplicity_method:
            raise ValueError("frozen family multiplicity differs from v2 specification")
        self.family = family
        self.specification = specification
        self._v1_contract = FixedSampleMultiRiskWarrant(family)

    def _component_tests(
        self, evidence: ObservedEvidence
    ) -> tuple[ComponentTestResult, ...]:
        tests: list[ComponentTestResult] = []
        bounds = self.family.quality_delta_bounds
        for policy_id in self.family.candidate_policy_ids:
            rows = evidence.rows_for(policy_id)
            quality_factory = (
                _quality_test
                if self.specification.quality_test == PAIRED_HOEFFDING
                else _hb_quality_test
            )
            if "overall_quality" in self.family.enabled_risks:
                pending = quality_factory(
                    policy_id=policy_id,
                    risk_id="overall_quality",
                    group_id=None,
                    deltas=tuple(row.quality_delta for row in rows),
                    margin=self.family.quality_noninferiority_margin,
                    bounds=bounds,
                )
                tests.append(
                    _from_v1_pending(pending, PAIRED_HOEFFDING)
                    if self.specification.quality_test == PAIRED_HOEFFDING
                    else pending
                )
            if "group_quality" in self.family.enabled_risks:
                for group_id in self.family.group_ids:
                    pending = quality_factory(
                        policy_id=policy_id,
                        risk_id="group_quality",
                        group_id=group_id,
                        deltas=tuple(
                            row.quality_delta for row in rows if row.group_id == group_id
                        ),
                        margin=self.family.group_quality_noninferiority_margin,
                        bounds=bounds,
                    )
                    tests.append(
                        _from_v1_pending(pending, PAIRED_HOEFFDING)
                        if self.specification.quality_test == PAIRED_HOEFFDING
                        else pending
                    )
            for risk_id, evidence_field in RISK_EVIDENCE_FIELDS.items():
                if risk_id not in self.family.enabled_risks:
                    continue
                threshold = self.family.binary_threshold(risk_id)
                tests.append(
                    _from_v1_pending(
                        _binary_test(
                            policy_id=policy_id,
                            risk_id=risk_id,
                            group_id=None,
                            values=tuple(
                                int(getattr(row, evidence_field)) for row in rows
                            ),
                            threshold=threshold,
                        ),
                        "exact_binomial_lower_tail_v1",
                    )
                )
                if risk_id in self.family.enabled_group_risks:
                    for group_id in self.family.group_ids:
                        tests.append(
                            _from_v1_pending(
                                _binary_test(
                                    policy_id=policy_id,
                                    risk_id=risk_id,
                                    group_id=group_id,
                                    values=tuple(
                                        int(getattr(row, evidence_field))
                                        for row in rows
                                        if row.group_id == group_id
                                    ),
                                    threshold=threshold,
                                ),
                                "exact_binomial_lower_tail_v1",
                            )
                        )
        if not tests or len({test.hypothesis_id for test in tests}) != len(tests):
            raise ValueError("frozen candidate-risk family is empty or duplicated")
        return tuple(tests)

    def _invalid_warrant(
        self, evidence: ObservedEvidence, reason: str
    ) -> V2PromotionWarrant:
        return V2PromotionWarrant(
            specification=self.specification,
            decision=BLOCKED_INVALID_EVIDENCE,
            decision_reason=f"confirmatory evidence failed closed: {reason}",
            family=self.family,
            evidence_hash=str(getattr(evidence, "evidence_hash", "")),
            certified_policy_ids=(),
            selected_policy_id=None,
            component_tests=(),
            candidate_tests=(),
            candidate_summaries=(),
            invalid_evidence_reason=reason,
        )

    def evaluate_warrant(
        self, evidence: ObservedEvidence, policy: PolicyConfig
    ) -> V2PromotionWarrant:
        try:
            self._v1_contract._validate_contract(evidence, policy)
            components = self._component_tests(evidence)
            summaries = self._v1_contract._candidate_summaries(evidence)
            by_candidate = {
                policy_id: tuple(
                    test for test in components if test.policy_id == policy_id
                )
                for policy_id in self.family.candidate_policy_ids
            }
            if any(not values for values in by_candidate.values()):
                raise ValueError("candidate is missing its enabled risk components")

            candidate_tests: list[CandidateTestResult] = []
            if self.specification.multiplicity_scope == CANDIDATE_IUT:
                candidate_raw = {
                    policy_id: candidate_iut_p_value(
                        test.raw_p_value for test in values
                    )
                    for policy_id, values in by_candidate.items()
                }
                adjusted = apply_multiplicity(
                    candidate_raw,
                    self.family.familywise_error_level,
                    self.specification.multiplicity_method,
                )
                for policy_id, values in by_candidate.items():
                    dominant = min(
                        values, key=lambda item: (-item.raw_p_value, item.hypothesis_id)
                    )
                    candidate_tests.append(
                        CandidateTestResult(
                            policy_id=policy_id,
                            component_hypothesis_ids=tuple(
                                test.hypothesis_id for test in values
                            ),
                            candidate_iut_p_value=candidate_raw[policy_id],
                            adjusted_candidate_p_value=adjusted.adjusted_p_value(policy_id),
                            rejection_threshold=adjusted.rejection_threshold(policy_id),
                            rejected=adjusted.is_rejected(policy_id),
                            dominant_component_hypothesis_id=dominant.hypothesis_id,
                            dominant_risk_id=dominant.risk_id,
                            dominant_group_id=dominant.group_id,
                        )
                    )
            else:
                adjusted = apply_multiplicity(
                    ((test.hypothesis_id, test.raw_p_value) for test in components),
                    self.family.familywise_error_level,
                    self.specification.multiplicity_method,
                )
                for policy_id, values in by_candidate.items():
                    dominant = min(
                        values, key=lambda item: (-item.raw_p_value, item.hypothesis_id)
                    )
                    candidate_tests.append(
                        CandidateTestResult(
                            policy_id=policy_id,
                            component_hypothesis_ids=tuple(
                                test.hypothesis_id for test in values
                            ),
                            candidate_iut_p_value=candidate_iut_p_value(
                                test.raw_p_value for test in values
                            ),
                            adjusted_candidate_p_value=None,
                            rejection_threshold=None,
                            rejected=all(
                                adjusted.is_rejected(test.hypothesis_id)
                                for test in values
                            ),
                            dominant_component_hypothesis_id=dominant.hypothesis_id,
                            dominant_risk_id=dominant.risk_id,
                            dominant_group_id=dominant.group_id,
                        )
                    )
            candidate_test_map = {
                item.policy_id: item for item in candidate_tests
            }
            if self.specification.multiplicity_scope == CANDIDATE_IUT:
                components = tuple(
                    replace(
                        component,
                        certification_threshold=candidate_test_map[
                            component.policy_id
                        ].rejection_threshold,
                        passed_certification_threshold=(
                            component.raw_p_value
                            <= float(
                                candidate_test_map[
                                    component.policy_id
                                ].rejection_threshold
                            )
                        ),
                    )
                    for component in components
                )
            else:
                components = tuple(
                    replace(
                        component,
                        multiplicity_adjusted_p_value=adjusted.adjusted_p_value(
                            component.hypothesis_id
                        ),
                        certification_threshold=adjusted.rejection_threshold(
                            component.hypothesis_id
                        ),
                        passed_certification_threshold=adjusted.is_rejected(
                            component.hypothesis_id
                        ),
                    )
                    for component in components
                )
        except (KeyError, TypeError, ValueError) as exc:
            return self._invalid_warrant(evidence, str(exc))

        candidate_tests_tuple = tuple(candidate_tests)
        certified = tuple(
            test.policy_id for test in candidate_tests_tuple if test.rejected
        )
        summary_map = dict(summaries)
        primary = (
            "mean_cost"
            if self.family.selection_objective == "minimize_cost"
            else "mean_latency"
        )
        secondary = "mean_latency" if primary == "mean_cost" else "mean_cost"
        selected = min(
            certified,
            key=lambda policy_id: (
                summary_map[policy_id][primary],
                summary_map[policy_id][secondary],
                policy_id,
            ),
            default=None,
        )
        decision = PROMOTE if selected is not None else INCONCLUSIVE
        return V2PromotionWarrant(
            specification=self.specification,
            decision=decision,
            decision_reason=(
                "selected the operational optimum after v2 certification"
                if selected is not None
                else (
                    "no candidate-level null was rejected by the prespecified "
                    "multiplicity procedure"
                )
            ),
            family=self.family,
            evidence_hash=evidence.evidence_hash,
            certified_policy_ids=certified,
            selected_policy_id=selected,
            component_tests=components,
            candidate_tests=candidate_tests_tuple,
            candidate_summaries=summaries,
        )

    def evaluate(
        self, evidence: ObservedEvidence, policy: PolicyConfig, method_seed: int = 0
    ) -> MethodDecision:
        del method_seed
        return self.evaluate_warrant(evidence, policy).to_method_decision()


def v2_contract_digest() -> str:
    return sha256_json(
        {
            "focus1_freeze_digest": FOCUS1_FREEZE_DIGEST,
            "method_id": METHOD_ID,
            "variants": [item.as_dict() for item in PRESPECIFIED_V2_VARIANTS],
            "candidate_p_value": "max_enabled_component_raw_p_values",
            "quality_transform": "(upper_bound-delta)/(upper_bound-lower_bound)",
            "hb_binomial_cutoff": "ceil(sample_count*empirical_risk)",
        }
    )


__all__ = [
    "CANDIDATE_IUT",
    "FLAT_WHOLE_FAMILY",
    "HOEFFDING_BENTKUS_QUALITY",
    "METHOD_ID",
    "PAIRED_HOEFFDING",
    "PRESPECIFIED_V2_VARIANTS",
    "VARIANT_A_ID",
    "VARIANT_B_ID",
    "VARIANT_C_ID",
    "VARIANT_D_BONFERRONI_ID",
    "VARIANT_D_ID",
    "CandidateTestResult",
    "ComponentTestResult",
    "FixedSampleMultiRiskWarrantV2",
    "V2PromotionWarrant",
    "VariantSpecification",
    "binary_relative_entropy",
    "candidate_iut_p_value",
    "hoeffding_bentkus_p_value",
    "hoeffding_bentkus_quality_p_value",
    "transform_quality_deltas_to_losses",
    "v2_contract_digest",
]
