"""Frozen Focus 1 adapter for the prespecified Focus 2 v2 ablation."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping
from numbers import Real
from pathlib import Path
from typing import Any

import yaml

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
    FOCUS1_FREEZE_DIGEST,
    HOLM,
    METHOD_ID as V1_METHOD_ID,
    SEED_SCHEDULE_VERSION,
    FixedSampleMultiRiskWarrant,
    freeze_candidate_family,
)
from .fixed_sample_warrant_v2 import (
    CANDIDATE_IUT,
    FLAT_WHOLE_FAMILY,
    HOEFFDING_BENTKUS_QUALITY,
    METHOD_ID,
    PAIRED_HOEFFDING,
    PRESPECIFIED_V2_VARIANTS,
    VARIANT_A_ID,
    FixedSampleMultiRiskWarrantV2,
    VariantSpecification,
    candidate_iut_p_value,
    v2_contract_digest,
)
from .focus2_benchmark import _verify_developmental_focus1_contract
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
    validate_config,
)
from .types import MethodDecision, ScenarioTruth, public_research_artifact


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FROZEN_FOCUS1_CONFIG_PATH = (
    REPOSITORY_ROOT / "configs/research/false_promotion_benchmark_v1.yaml"
)
FROZEN_V2_CONFIG_PATH = (
    REPOSITORY_ROOT
    / "configs/research/fixed_sample_multi_risk_warrant_v2.yaml"
)
V2_CONFIG_FILE_SHA256 = (
    "9ea78712a5ab0cee58982cec0cd2d69bc363d2c3c084d9507e54416dc18d1238"
)
V2_CONFIG_CANONICAL_HASH = (
    "debc0ac33b59650697daa7d9dbec5890e99b1fc8ec3d0f0df88f80b9f1dd347d"
)
V1_BASELINE_COMMIT = "bf3b3331b623afbdaed295919b3ac945c10692f6"
V1_BASELINE_TAG = "V1_VALID_ZERO_POWER_BASELINE"
V1_SOURCE_SHA256 = "87e88342354346d0dceb29f45946e846b68f6b1fbaa42a946d5a53822ef4e8ad"
V1_CONFIG_SHA256 = "74773244d4267d1a8d72c993234e4aebdc62141d4a155fb972e4ecd6f9279a53"
SUPPORTED_PROFILES = ("CI", "LOCAL")
FOCUS2_V2_BENCHMARK_ID = "fixed_sample_multi_risk_warrant_benchmark_v2"
NOT_APPLICABLE = "not_applicable"

V1_TRACKED_PATHS = (
    "configs/research/fixed_sample_multi_risk_warrant_v1.yaml",
    "docs/research/fixed_sample_multi_risk_warrant_v1_implementation.md",
    "docs/research/focus2_platform_preflight_plan.md",
    "schemas/research/promotion_warrant_v1.schema.json",
    "scripts/run_fixed_sample_warrant_benchmark.py",
    "src/ragwarrant/research/fixed_sample_warrant.py",
    "src/ragwarrant/research/focus2_benchmark.py",
    "src/ragwarrant/research/focus2_reporting.py",
    "tests/research/test_fixed_sample_warrant.py",
    "tests/research/test_fixed_sample_warrant_method.py",
    "tests/research/test_focus2_benchmark_integration.py",
    "tests/research/test_focus2_output_contract.py",
)


def load_v2_config(path: str | Path = FROZEN_V2_CONFIG_PATH) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError("Focus 2 v2 config is unreadable") from exc
    if not isinstance(loaded, dict):
        raise ValueError("Focus 2 v2 config must be a mapping")
    return loaded


def _finite_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    return result


def _variant_a_specification() -> VariantSpecification:
    return VariantSpecification(
        VARIANT_A_ID,
        V1_METHOD_ID,
        FLAT_WHOLE_FAMILY,
        HOLM,
        PAIRED_HOEFFDING,
    )


def _expected_variant_payloads() -> list[dict[str, str]]:
    return [
        _variant_a_specification().as_dict(),
        *(specification.as_dict() for specification in PRESPECIFIED_V2_VARIANTS),
    ]


def _validate_v2_config(config: Mapping[str, Any]) -> None:
    required_exact = {
        "schema_version": "fixed_sample_multi_risk_warrant_config.v2",
        "method_id": METHOD_ID,
        "focus1_benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST,
        "v1_baseline_tag": V1_BASELINE_TAG,
        "v1_baseline_commit": V1_BASELINE_COMMIT,
        "seed_schedule_version": SEED_SCHEDULE_VERSION,
        "primary_candidate_multiplicity_method": "holm",
        "comparison_candidate_multiplicity_method": "bonferroni",
        "dominant_bottleneck_rule": (
            "largest_raw_component_p_value_then_lexical_hypothesis_id"
        ),
        "development_evidence_used_for_certification": False,
        "full_profile_permitted": False,
        "target_drand_round_selected": False,
        "post_hoc_method_switching_permitted": False,
        "research_only": True,
        "production_integrated": False,
    }
    for field, expected in required_exact.items():
        if config.get(field) != expected:
            raise ValueError(f"Focus 2 v2 config {field} must equal {expected!r}")
    alpha = _finite_float(config.get("familywise_error_level"), "familywise_error_level")
    if not 0.0 < alpha < 1.0:
        raise ValueError("familywise_error_level must lie strictly between zero and one")
    if config.get("quality_delta_bounds") != [-0.25, 0.25]:
        raise ValueError("quality_delta_bounds must remain frozen at [-0.25, 0.25]")
    if config.get("variants") != _expected_variant_payloads():
        raise ValueError("Focus 2 v2 variants differ from the prespecified ablation")
    sample_limit = config.get("trial_diagnostic_sample_limit")
    if isinstance(sample_limit, bool) or not isinstance(sample_limit, int) or sample_limit < 0:
        raise ValueError("trial_diagnostic_sample_limit must be a nonnegative integer")
    if config.get("selection_objective") not in config.get(
        "permitted_selection_objectives", ()
    ):
        raise ValueError("selection objective is not prespecified")
    criteria = config.get("prespecified_descriptive_criteria")
    if not isinstance(criteria, Mapping) or not criteria:
        raise ValueError("prespecified descriptive criteria are required")


def _verify_v2_config(config: Mapping[str, Any]) -> None:
    payload = FROZEN_V2_CONFIG_PATH.read_bytes()
    if hashlib.sha256(payload).hexdigest() != V2_CONFIG_FILE_SHA256:
        raise ValueError("tracked Focus 2 v2 config differs from the frozen specification")
    if sha256_json(config) != V2_CONFIG_CANONICAL_HASH:
        raise ValueError("supplied Focus 2 v2 config differs from the frozen specification")


def _verify_v1_developmental_contract() -> Mapping[str, str | bool]:
    if (
        hashlib.sha256(
            (REPOSITORY_ROOT / "src/ragwarrant/research/fixed_sample_warrant.py").read_bytes()
        ).hexdigest()
        != V1_SOURCE_SHA256
    ):
        raise ValueError("v1 statistical implementation changed")
    if (
        hashlib.sha256(
            (REPOSITORY_ROOT / V1_TRACKED_PATHS[0]).read_bytes()
        ).hexdigest()
        != V1_CONFIG_SHA256
    ):
        raise ValueError("v1 configuration changed")
    return {
        "status": "DEVELOPMENTAL_TRACKED_CONTRACT_VERIFIED",
        "v1_source_sha256": V1_SOURCE_SHA256,
        "v1_config_sha256": V1_CONFIG_SHA256,
        "remote_tag_required": False,
        "complete_historical_authority_claimed": False,
    }


def _aggregate_method_rows(
    trials: list[dict[str, object]], truth_by_scenario: Mapping[str, ScenarioTruth]
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for aggregate in _aggregate_rows(trials, truth_by_scenario):
        matching = [
            row
            for row in trials
            if row["scenario_id"] == aggregate["scenario_id"]
            and row["method_id"] == aggregate["method_id"]
        ]
        first = matching[0]
        trial_count = int(aggregate["trial_count"])
        for event in EVENT_FIELDS:
            interval = wilson_interval(
                sum(int(row[event]) for row in matching), trial_count
            )
            aggregate[f"{event}_rate_confidence_interval"] = canonical_json(
                list(interval)
            )
        inconclusive_count = sum(int(row["inconclusive"]) for row in matching)
        aggregate.update(
            {
                "variant_id": first["variant_id"],
                "multiplicity_scope": first["multiplicity_scope"],
                "multiplicity_method": first["multiplicity_method"],
                "quality_test": first["quality_test"],
                "familywise_error_level": first["familywise_error_level"],
                "family_hash": first["family_hash"],
                "component_hypothesis_count": first["component_hypothesis_count"],
                "candidate_hypothesis_count": first["candidate_hypothesis_count"],
                "inconclusive_count": inconclusive_count,
                "inconclusive_rate": inconclusive_count / trial_count,
            }
        )
        output.append(aggregate)
    return sorted(
        output,
        key=lambda row: (str(row["scenario_id"]), str(row["variant_id"])),
    )


def _trial_row(
    *,
    truth: ScenarioTruth,
    trial_index: int,
    trial_identity: str,
    seed_fingerprint: str,
    evidence_hash: str,
    development_evidence_hash: str,
    decision: MethodDecision,
    specification: VariantSpecification,
    family_hash: str,
    component_count: int,
    candidate_count: int,
    invalid_evidence: bool,
    scored: Mapping[str, object],
) -> dict[str, object]:
    return {
        "scenario_id": truth.scenario_id,
        "base_scenario_id": truth.base_scenario_id,
        "family": truth.family,
        "sample_size": truth.sample_size,
        "candidate_count": len(truth.confirmatory_candidates),
        "trial_index": trial_index,
        "seed_schedule_version": SEED_SCHEDULE_VERSION,
        "evidence_trial_identity": trial_identity,
        "seed_fingerprint": seed_fingerprint,
        "method_id": decision.method_id,
        "variant_id": specification.variant_id,
        "multiplicity_scope": specification.multiplicity_scope,
        "multiplicity_method": specification.multiplicity_method,
        "quality_test": specification.quality_test,
        "familywise_error_level": 0.05,
        "family_hash": family_hash,
        "component_hypothesis_count": component_count,
        "candidate_hypothesis_count": candidate_count,
        **decision.public_research_metadata(),
        "evidence_hash": evidence_hash,
        "development_evidence_hash": development_evidence_hash,
        "selected_policy_id": decision.selected_policy_id,
        "certified_policy_ids": canonical_json(list(decision.certified_policy_ids)),
        "decision": decision.decision,
        "decision_reason": decision.decision_reason,
        "invalid_evidence": int(invalid_evidence),
        "inconclusive": int(decision.decision == "NO_DECISION" and not invalid_evidence),
        **scored,
    }


def _canonical_hypothesis_id(
    hypothesis_id: str, opaque_to_canonical: Mapping[str, str]
) -> str:
    policy_id, separator, suffix = hypothesis_id.partition("::")
    if not separator:
        raise ValueError("component hypothesis ID is malformed")
    return f"{opaque_to_canonical[policy_id]}::{suffix}"


def _diagnostic_retention_reason(
    trial_index: int, diagnostic_limit: int, scored: Mapping[str, object]
) -> str | None:
    if trial_index < diagnostic_limit:
        return "bounded_routine_sample"
    if bool(scored.get("false_promotion")) or bool(
        scored.get("false_certification")
    ):
        return "false_promotion_or_certification_event"
    return None


def _collect_v1_diagnostics(
    warrant: Any,
    specification: VariantSpecification,
    opaque_to_canonical: Mapping[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    candidate_rows: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
    for opaque_id in warrant.family.candidate_policy_ids:
        tests = tuple(test for test in warrant.risk_tests if test.policy_id == opaque_id)
        if not tests:
            raise ValueError("v1 warrant omitted a candidate component family")
        dominant = min(tests, key=lambda item: (-item.raw_p_value, item.hypothesis_id))
        certified = opaque_id in warrant.certified_policy_ids
        canonical_id = opaque_to_canonical[opaque_id]
        candidate_rows.append(
            {
                "policy_id": canonical_id,
                "component_p_values": canonical_json(
                    {
                        _canonical_hypothesis_id(test.hypothesis_id, opaque_to_canonical): test.raw_p_value
                        for test in tests
                    }
                ),
                "candidate_iut_p_value": candidate_iut_p_value(
                    test.raw_p_value for test in tests
                ),
                "adjusted_candidate_p_value": None,
                "candidate_rejection_threshold": None,
                "candidate_certified": certified,
                "dominant_hypothesis_id": _canonical_hypothesis_id(
                    dominant.hypothesis_id, opaque_to_canonical
                ),
                "dominant_risk_id": dominant.risk_id,
                "dominant_group_id": dominant.group_id,
            }
        )
        for test in tests:
            component_rows.append(
                {
                    "policy_id": canonical_id,
                    "hypothesis_id": _canonical_hypothesis_id(
                        test.hypothesis_id, opaque_to_canonical
                    ),
                    "risk_id": test.risk_id,
                    "group_id": test.group_id,
                    "raw_p_value": test.raw_p_value,
                    "multiplicity_adjusted_p_value": test.adjusted_p_value,
                    "certification_threshold": test.rejection_threshold,
                    "passed_certification_threshold": test.rejected,
                    "candidate_certified": certified,
                    "is_dominant_bottleneck": (
                        not certified and test.hypothesis_id == dominant.hypothesis_id
                    ),
                    "test_implementation": (
                        PAIRED_HOEFFDING
                        if test.risk_id in {"overall_quality", "group_quality"}
                        else "exact_binomial_lower_tail_v1"
                    ),
                }
            )
    return candidate_rows, component_rows


def _collect_v2_diagnostics(
    warrant: Any, opaque_to_canonical: Mapping[str, str]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    candidate_rows: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
    candidates = {item.policy_id: item for item in warrant.candidate_tests}
    for opaque_id in warrant.family.candidate_policy_ids:
        candidate = candidates[opaque_id]
        canonical_id = opaque_to_canonical[opaque_id]
        candidate_rows.append(
            {
                "policy_id": canonical_id,
                "component_p_values": canonical_json(
                    {
                        _canonical_hypothesis_id(test.hypothesis_id, opaque_to_canonical): test.raw_p_value
                        for test in warrant.component_tests
                        if test.policy_id == opaque_id
                    }
                ),
                "candidate_iut_p_value": candidate.candidate_iut_p_value,
                "adjusted_candidate_p_value": candidate.adjusted_candidate_p_value,
                "candidate_rejection_threshold": candidate.rejection_threshold,
                "candidate_certified": candidate.rejected,
                "dominant_hypothesis_id": _canonical_hypothesis_id(
                    candidate.dominant_component_hypothesis_id, opaque_to_canonical
                ),
                "dominant_risk_id": candidate.dominant_risk_id,
                "dominant_group_id": candidate.dominant_group_id,
            }
        )
    for test in warrant.component_tests:
        candidate = candidates[test.policy_id]
        component_rows.append(
            {
                "policy_id": opaque_to_canonical[test.policy_id],
                "hypothesis_id": _canonical_hypothesis_id(
                    test.hypothesis_id, opaque_to_canonical
                ),
                "risk_id": test.risk_id,
                "group_id": test.group_id,
                "raw_p_value": test.raw_p_value,
                "multiplicity_adjusted_p_value": test.multiplicity_adjusted_p_value,
                "certification_threshold": test.certification_threshold,
                "passed_certification_threshold": test.passed_certification_threshold,
                "candidate_certified": candidate.rejected,
                "is_dominant_bottleneck": (
                    not candidate.rejected
                    and test.hypothesis_id
                    == candidate.dominant_component_hypothesis_id
                ),
                "test_implementation": test.test_implementation,
            }
        )
    return candidate_rows, component_rows


def _aggregate_bottlenecks(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    key_fields = (
        "scenario_id",
        "base_scenario_id",
        "family",
        "sample_size",
        "candidate_count",
        "variant_id",
        "method_id",
        "multiplicity_scope",
        "multiplicity_method",
        "quality_test",
        "policy_id",
        "risk_id",
        "group_id",
        "test_implementation",
    )
    for row in rows:
        grouped[tuple(row[field] for field in key_fields)].append(row)
    output: list[dict[str, object]] = []
    for key, values in sorted(grouped.items(), key=lambda item: tuple(str(v) for v in item[0])):
        result = dict(zip(key_fields, key))
        trial_count = len(values)
        pass_count = sum(bool(value["passed_certification_threshold"]) for value in values)
        certified_count = sum(bool(value["candidate_certified"]) for value in values)
        dominant_count = sum(bool(value["is_dominant_bottleneck"]) for value in values)
        blocked_count = trial_count - certified_count
        result.update(
            {
                "trial_count": trial_count,
                "component_pass_count": pass_count,
                "component_pass_rate": pass_count / trial_count,
                "candidate_certification_count": certified_count,
                "candidate_certification_rate": certified_count / trial_count,
                "dominant_bottleneck_count": dominant_count,
                "dominant_bottleneck_rate_all_trials": dominant_count / trial_count,
                "dominant_bottleneck_rate_when_not_certified": (
                    dominant_count / blocked_count if blocked_count else 0.0
                ),
            }
        )
        output.append(result)
    return output


def run_focus2_v2_benchmark(
    config: Mapping[str, Any],
    v2_config: Mapping[str, Any],
    profile: str = "CI",
    master_seed: int | None = None,
) -> dict[str, object]:
    """Run A/B/C/D plus the prespecified D/Bonferroni comparison."""

    if profile not in SUPPORTED_PROFILES:
        if profile == "FULL":
            raise ValueError("FULL is prohibited in the Focus 2 v2 developmental runner")
        raise ValueError(f"unknown Focus 2 v2 profile: {profile}")
    _validate_v2_config(v2_config)
    _verify_v2_config(v2_config)
    v1_developmental_contract = _verify_v1_developmental_contract()
    focus1_developmental_contract = _verify_developmental_focus1_contract(
        config,
        {"focus1_benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST},
    )
    validate_config(config)

    seed_value = config["master_seed"] if master_seed is None else master_seed
    if isinstance(seed_value, bool) or not isinstance(seed_value, int) or seed_value < 0:
        raise ValueError("master seed must be a nonnegative integer")
    validate_revealed_profile_seed_uniqueness(config, profile, seed_value)
    schedule_manifest = build_seed_schedule_manifest(config)
    replicate_count = int(config["profiles"][profile]["replicate_count"])
    diagnostic_limit = int(v2_config["trial_diagnostic_sample_limit"])
    alpha = float(v2_config["familywise_error_level"])
    bounds = tuple(float(item) for item in v2_config["quality_delta_bounds"])
    incumbent = str(v2_config["incumbent_policy_id"])
    selection_objective = str(v2_config["selection_objective"])
    specifications = (_variant_a_specification(), *PRESPECIFIED_V2_VARIANTS)

    truth_rows: list[dict[str, object]] = []
    scenario_rows: list[dict[str, object]] = []
    all_trial_rows: list[dict[str, object]] = []
    sampled_trial_rows: list[dict[str, object]] = []
    diagnostic_sample_rows: list[dict[str, object]] = []
    component_trial_rows: list[dict[str, object]] = []
    truth_by_scenario: dict[str, ScenarioTruth] = {}
    evidence_hashes: dict[str, str] = {}
    warrant_samples: dict[str, dict[str, object]] = {}

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
            families = {
                specification.variant_id: freeze_candidate_family(
                    candidate_policy_ids=opaque_candidate_ids,
                    incumbent_policy_id=incumbent,
                    confirmatory_unit_count=sample_size,
                    policy=run_policy,
                    quality_delta_bounds=(bounds[0], bounds[1]),
                    familywise_error_level=alpha,
                    multiplicity_method=specification.multiplicity_method,
                    selection_objective=selection_objective,
                )
                for specification in specifications
            }
            methods: dict[str, object] = {
                VARIANT_A_ID: FixedSampleMultiRiskWarrant(families[VARIANT_A_ID])
            }
            methods.update(
                {
                    specification.variant_id: FixedSampleMultiRiskWarrantV2(
                        families[specification.variant_id], specification
                    )
                    for specification in PRESPECIFIED_V2_VARIANTS
                }
            )

            for trial_index in range(replicate_count):
                trial = simulate_trial(
                    config,
                    scenario,
                    sample_size,
                    trial_index,
                    profile,
                    master_seed=seed_value,
                )
                truth = trial.truth
                if tuple(
                    candidate.policy_id for candidate in truth.confirmatory_candidates
                ) != canonical_candidate_ids:
                    raise ValueError("simulator candidate IDs differ from frozen family")
                if truth.scenario_id not in truth_by_scenario:
                    truth_by_scenario[truth.scenario_id] = truth
                    truth_rows.extend(_truth_rows(truth))
                    scenario_rows.append(_scenario_summary_row(truth))

                canonical_evidence = trial.confirmatory_evidence
                development_evidence = trial.development_evidence
                if _evidence_digest(canonical_evidence) != canonical_evidence.evidence_hash:
                    raise ValueError("confirmatory evidence hash mismatch")
                if _evidence_digest(development_evidence) != development_evidence.evidence_hash:
                    raise ValueError("development evidence hash mismatch")
                evidence, opaque_to_canonical = _opaque_method_evidence(
                    canonical_evidence, canonical_candidate_ids
                )
                before_hash = _evidence_digest(evidence)
                before_object_id = id(evidence)
                if before_hash != evidence.evidence_hash:
                    raise ValueError("opaque evidence hash mismatch")
                existing_hash = evidence_hashes.setdefault(
                    trial.trial_identity, evidence.evidence_hash
                )
                if existing_hash != evidence.evidence_hash:
                    raise ValueError("methods within a trial received different evidence")

                for specification in specifications:
                    method = methods[specification.variant_id]
                    warrant = method.evaluate_warrant(evidence, run_policy)  # type: ignore[attr-defined]
                    if id(evidence) != before_object_id or _evidence_digest(evidence) != before_hash:
                        raise ValueError("a warrant variant replaced or mutated shared evidence")
                    decision = warrant.to_method_decision()
                    validate_method_decision(
                        decision,
                        specification.method_id,
                        evidence.policy_ids,
                        evidence,
                    )
                    canonical_decision = _canonical_decision(decision, opaque_to_canonical)
                    validate_method_decision(
                        canonical_decision,
                        specification.method_id,
                        canonical_candidate_ids,
                        None,
                    )
                    if canonical_decision.uses_population_truth:
                        raise ValueError("truth-isolated v2 variant accessed population truth")

                    if specification.variant_id == VARIANT_A_ID:
                        candidate_diagnostics, component_diagnostics = _collect_v1_diagnostics(
                            warrant, specification, opaque_to_canonical
                        )
                        component_count = len(warrant.risk_tests)
                        invalid_evidence = warrant.invalid_evidence_reason is not None
                    else:
                        candidate_diagnostics, component_diagnostics = _collect_v2_diagnostics(
                            warrant, opaque_to_canonical
                        )
                        component_count = len(warrant.component_tests)
                        invalid_evidence = warrant.invalid_evidence_reason is not None
                    family = families[specification.variant_id]
                    scored = score_decision(truth, canonical_decision, run_policy)
                    row = _trial_row(
                        truth=truth,
                        trial_index=trial_index,
                        trial_identity=trial.trial_identity,
                        seed_fingerprint=trial.seed_fingerprint,
                        evidence_hash=evidence.evidence_hash,
                        development_evidence_hash=development_evidence.evidence_hash,
                        decision=canonical_decision,
                        specification=specification,
                        family_hash=family.family_hash,
                        component_count=component_count,
                        candidate_count=len(family.candidate_policy_ids),
                        invalid_evidence=invalid_evidence,
                        scored=scored,
                    )
                    all_trial_rows.append(row)
                    if trial_index < diagnostic_limit:
                        sampled_trial_rows.append(dict(row))
                    if specification.variant_id not in warrant_samples:
                        warrant_samples[specification.variant_id] = json.loads(
                            canonical_json(public_research_artifact(warrant.as_dict()))
                        )

                    diagnostic_retention_reason = _diagnostic_retention_reason(
                        trial_index, diagnostic_limit, scored
                    )
                    for candidate_row in candidate_diagnostics:
                        diagnostic = {
                            "scenario_id": truth.scenario_id,
                            "base_scenario_id": truth.base_scenario_id,
                            "family": truth.family,
                            "sample_size": sample_size,
                            "candidate_count": len(canonical_candidate_ids),
                            "trial_index": trial_index,
                            "evidence_trial_identity": trial.trial_identity,
                            "evidence_hash": evidence.evidence_hash,
                            "variant_id": specification.variant_id,
                            "method_id": specification.method_id,
                            "multiplicity_scope": specification.multiplicity_scope,
                            "multiplicity_method": specification.multiplicity_method,
                            "quality_test_implementation_used": specification.quality_test,
                            "diagnostic_retention_reason": diagnostic_retention_reason,
                            "false_promotion_event": int(
                                bool(scored["false_promotion"])
                            ),
                            "false_certification_event": int(
                                bool(scored["false_certification"])
                            ),
                            **candidate_row,
                        }
                        diagnostic["candidate_status"] = (
                            "CERTIFIED"
                            if candidate_row["candidate_certified"]
                            else "NOT_CERTIFIED"
                        )
                        diagnostic["first_or_dominant_risk_preventing_certification"] = (
                            None
                            if candidate_row["candidate_certified"]
                            else (
                                f"{candidate_row['dominant_risk_id']}:{candidate_row['dominant_group_id']}"
                                if candidate_row["dominant_group_id"] is not None
                                else candidate_row["dominant_risk_id"]
                            )
                        )
                        if diagnostic_retention_reason is not None:
                            diagnostic_sample_rows.append(diagnostic)

                    for component_row in component_diagnostics:
                        component_trial_rows.append(
                            {
                                "scenario_id": truth.scenario_id,
                                "base_scenario_id": truth.base_scenario_id,
                                "family": truth.family,
                                "sample_size": sample_size,
                                "candidate_count": len(canonical_candidate_ids),
                                "trial_index": trial_index,
                                "variant_id": specification.variant_id,
                                "method_id": specification.method_id,
                                "multiplicity_scope": specification.multiplicity_scope,
                                "multiplicity_method": specification.multiplicity_method,
                                "quality_test": specification.quality_test,
                                **component_row,
                            }
                        )

    method_rows = _aggregate_method_rows(all_trial_rows, truth_by_scenario)
    scenario_ids = tuple(sorted(truth_by_scenario))
    manifest = {
        "benchmark_id": FOCUS2_V2_BENCHMARK_ID,
        "focus1_benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST,
        "v1_frozen_baseline_tag": V1_BASELINE_TAG,
        "v1_frozen_baseline_commit": V1_BASELINE_COMMIT,
        "v1_source_sha256": V1_SOURCE_SHA256,
        "v2_method_id": METHOD_ID,
        "v2_contract_digest": v2_contract_digest(),
        "protocol_version": str(config["protocol_version"]),
        "seed_schedule_version": SEED_SCHEDULE_VERSION,
        "seed_schedule_amendment_id": AMENDMENT_ID,
        "profile": profile,
        "evidence_role": "developmental",
        "developmental_contracts": {
            "focus1": focus1_developmental_contract,
            "v1": v1_developmental_contract,
        },
        "replicate_count_per_scenario_sample_size": replicate_count,
        "development_master_seed": seed_value,
        "full_profile_used": False,
        "full_evidence_generated": False,
        "full_results_inspected": False,
        "target_drand_round_selected": False,
        "canonical_evidence_trial_identity_format": CANONICAL_IDENTITY_FORMAT,
        "profile_identity_set_hash": schedule_manifest[
            "identity_set_hashes_by_profile"
        ][profile],
        "complete_schedule_hash": schedule_manifest["complete_schedule_hash"],
        "seed_plan": {
            "evidence_trial": DERIVATION_ALGORITHM,
            "schedule_fingerprint": SEED_FINGERPRINT_ALGORITHM,
        },
        "config_hash": sha256_json(config),
        "focus2_v2_config_hash": V2_CONFIG_CANONICAL_HASH,
        "focus2_v2_config_file_sha256": V2_CONFIG_FILE_SHA256,
        "protocol_hashes": {
            scenario_id: truth_by_scenario[scenario_id].protocol_hash
            for scenario_id in scenario_ids
        },
        "executed_method_ids": [item.method_id for item in specifications],
        "executed_method_variants": [item.as_dict() for item in specifications],
        "observed_evidence_only_method_ids": [
            item.method_id for item in specifications
        ],
        "truth_isolated_method_ids": [item.method_id for item in specifications],
        "research_candidate_method_ids": [item.method_id for item in specifications],
        "benchmark_control_method_ids": [],
        "truth_access_method_ids": [],
        "truth_isolated_method_accessed_population_truth": False,
        "same_observed_evidence_object_shared_by_all_variants": True,
        "candidate_families_frozen_before_confirmatory_evidence": True,
        "method_facing_identifiers": (
            "opaque candidate IDs; canonical IDs restored only after decision validation"
        ),
        "scenario_ids": list(scenario_ids),
        "base_scenario_ids": sorted(str(item["scenario_id"]) for item in scenarios),
        "trial_count_total": len(evidence_hashes),
        "method_trial_row_count_total": len(all_trial_rows),
        "scenario_method_summary_count": len(method_rows),
        "bounded_trial_sample_rows": len(sampled_trial_rows),
        "retained_power_diagnostic_rows": len(diagnostic_sample_rows),
        "bounded_routine_power_diagnostic_rows": sum(
            1
            for row in diagnostic_sample_rows
            if row["diagnostic_retention_reason"] == "bounded_routine_sample"
        ),
        "false_event_power_diagnostic_rows": sum(
            1
            for row in diagnostic_sample_rows
            if bool(row["false_promotion_event"])
            or bool(row["false_certification_event"])
        ),
        "post_hoc_filtered": False,
        "post_hoc_method_switching": False,
        "scenario_results_aggregated_into_headline": False,
        "prespecified_descriptive_criteria": dict(
            v2_config["prespecified_descriptive_criteria"]
        ),
        "monte_carlo_interval": (
            "two-sided 95% Wilson intervals for trial event rates"
        ),
        "candidate_risk_interval": (
            "method-specific finite-sample p-values; distinct from Monte Carlo uncertainty"
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
                str(row["scenario_id"]), int(row["trial_index"]), str(row["variant_id"])
            ),
        ),
        "risk_bottleneck_summary_rows": _aggregate_bottlenecks(component_trial_rows),
        "power_diagnostics_sample_rows": sorted(
            diagnostic_sample_rows,
            key=lambda row: (
                str(row["scenario_id"]),
                int(row["trial_index"]),
                str(row["variant_id"]),
                str(row["policy_id"]),
            ),
        ),
        "config_snapshot": json.loads(canonical_json(config)),
        "focus2_v2_config_snapshot": json.loads(canonical_json(v2_config)),
        "variant_specifications": [item.as_dict() for item in specifications],
        "warrant_samples": warrant_samples,
    }


__all__ = [
    "FOCUS2_V2_BENCHMARK_ID",
    "SUPPORTED_PROFILES",
    "V1_BASELINE_COMMIT",
    "V1_BASELINE_TAG",
    "V2_CONFIG_CANONICAL_HASH",
    "V2_CONFIG_FILE_SHA256",
    "load_v2_config",
    "run_focus2_v2_benchmark",
]
