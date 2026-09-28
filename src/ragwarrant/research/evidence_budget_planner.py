"""Pre-confirmatory evidence sufficiency planning for RAGWarrant research.

This module is intentionally independent of the simulator and benchmark runners.
It consumes only prespecified planning assumptions and never observed
confirmatory outcomes or population-truth objects.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


PLANNER_ID = "RAGWARRANT_EVIDENCE_BUDGET_PLANNER_V1"
SCHEMA_VERSION = "ragwarrant_evidence_budget_planner_v1"
FOCUS1_FREEZE_DIGEST = (
    "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
)
CANDIDATE_IUT = "CANDIDATE_IUT"
FLAT_FAMILY = "FLAT_FAMILY"
HOLM = "HOLM"
BONFERRONI = "BONFERRONI"
SUPPORTED_MULTIPLICITY = (HOLM, BONFERRONI)
SUPPORTED_ORGANIZATIONS = (CANDIDATE_IUT, FLAT_FAMILY)
BINARY_RISKS = (
    "safety_violation_probability",
    "execution_failure_probability",
    "insufficient_evidence_probability",
)
QUALITY_RISKS = ("overall_quality", "group_quality")
SUPPORTED_RISKS = QUALITY_RISKS + BINARY_RISKS
MANDATORY_GROUP_RISKS = ("safety_violation_probability",)
MANDATORY_GROUPS = {"majority": 0.90, "minority": 0.10}
PLANNING_ALTERNATIVE_FRACTIONS = (0.20, 0.50, 0.80)

CERTIFICATION_BUDGET_FEASIBLE = "CERTIFICATION_BUDGET_FEASIBLE"
CERTIFICATION_BUDGET_MARGINAL = "CERTIFICATION_BUDGET_MARGINAL"
CERTIFICATION_BUDGET_UNDERPOWERED = "CERTIFICATION_BUDGET_UNDERPOWERED"
CERTIFICATION_STRUCTURALLY_INFEASIBLE = (
    "CERTIFICATION_STRUCTURALLY_INFEASIBLE"
)

FROZEN_BINARY_THRESHOLDS = {
    "safety_violation_probability": 0.05,
    "execution_failure_probability": 0.03,
    "insufficient_evidence_probability": 0.10,
}
FROZEN_QUALITY_MARGINS = {
    "overall_quality": 0.02,
    "group_quality": 0.03,
}
FROZEN_QUALITY_BOUNDS = (-0.25, 0.25)


@dataclass(frozen=True)
class BinaryRejectionPlan:
    sample_count: int
    threshold: float
    effective_alpha: float
    rejection_max_events: int | None
    zero_event_p_value: float

    @property
    def structurally_certifiable(self) -> bool:
        return self.rejection_max_events is not None


@dataclass(frozen=True)
class EmpiricalBernsteinResult:
    sample_count: int
    sample_mean: float
    sample_variance: float
    alpha: float
    upper_confidence_bound: float
    risk_threshold: float
    certifies: bool


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _positive_integer(value: Any, field: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{field} must be a {qualifier} integer")
    return value


def _reject_forbidden_planning_keys(value: Any, path: str = "config") -> None:
    forbidden_fragments = (
        "population_truth",
        "simulator_truth",
        "observed_confirmatory",
        "confirmatory_outcome",
        "observed_evidence",
    )
    if isinstance(value, Mapping):
        for key, child in value.items():
            label = str(key).lower()
            if any(fragment in label for fragment in forbidden_fragments):
                raise ValueError(f"planning config may not contain truth/outcome field: {path}.{key}")
            _reject_forbidden_planning_keys(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            _reject_forbidden_planning_keys(child, f"{path}[{index}]")


def load_planner_config(path: str | Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError("evidence-budget planner config is unreadable") from exc
    if not isinstance(loaded, dict):
        raise ValueError("evidence-budget planner config must be a mapping")
    validate_planner_config(loaded)
    return loaded


def validate_planner_config(config: Mapping[str, Any]) -> None:
    _reject_forbidden_planning_keys(config)
    required_exact = {
        "schema_version": SCHEMA_VERSION,
        "planner_id": PLANNER_ID,
        "focus1_benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST,
        "research_only": True,
        "production_integrated": False,
        "full_execution_permitted": False,
        "drand_round_selected": False,
    }
    for field, expected in required_exact.items():
        if config.get(field) != expected:
            raise ValueError(f"{field} must equal {expected!r}")

    candidate_count = _positive_integer(config.get("candidate_count"), "candidate_count")
    if candidate_count > 10000:
        raise ValueError("candidate_count exceeds the planner safety limit")
    alpha = _finite_number(config.get("familywise_error_level"), "familywise_error_level")
    if not 0.0 < alpha < 1.0:
        raise ValueError("familywise_error_level must lie strictly between zero and one")
    if config.get("multiplicity_procedure") not in SUPPORTED_MULTIPLICITY:
        raise ValueError("unknown multiplicity_procedure")
    if config.get("hypothesis_organization") not in SUPPORTED_ORGANIZATIONS:
        raise ValueError("unknown hypothesis_organization")

    enabled_risks = config.get("enabled_risks")
    if not isinstance(enabled_risks, list) or not enabled_risks:
        raise ValueError("enabled_risks must be a nonempty list")
    if len(set(enabled_risks)) != len(enabled_risks):
        raise ValueError("enabled_risks contains duplicates")
    unknown = sorted(set(enabled_risks) - set(SUPPORTED_RISKS))
    if unknown:
        raise ValueError(f"unknown enabled risks: {unknown}")
    if tuple(enabled_risks) != SUPPORTED_RISKS:
        raise ValueError("enabled_risks must retain every mandatory frozen risk")
    group_risks = config.get("enabled_group_risks")
    if not isinstance(group_risks, list):
        raise ValueError("enabled_group_risks must be a list")
    if len(set(group_risks)) != len(group_risks):
        raise ValueError("enabled_group_risks contains duplicates")
    if set(group_risks) - set(BINARY_RISKS):
        raise ValueError("enabled_group_risks may contain only supported binary risks")
    if tuple(group_risks) != MANDATORY_GROUP_RISKS:
        raise ValueError("enabled_group_risks must retain every mandatory group risk")

    if config.get("binary_planning_alternative_rule") != (
        "THRESHOLD_FRACTIONS_0.20_0.50_0.80"
    ):
        raise ValueError("binary_planning_alternative_rule must use the prespecified grid")

    binary = config.get("binary_risks")
    if not isinstance(binary, Mapping):
        raise ValueError("binary_risks must be a mapping")
    selected_binary = config.get("selected_binary_planning_alternatives")
    if not isinstance(selected_binary, Mapping):
        raise ValueError("selected_binary_planning_alternatives must be a mapping")
    needed_binary = (set(enabled_risks) | set(group_risks)) & set(BINARY_RISKS)
    for risk_id in sorted(needed_binary):
        item = binary.get(risk_id)
        if not isinstance(item, Mapping):
            raise ValueError(f"missing binary-risk plan for {risk_id}")
        threshold = _finite_number(item.get("threshold"), f"{risk_id}.threshold")
        if threshold != FROZEN_BINARY_THRESHOLDS[risk_id]:
            raise ValueError(f"{risk_id} threshold differs from the frozen contract")
        alternatives = item.get("planning_alternatives")
        if not isinstance(alternatives, list) or not alternatives:
            raise ValueError(f"{risk_id} planning_alternatives must be nonempty")
        normalized: list[float] = []
        for value in alternatives:
            alternative = _finite_number(value, f"{risk_id}.planning_alternative")
            if not 0.0 <= alternative < threshold:
                raise ValueError(f"{risk_id} planning alternatives must satisfy 0 <= p_alt < threshold")
            normalized.append(alternative)
        if len(set(normalized)) != len(normalized):
            raise ValueError(f"{risk_id} planning alternatives contain duplicates")
        expected_grid = [threshold * fraction for fraction in PLANNING_ALTERNATIVE_FRACTIONS]
        if any(
            not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-15)
            for actual, expected in zip(normalized, expected_grid, strict=True)
        ):
            raise ValueError(
                f"{risk_id} planning alternatives must be the prespecified threshold fractions"
            )
        selected = _finite_number(selected_binary.get(risk_id), f"selected {risk_id} alternative")
        if selected not in normalized:
            raise ValueError(f"selected {risk_id} alternative must be prespecified")

    quality = config.get("quality")
    if not isinstance(quality, Mapping):
        raise ValueError("quality must be a mapping")
    lower = _finite_number(quality.get("support_lower"), "quality.support_lower")
    upper = _finite_number(quality.get("support_upper"), "quality.support_upper")
    if (lower, upper) != FROZEN_QUALITY_BOUNDS:
        raise ValueError("quality support differs from the frozen public contract")
    for risk_id, expected in FROZEN_QUALITY_MARGINS.items():
        field = f"{risk_id}_margin"
        if _finite_number(quality.get(field), f"quality.{field}") != expected:
            raise ValueError(f"quality {field} differs from the frozen contract")
    slacks = quality.get("planning_slacks")
    if not isinstance(slacks, list) or not slacks:
        raise ValueError("quality.planning_slacks must be nonempty")
    normalized_slacks = [_finite_number(value, "quality planning slack") for value in slacks]
    if any(value <= 0.0 or value > upper - lower for value in normalized_slacks):
        raise ValueError("quality planning slacks must lie in (0, support_width]")
    selected_slack = _finite_number(
        quality.get("selected_planning_slack"), "quality.selected_planning_slack"
    )
    if selected_slack not in normalized_slacks:
        raise ValueError("selected quality slack must be prespecified")
    variances = quality.get("empirical_bernstein_loss_variances")
    if not isinstance(variances, list) or not variances:
        raise ValueError("empirical_bernstein_loss_variances must be nonempty")
    if any(
        not 0.0 <= _finite_number(value, "empirical Bernstein variance") <= 0.25
        for value in variances
    ):
        raise ValueError("normalized [0,1] loss variance must lie in [0,0.25]")

    groups = config.get("protected_groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("protected_groups must be a nonempty list")
    if config.get("group_structure") != "CATEGORICAL_PARTITION":
        raise ValueError(
            "group_structure must be CATEGORICAL_PARTITION so protected groups "
            "are mutually exclusive and exhaustive"
        )
    group_ids: list[str] = []
    prevalence_sum = 0.0
    for group in groups:
        if not isinstance(group, Mapping) or not str(group.get("group_id", "")).strip():
            raise ValueError("each protected group requires group_id")
        group_id = str(group["group_id"])
        group_ids.append(group_id)
        prevalence = _finite_number(group.get("target_population_prevalence"), f"{group_id}.prevalence")
        if not 0.0 <= prevalence <= 1.0:
            raise ValueError("group prevalence must lie in [0,1]")
        prevalence_sum += prevalence
        _positive_integer(
            group.get("guaranteed_minimum_count", 0),
            f"{group_id}.guaranteed_minimum_count",
            allow_zero=True,
        )
    if len(group_ids) != len(set(group_ids)):
        raise ValueError("protected group IDs must be unique")
    if not math.isclose(prevalence_sum, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("protected-group prevalences must sum to one")
    observed_groups = {
        str(group["group_id"]): float(group["target_population_prevalence"])
        for group in groups
    }
    if observed_groups != MANDATORY_GROUPS:
        raise ValueError("protected_groups must retain the mandatory frozen group plan")

    targets = config.get("planning_power_targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("planning_power_targets must be nonempty")
    normalized_targets = [_finite_number(value, "planning power target") for value in targets]
    if any(not 0.0 < value < 1.0 for value in normalized_targets):
        raise ValueError("planning power targets must lie strictly between zero and one")
    if normalized_targets != sorted(set(normalized_targets)):
        raise ValueError("planning_power_targets must be unique and sorted")
    desired = _finite_number(config.get("desired_planning_power"), "desired_planning_power")
    marginal = _finite_number(config.get("marginal_planning_power"), "marginal_planning_power")
    if desired not in normalized_targets or marginal not in normalized_targets or marginal >= desired:
        raise ValueError("desired and marginal powers must be prespecified targets with marginal < desired")
    acquisition = _finite_number(
        config.get("target_acquisition_probability"), "target_acquisition_probability"
    )
    marginal_acquisition = _finite_number(
        config.get("marginal_acquisition_probability"),
        "marginal_acquisition_probability",
    )
    if not 0.0 < marginal_acquisition < acquisition < 1.0:
        raise ValueError(
            "marginal_acquisition_probability must be positive and less than "
            "target_acquisition_probability, which must be less than one"
        )
    cost_unit = config.get("cost_unit")
    if not isinstance(cost_unit, str) or not cost_unit.strip():
        raise ValueError("cost_unit must be a nonempty string")
    if not 0.0 < acquisition < 1.0:
        raise ValueError("target_acquisition_probability must lie strictly between zero and one")
    budgets = config.get("study_budgets")
    if not isinstance(budgets, list) or not budgets:
        raise ValueError("study_budgets must be nonempty")
    normalized_budgets = [_positive_integer(value, "study budget") for value in budgets]
    if normalized_budgets != sorted(set(normalized_budgets)):
        raise ValueError("study_budgets must be unique and sorted")
    proposed = _positive_integer(
        config.get("proposed_overall_evidence_budget"),
        "proposed_overall_evidence_budget",
    )
    if proposed > _positive_integer(config.get("maximum_search_n"), "maximum_search_n"):
        raise ValueError("proposed budget exceeds maximum_search_n")
    cost = _finite_number(config.get("per_example_cost"), "per_example_cost")
    if cost < 0.0:
        raise ValueError("per_example_cost must be nonnegative")


def component_count_per_candidate(config: Mapping[str, Any]) -> int:
    group_count = len(config["protected_groups"])
    count = 0
    for risk_id in config["enabled_risks"]:
        count += group_count if risk_id == "group_quality" else 1
    count += group_count * len(config["enabled_group_risks"])
    return count


def planning_family_size(config: Mapping[str, Any]) -> int:
    candidates = int(config["candidate_count"])
    if config["hypothesis_organization"] == CANDIDATE_IUT:
        return candidates
    return candidates * component_count_per_candidate(config)


def effective_planning_alpha(config: Mapping[str, Any]) -> float:
    """Conservative pre-data first-step cutoff for Holm or Bonferroni."""

    return float(config["familywise_error_level"]) / planning_family_size(config)


def _log_binomial_pmf(event_count: int, sample_count: int, probability: float) -> float:
    if event_count < 0 or event_count > sample_count:
        return -math.inf
    if probability == 0.0:
        return 0.0 if event_count == 0 else -math.inf
    if probability == 1.0:
        return 0.0 if event_count == sample_count else -math.inf
    return (
        math.lgamma(sample_count + 1)
        - math.lgamma(event_count + 1)
        - math.lgamma(sample_count - event_count + 1)
        + event_count * math.log(probability)
        + (sample_count - event_count) * math.log1p(-probability)
    )


def binomial_cdf(event_count: int, sample_count: int, probability: float) -> float:
    sample_count = _positive_integer(sample_count, "sample_count", allow_zero=True)
    probability = _finite_number(probability, "probability")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must lie in [0,1]")
    if event_count < 0:
        return 0.0
    if event_count >= sample_count:
        return 1.0
    logs = [
        _log_binomial_pmf(value, sample_count, probability)
        for value in range(event_count + 1)
    ]
    finite = [value for value in logs if math.isfinite(value)]
    if not finite:
        return 0.0
    anchor = max(finite)
    total = math.fsum(math.exp(value - anchor) for value in finite)
    return min(1.0, math.exp(anchor) * total)


def exact_binary_rejection_region(
    sample_count: int, threshold: float, effective_alpha: float
) -> BinaryRejectionPlan:
    sample_count = _positive_integer(sample_count, "sample_count", allow_zero=True)
    threshold = _finite_number(threshold, "threshold")
    effective_alpha = _finite_number(effective_alpha, "effective_alpha")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must lie in [0,1]")
    if not 0.0 < effective_alpha < 1.0:
        raise ValueError("effective_alpha must lie strictly between zero and one")
    zero_p = binomial_cdf(0, sample_count, threshold)
    if sample_count == 0 or zero_p > effective_alpha:
        rejection = None
    else:
        low, high = 0, sample_count - 1
        while low < high:
            middle = (low + high + 1) // 2
            if binomial_cdf(middle, sample_count, threshold) <= effective_alpha:
                low = middle
            else:
                high = middle - 1
        rejection = low
    return BinaryRejectionPlan(
        sample_count=sample_count,
        threshold=threshold,
        effective_alpha=effective_alpha,
        rejection_max_events=rejection,
        zero_event_p_value=zero_p,
    )


def binary_planning_power(plan: BinaryRejectionPlan, planning_alternative: float) -> float:
    alternative = _finite_number(planning_alternative, "planning_alternative")
    if not 0.0 <= alternative < plan.threshold:
        raise ValueError("planning alternative must satisfy 0 <= p_alt < threshold")
    if plan.rejection_max_events is None:
        return 0.0
    return binomial_cdf(
        plan.rejection_max_events, plan.sample_count, alternative
    )


def minimum_binary_sample_count(
    threshold: float,
    effective_alpha: float,
    planning_alternative: float,
    planning_power: float,
    maximum_n: int,
) -> int | None:
    planning_power = _finite_number(planning_power, "planning_power")
    if not 0.0 < planning_power < 1.0:
        raise ValueError("planning_power must lie strictly between zero and one")
    maximum_n = _positive_integer(maximum_n, "maximum_n")
    for sample_count in range(1, maximum_n + 1):
        plan = exact_binary_rejection_region(
            sample_count, threshold, effective_alpha
        )
        if binary_planning_power(plan, planning_alternative) >= planning_power:
            return sample_count
    return None


def minimum_binary_structural_count(
    threshold: float, effective_alpha: float, maximum_n: int
) -> int | None:
    maximum_n = _positive_integer(maximum_n, "maximum_n")
    for sample_count in range(1, maximum_n + 1):
        if exact_binary_rejection_region(
            sample_count, threshold, effective_alpha
        ).structurally_certifiable:
            return sample_count
    return None


def hoeffding_required_slack(
    sample_count: int, support_width: float, effective_alpha: float
) -> float:
    sample_count = _positive_integer(sample_count, "sample_count")
    support_width = _finite_number(support_width, "support_width")
    effective_alpha = _finite_number(effective_alpha, "effective_alpha")
    if support_width <= 0.0:
        raise ValueError("support_width must be positive")
    if not 0.0 < effective_alpha < 1.0:
        raise ValueError("effective_alpha must lie strictly between zero and one")
    return support_width * math.sqrt(
        math.log(1.0 / effective_alpha) / (2.0 * sample_count)
    )


def hoeffding_minimum_certifying_mean(
    sample_count: int,
    margin: float,
    support_lower: float,
    support_upper: float,
    effective_alpha: float,
) -> float:
    margin = _finite_number(margin, "margin")
    lower = _finite_number(support_lower, "support_lower")
    upper = _finite_number(support_upper, "support_upper")
    if margin < 0.0 or upper <= lower:
        raise ValueError("quality margin/support is invalid")
    return -margin + hoeffding_required_slack(
        sample_count, upper - lower, effective_alpha
    )


def minimum_hoeffding_structural_count(
    margin: float,
    support_lower: float,
    support_upper: float,
    effective_alpha: float,
) -> int | None:
    width = support_upper - support_lower
    best_slack = support_upper + margin
    if width <= 0.0 or best_slack <= 0.0:
        return None
    estimate = math.ceil(
        width * width
        * math.log(1.0 / effective_alpha)
        / (2.0 * best_slack * best_slack)
    )
    return max(1, estimate)


def hoeffding_planning_power_lower_bound(
    sample_count: int,
    support_width: float,
    effective_alpha: float,
    planning_slack: float,
) -> float:
    slack = _finite_number(planning_slack, "planning_slack")
    if slack <= 0.0:
        raise ValueError("planning_slack must be positive")
    crossing = hoeffding_required_slack(
        sample_count, support_width, effective_alpha
    )
    if slack <= crossing:
        return 0.0
    miss_bound = math.exp(
        -2.0 * sample_count * (slack - crossing) ** 2 / (support_width**2)
    )
    return max(0.0, min(1.0, 1.0 - miss_bound))


def minimum_hoeffding_sample_count_for_power(
    support_width: float,
    effective_alpha: float,
    planning_slack: float,
    planning_power: float,
) -> int:
    width = _finite_number(support_width, "support_width")
    slack = _finite_number(planning_slack, "planning_slack")
    power = _finite_number(planning_power, "planning_power")
    if width <= 0.0 or slack <= 0.0:
        raise ValueError("support_width and planning_slack must be positive")
    if not 0.0 < power < 1.0:
        raise ValueError("planning_power must lie strictly between zero and one")
    root = (width / slack) * (
        math.sqrt(math.log(1.0 / effective_alpha) / 2.0)
        + math.sqrt(math.log(1.0 / (1.0 - power)) / 2.0)
    )
    candidate = max(1, math.ceil(root * root))
    while (
        hoeffding_planning_power_lower_bound(
            candidate, width, effective_alpha, slack
        )
        < power
    ):
        candidate += 1
    while candidate > 1 and (
        hoeffding_planning_power_lower_bound(
            candidate - 1, width, effective_alpha, slack
        )
        >= power
    ):
        candidate -= 1
    return candidate


def empirical_bernstein_radius(
    sample_count: int, sample_variance: float, alpha: float
) -> float:
    sample_count = _positive_integer(sample_count, "sample_count")
    variance = _finite_number(sample_variance, "sample_variance")
    alpha = _finite_number(alpha, "alpha")
    if sample_count < 2:
        raise ValueError("empirical Bernstein requires n >= 2")
    if not 0.0 <= variance <= 0.25:
        raise ValueError("normalized [0,1] sample variance must lie in [0,0.25]")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie strictly between zero and one")
    log_term = math.log(2.0 / alpha)
    return math.sqrt(2.0 * variance * log_term / sample_count) + (
        7.0 * log_term / (3.0 * (sample_count - 1))
    )


def empirical_bernstein_test(
    normalized_losses: Sequence[float], risk_threshold: float, alpha: float
) -> EmpiricalBernsteinResult:
    if len(normalized_losses) < 2:
        raise ValueError("empirical Bernstein requires at least two losses")
    values = tuple(_finite_number(value, "normalized loss") for value in normalized_losses)
    if any(not 0.0 <= value <= 1.0 for value in values):
        raise ValueError("normalized losses must lie in [0,1]")
    threshold = _finite_number(risk_threshold, "risk_threshold")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("risk_threshold must lie in [0,1]")
    mean = math.fsum(values) / len(values)
    variance = math.fsum((value - mean) ** 2 for value in values) / (
        len(values) - 1
    )
    radius = empirical_bernstein_radius(len(values), variance, alpha)
    upper = mean + radius
    return EmpiricalBernsteinResult(
        sample_count=len(values),
        sample_mean=mean,
        sample_variance=variance,
        alpha=alpha,
        upper_confidence_bound=upper,
        risk_threshold=threshold,
        certifies=upper < threshold,
    )


def minimum_empirical_bernstein_crossing_count(
    support_width: float,
    planning_slack: float,
    normalized_loss_variance: float,
    effective_alpha: float,
    maximum_n: int,
) -> int | None:
    width = _finite_number(support_width, "support_width")
    slack = _finite_number(planning_slack, "planning_slack")
    variance = _finite_number(
        normalized_loss_variance, "normalized_loss_variance"
    )
    maximum_n = _positive_integer(maximum_n, "maximum_n")
    if width <= 0.0 or slack <= 0.0:
        raise ValueError("support_width and planning_slack must be positive")
    for sample_count in range(2, maximum_n + 1):
        if width * empirical_bernstein_radius(
            sample_count, variance, effective_alpha
        ) < slack:
            return sample_count
    return None


def expected_total_for_group_count(required_group_n: int, prevalence: float) -> int | None:
    required = _positive_integer(
        required_group_n, "required_group_n", allow_zero=True
    )
    prevalence = _finite_number(prevalence, "prevalence")
    if not 0.0 <= prevalence <= 1.0:
        raise ValueError("prevalence must lie in [0,1]")
    if required == 0:
        return 0
    if prevalence == 0.0:
        return None
    return math.ceil(required / prevalence)


def expected_group_topup_count(
    representative_core_n: int, required_group_n: int, prevalence: float
) -> float:
    """Exact expected quota shortfall after an IID representative core.

    This is an acquisition-cost expectation, not a statistical guarantee. A
    future stratified design fills the realized shortfall with conditional-IID
    group observations and keeps those top-ups out of unweighted overall tests.
    """

    core_n = _positive_integer(
        representative_core_n, "representative_core_n", allow_zero=True
    )
    required = _positive_integer(
        required_group_n, "required_group_n", allow_zero=True
    )
    prevalence = _finite_number(prevalence, "prevalence")
    if not 0.0 <= prevalence <= 1.0:
        raise ValueError("prevalence must lie in [0,1]")
    if required == 0:
        return 0.0
    probability_below_quota = binomial_cdf(required - 1, core_n, prevalence)
    truncated_first_moment = 0.0
    if core_n > 0 and prevalence > 0.0 and required >= 2:
        truncated_first_moment = core_n * prevalence * binomial_cdf(
            required - 2, core_n - 1, prevalence
        )
    return max(
        0.0,
        required * probability_below_quota - truncated_first_moment,
    )


def group_count_sufficiency_probability(
    total_sample_count: int, required_group_n: int, prevalence: float
) -> float:
    total = _positive_integer(
        total_sample_count, "total_sample_count", allow_zero=True
    )
    required = _positive_integer(
        required_group_n, "required_group_n", allow_zero=True
    )
    prevalence = _finite_number(prevalence, "prevalence")
    if not 0.0 <= prevalence <= 1.0:
        raise ValueError("prevalence must lie in [0,1]")
    if required == 0:
        return 1.0
    if required > total or prevalence == 0.0:
        return 0.0
    if prevalence == 1.0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - binomial_cdf(required - 1, total, prevalence)))


def high_probability_total_for_group_count(
    required_group_n: int,
    prevalence: float,
    target_probability: float,
    maximum_n: int,
) -> int | None:
    required = _positive_integer(
        required_group_n, "required_group_n", allow_zero=True
    )
    target = _finite_number(target_probability, "target_probability")
    maximum_n = _positive_integer(maximum_n, "maximum_n")
    if not 0.0 < target < 1.0:
        raise ValueError("target_probability must lie strictly between zero and one")
    if required == 0:
        return 0
    if prevalence == 0.0 or required > maximum_n:
        return None
    low = required
    if group_count_sufficiency_probability(low, required, prevalence) >= target:
        return low
    high = low
    while high < maximum_n:
        high = min(maximum_n, max(high + 1, high * 2))
        if group_count_sufficiency_probability(high, required, prevalence) >= target:
            break
    else:
        return None
    if group_count_sufficiency_probability(high, required, prevalence) < target:
        return None
    while low < high:
        middle = (low + high) // 2
        if group_count_sufficiency_probability(
            middle, required, prevalence
        ) >= target:
            high = middle
        else:
            low = middle + 1
    return low


def validate_stratified_quotas(
    overall_representative_n: int,
    group_quotas: Mapping[str, int],
    required_group_ids: Sequence[str],
) -> None:
    _positive_integer(overall_representative_n, "overall_representative_n")
    if set(group_quotas) != set(required_group_ids):
        raise ValueError("stratified quotas must contain every required group exactly once")
    for group_id, quota in group_quotas.items():
        _positive_integer(quota, f"quota[{group_id}]")


def _risk_minimums(
    config: Mapping[str, Any], planning_power: float, alpha: float
) -> tuple[dict[str, int], dict[str, dict[str, int]], list[dict[str, Any]]]:
    maximum_n = int(config["maximum_search_n"])
    selected_binary = config["selected_binary_planning_alternatives"]
    selected_slack = float(config["quality"]["selected_planning_slack"])
    lower = float(config["quality"]["support_lower"])
    upper = float(config["quality"]["support_upper"])
    width = upper - lower
    overall: dict[str, int] = {}
    by_group: dict[str, dict[str, int]] = {
        str(group["group_id"]): {} for group in config["protected_groups"]
    }
    rows: list[dict[str, Any]] = []

    for risk_id in config["enabled_risks"]:
        if risk_id == "overall_quality":
            required = minimum_hoeffding_sample_count_for_power(
                width, alpha, selected_slack, planning_power
            )
            overall[risk_id] = required
            rows.append({"scope": "overall", "group_id": None, "risk_id": risk_id, "required_n": required})
        elif risk_id == "group_quality":
            required = minimum_hoeffding_sample_count_for_power(
                width, alpha, selected_slack, planning_power
            )
            for group_id in by_group:
                by_group[group_id][risk_id] = required
                rows.append({"scope": "group", "group_id": group_id, "risk_id": risk_id, "required_n": required})
        else:
            threshold = float(config["binary_risks"][risk_id]["threshold"])
            alternative = float(selected_binary[risk_id])
            required = minimum_binary_sample_count(
                threshold, alpha, alternative, planning_power, maximum_n
            )
            if required is None:
                raise ValueError(f"{risk_id} planning target exceeds maximum_search_n")
            overall[risk_id] = required
            rows.append({"scope": "overall", "group_id": None, "risk_id": risk_id, "required_n": required})

    for risk_id in config["enabled_group_risks"]:
        threshold = float(config["binary_risks"][risk_id]["threshold"])
        alternative = float(selected_binary[risk_id])
        required = minimum_binary_sample_count(
            threshold, alpha, alternative, planning_power, maximum_n
        )
        if required is None:
            raise ValueError(f"group {risk_id} planning target exceeds maximum_search_n")
        for group_id in by_group:
            by_group[group_id][risk_id] = required
            rows.append({"scope": "group", "group_id": group_id, "risk_id": risk_id, "required_n": required})
    return overall, by_group, rows


def _structural_minimums(
    config: Mapping[str, Any], alpha: float
) -> tuple[int, dict[str, int]]:
    maximum_n = int(config["maximum_search_n"])
    quality = config["quality"]
    overall_values: list[int] = []
    group_values: dict[str, list[int]] = {
        str(group["group_id"]): [] for group in config["protected_groups"]
    }
    for risk_id in config["enabled_risks"]:
        if risk_id == "overall_quality":
            value = minimum_hoeffding_structural_count(
                float(quality["overall_quality_margin"]),
                float(quality["support_lower"]),
                float(quality["support_upper"]),
                alpha,
            )
            if value is None:
                raise ValueError("overall quality is structurally infeasible")
            overall_values.append(value)
        elif risk_id == "group_quality":
            value = minimum_hoeffding_structural_count(
                float(quality["group_quality_margin"]),
                float(quality["support_lower"]),
                float(quality["support_upper"]),
                alpha,
            )
            if value is None:
                raise ValueError("group quality is structurally infeasible")
            for values in group_values.values():
                values.append(value)
        else:
            value = minimum_binary_structural_count(
                float(config["binary_risks"][risk_id]["threshold"]),
                alpha,
                maximum_n,
            )
            if value is None:
                raise ValueError(f"{risk_id} is structurally infeasible")
            overall_values.append(value)
    for risk_id in config["enabled_group_risks"]:
        value = minimum_binary_structural_count(
            float(config["binary_risks"][risk_id]["threshold"]),
            alpha,
            maximum_n,
        )
        if value is None:
            raise ValueError(f"group {risk_id} is structurally infeasible")
        for values in group_values.values():
            values.append(value)
    return max(overall_values, default=1), {
        group_id: max(values, default=1) for group_id, values in group_values.items()
    }


def _target_design(
    config: Mapping[str, Any], planning_power: float, alpha: float
) -> dict[str, Any]:
    overall, group_risks, rows = _risk_minimums(config, planning_power, alpha)
    overall_required = max(overall.values(), default=1)
    groups = {str(item["group_id"]): item for item in config["protected_groups"]}
    group_required = {
        group_id: max(
            max(risks.values(), default=1),
            int(groups[group_id].get("guaranteed_minimum_count", 0)),
        )
        for group_id, risks in group_risks.items()
    }
    joint_target = float(config["target_acquisition_probability"])
    per_group_target = 1.0 - (1.0 - joint_target) / len(groups)
    acquisition: dict[str, dict[str, Any]] = {}
    for group_id, required in group_required.items():
        prevalence = float(groups[group_id]["target_population_prevalence"])
        expected_total = expected_total_for_group_count(required, prevalence)
        high_probability_total = high_probability_total_for_group_count(
            required, prevalence, per_group_target, int(config["maximum_search_n"])
        )
        if high_probability_total is None:
            raise ValueError(f"group {group_id} acquisition target exceeds maximum_search_n")
        acquisition[group_id] = {
            "required_group_n": required,
            "configured_guaranteed_minimum_count": int(
                groups[group_id].get("guaranteed_minimum_count", 0)
            ),
            "target_population_prevalence": prevalence,
            "expected_total_n": expected_total,
            "per_group_acquisition_probability": per_group_target,
            "high_probability_total_n": high_probability_total,
        }
    natural_total = max(
        [overall_required]
        + [int(item["high_probability_total_n"]) for item in acquisition.values()]
    )
    binding = max(
        [("overall", overall_required)]
        + [
            (f"group_acquisition:{group_id}", int(item["high_probability_total_n"]))
            for group_id, item in acquisition.items()
        ],
        key=lambda item: (item[1], item[0]),
    )[0]
    quotas = {group_id: required for group_id, required in group_required.items()}
    validate_stratified_quotas(overall_required, quotas, tuple(groups))
    stratified_conservative_max = overall_required + sum(quotas.values())
    expected_topups = {
        group_id: expected_group_topup_count(
            overall_required,
            quota,
            float(groups[group_id]["target_population_prevalence"]),
        )
        for group_id, quota in quotas.items()
    }
    expected_total_with_topups = overall_required + math.fsum(expected_topups.values())
    return {
        "planning_power": planning_power,
        "overall_required_n": overall_required,
        "required_n_by_overall_risk": overall,
        "required_n_by_group": group_required,
        "required_n_by_group_risk": group_risks,
        "risk_requirement_rows": rows,
        "acquisition": acquisition,
        "simultaneous_acquisition_target": joint_target,
        "acquisition_control": "BONFERRONI_UNION_BOUND_ACROSS_GROUP_COUNTS",
        "natural_sampling_required_total_n": natural_total,
        "binding_constraint": binding,
        "stratified_design": {
            "design_id": "STRATIFIED_CONFIRMATORY_EVIDENCE_V1",
            "representative_iid_core_n": overall_required,
            "group_specific_minimum_quotas": quotas,
            "expected_conditional_topups_after_iid_core": expected_topups,
            "expected_total_evaluations_with_topups": expected_total_with_topups,
            "estimated_expected_cost": expected_total_with_topups
            * float(config["per_example_cost"]),
            "conservative_max_evaluations_without_reuse": stratified_conservative_max,
            "estimated_conservative_cost": stratified_conservative_max
            * float(config["per_example_cost"]),
            "cost_unit": str(config["cost_unit"]),
            "overall_estimand_source": "representative_iid_core_only",
            "group_estimand_source": "iid_core_group_members_plus_conditional_group_topups",
            "population_weighting_implemented": False,
        },
    }


def _evaluate_budget(
    config: Mapping[str, Any], budget: int, plans_by_power: Mapping[float, Mapping[str, Any]], alpha: float
) -> dict[str, Any]:
    desired = float(config["desired_planning_power"])
    marginal = float(config["marginal_planning_power"])
    desired_plan = plans_by_power[desired]
    marginal_plan = plans_by_power[marginal]
    structural_overall, structural_groups = _structural_minimums(config, alpha)
    groups = {str(item["group_id"]): item for item in config["protected_groups"]}

    desired_failures = 0.0
    marginal_failures = 0.0
    group_rows: dict[str, dict[str, Any]] = {}
    for group_id, group in groups.items():
        prevalence = float(group["target_population_prevalence"])
        desired_required = int(desired_plan["required_n_by_group"][group_id])
        marginal_required = int(marginal_plan["required_n_by_group"][group_id])
        desired_probability = group_count_sufficiency_probability(
            budget, desired_required, prevalence
        )
        marginal_probability = group_count_sufficiency_probability(
            budget, marginal_required, prevalence
        )
        desired_failures += 1.0 - desired_probability
        marginal_failures += 1.0 - marginal_probability
        group_rows[group_id] = {
            "expected_group_count": budget * prevalence,
            "desired_required_group_n": desired_required,
            "desired_sufficiency_probability": desired_probability,
            "marginal_required_group_n": marginal_required,
            "marginal_sufficiency_probability": marginal_probability,
        }
    desired_joint_lower = max(0.0, 1.0 - desired_failures)
    marginal_joint_lower = max(0.0, 1.0 - marginal_failures)
    structurally_possible = budget >= structural_overall and all(
        budget >= required for required in structural_groups.values()
    )
    if not structurally_possible:
        status = CERTIFICATION_STRUCTURALLY_INFEASIBLE
    elif (
        budget >= int(desired_plan["overall_required_n"])
        and desired_joint_lower >= float(config["target_acquisition_probability"])
    ):
        status = CERTIFICATION_BUDGET_FEASIBLE
    elif (
        budget >= int(marginal_plan["overall_required_n"])
        and marginal_joint_lower >= float(config["marginal_acquisition_probability"])
    ):
        status = CERTIFICATION_BUDGET_MARGINAL
    else:
        status = CERTIFICATION_BUDGET_UNDERPOWERED
    return {
        "budget": budget,
        "status": status,
        "structurally_certifiable": structurally_possible,
        "conditional_plugin_group_counts_at_target_prevalence": {
            group_id: item["expected_group_count"] for group_id, item in group_rows.items()
        },
        "group_acquisition": group_rows,
        "desired_joint_acquisition_probability_lower_bound": desired_joint_lower,
        "marginal_joint_acquisition_probability_lower_bound": marginal_joint_lower,
        "binding_constraint": desired_plan["binding_constraint"],
        "estimated_evaluation_cost": budget * float(config["per_example_cost"]),
        "per_example_cost": float(config["per_example_cost"]),
        "cost_unit": str(config["cost_unit"]),
    }


def plan_evidence_budget(config: Mapping[str, Any]) -> dict[str, Any]:
    validate_planner_config(config)
    alpha = effective_planning_alpha(config)
    plans = {
        float(power): _target_design(config, float(power), alpha)
        for power in config["planning_power_targets"]
    }
    structural_overall, structural_groups = _structural_minimums(config, alpha)
    group_items = {str(item["group_id"]): item for item in config["protected_groups"]}
    per_group_structural_target = 1.0 - (
        1.0 - float(config["target_acquisition_probability"])
    ) / len(group_items)
    structural_acquisition = {
        group_id: high_probability_total_for_group_count(
            structural_groups[group_id],
            float(group["target_population_prevalence"]),
            per_group_structural_target,
            int(config["maximum_search_n"]),
        )
        for group_id, group in group_items.items()
    }
    if any(value is None for value in structural_acquisition.values()):
        structural_natural_minimum = None
    else:
        structural_natural_minimum = max(
            [structural_overall]
            + [int(value) for value in structural_acquisition.values() if value is not None]
        )

    quality = config["quality"]
    width = float(quality["support_upper"]) - float(quality["support_lower"])
    empirical_sensitivity: list[dict[str, Any]] = []
    for variance in quality["empirical_bernstein_loss_variances"]:
        for slack in quality["planning_slacks"]:
            empirical_sensitivity.append(
                {
                    "normalized_loss_variance": float(variance),
                    "planning_slack": float(slack),
                    "minimum_crossing_n": minimum_empirical_bernstein_crossing_count(
                        width,
                        float(slack),
                        float(variance),
                        alpha,
                        int(config["maximum_search_n"]),
                    ),
                    "interpretation": "CONDITIONAL_CROSSING_SENSITIVITY_NOT_POWER",
                }
            )

    candidate_budgets = sorted(
        set(int(value) for value in config["study_budgets"])
        | {
            int(plan["natural_sampling_required_total_n"])
            for plan in plans.values()
        }
        | {int(config["proposed_overall_evidence_budget"])}
    )
    budgets = [
        _evaluate_budget(config, budget, plans, alpha) for budget in candidate_budgets
    ]
    desired = float(config["desired_planning_power"])
    recommended = dict(plans[desired])
    recommended["selection_basis"] = (
        "PRESPECIFIED_DESIRED_POWER_AND_ACQUISITION_TARGET_NOT_OBSERVED_OUTCOMES"
    )
    recommended["recommended_acquisition_strategy"] = (
        "STRATIFIED_CONFIRMATORY_EVIDENCE_V1_REPRESENTATIVE_CORE_PLUS_GROUP_TOPUPS"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "planner_id": PLANNER_ID,
        "focus1_benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST,
        "candidate_count": int(config["candidate_count"]),
        "familywise_error_level": float(config["familywise_error_level"]),
        "multiplicity_procedure": config["multiplicity_procedure"],
        "hypothesis_organization": config["hypothesis_organization"],
        "component_count_per_candidate": component_count_per_candidate(config),
        "planning_family_size": planning_family_size(config),
        "effective_planning_alpha": alpha,
        "effective_alpha_interpretation": (
            "CONSERVATIVE_PRE_DATA_FIRST_STEP_HOLM_CUTOFF"
            if config["multiplicity_procedure"] == HOLM
            else "BONFERRONI_CUTOFF"
        ),
        "planning_alternatives_are_explicit_inputs": True,
        "binary_planning_alternative_rule": config["binary_planning_alternative_rule"],
        "planning_power_scope": "MARGINAL_COMPONENT_POWER_NOT_JOINT_CANDIDATE_POWER",
        "population_truth_accessed": False,
        "confirmatory_outcomes_accessed": False,
        "joint_candidate_power_calculated": False,
        "per_example_cost": float(config["per_example_cost"]),
        "cost_unit": str(config["cost_unit"]),
        "target_designs": {str(power): plan for power, plan in plans.items()},
        "mathematical_minimum": {
            "overall_n": structural_overall,
            "group_n": structural_groups,
            "natural_sampling_total_n_with_acquisition_control": structural_natural_minimum,
        },
        "empirical_bernstein_sensitivity": empirical_sensitivity,
        "empirical_bernstein_planning_power_calculated": False,
        "budget_matrix": budgets,
        "recommended_design": recommended,
        "full_evidence_generated": False,
        "drand_round_selected": False,
    }


def study_rows(config: Mapping[str, Any], plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    alpha = float(plan["effective_planning_alpha"])
    selected_binary = config["selected_binary_planning_alternatives"]
    selected_slack = float(config["quality"]["selected_planning_slack"])
    width = float(config["quality"]["support_upper"]) - float(
        config["quality"]["support_lower"]
    )
    groups = {str(item["group_id"]): item for item in config["protected_groups"]}
    rows: list[dict[str, Any]] = []
    for summary in plan["budget_matrix"]:
        budget = int(summary["budget"])
        common = {
            "budget": budget,
            "effective_alpha": alpha,
            "budget_status": summary["status"],
            "binding_constraint": summary["binding_constraint"],
            "estimated_evaluation_cost": summary["estimated_evaluation_cost"],
        }
        rows.append(
            {
                **common,
                "record_type": "budget_summary",
                "risk_id": "",
                "scope": "overall_plan",
                "group_id": "",
                "threshold_or_margin": "",
                "planning_alternative": "",
                "rejection_max_events": "",
                "structurally_certifiable": summary["structurally_certifiable"],
                "planning_power_or_lower_bound": "",
                "minimum_certifying_quality_mean": "",
                "expected_group_count": "",
                "group_sufficiency_probability": summary[
                    "desired_joint_acquisition_probability_lower_bound"
                ],
                "interpretation": "JOINT_ACQUISITION_UNION_BOUND_LOWER_BOUND",
            }
        )
        for risk_id in config["enabled_risks"]:
            if risk_id == "overall_quality":
                margin = float(config["quality"]["overall_quality_margin"])
                rows.append(
                    {
                        **common,
                        "record_type": "quality_gate",
                        "risk_id": risk_id,
                        "scope": "overall",
                        "group_id": "",
                        "threshold_or_margin": margin,
                        "planning_alternative": selected_slack,
                        "rejection_max_events": "",
                        "structurally_certifiable": hoeffding_minimum_certifying_mean(
                            budget,
                            margin,
                            float(config["quality"]["support_lower"]),
                            float(config["quality"]["support_upper"]),
                            alpha,
                        )
                        <= float(config["quality"]["support_upper"]),
                        "planning_power_or_lower_bound": hoeffding_planning_power_lower_bound(
                            budget, width, alpha, selected_slack
                        ),
                        "minimum_certifying_quality_mean": hoeffding_minimum_certifying_mean(
                            budget,
                            margin,
                            float(config["quality"]["support_lower"]),
                            float(config["quality"]["support_upper"]),
                            alpha,
                        ),
                        "expected_group_count": "",
                        "group_sufficiency_probability": "",
                        "interpretation": "DISTRIBUTION_FREE_HOEFFDING_POWER_LOWER_BOUND",
                    }
                )
            elif risk_id == "group_quality":
                for group_id, group in groups.items():
                    group_n = max(1, math.floor(budget * float(group["target_population_prevalence"])))
                    margin = float(config["quality"]["group_quality_margin"])
                    required = int(plan["recommended_design"]["required_n_by_group"][group_id])
                    rows.append(
                        {
                            **common,
                            "record_type": "quality_gate",
                            "risk_id": risk_id,
                            "scope": "group",
                            "group_id": group_id,
                            "threshold_or_margin": margin,
                            "planning_alternative": selected_slack,
                            "rejection_max_events": "",
                            "structurally_certifiable": hoeffding_minimum_certifying_mean(
                                group_n,
                                margin,
                                float(config["quality"]["support_lower"]),
                                float(config["quality"]["support_upper"]),
                                alpha,
                            )
                            <= float(config["quality"]["support_upper"]),
                            "planning_power_or_lower_bound": hoeffding_planning_power_lower_bound(
                                group_n, width, alpha, selected_slack
                            ),
                            "minimum_certifying_quality_mean": hoeffding_minimum_certifying_mean(
                                group_n,
                                margin,
                                float(config["quality"]["support_lower"]),
                                float(config["quality"]["support_upper"]),
                                alpha,
                            ),
                            "expected_group_count": budget
                            * float(group["target_population_prevalence"]),
                            "group_sufficiency_probability": group_count_sufficiency_probability(
                                budget,
                                required,
                                float(group["target_population_prevalence"]),
                            ),
                            "interpretation": "CONDITIONAL_AT_FLOORED_EXPECTED_GROUP_COUNT_HOEFFDING_POWER_LOWER_BOUND_PLUS_EXACT_ACQUISITION_TAIL",
                        }
                    )
            else:
                threshold = float(config["binary_risks"][risk_id]["threshold"])
                alternative = float(selected_binary[risk_id])
                binary = exact_binary_rejection_region(budget, threshold, alpha)
                rows.append(
                    {
                        **common,
                        "record_type": "binary_gate",
                        "risk_id": risk_id,
                        "scope": "overall",
                        "group_id": "",
                        "threshold_or_margin": threshold,
                        "planning_alternative": alternative,
                        "rejection_max_events": binary.rejection_max_events
                        if binary.rejection_max_events is not None
                        else "",
                        "structurally_certifiable": binary.structurally_certifiable,
                        "planning_power_or_lower_bound": binary_planning_power(
                            binary, alternative
                        ),
                        "minimum_certifying_quality_mean": "",
                        "expected_group_count": "",
                        "group_sufficiency_probability": "",
                        "interpretation": "EXACT_CONDITIONAL_BINOMIAL_PLANNING_POWER",
                    }
                )
        for risk_id in config["enabled_group_risks"]:
            threshold = float(config["binary_risks"][risk_id]["threshold"])
            alternative = float(selected_binary[risk_id])
            for group_id, group in groups.items():
                group_n = max(1, math.floor(budget * float(group["target_population_prevalence"])))
                binary = exact_binary_rejection_region(group_n, threshold, alpha)
                required = int(plan["recommended_design"]["required_n_by_group"][group_id])
                rows.append(
                    {
                        **common,
                        "record_type": "binary_gate",
                        "risk_id": risk_id,
                        "scope": "group",
                        "group_id": group_id,
                        "threshold_or_margin": threshold,
                        "planning_alternative": alternative,
                        "rejection_max_events": binary.rejection_max_events
                        if binary.rejection_max_events is not None
                        else "",
                        "structurally_certifiable": binary.structurally_certifiable,
                        "planning_power_or_lower_bound": binary_planning_power(
                            binary, alternative
                        ),
                        "minimum_certifying_quality_mean": "",
                        "expected_group_count": budget
                        * float(group["target_population_prevalence"]),
                        "group_sufficiency_probability": group_count_sufficiency_probability(
                            budget,
                            required,
                            float(group["target_population_prevalence"]),
                        ),
                        "interpretation": "EXACT_CONDITIONAL_BINOMIAL_POWER_AT_FLOORED_EXPECTED_GROUP_COUNT",
                    }
                )
    return rows


def render_study_report(config: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    desired = str(float(config["desired_planning_power"]))
    recommended = plan["target_designs"][desired]
    lines = [
        "# RAGWarrant evidence-budget study",
        "",
        "Status: pre-confirmatory analytical planning; no evidence generated.",
        "",
        "## Frozen contract",
        "",
        f"- Focus 1 digest: `{FOCUS1_FREEZE_DIGEST}`.",
        f"- Candidate family: `{plan['candidate_count']}` candidates.",
        f"- Hypothesis organization: `{plan['hypothesis_organization']}`.",
        f"- Multiplicity: `{plan['multiplicity_procedure']}`; conservative pre-data alpha `{plan['effective_planning_alpha']:.12g}`.",
        "- Planning alternatives are explicit inputs and are not simulator truth.",
        "- Component planning powers are not multiplied into an unsupported joint-candidate power claim.",
        "",
        "## Mathematical structural minimum",
        "",
        f"With the conservative pre-data alpha, the smallest best-case-certifiable overall count is `{plan['mathematical_minimum']['overall_n']}` and the corresponding per-group counts are "
        + ", ".join(
            f"`{group}={count}`"
            for group, count in plan["mathematical_minimum"]["group_n"].items()
        )
        + f". Natural sampling with the acquisition tail requires total `N={plan['mathematical_minimum']['natural_sampling_total_n_with_acquisition_control']}`. These are algebraic/best-case crossings, not planning-power guarantees.",
        "",
        "## Target designs",
        "",
        "| Marginal component planning target | Overall core n | Natural-sampling total n | Group quotas | Binding constraint |",
        "|---:|---:|---:|---|---|",
    ]
    for key in sorted(plan["target_designs"], key=float):
        item = plan["target_designs"][key]
        quotas = ", ".join(
            f"{group}={count}" for group, count in item["required_n_by_group"].items()
        )
        lines.append(
            f"| {float(key):.0%} | {item['overall_required_n']} | {item['natural_sampling_required_total_n']} | {quotas} | `{item['binding_constraint']}` |"
        )
    lines.extend(
        [
            "",
            "### Risk-specific required observations",
            "",
            "| Marginal component target | Scope | Group | Risk | Required n |",
            "|---:|---|---|---|---:|",
        ]
    )
    for key in sorted(plan["target_designs"], key=float):
        for row in plan["target_designs"][key]["risk_requirement_rows"]:
            lines.append(
                f"| {float(key):.0%} | `{row['scope']}` | `{row['group_id'] or ''}` | `{row['risk_id']}` | {row['required_n']} |"
            )
    lines.extend(
        [
            "",
            "The natural-sampling total uses exact binomial group-count tails with a prespecified union-bound allocation of acquisition failure. Expected `required_group_n / prevalence` totals are reported separately in the subgroup plan and are not guarantees.",
            "",
            "## Budget matrix",
            "",
            "| Budget | Status | Joint desired-group acquisition lower bound | Binding constraint | Cost |",
            "|---:|---|---:|---|---:|",
        ]
    )
    for row in plan["budget_matrix"]:
        lines.append(
            f"| {row['budget']} | `{row['status']}` | {row['desired_joint_acquisition_probability_lower_bound']:.6f} | `{row['binding_constraint']}` | {row['estimated_evaluation_cost']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Recommended design",
            "",
            f"The prespecified {float(config['desired_planning_power']):.0%} marginal-component planning-power operating point requires representative IID overall core `n={recommended['overall_required_n']}` and conditional-group quotas "
            + ", ".join(
                f"`{group}>={count}`" for group, count in recommended["required_n_by_group"].items()
            )
            + ".",
            "",
            f"With target prevalences, the exact expected top-up calculation gives `{recommended['stratified_design']['expected_total_evaluations_with_topups']:.2f}` fully evaluated family rows (cost `{recommended['stratified_design']['estimated_expected_cost']:.2f}` `{recommended['stratified_design']['cost_unit']}`); the no-reuse conservative maximum is `{recommended['stratified_design']['conservative_max_evaluations_without_reuse']}`. The expectation is a cost estimate, not an acquisition guarantee.",
            "",
            "The recommended acquisition strategy is `STRATIFIED_CONFIRMATORY_EVIDENCE_V1`: overall-population tests use only the representative IID core; group tests may reuse matching core observations and add independently recruited IID observations from the same target conditional group. No unweighted overall estimate may consume quota-altered top-ups.",
            "",
            "## Empirical Bernstein sensitivity",
            "",
            "Maurer-Pontil Theorem 4 is retained as a separate strict fixed-level test/sensitivity alternative. Its rows condition on prespecified normalized-loss sample variances and report crossing counts, not 50/80/90% power. Zero variance retains the theorem's additive penalty.",
            "",
            "| Normalized loss variance | Declared mean slack | Conditional crossing n |",
            "|---:|---:|---:|",
        ]
    )
    for row in plan["empirical_bernstein_sensitivity"]:
        lines.append(
            f"| {row['normalized_loss_variance']:.3f} | {row['planning_slack']:.3f} | {row['minimum_crossing_n']} |"
        )
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- Exact binomial power can be saw-toothed across adjacent n; the minimum-n search enumerates n rather than assuming monotonic power.",
            "- Hoeffding power values are conservative distribution-free lower bounds under declared mean slack.",
            "- Empirical-Bernstein power is not calculated from mean and variance alone.",
            "- This planning mechanism is not a favorable benchmark result and does not authorize FULL or a drand round.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_subgroup_plan(config: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    lines = [
        "# Subgroup evidence plan",
        "",
        "This is a design-only acquisition plan. Group-specific inference and overall-population inference remain separate.",
        "",
    ]
    for target, item in sorted(plan["target_designs"].items(), key=lambda pair: float(pair[0])):
        lines.extend(
            [
                f"## {float(target):.0%} component planning target",
                "",
                "| Group | Required group n | Prevalence | Expected total n | Per-group acquisition target | High-probability total n |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for group_id, acquisition in item["acquisition"].items():
            lines.append(
                f"| `{group_id}` | {acquisition['required_group_n']} | {acquisition['target_population_prevalence']:.3f} | {acquisition['expected_total_n']} | {acquisition['per_group_acquisition_probability']:.4f} | {acquisition['high_probability_total_n']} |"
            )
        stratified = item["stratified_design"]
        lines.extend(
            [
                "",
                f"Simultaneous acquisition target: `{item['simultaneous_acquisition_target']:.3f}` using `{item['acquisition_control']}`.",
                f"Representative core `n={stratified['representative_iid_core_n']}` plus realized quota top-ups has exact expected total `{stratified['expected_total_evaluations_with_topups']:.2f}` under the declared target prevalences; the no-reuse conservative maximum is `{stratified['conservative_max_evaluations_without_reuse']}`.",
                "",
            ]
        )
    lines.extend(
        [
            "## Stratified acquisition boundary",
            "",
            "The representative IID core is the only source for unweighted overall-population tests. Conditional-group quota top-ups may support group-specific guarantees when recruitment is IID from the same target conditional population. They change the population mixture and therefore cannot enter the preserved unweighted overall tests.",
            "",
            "A future weighted overall design would require prespecified target prevalences, known or independently estimated inclusion probabilities, a bounded weighted-loss contract, and newly derived finite-sample tests. No such weighted method or sampler is implemented here.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_study_csv(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("study rows must be nonempty")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def stable_config_hash(config: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        config, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
