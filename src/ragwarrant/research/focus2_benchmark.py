"""Freeze-verified benchmark adapter for the Focus 2 warrant.

This module is intentionally version-locked to the frozen Focus 1 benchmark.
It reuses the frozen simulator, identifier isolation, decision validation,
truth-side scoring, and estimators without changing their implementations.
Only the developmental CI and LOCAL profiles are accepted here.
"""

from __future__ import annotations

import json
import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from numbers import Real
from pathlib import Path
from typing import Any

from .benchmark import (
    EVENT_FIELDS,
    _aggregate_rows,
    _canonical_decision,
    _evidence_digest,
    _opaque_method_evidence,
    _scenario_summary_row,
    _truth_rows,
    score_decision,
    validate_method_decision,
    wilson_interval,
)
from .fixed_sample_warrant import (
    BONFERRONI,
    FOCUS1_FREEZE_DIGEST,
    HOLM,
    METHOD_ID as WARRANT_METHOD_ID,
    SEED_SCHEDULE_VERSION,
    FixedSampleMultiRiskWarrant,
    freeze_candidate_family,
)
from .methods import method_capabilities, method_registry, oracle_safe_objective
from .public_beacon import verify_benchmark_freeze_manifest
from .seed_schedule import (
    AMENDMENT_ID,
    CANONICAL_IDENTITY_FORMAT,
    DERIVATION_ALGORITHM,
    SEED_FINGERPRINT_ALGORITHM,
    build_seed_schedule_manifest,
    validate_revealed_profile_seed_uniqueness,
)
from .simulator import (
    canonical_json,
    load_config,
    policy_config,
    sha256_json,
    simulate_trial,
    stable_seed,
    validate_config,
)
from .types import MethodDecision, ScenarioTruth, public_research_artifact


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FREEZE_MANIFEST_PATH = (
    REPOSITORY_ROOT / ".local_data" / "research_review" / "BENCHMARK_FREEZE_MANIFEST.json"
)
FROZEN_FOCUS1_CONFIG_PATH = (
    REPOSITORY_ROOT / "configs" / "research" / "false_promotion_benchmark_v1.yaml"
)
FROZEN_FOCUS2_CONFIG_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "research"
    / "fixed_sample_multi_risk_warrant_v1.yaml"
)
FOCUS2_CONFIG_FILE_SHA256 = (
    "74773244d4267d1a8d72c993234e4aebdc62141d4a155fb972e4ecd6f9279a53"
)
FOCUS2_CONFIG_CANONICAL_HASH = (
    "7c7efdaa389c40a2ec17c1fcd63ca99c1c98abd85dc56ad2d105427fa38e7fdc"
)
SUPPORTED_PROFILES = ("CI", "LOCAL")
NOT_APPLICABLE = "not_applicable"
FOCUS2_BENCHMARK_ID = "fixed_sample_multi_risk_warrant_benchmark_v1"


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _finite_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    return result


def _validate_focus2_config(config: Mapping[str, Any]) -> None:
    required_exact = {
        "schema_version": "fixed_sample_multi_risk_warrant_config.v1",
        "method_id": WARRANT_METHOD_ID,
        "focus1_benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST,
        "seed_schedule_version": SEED_SCHEDULE_VERSION,
        "primary_multiplicity_method": HOLM,
        "structural_family_mismatch_behavior": "invalidate_warrant",
        "insufficient_prespecified_group_count_behavior": (
            "retain_hypothesis_with_p_value_one"
        ),
        "development_evidence_used_for_certification": False,
        "full_profile_permitted": False,
        "research_only": True,
        "production_integrated": False,
    }
    for field, expected in required_exact.items():
        if config.get(field) != expected:
            raise ValueError(f"Focus 2 config {field} must equal {expected!r}")

    alpha = _finite_float(config.get("familywise_error_level"), "familywise_error_level")
    if not 0.0 < alpha < 1.0:
        raise ValueError("familywise_error_level must be strictly between zero and one")

    methods = config.get("multiplicity_methods")
    if not isinstance(methods, list) or tuple(methods) != (HOLM, BONFERRONI):
        raise ValueError("multiplicity_methods must be prespecified as [holm, bonferroni]")

    incumbent = config.get("incumbent_policy_id")
    if not isinstance(incumbent, str) or not incumbent or incumbent.strip() != incumbent:
        raise ValueError("incumbent_policy_id must be a non-empty canonical string")

    raw_bounds = config.get("quality_delta_bounds")
    if not isinstance(raw_bounds, list) or len(raw_bounds) != 2:
        raise ValueError("quality_delta_bounds must contain exactly two values")
    lower = _finite_float(raw_bounds[0], "quality_delta_bounds lower")
    upper = _finite_float(raw_bounds[1], "quality_delta_bounds upper")
    if lower >= upper:
        raise ValueError("quality_delta_bounds must be strictly increasing")

    permitted = config.get("permitted_selection_objectives")
    if not isinstance(permitted, list) or set(permitted) != {
        "minimize_cost",
        "minimize_latency",
    }:
        raise ValueError("permitted_selection_objectives must contain cost and latency")
    if config.get("selection_objective") not in permitted:
        raise ValueError("selection_objective is not permitted")


def _verify_frozen_focus2_config(config: Mapping[str, Any]) -> None:
    try:
        payload = FROZEN_FOCUS2_CONFIG_PATH.read_bytes()
    except OSError as exc:
        raise ValueError("the tracked Focus 2 config is required before sampling") from exc
    file_digest = hashlib.sha256(payload).hexdigest()
    if file_digest != FOCUS2_CONFIG_FILE_SHA256:
        raise ValueError("tracked Focus 2 config hash differs from the approved v1 contract")
    if sha256_json(config) != FOCUS2_CONFIG_CANONICAL_HASH:
        raise ValueError("supplied Focus 2 config differs from the approved v1 contract")


def _load_freeze_manifest() -> Mapping[str, Any]:
    try:
        loaded = json.loads(FREEZE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("Focus 1 freeze manifest is required before Focus 2 sampling") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Focus 1 freeze manifest is not valid JSON") from exc
    return _require_mapping(loaded, "Focus 1 freeze manifest")


def _load_frozen_focus1_config() -> dict[str, Any]:
    return load_config(FROZEN_FOCUS1_CONFIG_PATH)


def _verify_frozen_focus1(
    config: Mapping[str, Any], focus2_config: Mapping[str, Any]
) -> Mapping[str, Any]:
    manifest = _load_freeze_manifest()
    actual_digest = verify_benchmark_freeze_manifest(manifest, REPOSITORY_ROOT)
    if actual_digest != FOCUS1_FREEZE_DIGEST:
        raise ValueError(
            "Focus 1 freeze digest mismatch: "
            f"expected {FOCUS1_FREEZE_DIGEST}, got {actual_digest}"
        )
    if focus2_config.get("focus1_benchmark_freeze_digest") != actual_digest:
        raise ValueError("Focus 2 config does not reference the verified Focus 1 freeze")
    frozen_config = _load_frozen_focus1_config()
    if canonical_json(config) != canonical_json(frozen_config):
        raise ValueError("Focus 1 benchmark config differs from the frozen on-disk config")
    return manifest


def _aggregate_focus2_rows(
    trials: list[dict[str, object]], truth_by_scenario: Mapping[str, ScenarioTruth]
) -> list[dict[str, object]]:
    """Reuse frozen aggregation within each prespecified procedure stratum."""

    by_procedure: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in trials:
        by_procedure[str(row["multiplicity_method"])].append(row)

    output: list[dict[str, object]] = []
    for procedure, values in sorted(by_procedure.items()):
        for aggregate in _aggregate_rows(values, truth_by_scenario):
            aggregate["multiplicity_method"] = procedure
            matching = [
                row
                for row in values
                if row["scenario_id"] == aggregate["scenario_id"]
                and row["method_id"] == aggregate["method_id"]
            ]
            trial_count = int(aggregate["trial_count"])
            for event in EVENT_FIELDS:
                interval = wilson_interval(
                    sum(int(row[event]) for row in matching), trial_count
                )
                aggregate[f"{event}_rate_confidence_interval"] = canonical_json(
                    list(interval)
                )
            first = matching[0]
            aggregate["familywise_error_level"] = first["familywise_error_level"]
            aggregate["family_hash"] = first["family_hash"]
            aggregate["hypothesis_count"] = first["hypothesis_count"]
            output.append(aggregate)
    return sorted(
        output,
        key=lambda row: (
            str(row["scenario_id"]),
            str(row["method_id"]),
            str(row["multiplicity_method"]),
        ),
    )


def _trial_row(
    *,
    truth: ScenarioTruth,
    sample_size: int,
    trial_index: int,
    trial_identity: str,
    seed_fingerprint: str,
    evidence_hash: str,
    development_evidence_hash: str,
    decision: MethodDecision,
    multiplicity_method: str,
    scored: Mapping[str, object],
) -> dict[str, object]:
    diagnostics = decision.diagnostics
    is_warrant = decision.method_id == WARRANT_METHOD_ID
    return {
        "scenario_id": truth.scenario_id,
        "base_scenario_id": truth.base_scenario_id,
        "family": truth.family,
        "sample_size": sample_size,
        "candidate_count": len(truth.confirmatory_candidates),
        "trial_index": trial_index,
        "seed_schedule_version": SEED_SCHEDULE_VERSION,
        "evidence_trial_identity": trial_identity,
        "seed_fingerprint": seed_fingerprint,
        "method_id": decision.method_id,
        "multiplicity_method": multiplicity_method,
        "familywise_error_level": (
            diagnostics.get("familywise_error_level") if is_warrant else None
        ),
        "family_hash": diagnostics.get("family_hash") if is_warrant else None,
        "hypothesis_count": (
            diagnostics.get("promotion_warrant", {})
            .get("diagnostics", {})
            .get("hypothesis_count")
            if is_warrant
            else None
        ),
        **decision.public_research_metadata(),
        "evidence_hash": evidence_hash,
        "development_evidence_hash": development_evidence_hash,
        "selected_policy_id": decision.selected_policy_id,
        "certified_policy_ids": canonical_json(list(decision.certified_policy_ids)),
        "decision": decision.decision,
        "decision_reason": decision.decision_reason,
        **scored,
    }


def run_focus2_benchmark(
    config: Mapping[str, Any],
    focus2_config: Mapping[str, Any],
    profile: str = "CI",
    master_seed: int | None = None,
) -> dict[str, object]:
    """Run the frozen benchmark plus both prespecified Focus 2 procedures.

    The exact same opaque ``ObservedEvidence`` instance is given to every
    truth-isolated observed-evidence method in one evidence trial. Population
    truth is used only by the oracle and by the frozen scorer after decisions
    return.
    """

    if profile not in SUPPORTED_PROFILES:
        if profile == "FULL":
            raise ValueError("FULL is prohibited in the Focus 2 developmental runner")
        raise ValueError(f"unknown Focus 2 profile: {profile}")
    _validate_focus2_config(_require_mapping(focus2_config, "Focus 2 config"))
    _verify_frozen_focus2_config(focus2_config)
    _verify_frozen_focus1(config, focus2_config)
    validate_config(config)

    seed_value = config["master_seed"] if master_seed is None else master_seed
    if isinstance(seed_value, bool) or not isinstance(seed_value, int) or seed_value < 0:
        raise ValueError("master seed must be a nonnegative integer")
    seed = seed_value
    validate_revealed_profile_seed_uniqueness(config, profile, seed)
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
    registry = method_registry()
    configured_methods = tuple(sorted(str(item) for item in config["methods"]))
    baseline_ids = tuple(
        method_id
        for method_id in configured_methods
        if capabilities[method_id].supported
    )
    truth_isolated_baseline_ids = tuple(
        method_id
        for method_id in baseline_ids
        if capabilities[method_id].deployable
        and not capabilities[method_id].uses_population_truth
    )
    benchmark_control_ids = tuple(
        method_id
        for method_id in baseline_ids
        if capabilities[method_id].benchmark_control_only
    )
    procedures = tuple(str(item) for item in focus2_config["multiplicity_methods"])
    alpha = float(focus2_config["familywise_error_level"])
    bounds = tuple(float(item) for item in focus2_config["quality_delta_bounds"])
    incumbent_policy_id = str(focus2_config["incumbent_policy_id"])
    selection_objective = str(focus2_config["selection_objective"])

    truth_rows: list[dict[str, object]] = []
    scenario_rows: list[dict[str, object]] = []
    all_trial_rows: list[dict[str, object]] = []
    sampled_trial_rows: list[dict[str, object]] = []
    truth_by_scenario: dict[str, ScenarioTruth] = {}
    evidence_hashes: dict[str, str] = {}
    warrant_artifacts: dict[str, dict[str, object]] = {}
    warrant_artifact_trials: dict[str, str] = {}
    truth_access_decision_ids: set[str] = set()
    truth_isolation_violation_decision_ids: set[str] = set()

    scenarios = sorted(config["scenarios"], key=lambda item: str(item["scenario_id"]))
    for scenario in scenarios:
        canonical_candidate_ids = tuple(
            sorted(str(candidate["policy_id"]) for candidate in scenario["candidates"])
        )
        opaque_candidate_ids = tuple(
            f"policy_{index:04d}"
            for index, _ in enumerate(canonical_candidate_ids, start=1)
        )
        for sample_size in sorted(int(value) for value in scenario["sample_sizes"]):
            run_policy = policy_config(config, scenario, profile)
            # Candidate-risk families are frozen before any call to the simulator.
            families = {
                procedure: freeze_candidate_family(
                    candidate_policy_ids=opaque_candidate_ids,
                    incumbent_policy_id=incumbent_policy_id,
                    confirmatory_unit_count=sample_size,
                    policy=run_policy,
                    quality_delta_bounds=(bounds[0], bounds[1]),
                    familywise_error_level=alpha,
                    multiplicity_method=procedure,
                    selection_objective=selection_objective,
                )
                for procedure in procedures
            }
            warrant_methods = {
                procedure: FixedSampleMultiRiskWarrant(family)
                for procedure, family in families.items()
            }

            for trial_index in range(replicate_count):
                trial = simulate_trial(
                    config,
                    scenario,
                    sample_size,
                    trial_index,
                    profile,
                    master_seed=seed,
                )
                truth = trial.truth
                if tuple(
                    candidate.policy_id for candidate in truth.confirmatory_candidates
                ) != canonical_candidate_ids:
                    raise ValueError("simulator candidate IDs differ from the frozen family")
                if truth.scenario_id not in truth_by_scenario:
                    truth_by_scenario[truth.scenario_id] = truth
                    truth_rows.extend(_truth_rows(truth))
                    scenario_rows.append(_scenario_summary_row(truth))

                canonical_evidence = trial.confirmatory_evidence
                development_evidence = trial.development_evidence
                if _evidence_digest(development_evidence) != development_evidence.evidence_hash:
                    raise ValueError("development simulator evidence hash does not match rows")
                if canonical_evidence.policy_ids != canonical_candidate_ids:
                    raise ValueError(
                        "confirmatory evidence candidate IDs do not match the frozen family"
                    )
                if _evidence_digest(canonical_evidence) != canonical_evidence.evidence_hash:
                    raise ValueError("confirmatory simulator evidence hash does not match rows")
                evidence, opaque_to_canonical = _opaque_method_evidence(
                    canonical_evidence, canonical_candidate_ids
                )
                before_hash = _evidence_digest(evidence)
                if before_hash != evidence.evidence_hash:
                    raise ValueError("opaque evidence hash does not match evidence rows")
                previous_hash = evidence_hashes.setdefault(
                    trial.trial_identity, evidence.evidence_hash
                )
                if previous_hash != evidence.evidence_hash:
                    raise ValueError("methods within a trial received different evidence")

                decisions: list[tuple[MethodDecision, str]] = []
                for method_id in baseline_ids:
                    if method_id == "oracle_safe_objective":
                        oracle_decision = oracle_safe_objective(truth, run_policy)
                        validate_method_decision(
                            oracle_decision,
                            method_id,
                            canonical_candidate_ids,
                            None,
                            capabilities[method_id],
                        )
                        decisions.append((oracle_decision, NOT_APPLICABLE))
                        continue
                    method_seed = stable_seed(
                        seed, trial.trial_identity, method_id, "method_internal"
                    )
                    decision = registry[method_id].evaluate(  # type: ignore[attr-defined]
                        evidence, run_policy, method_seed
                    )
                    validate_method_decision(
                        decision,
                        method_id,
                        evidence.policy_ids,
                        evidence,
                        capabilities[method_id],
                    )
                    if _evidence_digest(evidence) != before_hash:
                        raise ValueError(f"method {method_id} mutated shared evidence")
                    canonical_decision = _canonical_decision(decision, opaque_to_canonical)
                    validate_method_decision(
                        canonical_decision,
                        method_id,
                        canonical_candidate_ids,
                        None,
                        capabilities[method_id],
                    )
                    decisions.append((canonical_decision, NOT_APPLICABLE))

                for procedure in procedures:
                    warrant = warrant_methods[procedure].evaluate_warrant(
                        evidence, run_policy
                    )
                    decision = warrant.to_method_decision()
                    validate_method_decision(
                        decision,
                        WARRANT_METHOD_ID,
                        evidence.policy_ids,
                        evidence,
                    )
                    if _evidence_digest(evidence) != before_hash:
                        raise ValueError(
                            f"warrant procedure {procedure} mutated shared evidence"
                        )
                    canonical_decision = _canonical_decision(decision, opaque_to_canonical)
                    validate_method_decision(
                        canonical_decision,
                        WARRANT_METHOD_ID,
                        canonical_candidate_ids,
                        None,
                    )
                    decisions.append((canonical_decision, procedure))
                    if procedure not in warrant_artifacts:
                        warrant_artifacts[procedure] = json.loads(
                            canonical_json(public_research_artifact(warrant.as_dict()))
                        )
                        warrant_artifact_trials[procedure] = trial.trial_identity

                for decision, procedure in decisions:
                    if decision.uses_population_truth:
                        truth_access_decision_ids.add(decision.method_id)
                    if decision.deployable and decision.uses_population_truth:
                        truth_isolation_violation_decision_ids.add(decision.method_id)
                    scored = score_decision(truth, decision, run_policy)
                    row = _trial_row(
                        truth=truth,
                        sample_size=sample_size,
                        trial_index=trial_index,
                        trial_identity=trial.trial_identity,
                        seed_fingerprint=trial.seed_fingerprint,
                        evidence_hash=evidence.evidence_hash,
                        development_evidence_hash=development_evidence.evidence_hash,
                        decision=decision,
                        multiplicity_method=procedure,
                        scored=scored,
                    )
                    all_trial_rows.append(row)
                    if trial_index < trial_sample_limit:
                        sampled_trial_rows.append(dict(row))

    method_rows = _aggregate_focus2_rows(all_trial_rows, truth_by_scenario)
    scenario_ids = tuple(sorted(truth_by_scenario))
    method_variants = [
        {"method_id": method_id, "multiplicity_method": NOT_APPLICABLE}
        for method_id in baseline_ids
    ] + [
        {"method_id": WARRANT_METHOD_ID, "multiplicity_method": procedure}
        for procedure in procedures
    ]
    truth_isolated_ids = sorted(
        set(truth_isolated_baseline_ids) | {WARRANT_METHOD_ID}
    )
    research_candidate_ids = [WARRANT_METHOD_ID]
    all_benchmark_control_ids = sorted(set(benchmark_control_ids))
    manifest = {
        "benchmark_id": FOCUS2_BENCHMARK_ID,
        "focus1_benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST,
        "protocol_version": str(config["protocol_version"]),
        "seed_schedule_version": SEED_SCHEDULE_VERSION,
        "seed_schedule_amendment_id": AMENDMENT_ID,
        "profile": profile,
        "evidence_role": "developmental",
        "replicate_count_per_scenario_sample_size": replicate_count,
        "development_master_seed": seed,
        "full_profile_used": False,
        "full_evidence_generated": False,
        "full_results_inspected": False,
        "target_drand_round_selected": False,
        "canonical_evidence_trial_identity_format": CANONICAL_IDENTITY_FORMAT,
        "profile_identity_set_hash": schedule_manifest["identity_set_hashes_by_profile"][
            profile
        ],
        "complete_schedule_hash": schedule_manifest["complete_schedule_hash"],
        "seed_plan": {
            "evidence_trial": DERIVATION_ALGORITHM,
            "schedule_fingerprint": SEED_FINGERPRINT_ALGORITHM,
            "method_internal": (
                "sha256(profile_master_seed, canonical_trial_identity, method_id, "
                "multiplicity_method when applicable, method_internal)"
            ),
        },
        "config_hash": sha256_json(config),
        "focus2_config_hash": sha256_json(focus2_config),
        "focus2_config_file_sha256": FOCUS2_CONFIG_FILE_SHA256,
        "protocol_hashes": {
            scenario_id: truth_by_scenario[scenario_id].protocol_hash
            for scenario_id in scenario_ids
        },
        "executed_method_ids": sorted(
            set(baseline_ids) | {WARRANT_METHOD_ID}
        ),
        "executed_method_variants": method_variants,
        "observed_evidence_only_method_ids": truth_isolated_ids,
        "truth_isolated_method_ids": truth_isolated_ids,
        "research_candidate_method_ids": research_candidate_ids,
        "benchmark_control_method_ids": all_benchmark_control_ids,
        "truth_access_method_ids": sorted(truth_access_decision_ids),
        "truth_isolated_method_accessed_population_truth": bool(
            truth_isolation_violation_decision_ids
        ),
        "same_observed_evidence_object_shared_by_truth_isolated_methods": True,
        "candidate_families_frozen_before_confirmatory_evidence": True,
        "method_facing_identifiers": (
            "opaque scenario and candidate IDs; canonical IDs restored only after "
            "decision validation"
        ),
        "scenario_ids": list(scenario_ids),
        "base_scenario_ids": sorted(str(item["scenario_id"]) for item in scenarios),
        "enabled_risks_by_scenario": {
            scenario_id: list(truth_by_scenario[scenario_id].enabled_risks)
            for scenario_id in scenario_ids
        },
        "trial_count_total": len(evidence_hashes),
        "method_trial_row_count_total": len(all_trial_rows),
        "bounded_trial_sample_rows": len(sampled_trial_rows),
        "warrant_artifact_evidence_trial_identity": warrant_artifact_trials,
        "warrant_artifact_selection_rule": (
            "lexicographically first base scenario_id, smallest sample_size, "
            "trial_index 0; one artifact per prespecified multiplicity method"
        ),
        "warrant_artifact_identifiers": "opaque method-facing policy IDs",
        "post_hoc_filtered": False,
        "scenario_results_aggregated_into_headline": False,
        "monte_carlo_interval": (
            "two-sided 95% Wilson intervals for trial event rates"
        ),
        "candidate_risk_interval": (
            "method-specific; distinct from Monte Carlo estimation uncertainty"
        ),
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
                str(row["scenario_id"]),
                int(row["trial_index"]),
                str(row["method_id"]),
                str(row["multiplicity_method"]),
            ),
        ),
        "config_snapshot": json.loads(canonical_json(config)),
        "focus2_config_snapshot": json.loads(canonical_json(focus2_config)),
        "warrant_artifacts": warrant_artifacts,
    }


__all__ = ["FOCUS2_BENCHMARK_ID", "run_focus2_benchmark"]
