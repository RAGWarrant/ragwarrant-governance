# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import replace
from statistics import NormalDist
from typing import Any

from .methods import (
    method_capabilities,
    method_registry,
    oracle_safe_objective,
)
from .simulator import (
    canonical_json,
    policy_config,
    sha256_json,
    simulate_trial,
    stable_seed,
    validate_config,
)
from .seed_schedule import (
    AMENDMENT_ID,
    CANONICAL_IDENTITY_FORMAT,
    DERIVATION_ALGORITHM,
    SEED_FINGERPRINT_ALGORITHM,
    SEED_SCHEDULE_VERSION,
    build_seed_schedule_manifest,
    profile_master_seed_value,
    validate_revealed_profile_seed_uniqueness,
)
from .public_beacon import (
    FULL_CONFIRMATION_STATUS,
    FULL_ENTROPY_AMENDMENT_ID,
    FULL_ENTROPY_PROTOCOL,
    RETIRED_FULL_SEED_STATUS,
    VerifiedFullEntropy,
    _authorized_full_execution,
)
from .types import (
    CandidateTruth,
    MethodCapability,
    MethodDecision,
    ObservedEvidence,
    PolicyConfig,
    ScenarioTruth,
)


EVENT_FIELDS = (
    "false_promotion",
    "false_certification",
    "false_block",
    "correct_promotion",
    "correct_no_safe_candidate_block",
    "no_decision",
)


def wilson_interval(
    event_count: int, trial_count: int, confidence: float = 0.95
) -> tuple[float, float]:
    if trial_count <= 0:
        raise ValueError("trial_count must be positive")
    if event_count < 0 or event_count > trial_count:
        raise ValueError("event_count must be between zero and trial_count")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between zero and one")
    rate = event_count / trial_count
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    denominator = 1.0 + z * z / trial_count
    center = (rate + z * z / (2.0 * trial_count)) / denominator
    radius = (
        z
        * math.sqrt(
            rate * (1.0 - rate) / trial_count
            + z * z / (4.0 * trial_count * trial_count)
        )
        / denominator
    )
    return max(0.0, center - radius), min(1.0, center + radius)


def _evidence_digest(evidence: ObservedEvidence) -> str:
    return sha256_json([row.as_dict() for row in evidence.rows])


def _opaque_method_evidence(
    evidence: ObservedEvidence, canonical_candidate_ids: tuple[str, ...]
) -> tuple[ObservedEvidence, dict[str, str]]:
    canonical_to_opaque = {
        candidate_id: f"policy_{index:04d}"
        for index, candidate_id in enumerate(canonical_candidate_ids, start=1)
    }
    opaque_to_canonical = {
        opaque: canonical for canonical, opaque in canonical_to_opaque.items()
    }
    opaque_rows = tuple(
        replace(row, policy_id=canonical_to_opaque[row.policy_id]) for row in evidence.rows
    )
    opaque_hash = sha256_json([row.as_dict() for row in opaque_rows])
    return (
        replace(
            evidence,
            scenario_id="scenario_opaque",
            rows=opaque_rows,
            evidence_hash=opaque_hash,
        ),
        opaque_to_canonical,
    )


def _canonical_decision(
    decision: MethodDecision, opaque_to_canonical: Mapping[str, str]
) -> MethodDecision:
    selected = (
        opaque_to_canonical[decision.selected_policy_id]
        if decision.selected_policy_id is not None
        else None
    )
    certified = tuple(
        sorted(opaque_to_canonical[policy_id] for policy_id in decision.certified_policy_ids)
    )
    return replace(
        decision,
        selected_policy_id=selected,
        certified_policy_ids=certified,
    )


def validate_method_decision(
    decision: MethodDecision,
    expected_method_id: str,
    candidate_ids: tuple[str, ...],
    evidence: ObservedEvidence | None,
    expected_capability: MethodCapability | None = None,
) -> None:
    if decision.method_id != expected_method_id:
        raise ValueError(
            f"method decision ID mismatch: expected {expected_method_id}, got {decision.method_id}"
        )
    if decision.decision not in {"PROMOTE", "BLOCK", "NO_DECISION", "UNSUPPORTED"}:
        raise ValueError(f"method {expected_method_id} returned invalid decision status")
    if len(set(decision.certified_policy_ids)) != len(decision.certified_policy_ids):
        raise ValueError(f"method {expected_method_id} returned duplicate certified policy IDs")
    unknown = sorted(set(decision.certified_policy_ids) - set(candidate_ids))
    if decision.selected_policy_id is not None and decision.selected_policy_id not in candidate_ids:
        unknown.append(decision.selected_policy_id)
    if unknown:
        raise ValueError(f"method {expected_method_id} returned unknown policy IDs: {unknown}")
    if decision.selected_policy_id is not None and decision.selected_policy_id not in decision.certified_policy_ids:
        raise ValueError(f"method {expected_method_id} selected an uncertified candidate")
    if (decision.decision == "PROMOTE") != (decision.selected_policy_id is not None):
        raise ValueError(f"method {expected_method_id} promotion status disagrees with selection")
    if decision.deployable and decision.uses_population_truth:
        raise ValueError(f"deployable method {expected_method_id} accessed population truth")
    if expected_capability is not None:
        expected_flags = (
            expected_capability.deployable,
            expected_capability.uses_population_truth,
            expected_capability.benchmark_control_only,
        )
        decision_flags = (
            decision.deployable,
            decision.uses_population_truth,
            decision.benchmark_control_only,
        )
        if decision_flags != expected_flags:
            raise ValueError(
                f"method {expected_method_id} decision flags do not match frozen capability"
            )
    if evidence is not None and decision.deployable:
        diagnostic_hash = decision.diagnostics.get("evidence_hash")
        if diagnostic_hash != evidence.evidence_hash:
            raise ValueError(f"method {expected_method_id} did not report the canonical evidence hash")


def score_decision(
    truth: ScenarioTruth, decision: MethodDecision, policy: PolicyConfig
) -> dict[str, object]:
    candidate_ids = tuple(candidate.policy_id for candidate in truth.confirmatory_candidates)
    validate_method_decision(decision, decision.method_id, candidate_ids, None)
    safe_ids = set(truth.safe_policy_ids)
    selected = decision.selected_policy_id
    certified = set(decision.certified_policy_ids)
    false_promotion = selected is not None and selected not in safe_ids
    false_certification = bool(certified - safe_ids)
    false_block = bool(safe_ids) and selected is None
    correct_promotion = selected is not None and selected in safe_ids
    correct_no_safe_block = not safe_ids and selected is None
    regret: float | None = None
    if correct_promotion and selected is not None:
        objective = lambda candidate: (
            policy.cost_weight * candidate.mean_cost
            + policy.latency_weight * candidate.mean_latency
        )
        selected_truth = truth.confirmatory_candidate(selected)
        optimal = min(
            objective(truth.confirmatory_candidate(policy_id)) for policy_id in safe_ids
        )
        regret = objective(selected_truth) - optimal
        if regret < 0.0 and math.isclose(regret, 0.0, abs_tol=1e-12):
            regret = 0.0
        if regret < 0.0:
            raise ValueError("operational regret cannot be negative")
    return {
        "false_promotion": int(false_promotion),
        "false_certification": int(false_certification),
        "false_block": int(false_block),
        "correct_promotion": int(correct_promotion),
        "correct_no_safe_candidate_block": int(correct_no_safe_block),
        "no_decision": int(decision.decision == "NO_DECISION"),
        "certified_set_size": len(certified),
        "operational_regret_when_safe_selection_occurs": regret,
    }


def _truth_summary(truth: ScenarioTruth) -> dict[str, object]:
    def comparable(candidate: CandidateTruth) -> dict[str, object]:
        values = candidate.as_dict()
        values.pop("phase")
        return values

    return {
        "safe_policy_ids": list(truth.safe_policy_ids),
        "unsafe_policy_ids": [
            candidate.policy_id
            for candidate in truth.confirmatory_candidates
            if not candidate.truly_promotion_safe
        ],
        "overall_safe_but_subgroup_unsafe_policy_ids": [
            candidate.policy_id
            for candidate in truth.confirmatory_candidates
            if candidate.overall_safe_but_subgroup_unsafe
        ],
        "development_to_confirmatory_truth_changed_policy_ids": [
            development.policy_id
            for development, confirmatory in zip(
                truth.development_candidates, truth.confirmatory_candidates, strict=True
            )
            if comparable(development) != comparable(confirmatory)
        ],
    }


def _truth_rows(truth: ScenarioTruth) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for phase, candidates in (
        ("development", truth.development_candidates),
        ("confirmatory", truth.confirmatory_candidates),
    ):
        for candidate in candidates:
            row = candidate.as_dict()
            for field, value in tuple(row.items()):
                if isinstance(value, (dict, list)):
                    row[field] = canonical_json(value)
            rows.append(
                {
                    "scenario_id": truth.scenario_id,
                    "base_scenario_id": truth.base_scenario_id,
                    "family": truth.family,
                    "sample_size": truth.sample_size,
                    "phase": phase,
                    **row,
                }
            )
    return rows


def _scenario_summary_row(truth: ScenarioTruth) -> dict[str, object]:
    summary = _truth_summary(truth)
    return {
        "scenario_id": truth.scenario_id,
        "base_scenario_id": truth.base_scenario_id,
        "family": truth.family,
        "sample_size": truth.sample_size,
        "candidate_count": len(truth.confirmatory_candidates),
        "truly_safe_candidate_count": len(truth.safe_policy_ids),
        "enabled_risks": canonical_json(list(truth.enabled_risks)),
        "enabled_group_risks": canonical_json(list(truth.enabled_group_risks)),
        "group_prevalence": canonical_json(dict(truth.group_prevalence)),
        "scenario_truth_summary": canonical_json(summary),
        "protocol_hash": truth.protocol_hash,
    }


def _aggregate_rows(
    trials: list[dict[str, object]], truth_by_scenario: Mapping[str, ScenarioTruth]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in trials:
        grouped[(str(row["scenario_id"]), str(row["method_id"]))].append(row)
    output: list[dict[str, object]] = []
    for (scenario_id, method_id), values in sorted(grouped.items()):
        truth = truth_by_scenario[scenario_id]
        trial_count = len(values)
        first = values[0]
        counts = {
            event: sum(int(value[event]) for value in values) for event in EVENT_FIELDS
        }
        false_promotion_interval = wilson_interval(counts["false_promotion"], trial_count)
        regrets = [
            float(value["operational_regret_when_safe_selection_occurs"])
            for value in values
            if value["operational_regret_when_safe_selection_occurs"] is not None
        ]
        row: dict[str, object] = {
            "scenario_id": scenario_id,
            "base_scenario_id": truth.base_scenario_id,
            "family": truth.family,
            "method_id": method_id,
            "observed_evidence_only": bool(first["observed_evidence_only"]),
            "truth_isolated": bool(first["truth_isolated"]),
            "benchmark_control_only": bool(first["benchmark_control_only"]),
            "research_only": bool(first["research_only"]),
            "production_integrated": bool(first["production_integrated"]),
            "trial_count": trial_count,
        }
        for event in EVENT_FIELDS:
            count_name = f"{event}_count"
            rate_name = f"{event}_rate"
            row[count_name] = counts[event]
            row[rate_name] = counts[event] / trial_count
        row["false_promotion_rate_confidence_interval"] = canonical_json(
            list(false_promotion_interval)
        )
        row["mean_certified_set_size"] = sum(
            int(value["certified_set_size"]) for value in values
        ) / trial_count
        row["mean_operational_regret_when_safe_selection_occurs"] = (
            sum(regrets) / len(regrets) if regrets else None
        )
        row["candidate_count"] = len(truth.confirmatory_candidates)
        row["sample_size"] = truth.sample_size
        row["enabled_risks"] = canonical_json(list(truth.enabled_risks))
        row["scenario_truth_summary"] = canonical_json(_truth_summary(truth))
        output.append(row)
    return output


def _run_benchmark_core(
    config: Mapping[str, Any],
    profile: str = "CI",
    master_seed: int | None = None,
    *,
    verified_full_entropy: VerifiedFullEntropy | None = None,
    github_execution_attestation: Mapping[str, object] | None = None,
) -> dict[str, object]:
    validate_config(config)
    if profile not in config["profiles"]:
        raise ValueError(f"unknown profile: {profile}")
    if profile == "FULL":
        if master_seed is not None:
            raise ValueError("FULL rejects public or development master-seed overrides")
        if verified_full_entropy is None:
            raise ValueError(
                "FULL requires a published seal and verified future-public-beacon receipt"
            )
        full_beacon_provenance = verified_full_entropy.public_provenance()
        if (
            not isinstance(github_execution_attestation, Mapping)
            or github_execution_attestation.get("github_oidc_execution_verified")
            is not True
        ):
            raise ValueError("FULL requires a verified GitHub Actions execution attestation")
        full_beacon_provenance.update(github_execution_attestation)
        seed_input = verified_full_entropy
        seed = profile_master_seed_value(config, profile, seed_input)
    else:
        if verified_full_entropy is not None:
            raise ValueError("verified FULL entropy is not accepted for development profiles")
        seed_value = config["master_seed"] if master_seed is None else master_seed
        if isinstance(seed_value, bool) or not isinstance(seed_value, int) or seed_value < 0:
            raise ValueError("master seed must be a nonnegative integer")
        seed = seed_value
        seed_input = seed
        full_beacon_provenance = None
    validate_revealed_profile_seed_uniqueness(
        config,
        profile,
        verified_full_entropy if profile == "FULL" else seed,
    )
    schedule_manifest = build_seed_schedule_manifest(config)
    replicate_count = int(config["profiles"][profile]["replicate_count"])
    trial_sample_limit_value = config.get("trial_sample_limit", 2)
    if (
        isinstance(trial_sample_limit_value, bool)
        or not isinstance(trial_sample_limit_value, int)
        or trial_sample_limit_value < 0
    ):
        raise ValueError("trial_sample_limit must be a nonnegative integer")
    trial_sample_limit = trial_sample_limit_value

    capabilities = {item.method_id: item for item in method_capabilities()}
    configured_methods = tuple(sorted(str(item) for item in config["methods"]))
    registry = method_registry()
    supported_ids = tuple(
        method_id for method_id in configured_methods if capabilities[method_id].supported
    )
    truth_isolated_ids = tuple(
        method_id
        for method_id in supported_ids
        if capabilities[method_id].supported
        and not capabilities[method_id].uses_population_truth
    )
    if "oracle_safe_objective" in truth_isolated_ids:
        raise ValueError("oracle cannot be included in truth-isolated method summaries")
    research_candidate_ids = tuple(
        method_id
        for method_id in truth_isolated_ids
        if not capabilities[method_id].benchmark_control_only
    )
    benchmark_control_ids = tuple(
        method_id
        for method_id in supported_ids
        if capabilities[method_id].benchmark_control_only
    )

    truth_rows: list[dict[str, object]] = []
    scenario_rows: list[dict[str, object]] = []
    all_trial_rows: list[dict[str, object]] = []
    sampled_trial_rows: list[dict[str, object]] = []
    truth_by_scenario: dict[str, ScenarioTruth] = {}
    evidence_hashes: dict[str, str] = {}
    truth_access_decision_ids: set[str] = set()
    truth_isolation_violation_decision_ids: set[str] = set()

    scenarios = sorted(config["scenarios"], key=lambda item: str(item["scenario_id"]))
    for scenario in scenarios:
        for sample_size in sorted(int(value) for value in scenario["sample_sizes"]):
            run_policy = policy_config(config, scenario, profile)
            for trial_index in range(replicate_count):
                trial = simulate_trial(
                    config,
                    scenario,
                    sample_size,
                    trial_index,
                    profile,
                    master_seed=seed_input,
                )
                truth = trial.truth
                if truth.scenario_id not in truth_by_scenario:
                    truth_by_scenario[truth.scenario_id] = truth
                    truth_rows.extend(_truth_rows(truth))
                    scenario_rows.append(_scenario_summary_row(truth))
                canonical_evidence = trial.confirmatory_evidence
                development_evidence = trial.development_evidence
                if _evidence_digest(development_evidence) != development_evidence.evidence_hash:
                    raise ValueError("development simulator evidence hash does not match rows")
                frozen_candidate_ids = tuple(
                    candidate.policy_id for candidate in truth.confirmatory_candidates
                )
                if canonical_evidence.policy_ids != frozen_candidate_ids:
                    raise ValueError(
                        "confirmatory evidence candidate IDs do not match the frozen family"
                    )
                if _evidence_digest(canonical_evidence) != canonical_evidence.evidence_hash:
                    raise ValueError("canonical simulator evidence hash does not match rows")
                evidence, opaque_to_canonical = _opaque_method_evidence(
                    canonical_evidence, frozen_candidate_ids
                )
                before_hash = _evidence_digest(evidence)
                if before_hash != evidence.evidence_hash:
                    raise ValueError("canonical evidence hash does not match evidence rows")
                evidence_key = trial.trial_identity
                previous_hash = evidence_hashes.setdefault(evidence_key, evidence.evidence_hash)
                if previous_hash != evidence.evidence_hash:
                    raise ValueError("methods within a trial received different evidence")

                decisions: list[MethodDecision] = []
                for method_id in supported_ids:
                    if method_id == "oracle_safe_objective":
                        oracle_decision = oracle_safe_objective(truth, run_policy)
                        validate_method_decision(
                            oracle_decision,
                            method_id,
                            frozen_candidate_ids,
                            None,
                            capabilities[method_id],
                        )
                        decisions.append(oracle_decision)
                        continue
                    method = registry[method_id]
                    method_seed = stable_seed(
                        seed, trial.trial_identity, method_id, "method_internal"
                    )
                    decision = method.evaluate(evidence, run_policy, method_seed)  # type: ignore[attr-defined]
                    validate_method_decision(
                        decision,
                        method_id,
                        evidence.policy_ids,
                        evidence,
                        capabilities[method_id],
                    )
                    if _evidence_digest(evidence) != before_hash:
                        raise ValueError(f"method {method_id} mutated canonical evidence")
                    canonical_decision = _canonical_decision(decision, opaque_to_canonical)
                    validate_method_decision(
                        canonical_decision,
                        method_id,
                        frozen_candidate_ids,
                        None,
                        capabilities[method_id],
                    )
                    decisions.append(canonical_decision)

                for decision in decisions:
                    if decision.uses_population_truth:
                        truth_access_decision_ids.add(decision.method_id)
                    if decision.deployable and decision.uses_population_truth:
                        truth_isolation_violation_decision_ids.add(decision.method_id)
                    scored = score_decision(truth, decision, run_policy)
                    row: dict[str, object] = {
                        "scenario_id": truth.scenario_id,
                        "base_scenario_id": truth.base_scenario_id,
                        "family": truth.family,
                        "sample_size": sample_size,
                        "candidate_count": len(truth.confirmatory_candidates),
                        "trial_index": trial_index,
                        "seed_schedule_version": SEED_SCHEDULE_VERSION,
                        "evidence_trial_identity": trial.trial_identity,
                        "seed_fingerprint": trial.seed_fingerprint,
                        "method_id": decision.method_id,
                        **decision.public_research_metadata(),
                        "evidence_hash": evidence.evidence_hash,
                        "development_evidence_hash": development_evidence.evidence_hash,
                        "selected_policy_id": decision.selected_policy_id,
                        "certified_policy_ids": canonical_json(
                            list(decision.certified_policy_ids)
                        ),
                        "decision": decision.decision,
                        "decision_reason": decision.decision_reason,
                        **scored,
                    }
                    all_trial_rows.append(row)
                    if trial_index < trial_sample_limit:
                        sampled_trial_rows.append(dict(row))

    method_rows = _aggregate_rows(all_trial_rows, truth_by_scenario)
    capabilities_list = [capabilities[method_id].as_dict() for method_id in configured_methods]
    scenario_ids = tuple(sorted(truth_by_scenario))
    manifest = {
        "benchmark_id": "known_truth_false_promotion_benchmark_v1",
        "protocol_version": str(config["protocol_version"]),
        "seed_schedule_version": SEED_SCHEDULE_VERSION,
        "seed_schedule_amendment_id": AMENDMENT_ID,
        "profile": profile,
        "evidence_role": "confirmatory" if profile == "FULL" else "developmental",
        "replicate_count_per_scenario_sample_size": replicate_count,
        "development_master_seed": seed if profile != "FULL" else None,
        "full_entropy_protocol": FULL_ENTROPY_PROTOCOL,
        "full_entropy_amendment_id": FULL_ENTROPY_AMENDMENT_ID,
        "full_confirmation_status": (
            "FULL_EXECUTED_FROM_VERIFIED_PUBLIC_BEACON"
            if profile == "FULL"
            else FULL_CONFIRMATION_STATUS
        ),
        "retired_full_seed_status": RETIRED_FULL_SEED_STATUS,
        "full_beacon_provenance": full_beacon_provenance,
        "full_master_seed_persisted": False,
        "full_evidence_generated": profile == "FULL",
        "full_results_inspected": profile == "FULL",
        "canonical_evidence_trial_identity_format": CANONICAL_IDENTITY_FORMAT,
        "profile_identity_set_hash": schedule_manifest["identity_set_hashes_by_profile"][
            profile
        ],
        "complete_schedule_hash": schedule_manifest["complete_schedule_hash"],
        "seed_plan": {
            "evidence_trial": DERIVATION_ALGORITHM,
            "schedule_fingerprint": SEED_FINGERPRINT_ALGORITHM,
            "method_internal": "sha256(profile_master_seed, canonical_trial_identity, method_id, method_internal), then opaque candidate and metric where applicable",
        },
        "config_hash": sha256_json(config),
        "protocol_hashes": {
            scenario_id: truth_by_scenario[scenario_id].protocol_hash
            for scenario_id in scenario_ids
        },
        "method_capabilities": capabilities_list,
        "executed_method_ids": list(supported_ids),
        "observed_evidence_only_method_ids": list(truth_isolated_ids),
        "truth_isolated_method_ids": list(truth_isolated_ids),
        "research_candidate_method_ids": list(research_candidate_ids),
        "benchmark_control_method_ids": list(benchmark_control_ids),
        "truth_access_method_ids": sorted(truth_access_decision_ids),
        "truth_isolated_method_accessed_population_truth": bool(
            truth_isolation_violation_decision_ids
        ),
        "method_facing_identifiers": "opaque scenario and candidate IDs; canonical IDs restored only after decision validation",
        "scenario_ids": list(scenario_ids),
        "base_scenario_ids": sorted(str(item["scenario_id"]) for item in scenarios),
        "enabled_risks_by_scenario": {
            scenario_id: list(truth_by_scenario[scenario_id].enabled_risks)
            for scenario_id in scenario_ids
        },
        "trial_count_total": len(evidence_hashes),
        "method_trial_row_count_total": len(all_trial_rows),
        "bounded_trial_sample_rows": len(sampled_trial_rows),
        "post_hoc_filtered": False,
        "scenario_results_aggregated_into_headline": False,
        "monte_carlo_interval": "two-sided 95% Wilson interval for trial event rates",
        "candidate_risk_interval": "method-specific; not the Monte Carlo interval",
        "complete": True,
    }
    return {
        "manifest": manifest,
        "scenario_truth_rows": sorted(
            truth_rows,
            key=lambda row: (
                str(row["scenario_id"]), str(row["phase"]), str(row["policy_id"])
            ),
        ),
        "scenario_summary_rows": sorted(
            scenario_rows, key=lambda row: str(row["scenario_id"])
        ),
        "method_summary_rows": method_rows,
        "trial_summary_sample_rows": sorted(
            sampled_trial_rows,
            key=lambda row: (
                str(row["scenario_id"]), int(row["trial_index"]), str(row["method_id"])
            ),
        ),
        "config_snapshot": json.loads(canonical_json(config)),
    }


def run_benchmark(
    config: Mapping[str, Any],
    profile: str = "CI",
    master_seed: int | None = None,
    *,
    verified_full_entropy: VerifiedFullEntropy | None = None,
) -> dict[str, object]:
    if profile == "FULL" and master_seed is None and verified_full_entropy is not None:
        with _authorized_full_execution(verified_full_entropy) as attestation:
            return _run_benchmark_core(
                config,
                profile,
                master_seed,
                verified_full_entropy=verified_full_entropy,
                github_execution_attestation=attestation,
            )
    return _run_benchmark_core(
        config,
        profile,
        master_seed,
        verified_full_entropy=verified_full_entropy,
    )
