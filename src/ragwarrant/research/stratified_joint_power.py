"""Planning-only stratified evidence and joint-warrant power utilities.

This namespace is additive.  It reuses the frozen v1 component tests and the
v2 candidate-IUT/Holm composition, but it never collects evidence or reads
population-truth objects.  Overall tests consume representative-core rows;
group tests consume matching core rows plus exchangeable conditional top-ups.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np

from .fixed_sample_warrant import (
    BLOCKED_INVALID_EVIDENCE,
    HOLM,
    INCONCLUSIVE,
    PROMOTE,
    FOCUS1_FREEZE_DIGEST,
    FrozenCandidateFamily,
    _binary_test,
    _quality_test,
    apply_multiplicity,
)
from .fixed_sample_warrant_v2 import candidate_iut_p_value
from .types import BINARY_RISKS, PolicyConfig


CONTRACT_ID = "STRATIFIED_CONFIRMATORY_EVIDENCE_V1"
PLANNER_ID = "RAGWARRANT_JOINT_WARRANT_POWER_PLANNER_V1"
BLOCKED_INSUFFICIENT_GROUP_EVIDENCE = "BLOCKED_INSUFFICIENT_GROUP_EVIDENCE"
BLOCKED_PENDING_OWNER_OPERATIONAL_FIELDS = "BLOCKED_PENDING_OWNER_OPERATIONAL_FIELDS"
BLOCKED_TOPUP_EXCHANGEABILITY = "STRATIFIED_DESIGN_BLOCKED_TOPUP_EXCHANGEABILITY"
FULL_STATUS = "FULL_ORIGINAL_BUDGET_NOT_EXECUTED_DEVELOPMENTALLY_UNDERPOWERED"
DEPENDENCE_LEVELS = ("low", "medium", "high")
DEPENDENCE_FRACTIONS = {"low": 0.0, "medium": 0.5, "high": 0.9}


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _positive_int(value: Any, name: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        word = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{name} must be a {word} integer")
    return value


def stable_hash(value: object) -> str:
    import json

    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def deterministic_seed(master_seed: int, *identity: object) -> int:
    _positive_int(master_seed, "master_seed", allow_zero=True)
    digest = stable_hash([master_seed, *identity])
    return int(digest[:16], 16)


def normalize_group_label(label: object, allowed_groups: Iterable[str]) -> str:
    """Return one frozen categorical group label or fail closed."""

    allowed = tuple(sorted(allowed_groups))
    if not allowed or len(set(allowed)) != len(allowed):
        raise ValueError("allowed groups must be nonempty and unique")
    if isinstance(label, (list, tuple, set, dict)):
        raise ValueError("ambiguous or multiple group labels are not permitted")
    if not isinstance(label, str) or not label or label.strip() != label:
        raise ValueError("missing or malformed group label")
    if label not in allowed:
        raise ValueError(f"unknown group label: {label}")
    return label


@dataclass(frozen=True)
class SamplingContract:
    target_population_id: str
    sampling_frame_id: str
    unit_definition: str
    group_ids: tuple[str, ...]
    group_prevalence: tuple[tuple[str, float], ...]
    core_mechanism: str
    topup_mechanism: str
    replacement: bool
    max_elapsed_days: int
    screening_cap: int
    recruitment_deadline_days: int
    candidate_family_hash: str
    incumbent_version: str
    model_version: str
    evaluator_version: str
    execution_authorized: bool = False

    def __post_init__(self) -> None:
        for name in (
            "target_population_id",
            "sampling_frame_id",
            "unit_definition",
            "incumbent_version",
            "model_version",
            "evaluator_version",
        ):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be frozen")
        if tuple(sorted(self.group_ids)) != self.group_ids:
            raise ValueError("group_ids must be sorted")
        prevalence = dict(self.group_prevalence)
        if tuple(sorted(prevalence)) != self.group_ids:
            raise ValueError("group prevalence must exactly match group_ids")
        if not math.isclose(sum(prevalence.values()), 1.0, abs_tol=1e-12):
            raise ValueError("group prevalence must sum to one")
        if any(not 0.0 < _finite(value, "group prevalence") < 1.0 for value in prevalence.values()):
            raise ValueError("group prevalence must lie strictly between zero and one")
        if self.core_mechanism != "IID_PROBABILITY_SAMPLE":
            raise ValueError("core must be an IID probability sample")
        if self.topup_mechanism != "OUTCOME_BLIND_RANDOM_WITHIN_GROUP":
            raise ValueError("top-ups must be random and outcome blind within group")
        if self.replacement:
            raise ValueError("v1 sampling is without replacement within the event frame")
        _positive_int(self.max_elapsed_days, "max_elapsed_days")
        _positive_int(self.screening_cap, "screening_cap")
        _positive_int(self.recruitment_deadline_days, "recruitment_deadline_days")
        if self.execution_authorized:
            raise ValueError("planning contract cannot authorize evidence collection")


@dataclass(frozen=True)
class CandidateSamples:
    policy_id: str
    core_group_ids: tuple[str, ...]
    core_quality_delta: tuple[float, ...]
    core_binary: tuple[tuple[str, tuple[int, ...]], ...]
    topup_quality_delta: tuple[tuple[str, tuple[float, ...]], ...]
    topup_binary: tuple[tuple[str, tuple[tuple[str, tuple[int, ...]], ...]], ...]
    mean_cost: float
    mean_latency: float

    def binary_core(self, risk_id: str) -> tuple[int, ...]:
        return dict(self.core_binary)[risk_id]

    def quality_topup(self, group_id: str) -> tuple[float, ...]:
        return dict(self.topup_quality_delta).get(group_id, ())

    def binary_topup(self, group_id: str, risk_id: str) -> tuple[int, ...]:
        return dict(dict(self.topup_binary).get(group_id, ()))[risk_id]


@dataclass(frozen=True)
class StratifiedEvidence:
    evidence_id: str
    core_unit_ids: tuple[str, ...]
    topup_unit_ids: tuple[tuple[str, tuple[str, ...]], ...]
    candidates: tuple[CandidateSamples, ...]
    recruitment_basis: str = "ELIGIBILITY_AND_FROZEN_GROUP_ONLY"

    def validate(self, family: FrozenCandidateFamily) -> None:
        if self.recruitment_basis != "ELIGIBILITY_AND_FROZEN_GROUP_ONLY":
            raise ValueError("recruitment may not depend on outcomes")
        if len(self.core_unit_ids) != family.confirmatory_unit_count:
            raise ValueError("core unit count differs from frozen family")
        if len(set(self.core_unit_ids)) != len(self.core_unit_ids):
            raise ValueError("duplicate core unit")
        topups = dict(self.topup_unit_ids)
        if tuple(sorted(topups)) != family.group_ids:
            raise ValueError("top-up sources must exactly match frozen groups")
        all_units = set(self.core_unit_ids)
        for group_id, unit_ids in self.topup_unit_ids:
            if len(set(unit_ids)) != len(unit_ids):
                raise ValueError(f"duplicate top-up unit in {group_id}")
            if all_units.intersection(unit_ids):
                raise ValueError("core/top-up or cross-top-up duplicate unit")
            all_units.update(unit_ids)
        if tuple(item.policy_id for item in self.candidates) != family.candidate_policy_ids:
            raise ValueError("evidence candidate family differs from frozen family")
        canonical_group_ids = self.candidates[0].core_group_ids
        for item in self.candidates:
            for field, value in (
                ("mean_cost", item.mean_cost),
                ("mean_latency", item.mean_latency),
            ):
                if _finite(value, field) <= 0.0:
                    raise ValueError(f"candidate {field} must be positive")
            if len(item.core_group_ids) != len(self.core_unit_ids):
                raise ValueError("candidate core group labels are incomplete")
            if len(item.core_quality_delta) != len(self.core_unit_ids):
                raise ValueError("candidate core quality evidence is incomplete")
            for label in item.core_group_ids:
                normalize_group_label(label, family.group_ids)
            if item.core_group_ids != canonical_group_ids:
                raise ValueError(
                    "core group assignment must be immutable and shared across candidates"
                )
            if set(dict(item.core_binary)) != set(family.enabled_risks).intersection(BINARY_RISKS):
                raise ValueError("candidate core binary risks are incomplete")
            for risk_id, values in item.core_binary:
                if len(values) != len(self.core_unit_ids) or any(value not in (0, 1) for value in values):
                    raise ValueError(f"invalid core binary evidence for {risk_id}")
            if tuple(sorted(dict(item.topup_quality_delta))) != family.group_ids:
                raise ValueError("candidate top-up quality groups are incomplete")
            for group_id in family.group_ids:
                expected = len(topups[group_id])
                if len(item.quality_topup(group_id)) != expected:
                    raise ValueError("candidate top-up quality evidence is incomplete")
                for risk_id in family.enabled_group_risks:
                    values = item.binary_topup(group_id, risk_id)
                    if len(values) != expected or any(value not in (0, 1) for value in values):
                        raise ValueError("candidate top-up binary evidence is incomplete")


@dataclass(frozen=True)
class StratifiedWarrantResult:
    decision: str
    certified_policy_ids: tuple[str, ...]
    selected_policy_id: str | None
    component_p_values: tuple[tuple[str, float], ...]
    candidate_p_values: tuple[tuple[str, float], ...]
    candidate_adjusted_p_values: tuple[tuple[str, float], ...]
    evidence_scope_counts: tuple[tuple[str, int], ...]
    invalid_reason: str | None = None


def evaluate_stratified_iut_holm(
    evidence: StratifiedEvidence,
    family: FrozenCandidateFamily,
    policy: PolicyConfig,
    group_quotas: Mapping[str, int],
) -> StratifiedWarrantResult:
    """Evaluate unchanged component tests with explicit evidence scopes."""

    try:
        evidence.validate(family)
        if family.multiplicity_method != HOLM:
            raise ValueError("joint-power v1 requires preserved candidate-level Holm")
        if tuple(policy.enabled_risks) != family.enabled_risks:
            raise ValueError("enabled risks differ from frozen family")
        if tuple(policy.enabled_group_risks) != family.enabled_group_risks:
            raise ValueError("enabled group risks differ from frozen family")
        if tuple(policy.group_ids) != family.group_ids:
            raise ValueError("groups differ from frozen family")
        for group_id in family.group_ids:
            _positive_int(group_quotas.get(group_id), f"quota {group_id}")
        canonical_groups = evidence.candidates[0].core_group_ids
        topup_unit_map = dict(evidence.topup_unit_ids)
        for group_id in family.group_ids:
            core_count = sum(label == group_id for label in canonical_groups)
            expected_topup_count = max(0, group_quotas[group_id] - core_count)
            actual_topup_count = len(topup_unit_map[group_id])
            if actual_topup_count < expected_topup_count:
                raise ValueError(BLOCKED_INSUFFICIENT_GROUP_EVIDENCE)
            if actual_topup_count > expected_topup_count:
                raise ValueError(
                    "top-up count must equal the frozen quota shortfall exactly"
                )

        components: list[tuple[str, str, float]] = []
        counts: dict[str, int] = {}
        for sample in evidence.candidates:
            core_groups = np.asarray(sample.core_group_ids)
            core_quality = sample.core_quality_delta
            if "overall_quality" in family.enabled_risks:
                test = _quality_test(
                    policy_id=sample.policy_id,
                    risk_id="overall_quality",
                    group_id=None,
                    deltas=core_quality,
                    margin=family.quality_noninferiority_margin,
                    bounds=family.quality_delta_bounds,
                )
                components.append((sample.policy_id, test.hypothesis_id, test.raw_p_value))
                counts[test.hypothesis_id] = test.sample_count
            if "group_quality" in family.enabled_risks:
                for group_id in family.group_ids:
                    core_values = tuple(
                        value for value, label in zip(core_quality, core_groups, strict=True)
                        if label == group_id
                    )
                    values = core_values + sample.quality_topup(group_id)
                    if len(values) < group_quotas[group_id]:
                        raise ValueError(BLOCKED_INSUFFICIENT_GROUP_EVIDENCE)
                    test = _quality_test(
                        policy_id=sample.policy_id,
                        risk_id="group_quality",
                        group_id=group_id,
                        deltas=values,
                        margin=family.group_quality_noninferiority_margin,
                        bounds=family.quality_delta_bounds,
                    )
                    components.append((sample.policy_id, test.hypothesis_id, test.raw_p_value))
                    counts[test.hypothesis_id] = test.sample_count
            for risk_id in BINARY_RISKS:
                if risk_id not in family.enabled_risks:
                    continue
                core_values = sample.binary_core(risk_id)
                test = _binary_test(
                    policy_id=sample.policy_id,
                    risk_id=risk_id,
                    group_id=None,
                    values=core_values,
                    threshold=family.binary_threshold(risk_id),
                )
                components.append((sample.policy_id, test.hypothesis_id, test.raw_p_value))
                counts[test.hypothesis_id] = test.sample_count
                if risk_id in family.enabled_group_risks:
                    for group_id in family.group_ids:
                        core_values_group = tuple(
                            value for value, label in zip(core_values, core_groups, strict=True)
                            if label == group_id
                        )
                        values = core_values_group + sample.binary_topup(group_id, risk_id)
                        if len(values) < group_quotas[group_id]:
                            raise ValueError(BLOCKED_INSUFFICIENT_GROUP_EVIDENCE)
                        test = _binary_test(
                            policy_id=sample.policy_id,
                            risk_id=risk_id,
                            group_id=group_id,
                            values=values,
                            threshold=family.binary_threshold(risk_id),
                        )
                        components.append((sample.policy_id, test.hypothesis_id, test.raw_p_value))
                        counts[test.hypothesis_id] = test.sample_count

        by_candidate = {
            policy_id: tuple(value for candidate, _, value in components if candidate == policy_id)
            for policy_id in family.candidate_policy_ids
        }
        if any(not values for values in by_candidate.values()):
            raise ValueError("candidate is missing mandatory component evidence")
        candidate_raw = {
            policy_id: candidate_iut_p_value(values)
            for policy_id, values in by_candidate.items()
        }
        adjusted = apply_multiplicity(
            candidate_raw, family.familywise_error_level, HOLM
        )
        certified = tuple(
            policy_id for policy_id in family.candidate_policy_ids
            if adjusted.is_rejected(policy_id)
        )
        summaries = {
            item.policy_id: (item.mean_cost, item.mean_latency)
            for item in evidence.candidates
        }
        if family.selection_objective == "minimize_cost":
            selection_key = lambda policy_id: (
                summaries[policy_id][0],
                summaries[policy_id][1],
                policy_id,
            )
        elif family.selection_objective == "minimize_latency":
            selection_key = lambda policy_id: (
                summaries[policy_id][1],
                summaries[policy_id][0],
                policy_id,
            )
        else:  # FrozenCandidateFamily already validates this field.
            raise ValueError("unsupported frozen selection objective")
        selected = min(
            certified,
            key=selection_key,
            default=None,
        )
        return StratifiedWarrantResult(
            decision=PROMOTE if selected else INCONCLUSIVE,
            certified_policy_ids=certified,
            selected_policy_id=selected,
            component_p_values=tuple(sorted((hypothesis_id, value) for _, hypothesis_id, value in components)),
            candidate_p_values=tuple(sorted(candidate_raw.items())),
            candidate_adjusted_p_values=adjusted.adjusted_p_values,
            evidence_scope_counts=tuple(sorted(counts.items())),
        )
    except (KeyError, TypeError, ValueError) as exc:
        return StratifiedWarrantResult(
            decision=BLOCKED_INVALID_EVIDENCE,
            certified_policy_ids=(),
            selected_policy_id=None,
            component_p_values=(),
            candidate_p_values=(),
            candidate_adjusted_p_values=(),
            evidence_scope_counts=(),
            invalid_reason=str(exc),
        )


def exact_binomial_tail_at_least(required: int, draws: int, probability: float) -> float:
    _positive_int(required, "required", allow_zero=True)
    _positive_int(draws, "draws", allow_zero=True)
    p = _finite(probability, "probability")
    if not 0.0 <= p <= 1.0:
        raise ValueError("probability must lie in [0,1]")
    if required <= 0:
        return 1.0
    if required > draws:
        return 0.0
    if p == 0.0:
        return 0.0
    if p == 1.0:
        return 1.0
    if required == 1:
        return -math.expm1(draws * math.log1p(-p))
    logs = [
        math.lgamma(draws + 1) - math.lgamma(k + 1) - math.lgamma(draws - k + 1)
        + k * math.log(p) + (draws - k) * math.log1p(-p)
        for k in range(required, draws + 1)
    ]
    largest = max(logs)
    return min(1.0, math.exp(largest) * math.fsum(math.exp(value - largest) for value in logs))


def minimum_screened_units(required: int, success_probability: float, target: float, cap: int) -> int | None:
    _positive_int(required, "required")
    _positive_int(cap, "cap")
    target_value = _finite(target, "target")
    if not 0.0 < target_value < 1.0:
        raise ValueError("target must lie strictly between zero and one")
    if not 0.0 < success_probability <= 1.0:
        raise ValueError("success_probability must lie in (0,1]")
    low, high = required, cap
    if exact_binomial_tail_at_least(required, high, success_probability) < target_value:
        return None
    while low < high:
        middle = (low + high) // 2
        if exact_binomial_tail_at_least(required, middle, success_probability) >= target_value:
            high = middle
        else:
            low = middle + 1
    return low


def recruitment_cost_plan(
    *,
    core_n: int,
    group_quotas: Mapping[str, int],
    prevalence: Mapping[str, float],
    eligibility_rate: float,
    usable_rate: float,
    duplicate_rate: float,
    acquisition_probability: float,
    screening_cap: int,
    unit_costs: Mapping[str, float],
) -> dict[str, object]:
    """Deterministic workload plan; costs are declared planning inputs."""

    _positive_int(core_n, "core_n")
    valid_yield = _finite(eligibility_rate, "eligibility_rate") * _finite(usable_rate, "usable_rate") * (1.0 - _finite(duplicate_rate, "duplicate_rate"))
    if not 0.0 < valid_yield <= 1.0:
        raise ValueError("combined valid yield must lie in (0,1]")
    expected_core_attempts = core_n / valid_yield
    expected_core_by_group = {group: core_n * p for group, p in prevalence.items()}
    expected_topups = {group: max(0.0, group_quotas[group] - expected_core_by_group[group]) for group in group_quotas}
    expected_topup_attempts = {
        group: count / valid_yield for group, count in expected_topups.items()
    }
    requirement_count = 1 + len(group_quotas)
    simultaneous_target = 1.0 - (1.0 - acquisition_probability) / requirement_count
    core_screen_bound = minimum_screened_units(
        core_n, valid_yield, simultaneous_target, screening_cap
    )
    conservative_screened: dict[str, int | None] = {}
    for group, quota in group_quotas.items():
        # Ignore all random core credit.  This is an unconditional conservative
        # acquisition bound for a fresh general-frame screen, not an expected-
        # core plug-in calculation.
        required = quota
        success = prevalence[group] * valid_yield
        conservative_screened[group] = minimum_screened_units(
            required, success, simultaneous_target, screening_cap
        )
    simultaneous_total = None
    if core_screen_bound is not None and all(
        value is not None for value in conservative_screened.values()
    ):
        simultaneous_total = core_screen_bound + sum(
            int(value) for value in conservative_screened.values()
        )
    expected_screened = expected_core_attempts + math.fsum(
        count / prevalence[group] for group, count in expected_topup_attempts.items()
    )
    expected_evaluated = core_n + math.fsum(expected_topups.values())
    costs = {name: _finite(value, f"cost {name}") for name, value in unit_costs.items()}
    required_costs = {"group_screen", "eligibility_screen", "full_evaluation", "manual_review", "data_acquisition"}
    if set(costs) != required_costs or any(value < 0.0 for value in costs.values()):
        raise ValueError("unit costs must contain every nonnegative cost stage")
    total_cost = (
        expected_screened * (costs["group_screen"] + costs["eligibility_screen"] + costs["data_acquisition"])
        + expected_evaluated * (costs["full_evaluation"] + costs["manual_review"])
    )
    return {
        "expected_screened_units": expected_screened,
        "expected_evaluated_units": expected_evaluated,
        "expected_core_attempts": expected_core_attempts,
        "expected_topup_units": expected_topups,
        "simultaneous_acquisition_probability_target": acquisition_probability,
        "union_bound_per_requirement_probability": simultaneous_target,
        "conservative_core_screened_units": core_screen_bound,
        "conservative_high_probability_screened_units_by_group_no_core_credit": conservative_screened,
        "conservative_simultaneous_high_probability_screened_units": simultaneous_total,
        "total_acquisition_cost": total_cost,
        "cost_unit": "declared_normalized_planning_cost",
    }


def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    _positive_int(trials, "trials")
    if successes < 0 or successes > trials:
        raise ValueError("successes must lie between zero and trials")
    if confidence != 0.95:
        raise ValueError("planning study v1 freezes the 95% Wilson interval")
    z = 1.959963984540054
    p = successes / trials
    denom = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denom
    radius = z / denom * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials))
    return max(0.0, center - radius), min(1.0, center + radius)


def _mixed_uniforms(
    rng: np.random.Generator,
    size: int,
    count: int,
    shared_fraction: float,
    *,
    shared: np.ndarray | None = None,
    use_shared: np.ndarray | None = None,
) -> np.ndarray:
    shared = rng.random(size) if shared is None else shared
    use_shared = (
        rng.random((count, size)) < shared_fraction
        if use_shared is None
        else use_shared
    )
    independent = rng.random((count, size))
    return np.where(use_shared, shared, independent)


def _mixed_signs(
    rng: np.random.Generator,
    size: int,
    count: int,
    shared_fraction: float,
    *,
    shared: np.ndarray | None = None,
    use_shared: np.ndarray | None = None,
) -> np.ndarray:
    return np.where(
        _mixed_uniforms(
            rng,
            size,
            count,
            shared_fraction,
            shared=shared,
            use_shared=use_shared,
        )
        < 0.5,
        -1.0,
        1.0,
    )


def simulate_joint_power(
    *,
    family: FrozenCandidateFamily,
    policy: PolicyConfig,
    core_n: int,
    group_quotas: Mapping[str, int],
    group_prevalence: Mapping[str, float],
    safe_policy_ids: Iterable[str],
    binary_alternatives: Mapping[str, float],
    quality_slack: float,
    dependence_level: str,
    replicates: int,
    master_seed: int,
) -> dict[str, object]:
    """Estimate developmental joint power under prespecified bounded models."""

    _positive_int(replicates, "replicates")
    if dependence_level not in DEPENDENCE_LEVELS:
        raise ValueError("unknown dependence level")
    if len(family.group_ids) != 2:
        raise ValueError("joint-power planning v1 requires exactly two frozen groups")
    if set(group_prevalence) != set(family.group_ids):
        raise ValueError("prevalence must exactly match frozen groups")
    safe_ids = tuple(sorted(safe_policy_ids))
    if not safe_ids or set(safe_ids) - set(family.candidate_policy_ids):
        raise ValueError("safe planning candidates must be a nonempty family subset")
    candidate_count = len(family.candidate_policy_ids)
    shared_fraction = DEPENDENCE_FRACTIONS[dependence_level]
    alpha_floor = family.familywise_error_level / candidate_count
    component_hits = {policy_id: {} for policy_id in safe_ids}
    candidate_hits = {policy_id: 0 for policy_id in safe_ids}
    any_safe = any_unsafe = total_certified = safe_selected = unsafe_selected = no_selection = 0
    groups = family.group_ids
    minority_probability = group_prevalence[groups[-1]]

    lower, upper = family.quality_delta_bounds
    quality_noise_half_width = 0.05
    planned_quality_means: list[dict[str, float]] = []
    for candidate_index, policy_id in enumerate(family.candidate_policy_ids):
        safe = policy_id in safe_ids
        means_by_group = {
            group: -family.group_quality_noninferiority_margin + quality_slack
            for group in groups
        }
        if not safe:
            failing = (candidate_index - len(safe_ids)) % 8
            if failing == 0:
                means_by_group = {
                    group: -family.quality_noninferiority_margin - 0.01
                    for group in groups
                }
            elif failing in (1, 2):
                means_by_group[groups[failing - 1]] = (
                    -family.group_quality_noninferiority_margin - 0.01
                )
        for mean in means_by_group.values():
            if (
                not math.isfinite(mean)
                or mean - quality_noise_half_width < lower
                or mean + quality_noise_half_width > upper
            ):
                raise ValueError(
                    "configured quality delta exceeds frozen support by noise width"
                )
        planned_quality_means.append(means_by_group)

    for replicate in range(replicates):
        rng = np.random.default_rng(deterministic_seed(master_seed, core_n, tuple(sorted(group_quotas.items())), dependence_level, replicate))
        core_labels_arr = np.where(rng.random(core_n) < minority_probability, groups[-1], groups[0])
        core_labels = tuple(str(value) for value in core_labels_arr)
        core_counts = {group: int(np.sum(core_labels_arr == group)) for group in groups}
        topup_counts = {group: max(0, group_quotas[group] - core_counts[group]) for group in groups}
        topup_ids = tuple((group, tuple(f"t-{replicate}-{group}-{i}" for i in range(topup_counts[group]))) for group in groups)

        # One unit-level latent and one candidate/unit mixture mask are reused
        # across quality and binary risks.  This creates the prespecified
        # cross-risk as well as cross-candidate shared-variation sensitivity
        # while preserving every declared marginal distribution.
        core_latent = rng.random(core_n)
        core_shared_mask = rng.random((candidate_count, core_n)) < shared_fraction
        quality_core_signs = _mixed_signs(
            rng,
            core_n,
            candidate_count,
            shared_fraction,
            shared=core_latent,
            use_shared=core_shared_mask,
        )
        binary_core_uniforms = {
            risk: _mixed_uniforms(
                rng,
                core_n,
                candidate_count,
                shared_fraction,
                shared=core_latent,
                use_shared=core_shared_mask,
            )
            for risk in BINARY_RISKS
        }
        topup_latent = {group: rng.random(topup_counts[group]) for group in groups}
        topup_shared_mask = {
            group: rng.random((candidate_count, topup_counts[group])) < shared_fraction
            for group in groups
        }
        quality_topup_signs = {
            group: _mixed_signs(
                rng,
                topup_counts[group],
                candidate_count,
                shared_fraction,
                shared=topup_latent[group],
                use_shared=topup_shared_mask[group],
            )
            for group in groups
        }
        binary_topup_uniforms = {
            (group, risk): _mixed_uniforms(
                rng,
                topup_counts[group],
                candidate_count,
                shared_fraction,
                shared=topup_latent[group],
                use_shared=topup_shared_mask[group],
            )
            for group in groups for risk in family.enabled_group_risks
        }
        candidates: list[CandidateSamples] = []
        for candidate_index, policy_id in enumerate(family.candidate_policy_ids):
            safe = policy_id in safe_ids
            # The configured slack is measured from the group boundary. With
            # margins 0.03 (group) and 0.02 (overall), quality_slack=0.10
            # therefore gives group slack 0.10 and overall slack 0.09.
            means_by_group = dict(planned_quality_means[candidate_index])
            binary_probabilities = dict(binary_alternatives)
            group_safety = {group: binary_alternatives["safety_violation_probability"] for group in groups}
            if not safe:
                failing = (candidate_index - len(safe_ids)) % 8
                if failing == 3:
                    # An overall marginal cannot exceed the threshold while
                    # every exhaustive group marginal remains below it.  This
                    # control therefore violates the overall component and,
                    # necessarily, the exhaustive group components as well.
                    binary_probabilities["safety_violation_probability"] = family.binary_threshold("safety_violation_probability") + 0.005
                    group_safety = {group: binary_probabilities["safety_violation_probability"] for group in groups}
                elif failing == 4:
                    binary_probabilities["execution_failure_probability"] = family.binary_threshold("execution_failure_probability") + 0.005
                elif failing == 5:
                    binary_probabilities["insufficient_evidence_probability"] = family.binary_threshold("insufficient_evidence_probability") + 0.01
                elif failing == 6:
                    group_safety[groups[0]] = family.binary_threshold("safety_violation_probability") + 0.005
                else:
                    group_safety[groups[-1]] = family.binary_threshold("safety_violation_probability") + 0.005
            core_means = np.asarray([means_by_group[label] for label in core_labels])
            core_quality = (
                core_means
                + quality_noise_half_width * quality_core_signs[candidate_index]
            )
            if (
                not np.all(np.isfinite(core_quality))
                or np.any(core_quality < lower)
                or np.any(core_quality > upper)
            ):
                raise ValueError("generated core quality delta exceeds frozen support")
            core_binary_items = []
            for risk in BINARY_RISKS:
                probabilities: float | np.ndarray
                if risk == "safety_violation_probability":
                    probabilities = np.asarray(
                        [group_safety[label] for label in core_labels], dtype=float
                    )
                else:
                    probabilities = binary_probabilities[risk]
                core_binary_items.append(
                    (
                        risk,
                        tuple(
                            int(value)
                            for value in (
                                binary_core_uniforms[risk][candidate_index]
                                < probabilities
                            )
                        ),
                    )
                )
            core_binary = tuple(core_binary_items)
            topup_quality_items = []
            for group in groups:
                values = (
                    means_by_group[group]
                    + quality_noise_half_width
                    * quality_topup_signs[group][candidate_index]
                )
                if (
                    not np.all(np.isfinite(values))
                    or np.any(values < lower)
                    or np.any(values > upper)
                ):
                    raise ValueError(
                        "generated group quality delta exceeds frozen support"
                    )
                topup_quality_items.append(
                    (group, tuple(float(value) for value in values))
                )
            topup_quality = tuple(topup_quality_items)
            topup_binary = tuple(
                (
                    group,
                    tuple(
                        (
                            risk,
                            tuple(int(value) for value in (binary_topup_uniforms[(group, risk)][candidate_index] < (group_safety[group] if risk == "safety_violation_probability" else binary_probabilities[risk]))),
                        )
                        for risk in family.enabled_group_risks
                    ),
                )
                for group in groups
            )
            cost_rank = (candidate_index * 7 + 3) % candidate_count
            latency_rank = (candidate_index * 11 + 5) % candidate_count
            candidates.append(CandidateSamples(policy_id, core_labels, tuple(float(value) for value in core_quality), core_binary, topup_quality, topup_binary, 1.0 + cost_rank / 100.0, 1.0 + latency_rank / 200.0))

        evidence = StratifiedEvidence(
            evidence_id=f"planning|{core_n}|{dependence_level}|{replicate}",
            core_unit_ids=tuple(f"c-{replicate}-{i}" for i in range(core_n)),
            topup_unit_ids=topup_ids,
            candidates=tuple(candidates),
        )
        result = evaluate_stratified_iut_holm(evidence, family, policy, group_quotas)
        if result.decision == BLOCKED_INVALID_EVIDENCE:
            raise RuntimeError(result.invalid_reason)
        pvalues = dict(result.component_p_values)
        for safe_id in safe_ids:
            candidate_component_ids = [key for key in pvalues if key.startswith(f"{safe_id}::")]
            for component_id in candidate_component_ids:
                short_id = component_id.split("::", 1)[1]
                component_hits[safe_id][short_id] = component_hits[safe_id].get(short_id, 0) + int(pvalues[component_id] <= alpha_floor)
            candidate_hits[safe_id] += int(safe_id in result.certified_policy_ids)
        certified = set(result.certified_policy_ids)
        any_safe += int(bool(certified.intersection(safe_ids)))
        any_unsafe += int(bool(certified - set(safe_ids)))
        total_certified += len(certified)
        if result.selected_policy_id is None:
            no_selection += 1
        elif result.selected_policy_id in safe_ids:
            safe_selected += 1
        else:
            unsafe_selected += 1

    candidate_rows = []
    for policy_id in safe_ids:
        powers = {risk: count / replicates for risk, count in sorted(component_hits[policy_id].items())}
        union_lower = max(0.0, 1.0 - math.fsum(1.0 - value for value in powers.values()))
        independence = math.prod(powers.values())
        candidate_rows.append({
            "policy_id": policy_id,
            "marginal_component_powers": powers,
            "union_bound_joint_lower_bound": union_lower,
            "independence_approximation": independence,
            "monte_carlo_joint_power": candidate_hits[policy_id] / replicates,
            "monte_carlo_joint_power_wilson": wilson_interval(candidate_hits[policy_id], replicates),
        })
    return {
        "core_n": core_n,
        "group_quotas": dict(group_quotas),
        "dependence_level": dependence_level,
        "shared_variation_fraction": shared_fraction,
        "replicates": replicates,
        "candidate_results": candidate_rows,
        "at_least_one_safe_certification_probability": any_safe / replicates,
        "at_least_one_safe_wilson": wilson_interval(any_safe, replicates),
        "false_certification_probability": any_unsafe / replicates,
        "false_certification_wilson": wilson_interval(any_unsafe, replicates),
        "expected_certified_set_size": total_certified / replicates,
        "safe_selection_probability": safe_selected / replicates,
        "unsafe_selection_probability": unsafe_selected / replicates,
        "no_selection_probability": no_selection / replicates,
        "planning_simulator_used_prespecified_truth": True,
        "warrant_method_accessed_population_truth": False,
        "confirmatory_evidence_collected": False,
    }


__all__ = [
    "BLOCKED_INSUFFICIENT_GROUP_EVIDENCE",
    "BLOCKED_PENDING_OWNER_OPERATIONAL_FIELDS",
    "BLOCKED_TOPUP_EXCHANGEABILITY",
    "CONTRACT_ID",
    "DEPENDENCE_FRACTIONS",
    "FULL_STATUS",
    "PLANNER_ID",
    "CandidateSamples",
    "SamplingContract",
    "StratifiedEvidence",
    "StratifiedWarrantResult",
    "deterministic_seed",
    "evaluate_stratified_iut_holm",
    "minimum_screened_units",
    "normalize_group_label",
    "recruitment_cost_plan",
    "simulate_joint_power",
    "stable_hash",
    "wilson_interval",
]
