"""Diagnostic-only Focus 2 power audit and named IUT-Holm comparison.

The module is additive.  It reuses the frozen v1 component tests through the
already-reviewed v2 IUT implementation, and it never changes Focus 1 inputs or
generates FULL evidence.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .benchmark import _evidence_digest, _opaque_method_evidence
from .fixed_sample_warrant import (
    FOCUS1_FREEZE_DIGEST,
    HOLM,
    FixedSampleMultiRiskWarrant,
    freeze_candidate_family,
)
from .fixed_sample_warrant_v2 import (
    CANDIDATE_IUT,
    PAIRED_HOEFFDING,
    VARIANT_B_ID,
    FixedSampleMultiRiskWarrantV2,
    VariantSpecification,
)
from .focus2_benchmark import _verify_frozen_focus1
from .focus2_v2_benchmark import V1_BASELINE_COMMIT, V1_BASELINE_TAG, V1_TRACKED_PATHS
from .simulator import canonical_json, policy_config, simulate_trial, validate_config
from .types import BINARY_RISKS, CandidateTruth, ObservedEvidence, PolicyConfig


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FOCUS1_CONFIG_PATH = REPOSITORY_ROOT / "configs/research/false_promotion_benchmark_v1.yaml"
V2_CONFIG_PATH = (
    REPOSITORY_ROOT / "configs/research/fixed_sample_multi_risk_warrant_v2.yaml"
)
OVERLAY_CONFIG_PATH = (
    REPOSITORY_ROOT
    / "configs/research/fixed_sample_multi_risk_warrant_v2_iut_holm.yaml"
)
V1_RESULT_ROOT = REPOSITORY_ROOT / ".local_data/fixed_sample_warrant"
V2_RESULT_ROOT = REPOSITORY_ROOT / ".local_data/fixed_sample_warrant_v2"
SUPPORTED_DIAGNOSTIC_PROFILES = ("CI", "LOCAL")
METHOD_ID = "FIXED_SAMPLE_MULTI_RISK_WARRANT_V2_IUT_HOLM"
VARIANT_ID = "FOCUS2_POWER_V2_IUT_HOLM"
COMPARISON_SPECIFICATION = VariantSpecification(
    VARIANT_ID,
    METHOD_ID,
    CANDIDATE_IUT,
    HOLM,
    PAIRED_HOEFFDING,
)
V1_RESULT_PROFILES = ("ci_v2", "local_v2")
V1_ARTIFACT_FILENAMES = (
    "benchmark_manifest.json",
    "claim_boundaries.md",
    "focus1_config_snapshot.yaml",
    "focus2_benchmark_report.md",
    "focus2_config_snapshot.yaml",
    "holm_bonferroni_comparison.csv",
    "method_summary.csv",
    "promotion_warrant.json",
    "promotion_warrant_bonferroni.json",
    "scenario_summary.csv",
    "scenario_truth.csv",
    "trial_summary_sample.csv",
)


@dataclass(frozen=True)
class BinaryBestCaseFeasibility:
    threshold: float
    sample_count: int
    cutoff: float
    minimum_attainable_p_value: float
    minimum_sample_count: int | None
    attainable: bool


class FixedSampleMultiRiskWarrantV2IUTHolm:
    """Explicit name for v1 components -> candidate IUT -> candidate Holm."""

    def __init__(self, family: Any) -> None:
        self._inner = FixedSampleMultiRiskWarrantV2(
            family, COMPARISON_SPECIFICATION
        )
        self.family = family
        self.specification = COMPARISON_SPECIFICATION

    def evaluate_warrant(
        self, evidence: ObservedEvidence, policy: PolicyConfig
    ) -> Any:
        return self._inner.evaluate_warrant(evidence, policy)

    def evaluate(
        self, evidence: ObservedEvidence, policy: PolicyConfig, method_seed: int = 0
    ) -> Any:
        del method_seed
        return self.evaluate_warrant(evidence, policy).to_method_decision()


def load_overlay_config(path: str | Path = OVERLAY_CONFIG_PATH) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError("Focus 2 IUT-Holm overlay is unreadable") from exc
    if not isinstance(loaded, dict):
        raise ValueError("Focus 2 IUT-Holm overlay must be a mapping")
    validate_overlay_config(loaded)
    return loaded


def validate_overlay_config(config: Mapping[str, Any]) -> None:
    required = {
        "schema_version": "fixed_sample_multi_risk_warrant_v2_iut_holm_overlay.v1",
        "method_id": METHOD_ID,
        "focus1_benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST,
        "v1_baseline_tag": V1_BASELINE_TAG,
        "v1_baseline_commit": V1_BASELINE_COMMIT,
        "base_component_method": "fixed_sample_multi_risk_warrant_v1",
        "base_component_variant": VARIANT_B_ID,
        "component_tests": "unchanged_v1",
        "hypothesis_composition": "candidate_max_component_p_value",
        "candidate_family_multiplicity": HOLM,
        "familywise_error_level": 0.05,
        "development_profiles": ["CI", "LOCAL"],
        "diagnostic_trial_indices": [0, 1],
        "full_profile_permitted": False,
        "target_drand_round_selected": False,
        "truth_available_to_method": False,
        "research_only": True,
        "production_integrated": False,
    }
    for field, expected in required.items():
        if config.get(field) != expected:
            raise ValueError(f"Focus 2 IUT-Holm overlay {field} must equal {expected!r}")


def binary_best_case_feasibility(
    threshold: float, sample_count: int, cutoff: float
) -> BinaryBestCaseFeasibility:
    """Best exact lower-tail result when zero adverse events are observed."""

    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("binary threshold must lie in [0, 1]")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 0:
        raise ValueError("sample_count must be a nonnegative integer")
    if not math.isfinite(cutoff) or not 0.0 < cutoff < 1.0:
        raise ValueError("cutoff must lie strictly between zero and one")
    if sample_count == 0 or threshold == 0.0:
        minimum_p = 1.0
        minimum_n = None
    elif threshold == 1.0:
        minimum_p = 0.0
        minimum_n = 1
    else:
        minimum_p = math.exp(sample_count * math.log1p(-threshold))
        minimum_n = max(1, math.ceil(math.log(cutoff) / math.log1p(-threshold)))
        while math.exp(minimum_n * math.log1p(-threshold)) > cutoff:
            minimum_n += 1
        while (
            minimum_n > 1
            and math.exp((minimum_n - 1) * math.log1p(-threshold)) <= cutoff
        ):
            minimum_n -= 1
    return BinaryBestCaseFeasibility(
        threshold=threshold,
        sample_count=sample_count,
        cutoff=cutoff,
        minimum_attainable_p_value=minimum_p,
        minimum_sample_count=minimum_n,
        attainable=minimum_p <= cutoff,
    )


def hoeffding_required_gap(
    sample_count: int, support_width: float, cutoff: float
) -> float:
    """Algebraic mean gap above the null boundary needed to cross cutoff."""

    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0:
        return math.inf
    if not math.isfinite(support_width) or support_width <= 0.0:
        raise ValueError("support_width must be positive")
    if not math.isfinite(cutoff) or not 0.0 < cutoff < 1.0:
        raise ValueError("cutoff must lie strictly between zero and one")
    return support_width * math.sqrt(math.log(1.0 / cutoff) / (2.0 * sample_count))


def hoeffding_best_case_p_value(
    sample_count: int,
    margin: float,
    lower_bound: float,
    upper_bound: float,
) -> float:
    if sample_count <= 0:
        return 1.0
    width = upper_bound - lower_bound
    if not math.isfinite(width) or width <= 0.0:
        raise ValueError("quality support must have positive width")
    best_excess = max(0.0, upper_bound + margin)
    return math.exp(-2.0 * sample_count * best_excess * best_excess / (width * width))


def minimum_hoeffding_sample_count(
    margin: float, lower_bound: float, upper_bound: float, cutoff: float
) -> int | None:
    width = upper_bound - lower_bound
    if not math.isfinite(width) or width <= 0.0:
        raise ValueError("quality support must have positive width")
    best_excess = max(0.0, upper_bound + margin)
    if best_excess == 0.0:
        return None
    return max(
        1,
        math.ceil(
            width * width * math.log(1.0 / cutoff) / (2.0 * best_excess * best_excess)
        ),
    )


def maurer_pontil_theorem4_radius(
    sample_count: int, sample_variance: float, delta: float
) -> float:
    """Diagnostic evaluation of Maurer-Pontil Theorem 4, not a test method."""

    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 2:
        return math.inf
    if not math.isfinite(sample_variance) or sample_variance < 0.0:
        raise ValueError("sample_variance must be finite and nonnegative")
    if not math.isfinite(delta) or not 0.0 < delta < 1.0:
        raise ValueError("delta must lie strictly between zero and one")
    log_term = math.log(2.0 / delta)
    return math.sqrt(2.0 * sample_variance * log_term / sample_count) + (
        7.0 * log_term / (3.0 * (sample_count - 1))
    )


def _sample_variance(values: Iterable[float]) -> float | None:
    materialized = tuple(values)
    if len(materialized) < 2:
        return None
    mean = math.fsum(materialized) / len(materialized)
    return math.fsum((value - mean) ** 2 for value in materialized) / (
        len(materialized) - 1
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def build_v1_preservation_manifest(
    *, include_result_artifacts: bool = True
) -> dict[str, object]:
    implementation_hashes = {
        path: _sha256_file(REPOSITORY_ROOT / path) for path in V1_TRACKED_PATHS
    }
    result_hashes: dict[str, str] = {}
    if include_result_artifacts:
        for profile in V1_RESULT_PROFILES:
            for filename in V1_ARTIFACT_FILENAMES:
                path = V1_RESULT_ROOT / profile / filename
                if not path.is_file():
                    raise ValueError(f"required v1 result artifact is missing: {path}")
                relative = path.relative_to(REPOSITORY_ROOT).as_posix()
                result_hashes[relative] = _sha256_file(path)
    peeled_tag = _git("rev-parse", f"{V1_BASELINE_TAG}^{{}}")
    changed_v1 = _git("diff", "--name-only", V1_BASELINE_COMMIT, "--", *V1_TRACKED_PATHS)
    return {
        "schema_version": "focus2_v1_preservation_manifest.v1",
        "focus1_benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST,
        "v1_baseline_tag": V1_BASELINE_TAG,
        "v1_baseline_commit": V1_BASELINE_COMMIT,
        "v1_baseline_tag_peeled_commit": peeled_tag,
        "v1_tracked_paths_changed_from_baseline": [
            value for value in changed_v1.splitlines() if value
        ],
        "implementation_sha256": implementation_hashes,
        "result_artifact_sha256": result_hashes,
    }


def _load_existing_hashes(profile: str) -> dict[tuple[str, int], str]:
    path = V2_RESULT_ROOT / f"{profile.lower()}_v2" / "power_diagnostics_sample.csv"
    if not path.is_file():
        raise ValueError(f"existing v2 diagnostic output is missing: {path}")
    hashes: dict[tuple[str, int], str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["variant_id"] != VARIANT_B_ID:
                continue
            key = (row["evidence_trial_identity"], int(row["trial_index"]))
            prior = hashes.setdefault(key, row["evidence_hash"])
            if prior != row["evidence_hash"]:
                raise ValueError("existing methods record different evidence hashes")
    return hashes


def _load_zero_certification_cells() -> dict[tuple[str, str, str], bool]:
    observed: dict[tuple[str, str, str], bool] = {}
    sources = (
        (V1_RESULT_ROOT, "fixed_sample_multi_risk_warrant_v1", None),
        (
            V2_RESULT_ROOT,
            "fixed_sample_multi_risk_warrant_v2_iut_hoeffding_ablation",
            VARIANT_B_ID,
        ),
    )
    for root, method_id, variant_id in sources:
        for profile in SUPPORTED_DIAGNOSTIC_PROFILES:
            path = root / f"{profile.lower()}_v2" / "method_summary.csv"
            with path.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    if row["method_id"] != method_id:
                        continue
                    if variant_id is None and row.get("multiplicity_method") != HOLM:
                        continue
                    if variant_id is not None and row.get("variant_id") != variant_id:
                        continue
                    label = "v1_holm" if variant_id is None else "v2_iut_holm"
                    observed[(profile, row["scenario_id"], label)] = (
                        float(row["mean_certified_set_size"]) > 0.0
                    )
    return observed


def _truth_value(candidate: CandidateTruth, risk_id: str, group_id: str | None) -> float:
    if risk_id == "overall_quality":
        return candidate.overall_quality_delta_vs_incumbent
    if risk_id == "group_quality":
        return dict(candidate.quality_delta_by_group)[str(group_id)]
    if risk_id not in BINARY_RISKS:
        raise ValueError(f"unknown component risk: {risk_id}")
    if group_id is None:
        return float(getattr(candidate, risk_id))
    return dict(getattr(candidate, f"{risk_id}_by_group"))[group_id]


def _quality_values(
    evidence: ObservedEvidence, policy_id: str, group_id: str | None
) -> tuple[float, ...]:
    rows = evidence.rows_for(policy_id)
    return tuple(
        row.quality_delta
        for row in rows
        if group_id is None or row.group_id == group_id
    )


def _canonical_hypothesis_id(hypothesis_id: str, canonical_policy_id: str) -> str:
    _, separator, suffix = hypothesis_id.partition("::")
    if not separator:
        raise ValueError("component hypothesis ID is malformed")
    return f"{canonical_policy_id}::{suffix}"


def build_power_feasibility_rows(
    config: Mapping[str, Any],
    overlay_config: Mapping[str, Any],
    *,
    verify_retained_outputs: bool = True,
) -> list[dict[str, object]]:
    validate_config(config)
    validate_overlay_config(overlay_config)
    if verify_retained_outputs:
        _verify_frozen_focus1(
            config, {"focus1_benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST}
        )
    alpha = float(overlay_config["familywise_error_level"])
    diagnostic_indices = tuple(int(value) for value in overlay_config["diagnostic_trial_indices"])
    existing_certifications = (
        _load_zero_certification_cells() if verify_retained_outputs else {}
    )
    output: list[dict[str, object]] = []

    for profile in SUPPORTED_DIAGNOSTIC_PROFILES:
        expected_hashes = (
            _load_existing_hashes(profile) if verify_retained_outputs else None
        )
        for scenario in sorted(config["scenarios"], key=lambda item: str(item["scenario_id"])):
            canonical_ids = tuple(
                sorted(str(candidate["policy_id"]) for candidate in scenario["candidates"])
            )
            opaque_ids = tuple(
                f"policy_{index:04d}" for index, _ in enumerate(canonical_ids, start=1)
            )
            for sample_size in sorted(int(value) for value in scenario["sample_sizes"]):
                run_policy = policy_config(config, scenario, profile)
                bounds = tuple(float(value) for value in scenario["noise"]["quality_delta_bounds"])
                family = freeze_candidate_family(
                    candidate_policy_ids=opaque_ids,
                    incumbent_policy_id="benchmark_incumbent_v1",
                    confirmatory_unit_count=sample_size,
                    policy=run_policy,
                    quality_delta_bounds=(bounds[0], bounds[1]),
                    familywise_error_level=alpha,
                    multiplicity_method=HOLM,
                    selection_objective="minimize_cost",
                )
                v1_method = FixedSampleMultiRiskWarrant(family)
                v2_method = FixedSampleMultiRiskWarrantV2IUTHolm(family)
                for trial_index in diagnostic_indices:
                    trial = simulate_trial(
                        config, scenario, sample_size, trial_index, profile
                    )
                    evidence, opaque_to_canonical = _opaque_method_evidence(
                        trial.confirmatory_evidence, canonical_ids
                    )
                    expected_key = (trial.trial_identity, trial_index)
                    if (
                        expected_hashes is not None
                        and expected_hashes.get(expected_key) != evidence.evidence_hash
                    ):
                        raise ValueError(
                            "regenerated diagnostic evidence does not match retained output"
                        )
                    before_id = id(evidence)
                    before_hash = _evidence_digest(evidence)
                    v1_warrant = v1_method.evaluate_warrant(evidence, run_policy)
                    v2_warrant = v2_method.evaluate_warrant(evidence, run_policy)
                    if id(evidence) != before_id or _evidence_digest(evidence) != before_hash:
                        raise ValueError("comparison methods did not preserve shared evidence")
                    if v1_warrant.invalid_evidence_reason or v2_warrant.invalid_evidence_reason:
                        raise ValueError("valid frozen evidence failed a warrant contract")

                    v1_tests = {item.hypothesis_id: item for item in v1_warrant.risk_tests}
                    v2_tests = {
                        item.hypothesis_id: item for item in v2_warrant.component_tests
                    }
                    candidates = {item.policy_id: item for item in v2_warrant.candidate_tests}
                    if set(v1_tests) != set(v2_tests):
                        raise ValueError("v1 and v2 component families differ")
                    component_count = len(v1_tests)
                    candidate_count = len(family.candidate_policy_ids)
                    for opaque_id in family.candidate_policy_ids:
                        canonical_id = opaque_to_canonical[opaque_id]
                        truth = trial.truth.confirmatory_candidate(canonical_id)
                        candidate_test = candidates[opaque_id]
                        for hypothesis_id in sorted(
                            key for key in v1_tests if key.startswith(f"{opaque_id}::")
                        ):
                            v1_test = v1_tests[hypothesis_id]
                            v2_test = v2_tests[hypothesis_id]
                            if (
                                v1_test.raw_p_value != v2_test.raw_p_value
                                or v2_test.test_implementation
                                not in {PAIRED_HOEFFDING, "exact_binomial_lower_tail_v1"}
                            ):
                                raise ValueError("v2 comparison changed a v1 component test")
                            n = int(v1_test.sample_count)
                            iut_conservative = alpha / candidate_count
                            flat_conservative = alpha / component_count
                            is_quality = v1_test.risk_id in {
                                "overall_quality",
                                "group_quality",
                            }
                            margin = (
                                run_policy.quality_noninferiority_margin
                                if v1_test.risk_id == "overall_quality"
                                else run_policy.group_quality_noninferiority_margin
                            )
                            binary_unadjusted = binary_iut = binary_flat = None
                            quality_p_min = None
                            min_quality_n_alpha = None
                            required_gap_alpha = None
                            required_gap_iut = None
                            required_gap_flat = None
                            observed_gap = None
                            normalized_variance = None
                            eb_radius_alpha = None
                            eb_radius_iut = None
                            eb_crosses_alpha = None
                            if is_quality:
                                quality_p_min = hoeffding_best_case_p_value(
                                    n, margin, bounds[0], bounds[1]
                                )
                                min_quality_n_alpha = minimum_hoeffding_sample_count(
                                    margin, bounds[0], bounds[1], alpha
                                )
                                required_gap_alpha = hoeffding_required_gap(
                                    n, bounds[1] - bounds[0], alpha
                                )
                                required_gap_iut = hoeffding_required_gap(
                                    n, bounds[1] - bounds[0], iut_conservative
                                )
                                required_gap_flat = hoeffding_required_gap(
                                    n, bounds[1] - bounds[0], flat_conservative
                                )
                                if v1_test.observed_statistic is not None:
                                    observed_gap = float(v1_test.observed_statistic) + margin
                                deltas = _quality_values(
                                    evidence, opaque_id, v1_test.group_id
                                )
                                losses = tuple(
                                    (bounds[1] - value) / (bounds[1] - bounds[0])
                                    for value in deltas
                                )
                                normalized_variance = _sample_variance(losses)
                                if normalized_variance is not None:
                                    eb_radius_alpha = maurer_pontil_theorem4_radius(
                                        n, normalized_variance, alpha
                                    )
                                    eb_radius_iut = maurer_pontil_theorem4_radius(
                                        n, normalized_variance, iut_conservative
                                    )
                                    threshold_loss = (bounds[1] + margin) / (
                                        bounds[1] - bounds[0]
                                    )
                                    mean_loss = math.fsum(losses) / len(losses)
                                    eb_crosses_alpha = (
                                        mean_loss + eb_radius_alpha < threshold_loss
                                    )
                                p_min = quality_p_min
                            else:
                                threshold = float(v1_test.null_boundary)
                                binary_unadjusted = binary_best_case_feasibility(
                                    threshold, n, alpha
                                )
                                binary_iut = binary_best_case_feasibility(
                                    threshold, n, iut_conservative
                                )
                                binary_flat = binary_best_case_feasibility(
                                    threshold, n, flat_conservative
                                )
                                p_min = binary_unadjusted.minimum_attainable_p_value

                            observed_event_count = (
                                int(round(float(v1_test.observed_statistic) * n))
                                if not is_quality
                                and v1_test.observed_statistic is not None
                                else None
                            )
                            candidate_components = tuple(
                                item
                                for item in v2_warrant.component_tests
                                if item.policy_id == opaque_id
                            )
                            prior_holm_stop = (
                                not candidate_test.rejected
                                and all(
                                    bool(item.passed_certification_threshold)
                                    for item in candidate_components
                                )
                            )
                            dominant_gate_label = (
                                f"{candidate_test.dominant_risk_id}:{candidate_test.dominant_group_id}"
                                if candidate_test.dominant_group_id is not None
                                else candidate_test.dominant_risk_id
                            )

                            missing = n == 0 or v1_test.failure_reason is not None
                            algebraically_possible = not missing and float(p_min) <= alpha
                            if missing:
                                feasibility_class = "MISSING_MANDATORY_EVIDENCE"
                            elif not algebraically_possible:
                                feasibility_class = (
                                    "MATHEMATICALLY_IMPOSSIBLE_UNADJUSTED_AT_ACTUAL_N"
                                )
                            elif v1_test.raw_p_value > alpha:
                                feasibility_class = (
                                    "OBSERVED_FAIL_UNADJUSTED_BUT_ALGEBRAICALLY_POSSIBLE"
                                )
                            elif not candidate_test.rejected:
                                feasibility_class = (
                                    "OBSERVED_PASS_UNADJUSTED_BLOCKED_BY_MULTIPLICITY_OR_OTHER_GATE"
                                )
                            else:
                                feasibility_class = "OBSERVED_CANDIDATE_CERTIFIED"

                            output.append(
                                {
                                    "profile": profile,
                                    "scenario_id": trial.truth.scenario_id,
                                    "base_scenario_id": trial.truth.base_scenario_id,
                                    "scenario_family": trial.truth.family,
                                    "sample_size": sample_size,
                                    "candidate_count": candidate_count,
                                    "trial_index": trial_index,
                                    "evidence_trial_identity": trial.trial_identity,
                                    "evidence_hash": evidence.evidence_hash,
                                    "policy_id": canonical_id,
                                    "candidate_truly_safe": truth.truly_promotion_safe,
                                    "candidate_failed_truth_conditions": canonical_json(
                                        list(truth.failed_truth_conditions)
                                    ),
                                    "hypothesis_id": _canonical_hypothesis_id(
                                        hypothesis_id, canonical_id
                                    ),
                                    "risk_id": v1_test.risk_id,
                                    "group_id": v1_test.group_id,
                                    "actual_observation_count": n,
                                    "null_hypothesis": v1_test.null_hypothesis,
                                    "null_boundary": v1_test.null_boundary,
                                    "support_lower": (
                                        v1_test.support_bounds[0]
                                        if v1_test.support_bounds is not None
                                        else None
                                    ),
                                    "support_upper": (
                                        v1_test.support_bounds[1]
                                        if v1_test.support_bounds is not None
                                        else None
                                    ),
                                    "true_component_value_diagnostic_only": _truth_value(
                                        truth, v1_test.risk_id, v1_test.group_id
                                    ),
                                    "observed_statistic": v1_test.observed_statistic,
                                    "observed_event_count": observed_event_count,
                                    "raw_p_value": v1_test.raw_p_value,
                                    "v1_flat_family_size": component_count,
                                    "v1_holm_adjusted_p_value": v1_test.adjusted_p_value,
                                    "v1_holm_rejection_threshold": v1_test.rejection_threshold,
                                    "v1_component_rejected": v1_test.rejected,
                                    "v1_gate_prevented_certification": not v1_test.rejected,
                                    "v1_candidate_certified": (
                                        opaque_id in v1_warrant.certified_policy_ids
                                    ),
                                    "v2_candidate_family_size": candidate_count,
                                    "v2_candidate_iut_p_value": candidate_test.candidate_iut_p_value,
                                    "v2_candidate_holm_adjusted_p_value": candidate_test.adjusted_candidate_p_value,
                                    "v2_candidate_holm_rejection_threshold": candidate_test.rejection_threshold,
                                    "v2_component_crossed_candidate_threshold": v2_test.passed_certification_threshold,
                                    "v2_gate_failed_candidate_threshold": not bool(
                                        v2_test.passed_certification_threshold
                                    ),
                                    "v2_candidate_blocked_by_prior_holm_stop": prior_holm_stop,
                                    "v2_candidate_certified": candidate_test.rejected,
                                    "first_or_dominant_gate_preventing_v2_certification": (
                                        None
                                        if candidate_test.rejected
                                        else dominant_gate_label
                                    ),
                                    "dominant_gate": (
                                        hypothesis_id
                                        == candidate_test.dominant_component_hypothesis_id
                                    ),
                                    "fails_even_without_multiplicity": (
                                        v1_test.raw_p_value > alpha
                                    ),
                                    "minimum_attainable_p_value_at_actual_n": p_min,
                                    "algebraically_possible_unadjusted": algebraically_possible,
                                    "feasibility_class": feasibility_class,
                                    "binary_min_n_unadjusted": (
                                        binary_unadjusted.minimum_sample_count
                                        if binary_unadjusted is not None
                                        else None
                                    ),
                                    "binary_min_n_candidate_bonferroni": (
                                        binary_iut.minimum_sample_count
                                        if binary_iut is not None
                                        else None
                                    ),
                                    "binary_min_n_flat_bonferroni": (
                                        binary_flat.minimum_sample_count
                                        if binary_flat is not None
                                        else None
                                    ),
                                    "hoeffding_min_n_best_case_unadjusted": min_quality_n_alpha,
                                    "observed_gap_above_quality_boundary": observed_gap,
                                    "required_quality_gap_unadjusted": required_gap_alpha,
                                    "required_quality_gap_candidate_bonferroni": required_gap_iut,
                                    "required_quality_gap_flat_bonferroni": required_gap_flat,
                                    "normalized_loss_sample_variance": normalized_variance,
                                    "maurer_pontil_radius_unadjusted_diagnostic": eb_radius_alpha,
                                    "maurer_pontil_radius_candidate_bonferroni_diagnostic": eb_radius_iut,
                                    "maurer_pontil_bound_crosses_unadjusted_diagnostic": eb_crosses_alpha,
                                    "existing_complete_developmental_profile_v1_holm_any_certification": existing_certifications.get(
                                        (profile, trial.truth.scenario_id, "v1_holm"),
                                        False,
                                    ),
                                    "existing_complete_developmental_profile_v2_iut_holm_any_certification": existing_certifications.get(
                                        (profile, trial.truth.scenario_id, "v2_iut_holm"),
                                        False,
                                    ),
                                    "method_received_population_truth": False,
                                }
                            )
    return sorted(
        output,
        key=lambda row: (
            str(row["profile"]),
            str(row["scenario_id"]),
            int(row["trial_index"]),
            str(row["policy_id"]),
            str(row["risk_id"]),
            str(row["group_id"]),
        ),
    )


def summarize_feasibility_cells(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["profile"]), str(row["scenario_id"]))].append(row)
    output: list[dict[str, object]] = []
    for (profile, scenario_id), values in sorted(grouped.items()):
        candidate_trials: dict[tuple[str, int], list[Mapping[str, object]]] = defaultdict(list)
        for row in values:
            candidate_trials[(str(row["policy_id"]), int(row["trial_index"]))].append(row)
        impossible_candidate_trials = sum(
            1
            for components in candidate_trials.values()
            if any(not bool(item["algebraically_possible_unadjusted"]) for item in components)
        )
        total_candidate_trials = len(candidate_trials)
        any_certification = bool(
            values[0][
                "existing_complete_developmental_profile_v2_iut_holm_any_certification"
            ]
        )
        empirical_result = (
            "A_CERTIFICATION_OBSERVED"
            if any_certification
            else "A_NO_CERTIFICATIONS_OBSERVED"
        )
        if impossible_candidate_trials == total_candidate_trials:
            structural_feasibility = (
                "B_IMPOSSIBLE_UNADJUSTED_AT_RETAINED_ACTUAL_COUNTS"
            )
        elif impossible_candidate_trials == 0:
            structural_feasibility = "C_ALGEBRAICALLY_POSSIBLE_AT_RETAINED_ACTUAL_COUNTS"
        else:
            structural_feasibility = "MIXED_B_C_FEASIBILITY_ACROSS_CANDIDATE_TRIALS"
        has_safe_candidate = any(bool(row["candidate_truly_safe"]) for row in values)
        if not has_safe_candidate:
            interpretation = "POWER_NOT_APPLICABLE_NO_SAFE_CANDIDATE_CORRECT_BLOCK_OBSERVED"
        elif structural_feasibility.startswith("B_"):
            interpretation = "COMPONENT_TEST_BUDGET_IMPOSSIBLE_FOR_RETAINED_COUNTS"
        elif structural_feasibility.startswith("C_"):
            interpretation = "C_CERTIFICATION_POSSIBLE_BUT_OBSERVED_POWER_LOW"
        else:
            interpretation = "MIXED_STRUCTURAL_FEASIBILITY_OBSERVED_POWER_LOW"
        dominant = Counter(
            (
                str(row["risk_id"]),
                "" if row["group_id"] is None else str(row["group_id"]),
            )
            for row in values
            if bool(row["dominant_gate"])
        )
        dominant_gate = dominant.most_common(1)[0][0] if dominant else ("", "")
        group_counts = [
            int(row["actual_observation_count"])
            for row in values
            if row["group_id"] is not None
        ]
        first = values[0]
        output.append(
            {
                "profile": profile,
                "scenario_id": scenario_id,
                "scenario_family": first["scenario_family"],
                "sample_size": first["sample_size"],
                "candidate_count": first["candidate_count"],
                "retained_trial_count": len({int(row["trial_index"]) for row in values}),
                "candidate_trial_count": total_candidate_trials,
                "impossible_candidate_trial_count": impossible_candidate_trials,
                "minimum_group_observation_count": min(group_counts) if group_counts else None,
                "maximum_group_observation_count": max(group_counts) if group_counts else None,
                "dominant_gate": (
                    f"{dominant_gate[0]}:{dominant_gate[1]}"
                    if dominant_gate[1]
                    else dominant_gate[0]
                ),
                "existing_v1_any_certification": first[
                    "existing_complete_developmental_profile_v1_holm_any_certification"
                ],
                "existing_v2_any_certification": first[
                    "existing_complete_developmental_profile_v2_iut_holm_any_certification"
                ],
                "empirical_result": empirical_result,
                "safe_candidate_exists": has_safe_candidate,
                "structural_feasibility": structural_feasibility,
                "classification": interpretation,
            }
        )
    return output


def render_feasibility_report(
    rows: list[dict[str, object]], preservation: Mapping[str, object]
) -> str:
    cells = summarize_feasibility_cells(rows)
    lines = [
        "# Focus 2 power feasibility audit",
        "",
        "Status: diagnostic developmental audit; not a confirmatory benchmark result.",
        "",
        "## Preserved baseline",
        "",
        f"- Focus 1 digest: `{FOCUS1_FREEZE_DIGEST}`.",
        f"- Frozen v1 tag/commit: `{V1_BASELINE_TAG}` / `{V1_BASELINE_COMMIT}`.",
        f"- v1 tracked files changed from the baseline: `{len(preservation['v1_tracked_paths_changed_from_baseline'])}`.",
        f"- v1 implementation files hashed: `{len(preservation['implementation_sha256'])}`.",
        f"- v1 result artifacts hashed without overwrite: `{len(preservation['result_artifact_sha256'])}`.",
        "- Actual CI-v2 and LOCAL-v2 method summaries confirm zero certifications for v1 Holm and the matched v2 candidate-IUT Holm comparison in every cell.",
        "",
        "## Audit scope",
        "",
        "The CSV records every candidate and mandatory risk for trial indices 0 and 1 in every frozen CI-v2 and LOCAL-v2 scenario/sample-size cell. These are the prespecified bounded diagnostic identities already retained by the completed developmental runs. Regenerated evidence hashes were required to match the existing outputs exactly. No replacement seed was drawn.",
        "",
        "Truth fields are joined only after method evaluation and are labeled `diagnostic_only`; neither deployable method receives population truth. Both methods receive the same immutable evidence object.",
        "",
        "## Feasibility definitions",
        "",
        "- **A — no certification observed:** an empirical result from the complete existing developmental profile; every current cell has this label.",
        "- **B — mathematically impossible at the actual component count:** at least one mandatory component has a best-case finite-sample p-value above 0.05 even before multiplicity. This is evaluated at the retained trial's actual subgroup count where applicable.",
        "- **C — algebraically possible:** every mandatory component could cross 0.05 at its actual count under documented support. In cells containing a truly safe candidate, the complete developmental profile's zero certifications are then described as observed low power.",
        "- **Mixed B/C:** some candidate-trials are structurally impossible at their actual counts while others remain algebraically possible. Mixed cells are never relabeled as C.",
        "- **No-safe-candidate cells:** certification power is not defined. Zero certification is correct blocking, even when unsafe-candidate certification is algebraically possible.",
        "",
        "These labels are not population power calculations. In particular, the Hoeffding gap is an algebraic crossing requirement, not an estimated certification probability.",
        "",
        "## Gate-by-gate cell summary",
        "",
        "| Profile | Scenario/sample cell | Family | Candidates | Group n range | Impossible candidate-trials | Structural feasibility | Interpretation |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    for cell in cells:
        group_range = (
            f"{cell['minimum_group_observation_count']}–{cell['maximum_group_observation_count']}"
            if cell["minimum_group_observation_count"] is not None
            else "n/a"
        )
        lines.append(
            "| {profile} | `{scenario_id}` | {family} | {candidate_count} | {group_range} | {impossible}/{total}; dominant `{dominant}` | `{structural}` | `{classification}` |".format(
                profile=cell["profile"],
                scenario_id=cell["scenario_id"],
                family=cell["scenario_family"],
                candidate_count=cell["candidate_count"],
                group_range=group_range,
                impossible=cell["impossible_candidate_trial_count"],
                total=cell["candidate_trial_count"],
                dominant=cell["dominant_gate"],
                structural=cell["structural_feasibility"],
                classification=cell["classification"],
            )
        )
    lines.extend(
        [
            "",
            "## Binary-risk feasibility",
            "",
            "For the exact lower-tail test of `H0: p >= tau`, the smallest possible p-value with zero adverse events is `p_min=(1-tau)^n`. For `0<tau<1`, the minimum count for cutoff `a` is `ceil(log(a)/log(1-tau))`, checked against floating-point boundary rounding. At `tau=0`, the strict alternative is empty and no finite n can reject; at `tau=1`, one zero-event observation has p-value zero.",
            "",
            "The frozen execution threshold is 0.03. At n=64, `p_min=0.97^64=0.1423609879`, so every n=64 candidate is blocked even at unadjusted alpha 0.05. The unadjusted best-case count is 99; conservative candidate-Bonferroni and flat-family requirements are larger and are reported row by row in the CSV. At n=256 the same best-case p-value is about 0.0004107371, so the overall execution gate is algebraically possible, though not necessarily powerful.",
            "",
            "The hidden-group scenario also applies the exact safety test to each group. Its minority-group actual counts are substantially below the nominal sample size; the CSV therefore evaluates feasibility using those realized counts rather than substituting overall n.",
            "",
            "## Paired-quality feasibility",
            "",
            "The public measurement contract fixes paired deltas to `[-0.25,0.25]`, width 0.5. V1 tests `H0: E[D] <= -margin` with `p=exp(-2*n*max(0, mean(D)+margin)^2/width^2)`. To cross cutoff `a`, the observed mean must exceed the noninferiority boundary by at least `width*sqrt(log(1/a)/(2*n))`. Each subgroup uses its actual n. The CSV reports this crossing gap at unadjusted alpha, candidate-Bonferroni, and flat-family-Bonferroni cutoffs. It does not label the gap as a power probability.",
            "",
            "## Candidate-IUT comparison",
            "",
            f"`{METHOD_ID}` is an explicit additive, post-developmental name for the already-reviewed and already-observed `B_IUT_HOEFFDING` construction. It is not fresh evaluation evidence. It preserves every v1 component p-value exactly, forms the maximum across every mandatory candidate component, and applies Holm across all frozen candidates. Missing evidence remains p=1/fail-closed and cannot shrink either family. Existing CI/LOCAL outputs are reused as the developmental comparison because they used the same evidence identities and exact construction; no redundant Monte Carlo run was performed.",
            "",
            "## Variance-sensitive quality design assessment",
            "",
            "Maurer and Pontil (2009), Theorem 4, gives for i.i.d. `[0,1]` observations and n>=2 the one-sided radius `sqrt(2*V_n*log(2/delta)/n) + 7*log(2/delta)/(3*(n-1))`, where `V_n` is the unbiased sample variance (equivalently their pairwise-difference definition). For paired quality, a future design would use the prespecified normalization `Z=(0.25-D)/0.5`; the null `E[D] <= -margin` is equivalent to `E[Z] >= (0.25+margin)/0.5`. Certification would require the empirical upper bound on `E[Z]` to be strictly below that threshold.",
            "",
            "This audit evaluates the theorem radius descriptively but does not implement a p-value or certification method. The decision to examine this direction is data-informed by the retained developmental counts, variances, and observed quality bottlenecks; it is not a prespecified confirmatory method choice. The additive `7 log(2/delta)/(3(n-1))` term is large at n=64 and at minority-group counts; lower empirical variance cannot remove it. At n=256 it may help some overall or majority-quality gates, but the retained minority-group counts remain the limiting case. A later implementation would need a separately versioned method, a monotone and numerically verified p-value inversion, endpoint tests, unchanged public support, and prespecification before new evidence is evaluated.",
            "",
            "## Limitations",
            "",
            "- CI and LOCAL are developmental, not sealed confirmation.",
            "- The detailed CSV covers two prespecified retained identities per cell; complete-profile certification counts come from the existing summaries.",
            "- Actual subgroup counts are random, so impossibility at a retained realized count is not a statement that every possible group allocation at the nominal n is impossible.",
            "- Zero observed certification is not zero theoretical power unless a best-case bound proves impossibility.",
            "- No FULL evidence was generated or inspected, and no drand round was selected.",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "COMPARISON_SPECIFICATION",
    "METHOD_ID",
    "FixedSampleMultiRiskWarrantV2IUTHolm",
    "binary_best_case_feasibility",
    "build_power_feasibility_rows",
    "build_v1_preservation_manifest",
    "hoeffding_best_case_p_value",
    "hoeffding_required_gap",
    "load_overlay_config",
    "maurer_pontil_theorem4_radius",
    "render_feasibility_report",
    "summarize_feasibility_cells",
    "validate_overlay_config",
]
