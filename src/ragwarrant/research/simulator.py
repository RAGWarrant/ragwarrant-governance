# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .types import (
    BINARY_RISKS,
    ENABLED_RISKS,
    CandidateTruth,
    EvidenceRow,
    ObservedEvidence,
    PolicyConfig,
    ScenarioTruth,
    SimulatedTrial,
    pairs,
)
from .seed_schedule import (
    SEED_SCHEDULE_VERSION,
    canonical_trial_identity,
    profile_master_seed_value,
    schedule_seed_fingerprint,
    trial_seed,
    validate_seed_schedule_metadata,
)
from .public_beacon import VerifiedFullEntropy, full_trial_seed_digest


KNOWN_METHODS = {
    "always_block",
    "oracle_safe_objective",
    "naive_point_estimate",
    "corrected_paired_bootstrap_gate",
    "current_ragwarrant_adapter",
}

KNOWN_FAMILIES = {
    "ALL_UNSAFE_BOUNDARY",
    "ONE_CLEARLY_SAFE",
    "MANY_CANDIDATES_MULTIPLICITY",
    "DEPENDENT_CANDIDATES",
    "HIDDEN_GROUP_REGRESSION",
    "DEVELOPMENT_CONFIRMATORY_SHIFT",
    "MULTIPLE_SAFE_CANDIDATES",
}

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_seed(master_seed: int, *parts: object) -> int:
    payload = canonical_json([int(master_seed), *parts])
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def _check_finite(value: object, path: str = "config") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            _check_finite(child, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            _check_finite(child, f"{path}[{index}]")
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"{path} must be finite")
        return
    raise ValueError(f"{path} contains unsupported value type {type(value).__name__}")


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a finite number, not {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{path} must be finite")
    return number


def _unique_ids(items: Sequence[Mapping[str, Any]], key: str, label: str) -> tuple[str, ...]:
    ids = tuple(str(item.get(key, "")).strip() for item in items)
    if any(not item_id for item_id in ids):
        raise ValueError(f"{label} must define non-empty {key} values")
    invalid = [item_id for item_id in ids if SAFE_ID.fullmatch(item_id) is None]
    if invalid:
        raise ValueError(
            f"{label} {key} values must use only portable letters, digits, dots, underscores, or hyphens: {invalid}"
        )
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate {label} {key}")
    return ids


def _probability(value: object, path: str) -> float:
    number = _number(value, path)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{path} must be between 0 and 1")
    return number


def _group_map(value: object, group_ids: tuple[str, ...], path: str) -> dict[str, float]:
    if isinstance(value, Mapping):
        keys = {str(key) for key in value}
        if keys != set(group_ids):
            missing = sorted(set(group_ids) - keys)
            extra = sorted(keys - set(group_ids))
            raise ValueError(f"{path} group keys mismatch; missing={missing}, extra={extra}")
        return {
            group_id: _number(value[group_id], f"{path}.{group_id}")
            for group_id in group_ids
        }
    number = _number(value, path)
    return {group_id: number for group_id in group_ids}


def _phase_maps(
    candidate: Mapping[str, Any], phase: str, group_ids: tuple[str, ...]
) -> dict[str, dict[str, float]]:
    if phase not in candidate or not isinstance(candidate[phase], Mapping):
        raise ValueError(f"candidate {candidate.get('policy_id')} missing {phase} parameters")
    values = candidate[phase]
    required = (
        "quality_delta_by_group",
        *BINARY_RISKS,
        "mean_cost",
        "mean_latency",
    )
    missing = [name for name in required if name not in values]
    if missing:
        raise ValueError(
            f"candidate {candidate.get('policy_id')} {phase} missing fields: {missing}"
        )
    return {
        name: _group_map(values[name], group_ids, f"{candidate.get('policy_id')}.{phase}.{name}")
        for name in required
    }


def validate_config(config: Mapping[str, Any]) -> None:
    _check_finite(config)
    if str(config.get("protocol_version", "")) != "false_promotion_benchmark_v1":
        raise ValueError("protocol_version must be false_promotion_benchmark_v1")
    validate_seed_schedule_metadata(config)
    master_seed = config.get("master_seed")
    if isinstance(master_seed, bool) or not isinstance(master_seed, int) or master_seed < 0:
        raise ValueError("master_seed must be a nonnegative integer")

    profiles = config.get("profiles")
    if not isinstance(profiles, Mapping) or not profiles:
        raise ValueError("profiles must be a non-empty mapping")
    for profile_id, profile in profiles.items():
        if not isinstance(profile, Mapping):
            raise ValueError(f"profile {profile_id} must be a mapping")
        for field in ("replicate_count", "bootstrap_resamples"):
            value = profile.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"profile {profile_id} {field} must be a positive integer")

    methods = config.get("methods")
    if not isinstance(methods, Sequence) or isinstance(methods, (str, bytes)):
        raise ValueError("methods must be a list")
    method_ids = tuple(str(value) for value in methods)
    if len(set(method_ids)) != len(method_ids):
        raise ValueError("duplicate method IDs")
    unknown_methods = sorted(set(method_ids) - KNOWN_METHODS)
    if unknown_methods:
        raise ValueError(f"unknown methods: {unknown_methods}")
    missing_methods = sorted(KNOWN_METHODS - set(method_ids))
    if missing_methods:
        raise ValueError(f"required benchmark methods missing: {missing_methods}")

    policy = config.get("policy")
    if not isinstance(policy, Mapping):
        raise ValueError("policy must be a mapping")
    for margin in ("quality_noninferiority_margin", "group_quality_noninferiority_margin"):
        value = _number(policy.get(margin), f"policy.{margin}")
        if value < 0.0:
            raise ValueError(f"policy {margin} must be nonnegative")
    for risk in BINARY_RISKS:
        threshold_name = f"max_{risk}"
        _probability(policy.get(threshold_name, -1.0), f"policy.{threshold_name}")
    for weight in ("cost_weight", "latency_weight"):
        if _number(policy.get(weight), f"policy.{weight}") < 0.0:
            raise ValueError(f"policy {weight} must be nonnegative")
    confidence = _number(policy.get("confidence_level"), "policy.confidence_level")
    if not 0.0 < confidence < 1.0:
        raise ValueError("policy confidence_level must be strictly between 0 and 1")

    scenarios = config.get("scenarios")
    if not isinstance(scenarios, Sequence) or isinstance(scenarios, (str, bytes)) or not scenarios:
        raise ValueError("scenarios must be a non-empty list")
    _unique_ids(scenarios, "scenario_id", "scenario")
    for scenario in scenarios:
        _validate_scenario(scenario, policy)


def _validate_scenario(scenario: Mapping[str, Any], policy: Mapping[str, Any]) -> None:
    scenario_id = str(scenario["scenario_id"])
    family = str(scenario.get("family", "")).strip()
    if not family:
        raise ValueError(f"scenario {scenario_id} missing family")
    if family not in KNOWN_FAMILIES:
        raise ValueError(f"scenario {scenario_id} has unknown family: {family}")
    sample_sizes = scenario.get("sample_sizes")
    if not isinstance(sample_sizes, Sequence) or isinstance(sample_sizes, (str, bytes)):
        raise ValueError(f"scenario {scenario_id} sample_sizes must be a list")
    if len(sample_sizes) < 2:
        raise ValueError(f"scenario {scenario_id} must define at least two sample sizes")
    if len(set(sample_sizes)) != len(sample_sizes):
        raise ValueError(f"scenario {scenario_id} contains duplicate sample sizes")
    for sample_size in sample_sizes:
        if isinstance(sample_size, bool) or not isinstance(sample_size, int) or sample_size <= 0:
            raise ValueError(f"scenario {scenario_id} sample sizes must be positive integers")

    incumbent = scenario.get("incumbent")
    if not isinstance(incumbent, Mapping):
        raise ValueError(f"scenario {scenario_id} missing incumbent")
    groups = scenario.get("groups")
    if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes)) or not groups:
        raise ValueError(f"scenario {scenario_id} missing group definitions")
    group_ids = tuple(sorted(_unique_ids(groups, "group_id", f"scenario {scenario_id} group")))
    prevalence = {
        str(group["group_id"]): _number(
            group.get("prevalence"),
            f"scenario {scenario_id} group {group['group_id']} prevalence",
        )
        for group in groups
    }
    if any(value <= 0.0 or value > 1.0 for value in prevalence.values()):
        raise ValueError(f"scenario {scenario_id} group prevalences must be in (0, 1]")
    if not math.isclose(sum(prevalence.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(f"scenario {scenario_id} group prevalences must sum to 1")
    incumbent_quality = _group_map(
        incumbent.get("quality_mean_by_group"), group_ids, f"scenario {scenario_id} incumbent"
    )
    if any(not 0.0 <= value <= 1.0 for value in incumbent_quality.values()):
        raise ValueError(f"scenario {scenario_id} incumbent quality means must be in [0, 1]")

    enabled_risks = tuple(scenario.get("enabled_risks", ENABLED_RISKS))
    if len(set(enabled_risks)) != len(enabled_risks):
        raise ValueError(f"scenario {scenario_id} contains duplicate enabled risks")
    unknown_risks = sorted(set(enabled_risks) - set(ENABLED_RISKS))
    if unknown_risks:
        raise ValueError(f"scenario {scenario_id} unknown enabled risks: {unknown_risks}")
    enabled_group_risks = tuple(scenario.get("enabled_group_risks", ()))
    if len(set(enabled_group_risks)) != len(enabled_group_risks):
        raise ValueError(f"scenario {scenario_id} contains duplicate enabled group risks")
    if set(enabled_group_risks) - set(BINARY_RISKS):
        raise ValueError(f"scenario {scenario_id} has unknown enabled group risks")
    if set(enabled_group_risks) - set(enabled_risks):
        raise ValueError(
            f"scenario {scenario_id} enabled group risks must also be enabled overall"
        )

    shared_fraction = scenario.get("shared_outcome_fraction")
    shared = _group_map(shared_fraction, BINARY_RISKS, f"scenario {scenario_id} shared fraction")
    for risk, value in shared.items():
        _probability(value, f"scenario {scenario_id} shared_outcome_fraction.{risk}")

    noise = scenario.get("noise")
    if not isinstance(noise, Mapping):
        raise ValueError(f"scenario {scenario_id} missing noise settings")
    noise_fields = (
        "quality_shared_half_width",
        "quality_candidate_half_width",
        "cost_shared_half_width",
        "cost_candidate_half_width",
        "latency_shared_half_width",
        "latency_candidate_half_width",
    )
    for field in noise_fields:
        if _number(noise.get(field), f"scenario {scenario_id} noise {field}") < 0.0:
            raise ValueError(f"scenario {scenario_id} noise {field} must be nonnegative")
    bounds = noise.get("quality_delta_bounds")
    if (
        not isinstance(bounds, Sequence)
        or isinstance(bounds, (str, bytes))
        or len(bounds) != 2
        or _number(bounds[0], f"scenario {scenario_id} quality_delta_bounds[0]")
        >= _number(bounds[1], f"scenario {scenario_id} quality_delta_bounds[1]")
    ):
        raise ValueError(f"scenario {scenario_id} quality_delta_bounds must be [low, high]")

    candidates = scenario.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)) or not candidates:
        raise ValueError(f"scenario {scenario_id} must define candidates")
    policy_ids = _unique_ids(candidates, "policy_id", f"scenario {scenario_id} candidate")
    if "incumbent" in policy_ids:
        raise ValueError(f"scenario {scenario_id} candidate ID 'incumbent' is reserved")

    quality_amplitude = float(noise["quality_shared_half_width"]) + float(
        noise["quality_candidate_half_width"]
    )
    cost_amplitude = float(noise["cost_shared_half_width"]) + float(
        noise["cost_candidate_half_width"]
    )
    latency_amplitude = float(noise["latency_shared_half_width"]) + float(
        noise["latency_candidate_half_width"]
    )
    low_delta, high_delta = float(bounds[0]), float(bounds[1])
    for candidate in candidates:
        for phase in ("development", "confirmatory"):
            phase_maps = _phase_maps(candidate, phase, group_ids)
            for risk in BINARY_RISKS:
                for group_id, probability in phase_maps[risk].items():
                    _probability(
                        probability,
                        f"scenario {scenario_id} {candidate['policy_id']} {phase} {risk}.{group_id}",
                    )
            for group_id in group_ids:
                delta = phase_maps["quality_delta_by_group"][group_id]
                if delta - quality_amplitude < low_delta or delta + quality_amplitude > high_delta:
                    raise ValueError(
                        f"scenario {scenario_id} {candidate['policy_id']} {phase} quality noise "
                        f"violates configured delta bounds for group {group_id}"
                    )
                candidate_quality = incumbent_quality[group_id] + delta
                if candidate_quality - quality_amplitude < 0.0 or candidate_quality + quality_amplitude > 1.0:
                    raise ValueError(
                        f"scenario {scenario_id} {candidate['policy_id']} {phase} quality support "
                        f"leaves [0, 1] for group {group_id}"
                    )
                if phase_maps["mean_cost"][group_id] - cost_amplitude <= 0.0:
                    raise ValueError(
                        f"scenario {scenario_id} {candidate['policy_id']} {phase} cost support must be positive"
                    )
                if phase_maps["mean_latency"][group_id] - latency_amplitude <= 0.0:
                    raise ValueError(
                        f"scenario {scenario_id} {candidate['policy_id']} {phase} latency support must be positive"
                    )


def load_config(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    loaded = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("benchmark config must contain a mapping at the root")
    validate_config(loaded)
    return loaded


def policy_config(
    config: Mapping[str, Any], scenario: Mapping[str, Any], profile: str
) -> PolicyConfig:
    if profile not in config["profiles"]:
        raise ValueError(f"unknown profile: {profile}")
    base = config["policy"]
    groups = tuple(sorted(str(group["group_id"]) for group in scenario["groups"]))
    return PolicyConfig(
        quality_noninferiority_margin=float(base["quality_noninferiority_margin"]),
        group_quality_noninferiority_margin=float(base["group_quality_noninferiority_margin"]),
        max_safety_violation_probability=float(base["max_safety_violation_probability"]),
        max_execution_failure_probability=float(base["max_execution_failure_probability"]),
        max_insufficient_evidence_probability=float(
            base["max_insufficient_evidence_probability"]
        ),
        cost_weight=float(base["cost_weight"]),
        latency_weight=float(base["latency_weight"]),
        confidence_level=float(base["confidence_level"]),
        bootstrap_resamples=int(config["profiles"][profile]["bootstrap_resamples"]),
        enabled_risks=tuple(scenario.get("enabled_risks", ENABLED_RISKS)),
        enabled_group_risks=tuple(scenario.get("enabled_group_risks", ())),
        group_ids=groups,
    )


def _weighted(values: Mapping[str, float], prevalence: Mapping[str, float]) -> float:
    return sum(prevalence[group_id] * values[group_id] for group_id in prevalence)


def _candidate_truth(
    candidate: Mapping[str, Any],
    phase: str,
    group_ids: tuple[str, ...],
    prevalence: Mapping[str, float],
    policy: PolicyConfig,
) -> CandidateTruth:
    maps = _phase_maps(candidate, phase, group_ids)
    overall_quality = _weighted(maps["quality_delta_by_group"], prevalence)
    overall_risks = {risk: _weighted(maps[risk], prevalence) for risk in BINARY_RISKS}
    overall_cost = _weighted(maps["mean_cost"], prevalence)
    overall_latency = _weighted(maps["mean_latency"], prevalence)

    failed_overall: list[str] = []
    failed_subgroup: list[str] = []
    if "overall_quality" in policy.enabled_risks and overall_quality < -policy.quality_noninferiority_margin:
        failed_overall.append("overall_quality")
    if "group_quality" in policy.enabled_risks:
        for group_id, value in maps["quality_delta_by_group"].items():
            if value < -policy.group_quality_noninferiority_margin:
                failed_subgroup.append(f"group_quality:{group_id}")
    for risk in BINARY_RISKS:
        if risk not in policy.enabled_risks:
            continue
        threshold = policy.binary_threshold(risk)
        if overall_risks[risk] > threshold:
            failed_overall.append(risk)
        if risk in policy.enabled_group_risks:
            for group_id, value in maps[risk].items():
                if value > threshold:
                    failed_subgroup.append(f"{risk}:{group_id}")
    failed = tuple(failed_overall + failed_subgroup)
    return CandidateTruth(
        policy_id=str(candidate["policy_id"]),
        phase=phase,
        overall_quality_delta_vs_incumbent=overall_quality,
        quality_delta_by_group=pairs(maps["quality_delta_by_group"]),
        safety_violation_probability=overall_risks["safety_violation_probability"],
        safety_violation_probability_by_group=pairs(maps["safety_violation_probability"]),
        execution_failure_probability=overall_risks["execution_failure_probability"],
        execution_failure_probability_by_group=pairs(
            maps["execution_failure_probability"]
        ),
        insufficient_evidence_probability=overall_risks[
            "insufficient_evidence_probability"
        ],
        insufficient_evidence_probability_by_group=pairs(
            maps["insufficient_evidence_probability"]
        ),
        mean_cost=overall_cost,
        mean_cost_by_group=pairs(maps["mean_cost"]),
        mean_latency=overall_latency,
        mean_latency_by_group=pairs(maps["mean_latency"]),
        truly_promotion_safe=not failed,
        overall_safe_but_subgroup_unsafe=not failed_overall and bool(failed_subgroup),
        failed_truth_conditions=failed,
    )


def scenario_truth(
    config: Mapping[str, Any],
    scenario: Mapping[str, Any],
    sample_size: int,
    profile: str,
) -> ScenarioTruth:
    policy = policy_config(config, scenario, profile)
    groups = tuple(sorted(scenario["groups"], key=lambda group: str(group["group_id"])))
    group_ids = tuple(str(group["group_id"]) for group in groups)
    prevalence = {str(group["group_id"]): float(group["prevalence"]) for group in groups}
    candidates = tuple(sorted(scenario["candidates"], key=lambda item: str(item["policy_id"])))
    expanded_id = f"{scenario['scenario_id']}__n{sample_size}"
    protocol_hash = sha256_json(
        {
            "protocol_version": config["protocol_version"],
            "policy": config["policy"],
            "scenario": scenario,
            "sample_size": sample_size,
        }
    )
    return ScenarioTruth(
        scenario_id=expanded_id,
        base_scenario_id=str(scenario["scenario_id"]),
        family=str(scenario["family"]),
        sample_size=sample_size,
        group_prevalence=pairs(prevalence),
        enabled_risks=policy.enabled_risks,
        enabled_group_risks=policy.enabled_group_risks,
        development_candidates=tuple(
            _candidate_truth(candidate, "development", group_ids, prevalence, policy)
            for candidate in candidates
        ),
        confirmatory_candidates=tuple(
            _candidate_truth(candidate, "confirmatory", group_ids, prevalence, policy)
            for candidate in candidates
        ),
        protocol_hash=protocol_hash,
    )


def _shared_fractions(scenario: Mapping[str, Any]) -> dict[str, float]:
    return _group_map(
        scenario["shared_outcome_fraction"],
        BINARY_RISKS,
        f"scenario {scenario['scenario_id']} shared fraction",
    )


def generate_evidence(
    config: Mapping[str, Any],
    scenario: Mapping[str, Any],
    sample_size: int,
    trial_index: int,
    phase: str,
    profile: str,
    master_seed: int | VerifiedFullEntropy | None = None,
) -> ObservedEvidence:
    if phase not in {"development", "confirmatory"}:
        raise ValueError("phase must be development or confirmatory")
    if sample_size <= 0 or trial_index < 0:
        raise ValueError("sample_size must be positive and trial_index nonnegative")
    if profile not in config["profiles"]:
        raise ValueError(f"unknown profile: {profile}")
    seed = profile_master_seed_value(config, profile, master_seed)
    base_scenario_id = str(scenario["scenario_id"])
    expanded_id = f"{base_scenario_id}__n{sample_size}"
    identity = canonical_trial_identity(
        SEED_SCHEDULE_VERSION,
        profile,
        base_scenario_id,
        sample_size,
        trial_index,
    )
    evidence_seed = (
        int(full_trial_seed_digest(master_seed._master_seed, identity), 16)
        if profile == "FULL" and isinstance(master_seed, VerifiedFullEntropy)
        else trial_seed(seed, identity)
    )
    groups = tuple(sorted(scenario["groups"], key=lambda group: str(group["group_id"])))
    group_ids = tuple(str(group["group_id"]) for group in groups)
    probabilities = np.array([float(group["prevalence"]) for group in groups])
    group_rng = np.random.default_rng(
        stable_seed(evidence_seed, phase, "groups")
    )
    sampled_groups = group_rng.choice(group_ids, size=sample_size, p=probabilities)
    group_index = {group_id: index for index, group_id in enumerate(group_ids)}
    incumbent_map = _group_map(
        scenario["incumbent"]["quality_mean_by_group"], group_ids, "incumbent"
    )
    incumbent_quality = np.array([incumbent_map[group_id] for group_id in sampled_groups])
    noise = scenario["noise"]

    shared_noise: dict[str, np.ndarray] = {}
    for metric in ("quality", "cost", "latency"):
        rng = np.random.default_rng(
            stable_seed(evidence_seed, phase, metric, "shared")
        )
        shared_noise[metric] = rng.uniform(-1.0, 1.0, size=sample_size)

    shared_fractions = _shared_fractions(scenario)
    risk_shared: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for risk in BINARY_RISKS:
        branch_rng = np.random.default_rng(
            stable_seed(evidence_seed, phase, risk, "shared_branch")
        )
        draw_rng = np.random.default_rng(
            stable_seed(evidence_seed, phase, risk, "shared_draw")
        )
        risk_shared[risk] = (
            branch_rng.random(sample_size) < shared_fractions[risk],
            draw_rng.random(sample_size),
        )

    rows: list[EvidenceRow] = []
    candidates = sorted(scenario["candidates"], key=lambda item: str(item["policy_id"]))
    risk_evidence_names = {
        "safety_violation_probability": "safety_violation",
        "execution_failure_probability": "execution_failure",
        "insufficient_evidence_probability": "insufficient_evidence",
    }
    for candidate in candidates:
        policy_id = str(candidate["policy_id"])
        maps = _phase_maps(candidate, phase, group_ids)
        mapped = {
            name: np.array([values[group_id] for group_id in sampled_groups])
            for name, values in maps.items()
        }
        candidate_noise: dict[str, np.ndarray] = {}
        for metric in ("quality", "cost", "latency"):
            rng = np.random.default_rng(
                stable_seed(evidence_seed, phase, metric, policy_id)
            )
            candidate_noise[metric] = rng.uniform(-1.0, 1.0, size=sample_size)

        quality_delta = (
            mapped["quality_delta_by_group"]
            + float(noise["quality_shared_half_width"]) * shared_noise["quality"]
            + float(noise["quality_candidate_half_width"]) * candidate_noise["quality"]
        )
        cost = (
            mapped["mean_cost"]
            + float(noise["cost_shared_half_width"]) * shared_noise["cost"]
            + float(noise["cost_candidate_half_width"]) * candidate_noise["cost"]
        )
        latency = (
            mapped["mean_latency"]
            + float(noise["latency_shared_half_width"]) * shared_noise["latency"]
            + float(noise["latency_candidate_half_width"]) * candidate_noise["latency"]
        )
        risk_events: dict[str, np.ndarray] = {}
        for risk, evidence_name in risk_evidence_names.items():
            branch, shared_draw = risk_shared[risk]
            independent_rng = np.random.default_rng(
                stable_seed(evidence_seed, phase, risk, policy_id)
            )
            independent_draw = independent_rng.random(sample_size)
            risk_events[evidence_name] = np.where(
                branch, shared_draw < mapped[risk], independent_draw < mapped[risk]
            ).astype(int)

        for index in range(sample_size):
            rows.append(
                EvidenceRow(
                    example_id=f"{phase}-{index:06d}",
                    group_id=str(sampled_groups[index]),
                    policy_id=policy_id,
                    incumbent_quality=float(incumbent_quality[index]),
                    candidate_quality=float(incumbent_quality[index] + quality_delta[index]),
                    quality_delta=float(quality_delta[index]),
                    safety_violation=int(risk_events["safety_violation"][index]),
                    execution_failure=int(risk_events["execution_failure"][index]),
                    insufficient_evidence=int(risk_events["insufficient_evidence"][index]),
                    cost=float(cost[index]),
                    latency=float(latency[index]),
                )
            )

    ordered_rows = tuple(sorted(rows, key=lambda row: (row.example_id, row.policy_id)))
    evidence_hash = sha256_json([row.as_dict() for row in ordered_rows])
    return ObservedEvidence(
        scenario_id=expanded_id,
        phase=phase,
        trial_index=trial_index,
        sample_size=sample_size,
        rows=ordered_rows,
        evidence_hash=evidence_hash,
    )


def simulate_trial(
    config: Mapping[str, Any],
    scenario: Mapping[str, Any],
    sample_size: int,
    trial_index: int,
    profile: str,
    master_seed: int | VerifiedFullEntropy | None = None,
) -> SimulatedTrial:
    truth = scenario_truth(config, scenario, sample_size, profile)
    seed = profile_master_seed_value(config, profile, master_seed)
    identity = canonical_trial_identity(
        SEED_SCHEDULE_VERSION,
        profile,
        str(scenario["scenario_id"]),
        sample_size,
        trial_index,
    )
    return SimulatedTrial(
        truth=truth,
        development_evidence=generate_evidence(
            config,
            scenario,
            sample_size,
            trial_index,
            "development",
            profile,
            seed if profile != "FULL" else master_seed,
        ),
        confirmatory_evidence=generate_evidence(
            config,
            scenario,
            sample_size,
            trial_index,
            "confirmatory",
            profile,
            seed if profile != "FULL" else master_seed,
        ),
        trial_identity=identity,
        seed_fingerprint=(
            full_trial_seed_digest(master_seed._master_seed, identity)
            if profile == "FULL" and isinstance(master_seed, VerifiedFullEntropy)
            else schedule_seed_fingerprint(
                config,
                profile,
                identity,
                development_master_seed=seed,
            )
        ),
    )
