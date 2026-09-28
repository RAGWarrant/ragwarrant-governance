"""Truth-isolated fixed-sample multi-risk certification for Focus 2.

The module implements the reviewed finite-sample tests, whole-family
multiplicity procedures, candidate certification, and post-certification
operational selection.  It has no population-truth or artifact-write access.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Any

from .methods import RISK_EVIDENCE_FIELDS, _validate_evidence
from .simulator import sha256_json
from .types import (
    BINARY_RISKS,
    ENABLED_RISKS,
    MethodDecision,
    ObservedEvidence,
    PolicyConfig,
)


BONFERRONI = "bonferroni"
HOLM = "holm"
SUPPORTED_MULTIPLICITY_METHODS = (BONFERRONI, HOLM)
METHOD_ID = "fixed_sample_multi_risk_warrant_v1"
FOCUS1_FREEZE_DIGEST = (
    "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
)
SEED_SCHEDULE_VERSION = 2
PROMOTE = "PROMOTE"
INCONCLUSIVE = "INCONCLUSIVE"
BLOCKED_INVALID_EVIDENCE = "BLOCKED_INVALID_EVIDENCE"
SELECTION_OBJECTIVES = ("minimize_cost", "minimize_latency")


@dataclass(frozen=True)
class MultiplicityResult:
    """Deterministic result for one complete, prespecified hypothesis family."""

    method: str
    alpha: float
    family_size: int
    ordered_hypothesis_ids: tuple[str, ...]
    raw_p_values: tuple[tuple[str, float], ...]
    adjusted_p_values: tuple[tuple[str, float], ...]
    rejection_thresholds: tuple[tuple[str, float], ...]
    rejected_hypothesis_ids: tuple[str, ...]

    def adjusted_p_value(self, hypothesis_id: str) -> float:
        return _lookup(self.adjusted_p_values, hypothesis_id)

    def rejection_threshold(self, hypothesis_id: str) -> float:
        return _lookup(self.rejection_thresholds, hypothesis_id)

    def is_rejected(self, hypothesis_id: str) -> bool:
        return hypothesis_id in self.rejected_hypothesis_ids


@dataclass(frozen=True)
class FrozenCandidateFamily:
    candidate_policy_ids: tuple[str, ...]
    incumbent_policy_id: str
    enabled_risks: tuple[str, ...]
    enabled_group_risks: tuple[str, ...]
    group_ids: tuple[str, ...]
    confirmatory_unit_count: int
    quality_noninferiority_margin: float
    group_quality_noninferiority_margin: float
    binary_thresholds: tuple[tuple[str, float], ...]
    quality_delta_bounds: tuple[float, float]
    familywise_error_level: float
    multiplicity_method: str
    selection_objective: str

    def __post_init__(self) -> None:
        if not self.candidate_policy_ids:
            raise ValueError("candidate family must not be empty")
        if tuple(sorted(self.candidate_policy_ids)) != self.candidate_policy_ids:
            raise ValueError("candidate policy IDs must be sorted before family freezing")
        if len(set(self.candidate_policy_ids)) != len(self.candidate_policy_ids):
            raise ValueError("candidate family contains duplicate policy IDs")
        if any(
            not value or value.strip() != value or "::" in value
            for value in self.candidate_policy_ids
        ):
            raise ValueError("candidate policy IDs must be non-empty canonical strings")
        if (
            not self.incumbent_policy_id
            or self.incumbent_policy_id.strip() != self.incumbent_policy_id
            or "::" in self.incumbent_policy_id
        ):
            raise ValueError("incumbent policy ID must be a non-empty canonical string")
        if self.incumbent_policy_id in self.candidate_policy_ids:
            raise ValueError("incumbent policy ID cannot be a candidate policy ID")
        if not self.enabled_risks or len(set(self.enabled_risks)) != len(self.enabled_risks):
            raise ValueError("enabled risks must be a non-empty unique sequence")
        unknown = sorted(set(self.enabled_risks) - set(ENABLED_RISKS))
        if unknown:
            raise ValueError(f"unknown enabled risks: {unknown}")
        if len(set(self.enabled_group_risks)) != len(self.enabled_group_risks):
            raise ValueError("enabled group risks must be unique")
        if set(self.enabled_group_risks) - set(BINARY_RISKS):
            raise ValueError("enabled group risks contain an unknown binary risk")
        if set(self.enabled_group_risks) - set(self.enabled_risks):
            raise ValueError("enabled group risks must also be enabled overall")
        if tuple(sorted(self.group_ids)) != self.group_ids or len(set(self.group_ids)) != len(
            self.group_ids
        ):
            raise ValueError("group IDs must be sorted and unique")
        if any(not value or value.strip() != value or "::" in value for value in self.group_ids):
            raise ValueError("group IDs must be non-empty canonical strings")
        if ("group_quality" in self.enabled_risks or self.enabled_group_risks) and not self.group_ids:
            raise ValueError("enabled group hypotheses require frozen group IDs")
        _positive_count(self.confirmatory_unit_count, "confirmatory_unit_count")
        if _finite_real(
            self.quality_noninferiority_margin, "quality_noninferiority_margin"
        ) < 0.0:
            raise ValueError("quality_noninferiority_margin must be nonnegative")
        if _finite_real(
            self.group_quality_noninferiority_margin,
            "group_quality_noninferiority_margin",
        ) < 0.0:
            raise ValueError("group_quality_noninferiority_margin must be nonnegative")
        lower, upper = self.quality_delta_bounds
        if _finite_real(lower, "quality_delta_bounds lower") >= _finite_real(
            upper, "quality_delta_bounds upper"
        ):
            raise ValueError("quality delta bounds must be strictly increasing")
        threshold_map = dict(self.binary_thresholds)
        if len(threshold_map) != len(self.binary_thresholds):
            raise ValueError("binary thresholds contain duplicate risk IDs")
        required_binary = set(self.enabled_risks) & set(BINARY_RISKS)
        if set(threshold_map) != required_binary:
            raise ValueError("binary thresholds must exactly match enabled binary risks")
        for risk, threshold in threshold_map.items():
            _probability(threshold, f"binary threshold {risk}")
        _alpha(self.familywise_error_level)
        if self.multiplicity_method not in SUPPORTED_MULTIPLICITY_METHODS:
            raise ValueError("unknown multiplicity method")
        if self.selection_objective not in SELECTION_OBJECTIVES:
            raise ValueError("unknown operational selection objective")

    @property
    def family_hash(self) -> str:
        return sha256_json(self.as_dict())

    def binary_threshold(self, risk_id: str) -> float:
        return _lookup(self.binary_thresholds, risk_id)

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_policy_ids": list(self.candidate_policy_ids),
            "incumbent_policy_id": self.incumbent_policy_id,
            "enabled_risks": list(self.enabled_risks),
            "enabled_group_risks": list(self.enabled_group_risks),
            "group_ids": list(self.group_ids),
            "confirmatory_unit_count": self.confirmatory_unit_count,
            "quality_noninferiority_margin": self.quality_noninferiority_margin,
            "group_quality_noninferiority_margin": self.group_quality_noninferiority_margin,
            "binary_thresholds": dict(self.binary_thresholds),
            "quality_delta_bounds": list(self.quality_delta_bounds),
            "familywise_error_level": self.familywise_error_level,
            "multiplicity_method": self.multiplicity_method,
            "selection_objective": self.selection_objective,
        }


@dataclass(frozen=True)
class RiskTestResult:
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
    adjusted_p_value: float
    rejection_threshold: float
    rejected: bool
    failure_reason: str | None

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
            "adjusted_p_value": self.adjusted_p_value,
            "rejection_threshold": self.rejection_threshold,
            "rejected": self.rejected,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class PromotionWarrant:
    decision: str
    decision_reason: str
    family: FrozenCandidateFamily
    evidence_hash: str
    certified_policy_ids: tuple[str, ...]
    selected_policy_id: str | None
    risk_tests: tuple[RiskTestResult, ...]
    candidate_summaries: tuple[tuple[str, Mapping[str, float]], ...]
    invalid_evidence_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        primary = "mean_cost" if self.family.selection_objective == "minimize_cost" else "mean_latency"
        secondary = "mean_latency" if primary == "mean_cost" else "mean_cost"
        selected_summary = dict(self.candidate_summaries).get(self.selected_policy_id or "")
        selected_value = selected_summary.get(primary) if selected_summary is not None else None
        return {
            "schema_version": "1.0",
            "method": METHOD_ID,
            "method_id": METHOD_ID,
            "status": "COMPLETED",
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "familywise_error_level": self.family.familywise_error_level,
            "multiplicity_method": self.family.multiplicity_method,
            "candidate_family_frozen": True,
            "family_hash": self.family.family_hash,
            "incumbent_policy_id": self.family.incumbent_policy_id,
            "confirmatory_unit_count": self.family.confirmatory_unit_count,
            "certified_policy_ids": list(self.certified_policy_ids),
            "selected_policy_id": self.selected_policy_id,
            "selection_objective": self.family.selection_objective,
            "risk_tests": [test.as_dict() for test in self.risk_tests],
            "enabled_risks": list(self.family.enabled_risks),
            "operational_selection_objective": {
                "primary": primary,
                "secondary": secondary,
                "tertiary": "lexical_policy_id",
                "selected_value": selected_value,
            },
            "diagnostics": {
                "evidence_hash": self.evidence_hash,
                "hypothesis_count": len(self.risk_tests),
                "candidate_summaries": {
                    policy_id: dict(values)
                    for policy_id, values in self.candidate_summaries
                },
                "invalid_evidence_reason": self.invalid_evidence_reason,
                "family_definition": self.family.as_dict(),
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
        benchmark_decision = PROMOTE if self.decision == PROMOTE else "NO_DECISION"
        return MethodDecision(
            method_id=METHOD_ID,
            selected_policy_id=self.selected_policy_id,
            certified_policy_ids=self.certified_policy_ids,
            decision=benchmark_decision,
            decision_reason=self.decision_reason,
            deployable=True,
            uses_population_truth=False,
            benchmark_control_only=False,
            diagnostics={
                "evidence_hash": self.evidence_hash,
                "multiplicity_method": self.family.multiplicity_method,
                "familywise_error_level": self.family.familywise_error_level,
                "family_hash": self.family.family_hash,
                "promotion_warrant": self.as_dict(),
            },
        )


def _lookup(values: tuple[tuple[str, float], ...], hypothesis_id: str) -> float:
    for current_id, value in values:
        if current_id == hypothesis_id:
            return value
    raise KeyError(hypothesis_id)


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    return result


def _probability(value: object, name: str) -> float:
    result = _finite_real(value, name)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between zero and one")
    return result


def _alpha(value: object) -> float:
    result = _finite_real(value, "alpha")
    if not 0.0 < result < 1.0:
        raise ValueError("alpha must be strictly between zero and one")
    return result


def _positive_count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _event_count(value: object, sample_count: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("event_count must be an integer")
    result = int(value)
    if result < 0 or result > sample_count:
        raise ValueError("event_count must be between zero and sample_count")
    return result


def _logsumexp(log_terms: Iterable[float]) -> float:
    terms = tuple(log_terms)
    if not terms:
        return -math.inf
    largest = max(terms)
    return largest + math.log(math.fsum(math.exp(term - largest) for term in terms))


def _log_binomial_probability(
    sample_count: int, event_count: int, probability: float
) -> float:
    return (
        math.lgamma(sample_count + 1)
        - math.lgamma(event_count + 1)
        - math.lgamma(sample_count - event_count + 1)
        + event_count * math.log(probability)
        + (sample_count - event_count) * math.log1p(-probability)
    )


def exact_binomial_lower_tail(
    event_count: int, sample_count: int, null_probability: float
) -> float:
    """Return ``P[X <= event_count]`` for ``X ~ Binomial(n, p)``.

    This is the exact lower-tail p-value for ``H0: p >= tau`` against
    ``H1: p < tau``, evaluated at the least-favourable boundary ``p=tau``.
    The implementation uses standard-library log-sum-exp arithmetic and no
    approximation, mid-p adjustment, or continuity correction.
    """

    n = _positive_count(sample_count, "sample_count")
    x = _event_count(event_count, n)
    probability = _probability(null_probability, "null_probability")

    if probability == 0.0:
        # The strict alternative p < 0 is empty.
        return 1.0
    if probability == 1.0:
        return 1.0 if x == n else 0.0
    if x == n:
        return 1.0

    # Sum the tail that avoids cancellation.  Below the binomial mean the CDF
    # is evaluated directly; above it, compute 1 - survival using expm1.
    if x <= math.floor(n * probability):
        log_cdf = _logsumexp(
            _log_binomial_probability(n, k, probability) for k in range(x + 1)
        )
        return min(1.0, max(0.0, math.exp(log_cdf)))

    log_survival = _logsumexp(
        _log_binomial_probability(n, k, probability) for k in range(x + 1, n + 1)
    )
    return min(1.0, max(0.0, -math.expm1(min(0.0, log_survival))))


def bounded_paired_quality_p_value(
    deltas: Iterable[float],
    noninferiority_margin: float,
    lower_bound: float,
    upper_bound: float,
) -> float:
    """Return the one-sided Hoeffding p-value for paired noninferiority.

    The tested hypotheses are ``H0: E[D] <= -margin`` versus
    ``H1: E[D] > -margin``.  Bounds must be prespecified; observations outside
    them are rejected rather than clipped.
    """

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

    sample_mean = math.fsum(values) / len(values)
    excess = max(0.0, sample_mean + margin)
    if excess == 0.0:
        return 1.0
    width = upper - lower
    p_value = math.exp(-2.0 * len(values) * excess * excess / (width * width))
    return min(1.0, max(0.0, p_value))


def _validated_family(
    p_values: Mapping[str, float] | Iterable[tuple[str, float]],
) -> tuple[tuple[str, float], ...]:
    try:
        supplied = tuple(p_values.items() if isinstance(p_values, Mapping) else p_values)
    except TypeError as exc:
        raise ValueError("p_values must be a non-empty hypothesis family") from exc
    if not supplied:
        raise ValueError("p_values must contain the complete hypothesis family")

    validated: list[tuple[str, float]] = []
    seen: set[str] = set()
    for item in supplied:
        try:
            hypothesis_id, raw_p_value = item
        except (TypeError, ValueError) as exc:
            raise ValueError("each p-value entry must be a (hypothesis_id, value) pair") from exc
        if (
            not isinstance(hypothesis_id, str)
            or not hypothesis_id
            or hypothesis_id.strip() != hypothesis_id
        ):
            raise ValueError("hypothesis IDs must be non-empty canonical strings")
        if hypothesis_id in seen:
            raise ValueError(f"duplicate hypothesis ID: {hypothesis_id}")
        seen.add(hypothesis_id)
        validated.append((hypothesis_id, _probability(raw_p_value, "raw p-value")))
    return tuple(sorted(validated, key=lambda pair: pair[0]))


def bonferroni_adjust(
    p_values: Mapping[str, float] | Iterable[tuple[str, float]], alpha: float
) -> MultiplicityResult:
    """Apply full-family Bonferroni adjustment with the ``<=`` convention."""

    family = _validated_family(p_values)
    family_alpha = _alpha(alpha)
    family_size = len(family)
    threshold = family_alpha / family_size
    adjusted = tuple(
        (hypothesis_id, min(1.0, family_size * p_value))
        for hypothesis_id, p_value in family
    )
    rejected = tuple(
        hypothesis_id for hypothesis_id, p_value in family if p_value <= threshold
    )
    return MultiplicityResult(
        method=BONFERRONI,
        alpha=family_alpha,
        family_size=family_size,
        ordered_hypothesis_ids=tuple(hypothesis_id for hypothesis_id, _ in family),
        raw_p_values=family,
        adjusted_p_values=adjusted,
        rejection_thresholds=tuple(
            (hypothesis_id, threshold) for hypothesis_id, _ in family
        ),
        rejected_hypothesis_ids=rejected,
    )


def holm_step_down_adjust(
    p_values: Mapping[str, float] | Iterable[tuple[str, float]], alpha: float
) -> MultiplicityResult:
    """Apply full-family Holm step-down with lexical ordering for exact ties."""

    family = _validated_family(p_values)
    family_alpha = _alpha(alpha)
    family_size = len(family)
    ordered = tuple(sorted(family, key=lambda pair: (pair[1], pair[0])))

    rejected: set[str] = set()
    thresholds: dict[str, float] = {}
    adjusted: dict[str, float] = {}
    running_adjusted = 0.0
    rejection_open = True
    for zero_based_rank, (hypothesis_id, p_value) in enumerate(ordered):
        remaining = family_size - zero_based_rank
        threshold = family_alpha / remaining
        thresholds[hypothesis_id] = threshold
        running_adjusted = max(running_adjusted, remaining * p_value)
        adjusted[hypothesis_id] = min(1.0, running_adjusted)
        if rejection_open and p_value <= threshold:
            rejected.add(hypothesis_id)
        else:
            rejection_open = False

    canonical_ids = tuple(hypothesis_id for hypothesis_id, _ in family)
    return MultiplicityResult(
        method=HOLM,
        alpha=family_alpha,
        family_size=family_size,
        ordered_hypothesis_ids=tuple(hypothesis_id for hypothesis_id, _ in ordered),
        raw_p_values=family,
        adjusted_p_values=tuple(
            (hypothesis_id, adjusted[hypothesis_id]) for hypothesis_id in canonical_ids
        ),
        rejection_thresholds=tuple(
            (hypothesis_id, thresholds[hypothesis_id]) for hypothesis_id in canonical_ids
        ),
        rejected_hypothesis_ids=tuple(
            hypothesis_id for hypothesis_id in canonical_ids if hypothesis_id in rejected
        ),
    )


def apply_multiplicity(
    p_values: Mapping[str, float] | Iterable[tuple[str, float]],
    alpha: float,
    method: str,
) -> MultiplicityResult:
    """Dispatch a prespecified, supported whole-family correction method."""

    if method == BONFERRONI:
        return bonferroni_adjust(p_values, alpha)
    if method == HOLM:
        return holm_step_down_adjust(p_values, alpha)
    raise ValueError(
        f"unknown multiplicity method {method!r}; expected one of "
        f"{SUPPORTED_MULTIPLICITY_METHODS}"
    )


@dataclass(frozen=True)
class _PendingRiskTest:
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
    failure_reason: str | None = None


def freeze_candidate_family(
    *,
    candidate_policy_ids: Iterable[str],
    incumbent_policy_id: str,
    confirmatory_unit_count: int,
    policy: PolicyConfig,
    quality_delta_bounds: tuple[float, float],
    familywise_error_level: float,
    multiplicity_method: str,
    selection_objective: str,
) -> FrozenCandidateFamily:
    """Freeze all non-truth method inputs before confirmatory evidence exists."""

    supplied_ids = tuple(candidate_policy_ids)
    if any(not isinstance(value, str) for value in supplied_ids):
        raise ValueError("candidate policy IDs must be strings")
    candidate_ids = tuple(sorted(supplied_ids))
    binary_thresholds = tuple(
        (risk, policy.binary_threshold(risk))
        for risk in BINARY_RISKS
        if risk in policy.enabled_risks
    )
    return FrozenCandidateFamily(
        candidate_policy_ids=candidate_ids,
        incumbent_policy_id=incumbent_policy_id,
        enabled_risks=tuple(policy.enabled_risks),
        enabled_group_risks=tuple(policy.enabled_group_risks),
        group_ids=tuple(policy.group_ids),
        confirmatory_unit_count=confirmatory_unit_count,
        quality_noninferiority_margin=policy.quality_noninferiority_margin,
        group_quality_noninferiority_margin=policy.group_quality_noninferiority_margin,
        binary_thresholds=binary_thresholds,
        quality_delta_bounds=quality_delta_bounds,
        familywise_error_level=familywise_error_level,
        multiplicity_method=multiplicity_method,
        selection_objective=selection_objective,
    )


def _mean(values: Iterable[float]) -> float:
    collected = tuple(_finite_real(value, "observation") for value in values)
    if not collected:
        raise ValueError("cannot calculate a mean from empty evidence")
    return math.fsum(collected) / len(collected)


def _hypothesis_id(policy_id: str, risk_id: str, group_id: str | None) -> str:
    scope = group_id if group_id is not None else "__overall__"
    return f"{policy_id}::{risk_id}::{scope}"


def _quality_test(
    *,
    policy_id: str,
    risk_id: str,
    group_id: str | None,
    deltas: tuple[float, ...],
    margin: float,
    bounds: tuple[float, float],
) -> _PendingRiskTest:
    hypothesis_id = _hypothesis_id(policy_id, risk_id, group_id)
    if not deltas:
        return _PendingRiskTest(
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
            failure_reason="missing_group_evidence",
        )
    observed_mean = _mean(deltas)
    return _PendingRiskTest(
        hypothesis_id=hypothesis_id,
        policy_id=policy_id,
        risk_id=risk_id,
        group_id=group_id,
        null_hypothesis=f"mean_quality_delta <= {-margin}",
        alternative_hypothesis=f"mean_quality_delta > {-margin}",
        null_boundary=-margin,
        support_bounds=bounds,
        sample_count=len(deltas),
        observed_statistic=observed_mean,
        raw_p_value=bounded_paired_quality_p_value(
            deltas, margin, bounds[0], bounds[1]
        ),
    )


def _binary_test(
    *,
    policy_id: str,
    risk_id: str,
    group_id: str | None,
    values: tuple[int, ...],
    threshold: float,
) -> _PendingRiskTest:
    hypothesis_id = _hypothesis_id(policy_id, risk_id, group_id)
    if not values:
        return _PendingRiskTest(
            hypothesis_id=hypothesis_id,
            policy_id=policy_id,
            risk_id=risk_id,
            group_id=group_id,
            null_hypothesis=f"event_probability >= {threshold}",
            alternative_hypothesis=f"event_probability < {threshold}",
            null_boundary=threshold,
            support_bounds=(0.0, 1.0),
            sample_count=0,
            observed_statistic=None,
            raw_p_value=1.0,
            failure_reason="missing_group_evidence",
        )
    event_count = sum(values)
    return _PendingRiskTest(
        hypothesis_id=hypothesis_id,
        policy_id=policy_id,
        risk_id=risk_id,
        group_id=group_id,
        null_hypothesis=f"event_probability >= {threshold}",
        alternative_hypothesis=f"event_probability < {threshold}",
        null_boundary=threshold,
        support_bounds=(0.0, 1.0),
        sample_count=len(values),
        observed_statistic=event_count / len(values),
        raw_p_value=exact_binomial_lower_tail(event_count, len(values), threshold),
    )


class FixedSampleMultiRiskWarrant:
    """Truth-isolated fixed-sample method for one prespecified candidate family."""

    method_id = METHOD_ID

    def __init__(self, family: FrozenCandidateFamily):
        self.family = family

    def _validate_contract(
        self, evidence: ObservedEvidence, policy: PolicyConfig
    ) -> None:
        if tuple(policy.enabled_risks) != self.family.enabled_risks:
            raise ValueError("enabled risks differ from the frozen candidate family")
        if tuple(policy.enabled_group_risks) != self.family.enabled_group_risks:
            raise ValueError("enabled group risks differ from the frozen candidate family")
        if tuple(policy.group_ids) != self.family.group_ids:
            raise ValueError("group IDs differ from the frozen candidate family")
        if evidence.sample_size != self.family.confirmatory_unit_count:
            raise ValueError("confirmatory unit count differs from the frozen family")
        if evidence.policy_ids != self.family.candidate_policy_ids:
            raise ValueError("evidence candidate IDs differ from the frozen family")
        numeric_pairs = (
            (
                policy.quality_noninferiority_margin,
                self.family.quality_noninferiority_margin,
                "quality noninferiority margin",
            ),
            (
                policy.group_quality_noninferiority_margin,
                self.family.group_quality_noninferiority_margin,
                "group quality noninferiority margin",
            ),
        )
        for actual, frozen, name in numeric_pairs:
            if not math.isclose(actual, frozen, rel_tol=0.0, abs_tol=1e-15):
                raise ValueError(f"{name} differs from the frozen family")
        for risk, threshold in self.family.binary_thresholds:
            if not math.isclose(
                policy.binary_threshold(risk), threshold, rel_tol=0.0, abs_tol=1e-15
            ):
                raise ValueError(f"binary threshold {risk} differs from the frozen family")
        _validate_evidence(evidence, policy)

    def _pending_tests(
        self, evidence: ObservedEvidence
    ) -> tuple[_PendingRiskTest, ...]:
        tests: list[_PendingRiskTest] = []
        for policy_id in self.family.candidate_policy_ids:
            rows = evidence.rows_for(policy_id)
            if "overall_quality" in self.family.enabled_risks:
                tests.append(
                    _quality_test(
                        policy_id=policy_id,
                        risk_id="overall_quality",
                        group_id=None,
                        deltas=tuple(row.quality_delta for row in rows),
                        margin=self.family.quality_noninferiority_margin,
                        bounds=self.family.quality_delta_bounds,
                    )
                )
            if "group_quality" in self.family.enabled_risks:
                for group_id in self.family.group_ids:
                    tests.append(
                        _quality_test(
                            policy_id=policy_id,
                            risk_id="group_quality",
                            group_id=group_id,
                            deltas=tuple(
                                row.quality_delta
                                for row in rows
                                if row.group_id == group_id
                            ),
                            margin=self.family.group_quality_noninferiority_margin,
                            bounds=self.family.quality_delta_bounds,
                        )
                    )
            for risk_id, evidence_field in RISK_EVIDENCE_FIELDS.items():
                if risk_id not in self.family.enabled_risks:
                    continue
                threshold = self.family.binary_threshold(risk_id)
                tests.append(
                    _binary_test(
                        policy_id=policy_id,
                        risk_id=risk_id,
                        group_id=None,
                        values=tuple(int(getattr(row, evidence_field)) for row in rows),
                        threshold=threshold,
                    )
                )
                if risk_id in self.family.enabled_group_risks:
                    for group_id in self.family.group_ids:
                        tests.append(
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
                            )
                        )
        if not tests:
            raise ValueError("frozen candidate-risk family is empty")
        if len({test.hypothesis_id for test in tests}) != len(tests):
            raise ValueError("frozen candidate-risk family contains duplicate hypotheses")
        return tuple(tests)

    def _candidate_summaries(
        self, evidence: ObservedEvidence
    ) -> tuple[tuple[str, Mapping[str, float]], ...]:
        summaries: list[tuple[str, Mapping[str, float]]] = []
        for policy_id in self.family.candidate_policy_ids:
            rows = evidence.rows_for(policy_id)
            summaries.append(
                (
                    policy_id,
                    {
                        "mean_cost": _mean(row.cost for row in rows),
                        "mean_latency": _mean(row.latency for row in rows),
                    },
                )
            )
        return tuple(summaries)

    def _invalid_warrant(
        self, evidence: ObservedEvidence, reason: str
    ) -> PromotionWarrant:
        return PromotionWarrant(
            decision=BLOCKED_INVALID_EVIDENCE,
            decision_reason=f"confirmatory evidence failed closed: {reason}",
            family=self.family,
            evidence_hash=str(getattr(evidence, "evidence_hash", "")),
            certified_policy_ids=(),
            selected_policy_id=None,
            risk_tests=(),
            candidate_summaries=(),
            invalid_evidence_reason=reason,
        )

    def evaluate_warrant(
        self, evidence: ObservedEvidence, policy: PolicyConfig
    ) -> PromotionWarrant:
        try:
            self._validate_contract(evidence, policy)
            pending = self._pending_tests(evidence)
            summaries = self._candidate_summaries(evidence)
            multiplicity = apply_multiplicity(
                ((test.hypothesis_id, test.raw_p_value) for test in pending),
                self.family.familywise_error_level,
                self.family.multiplicity_method,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return self._invalid_warrant(evidence, str(exc))

        results = tuple(
            RiskTestResult(
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
                adjusted_p_value=multiplicity.adjusted_p_value(test.hypothesis_id),
                rejection_threshold=multiplicity.rejection_threshold(test.hypothesis_id),
                rejected=multiplicity.is_rejected(test.hypothesis_id),
                failure_reason=test.failure_reason,
            )
            for test in pending
        )
        tests_by_candidate = {
            policy_id: tuple(test for test in results if test.policy_id == policy_id)
            for policy_id in self.family.candidate_policy_ids
        }
        certified = tuple(
            policy_id
            for policy_id in self.family.candidate_policy_ids
            if tests_by_candidate[policy_id]
            and all(test.rejected for test in tests_by_candidate[policy_id])
        )
        summary_map = dict(summaries)
        primary = "mean_cost" if self.family.selection_objective == "minimize_cost" else "mean_latency"
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
        return PromotionWarrant(
            decision=decision,
            decision_reason=(
                "selected the operational optimum after whole-family certification"
                if selected is not None
                else "no candidate passed every enabled whole-family risk test"
            ),
            family=self.family,
            evidence_hash=evidence.evidence_hash,
            certified_policy_ids=certified,
            selected_policy_id=selected,
            risk_tests=results,
            candidate_summaries=summaries,
        )

    def evaluate(
        self, evidence: ObservedEvidence, policy: PolicyConfig, method_seed: int = 0
    ) -> MethodDecision:
        del method_seed
        return self.evaluate_warrant(evidence, policy).to_method_decision()


__all__ = [
    "BONFERRONI",
    "BLOCKED_INVALID_EVIDENCE",
    "FOCUS1_FREEZE_DIGEST",
    "HOLM",
    "INCONCLUSIVE",
    "METHOD_ID",
    "PROMOTE",
    "SEED_SCHEDULE_VERSION",
    "SELECTION_OBJECTIVES",
    "SUPPORTED_MULTIPLICITY_METHODS",
    "FixedSampleMultiRiskWarrant",
    "FrozenCandidateFamily",
    "MultiplicityResult",
    "PromotionWarrant",
    "RiskTestResult",
    "apply_multiplicity",
    "bonferroni_adjust",
    "bounded_paired_quality_p_value",
    "exact_binomial_lower_tail",
    "freeze_candidate_family",
    "holm_step_down_adjust",
]
