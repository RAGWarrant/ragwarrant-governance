"""Independent planning confirmation for two frozen stratified designs.

This module is an additive orchestration layer. It derives an immutable seed
from every confirmation identity and calls the preserved stratified planning
simulator once for that identity. It does not collect evidence, query a
beacon, or authorize FULL execution.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .fixed_sample_warrant import FrozenCandidateFamily
from .stratified_joint_power import simulate_joint_power, stable_hash, wilson_interval
from .types import PolicyConfig


PROTOCOL_ID = "STRATIFIED_JOINT_POWER_CONFIRMATION_V1"
DESIGN_IDS = (
    "COMPONENT_PLANNING_COMPARATOR",
    "SELECTED_JOINT_PLANNING_CANDIDATE",
)
DEPENDENCE_CONDITIONS = ("low", "medium", "high")
REPLICATES_PER_CELL = 1000
PUBLIC_MASTER_SEED = 1554387201
FOCUS1_DIGEST = "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
V1_BASELINE_COMMIT = "bf3b3331b623afbdaed295919b3ac945c10692f6"


@dataclass(frozen=True)
class ConfirmationIdentity:
    protocol_version: str
    design_id: str
    dependence_condition: str
    replicate_index: int

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_ID:
            raise ValueError("unknown confirmation protocol version")
        if self.design_id not in DESIGN_IDS:
            raise ValueError("unknown confirmation design")
        if self.dependence_condition not in DEPENDENCE_CONDITIONS:
            raise ValueError("unknown confirmation dependence condition")
        if (
            isinstance(self.replicate_index, bool)
            or not isinstance(self.replicate_index, int)
            or not 0 <= self.replicate_index < REPLICATES_PER_CELL
        ):
            raise ValueError("replicate_index is outside the frozen schedule")

    @property
    def canonical(self) -> str:
        return (
            f"{self.protocol_version}|{self.design_id}|"
            f"{self.dependence_condition}|{self.replicate_index}"
        )


def derive_confirmation_seed(
    identity: ConfirmationIdentity,
    master_seed: int = PUBLIC_MASTER_SEED,
) -> int:
    """Derive a stable unsigned 64-bit seed without Python ``hash()``."""

    if isinstance(master_seed, bool) or not isinstance(master_seed, int) or master_seed < 0:
        raise ValueError("master_seed must be a nonnegative integer")
    payload = json.dumps(
        [master_seed, identity.canonical],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


def enumerate_confirmation_schedule() -> tuple[ConfirmationIdentity, ...]:
    return tuple(
        ConfirmationIdentity(PROTOCOL_ID, design_id, dependence, replicate)
        for design_id in DESIGN_IDS
        for dependence in DEPENDENCE_CONDITIONS
        for replicate in range(REPLICATES_PER_CELL)
    )


def schedule_fingerprints() -> dict[str, object]:
    identities = enumerate_confirmation_schedule()
    canonical = [identity.canonical for identity in identities]
    seeds = [derive_confirmation_seed(identity) for identity in identities]
    return {
        "identity_count": len(canonical),
        "identity_set_hash": stable_hash(sorted(canonical)),
        "seed_fingerprint_set_hash": stable_hash(sorted(seeds)),
        "duplicate_identity_count": len(canonical) - len(set(canonical)),
        "duplicate_seed_count": len(seeds) - len(set(seeds)),
    }


def planning_label(successes: int, trials: int, target: float) -> str:
    if target not in (0.80, 0.90):
        raise ValueError("confirmation targets are frozen at 0.80 and 0.90")
    if isinstance(successes, bool) or not isinstance(successes, int):
        raise ValueError("successes must be an integer")
    lower, _ = wilson_interval(successes, trials)
    point = successes / trials
    if lower >= target:
        return (
            "PLANNING_SUPPORTS_80_PERCENT"
            if target == 0.80
            else "PLANNING_SUPPORTS_90_PERCENT"
        )
    if point >= target:
        return "PLANNING_POINT_ESTIMATE_ONLY"
    return "PLANNING_TARGET_NOT_SUPPORTED"


def _empty_candidate_counts(safe_policy_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    return {
        policy_id: {
            "joint": 0,
            "components": {},
            "component_ids": None,
        }
        for policy_id in sorted(safe_policy_ids)
    }


def aggregate_candidate_diagnostics(
    *,
    component_pass_counts: Iterable[tuple[str, int]],
    total_replicates: int,
    direct_joint_certification_count: int,
) -> dict[str, object]:
    """Derive secondary diagnostics from aggregate marginal pass counts."""

    if (
        isinstance(total_replicates, bool)
        or not isinstance(total_replicates, int)
        or total_replicates <= 0
    ):
        raise ValueError("total_replicates must be a positive integer")
    if (
        isinstance(direct_joint_certification_count, bool)
        or not isinstance(direct_joint_certification_count, int)
        or not 0 <= direct_joint_certification_count <= total_replicates
    ):
        raise ValueError("direct joint certification count is invalid")

    counts: dict[str, int] = {}
    for component_id, pass_count in component_pass_counts:
        if (
            not isinstance(component_id, str)
            or not component_id
            or component_id.strip() != component_id
        ):
            raise ValueError("mandatory component identity is malformed")
        if component_id in counts:
            raise ValueError("duplicate mandatory component identity")
        if (
            isinstance(pass_count, bool)
            or not isinstance(pass_count, int)
            or not 0 <= pass_count <= total_replicates
        ):
            raise ValueError("mandatory component pass count is invalid")
        counts[component_id] = pass_count
    if not counts:
        raise ValueError("mandatory component pass counts are required")

    marginal_powers = {
        component_id: pass_count / total_replicates
        for component_id, pass_count in sorted(counts.items())
    }
    return {
        "direct_monte_carlo_joint_certification_count": (
            direct_joint_certification_count
        ),
        "direct_monte_carlo_joint_certification_probability": (
            direct_joint_certification_count / total_replicates
        ),
        "aggregate_union_bound_joint_lower_bound": max(
            0.0,
            math.fsum(marginal_powers.values()) - (len(marginal_powers) - 1),
        ),
        "aggregate_independence_approximation": math.prod(
            marginal_powers.values()
        ),
        "marginal_component_powers": marginal_powers,
    }


def run_confirmation_cell(
    *,
    design_id: str,
    family: FrozenCandidateFamily,
    policy: PolicyConfig,
    core_n: int,
    group_quotas: Mapping[str, int],
    group_prevalence: Mapping[str, float],
    safe_policy_ids: Iterable[str],
    binary_alternatives: Mapping[str, float],
    quality_slack: float,
    dependence_condition: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Run exactly one frozen 1,000-replicate confirmation cell."""

    if design_id not in DESIGN_IDS:
        raise ValueError("unknown confirmation design")
    if dependence_condition not in DEPENDENCE_CONDITIONS:
        raise ValueError("unknown confirmation dependence condition")
    safe_ids = tuple(sorted(safe_policy_ids))
    candidate_counts = _empty_candidate_counts(safe_ids)
    any_safe = false_certification = total_certified = 0
    safe_selection = unsafe_selection = no_selection = 0

    for replicate_index in range(REPLICATES_PER_CELL):
        identity = ConfirmationIdentity(
            PROTOCOL_ID, design_id, dependence_condition, replicate_index
        )
        result = simulate_joint_power(
            family=family,
            policy=policy,
            core_n=core_n,
            group_quotas=group_quotas,
            group_prevalence=group_prevalence,
            safe_policy_ids=safe_ids,
            binary_alternatives=binary_alternatives,
            quality_slack=quality_slack,
            dependence_level=dependence_condition,
            replicates=1,
            master_seed=derive_confirmation_seed(identity),
        )
        any_safe += int(result["at_least_one_safe_certification_probability"])
        false_certification += int(result["false_certification_probability"])
        total_certified += int(round(float(result["expected_certified_set_size"])))
        safe_selection += int(result["safe_selection_probability"])
        unsafe_selection += int(result["unsafe_selection_probability"])
        no_selection += int(result["no_selection_probability"])
        candidate_results = result["candidate_results"]
        if not isinstance(candidate_results, list):
            raise ValueError("candidate results must be a list")
        seen_candidate_ids: set[str] = set()
        for candidate in candidate_results:
            policy_id = str(candidate["policy_id"])
            if policy_id in seen_candidate_ids:
                raise ValueError("duplicate candidate result")
            seen_candidate_ids.add(policy_id)
            if policy_id not in candidate_counts:
                raise ValueError("unexpected candidate result")
            counts = candidate_counts[policy_id]
            counts["joint"] += int(candidate["monte_carlo_joint_power"])
            component_powers = candidate["marginal_component_powers"]
            if not isinstance(component_powers, Mapping) or not component_powers:
                raise ValueError("mandatory component results are required")
            component_ids = tuple(sorted(str(item) for item in component_powers))
            if counts["component_ids"] is None:
                counts["component_ids"] = component_ids
            elif counts["component_ids"] != component_ids:
                raise ValueError("mandatory component result set changed across replicates")
            for component, value in component_powers.items():
                counts["components"][component] = (
                    counts["components"].get(component, 0) + int(value)
                )
        if seen_candidate_ids != set(candidate_counts):
            raise ValueError("candidate result set differs from the frozen safe family")

    trials = REPLICATES_PER_CELL
    any_safe_wilson = wilson_interval(any_safe, trials)
    false_wilson = wilson_interval(false_certification, trials)
    design_row: dict[str, object] = {
        "protocol_id": PROTOCOL_ID,
        "design_id": design_id,
        "core_n": core_n,
        "group_quota": next(iter(group_quotas.values())),
        "dependence_condition": dependence_condition,
        "replicates": trials,
        "at_least_one_safe_certification_count": any_safe,
        "at_least_one_safe_certification_probability": any_safe / trials,
        "at_least_one_safe_wilson_low": any_safe_wilson[0],
        "at_least_one_safe_wilson_high": any_safe_wilson[1],
        "false_certification_count": false_certification,
        "false_certification_probability": false_certification / trials,
        "false_certification_wilson_low": false_wilson[0],
        "false_certification_wilson_high": false_wilson[1],
        "mean_certified_set_size": total_certified / trials,
        "operational_selection_probability": (safe_selection + unsafe_selection) / trials,
        "safe_selection_probability": safe_selection / trials,
        "unsafe_selection_probability": unsafe_selection / trials,
        "no_selection_probability": no_selection / trials,
        "planning_label_80": planning_label(any_safe, trials, 0.80),
        "planning_label_90": planning_label(any_safe, trials, 0.90),
        "conditional_simulation_only": True,
        "confirmatory_evidence_collected": False,
    }
    candidate_rows: list[dict[str, object]] = []
    for policy_id, counts in candidate_counts.items():
        joint = int(counts["joint"])
        joint_wilson = wilson_interval(joint, trials)
        diagnostics = aggregate_candidate_diagnostics(
            component_pass_counts=counts["components"].items(),
            total_replicates=trials,
            direct_joint_certification_count=joint,
        )
        marginal_powers = diagnostics.pop("marginal_component_powers")
        candidate_rows.append(
            {
                "protocol_id": PROTOCOL_ID,
                "design_id": design_id,
                "core_n": core_n,
                "group_quota": next(iter(group_quotas.values())),
                "dependence_condition": dependence_condition,
                "safe_policy_id": policy_id,
                "replicates": trials,
                **diagnostics,
                "direct_monte_carlo_joint_certification_wilson_low": joint_wilson[0],
                "direct_monte_carlo_joint_certification_wilson_high": joint_wilson[1],
                "marginal_component_powers": json.dumps(
                    marginal_powers,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    return design_row, candidate_rows


__all__ = [
    "DEPENDENCE_CONDITIONS",
    "DESIGN_IDS",
    "FOCUS1_DIGEST",
    "PROTOCOL_ID",
    "PUBLIC_MASTER_SEED",
    "REPLICATES_PER_CELL",
    "V1_BASELINE_COMMIT",
    "ConfirmationIdentity",
    "derive_confirmation_seed",
    "enumerate_confirmation_schedule",
    "planning_label",
    "run_confirmation_cell",
    "schedule_fingerprints",
]
