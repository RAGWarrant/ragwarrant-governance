from __future__ import annotations

import math
from collections.abc import Iterable
from statistics import NormalDist

import numpy as np

from .simulator import sha256_json, stable_seed
from .types import (
    BINARY_RISKS,
    CandidateTruth,
    MethodCapability,
    MethodDecision,
    ObservedEvidence,
    PolicyConfig,
    ScenarioTruth,
)


RISK_EVIDENCE_FIELDS = {
    "safety_violation_probability": "safety_violation",
    "execution_failure_probability": "execution_failure",
    "insufficient_evidence_probability": "insufficient_evidence",
}


def _validate_evidence(evidence: ObservedEvidence, policy: PolicyConfig) -> None:
    if evidence.phase != "confirmatory":
        raise ValueError("deployable methods require confirmatory evidence")
    if evidence.sample_size <= 0 or not evidence.rows:
        raise ValueError("evidence must contain rows")
    expected_examples = {f"confirmatory-{index:06d}" for index in range(evidence.sample_size)}
    row_keys = {(row.policy_id, row.example_id) for row in evidence.rows}
    if len(row_keys) != len(evidence.rows):
        raise ValueError("evidence contains duplicate policy/example rows")
    for policy_id in evidence.policy_ids:
        rows = evidence.rows_for(policy_id)
        if len(rows) != evidence.sample_size:
            raise ValueError(f"policy {policy_id} must have exactly sample_size rows")
        if {row.example_id for row in rows} != expected_examples:
            raise ValueError(f"policy {policy_id} evidence example IDs are malformed")
    for row in evidence.rows:
        numeric = (
            row.incumbent_quality,
            row.candidate_quality,
            row.quality_delta,
            row.cost,
            row.latency,
        )
        if any(not math.isfinite(value) for value in numeric):
            raise ValueError("evidence contains nonfinite continuous values")
        if row.safety_violation not in {0, 1} or row.execution_failure not in {0, 1}:
            raise ValueError("evidence contains malformed binary risks")
        if row.insufficient_evidence not in {0, 1}:
            raise ValueError("evidence contains malformed insufficient-evidence values")
        if row.group_id not in policy.group_ids:
            raise ValueError(f"evidence contains unknown group {row.group_id}")
        if row.cost <= 0.0 or row.latency <= 0.0:
            raise ValueError("cost and latency evidence must be positive")
        if not 0.0 <= row.incumbent_quality <= 1.0 or not 0.0 <= row.candidate_quality <= 1.0:
            raise ValueError("quality evidence must be between zero and one")
        if not math.isclose(
            row.candidate_quality - row.incumbent_quality,
            row.quality_delta,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("candidate quality and paired quality delta are inconsistent")
    pairing: dict[str, tuple[str, float]] = {}
    for row in evidence.rows:
        current = (row.group_id, row.incumbent_quality)
        previous = pairing.setdefault(row.example_id, current)
        if previous != current:
            raise ValueError("candidates do not share paired group/incumbent evidence")
    calculated_hash = sha256_json([row.as_dict() for row in evidence.rows])
    if calculated_hash != evidence.evidence_hash:
        raise ValueError("evidence hash does not match canonical rows")


def _mean(values: Iterable[float]) -> float:
    collected = tuple(float(value) for value in values)
    if not collected:
        raise ValueError("cannot calculate a mean from empty evidence")
    value = float(np.mean(np.asarray(collected, dtype=float)))
    if not math.isfinite(value):
        raise ValueError("nonfinite evidence mean")
    return value


def one_sided_wilson_upper(event_count: int, sample_count: int, confidence: float) -> float:
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    if event_count < 0 or event_count > sample_count:
        raise ValueError("event_count must be between zero and sample_count")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between zero and one")
    proportion = event_count / sample_count
    z = NormalDist().inv_cdf(confidence)
    denominator = 1.0 + z * z / sample_count
    center = proportion + z * z / (2.0 * sample_count)
    radius = z * math.sqrt(
        proportion * (1.0 - proportion) / sample_count
        + z * z / (4.0 * sample_count * sample_count)
    )
    return min(1.0, (center + radius) / denominator)


def paired_bootstrap_lower_bound(
    deltas: Iterable[float], confidence: float, resamples: int, seed: int
) -> float:
    values = np.asarray(tuple(float(value) for value in deltas), dtype=float)
    if values.size == 0:
        raise ValueError("paired bootstrap requires non-empty deltas")
    if not np.isfinite(values).all():
        raise ValueError("paired bootstrap deltas must be finite")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between zero and one")
    if resamples <= 0:
        raise ValueError("resamples must be positive")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, values.size, size=(resamples, values.size))
    means = values[indices].mean(axis=1)
    return float(np.quantile(means, 1.0 - confidence))


def _objective(cost: float, latency: float, policy: PolicyConfig) -> float:
    return policy.cost_weight * cost + policy.latency_weight * latency


def _observed_summary(evidence: ObservedEvidence, policy_id: str) -> dict[str, object]:
    rows = evidence.rows_for(policy_id)
    summary: dict[str, object] = {
        "overall_quality_delta": _mean(row.quality_delta for row in rows),
        "mean_cost": _mean(row.cost for row in rows),
        "mean_latency": _mean(row.latency for row in rows),
        "group_quality_delta": {},
        "binary_risk": {},
        "group_binary_risk": {},
    }
    for group_id in sorted({row.group_id for row in rows}):
        group_rows = tuple(row for row in rows if row.group_id == group_id)
        summary["group_quality_delta"][group_id] = _mean(  # type: ignore[index]
            row.quality_delta for row in group_rows
        )
    for risk, field in RISK_EVIDENCE_FIELDS.items():
        summary["binary_risk"][risk] = _mean(  # type: ignore[index]
            float(getattr(row, field)) for row in rows
        )
        summary["group_binary_risk"][risk] = {  # type: ignore[index]
            group_id: _mean(
                float(getattr(row, field)) for row in rows if row.group_id == group_id
            )
            for group_id in sorted({row.group_id for row in rows})
        }
    return summary


def _point_eligible(summary: dict[str, object], policy: PolicyConfig) -> tuple[bool, list[str]]:
    failed: list[str] = []
    if "overall_quality" in policy.enabled_risks:
        if float(summary["overall_quality_delta"]) < -policy.quality_noninferiority_margin:
            failed.append("overall_quality")
    if "group_quality" in policy.enabled_risks:
        group_values = summary["group_quality_delta"]
        for group_id in policy.group_ids:
            if group_id not in group_values:  # type: ignore[operator]
                failed.append(f"group_quality:{group_id}:missing")
            elif float(group_values[group_id]) < -policy.group_quality_noninferiority_margin:  # type: ignore[index]
                failed.append(f"group_quality:{group_id}")
    for risk in BINARY_RISKS:
        if risk not in policy.enabled_risks:
            continue
        threshold = policy.binary_threshold(risk)
        if float(summary["binary_risk"][risk]) > threshold:  # type: ignore[index]
            failed.append(risk)
        if risk in policy.enabled_group_risks:
            group_values = summary["group_binary_risk"][risk]  # type: ignore[index]
            for group_id in policy.group_ids:
                if group_id not in group_values:
                    failed.append(f"{risk}:{group_id}:missing")
                elif float(group_values[group_id]) > threshold:
                    failed.append(f"{risk}:{group_id}")
    return not failed, failed


class AlwaysBlock:
    method_id = "always_block"

    def evaluate(
        self, evidence: ObservedEvidence, policy: PolicyConfig, method_seed: int = 0
    ) -> MethodDecision:
        del method_seed
        _validate_evidence(evidence, policy)
        return MethodDecision(
            method_id=self.method_id,
            selected_policy_id=None,
            certified_policy_ids=(),
            decision="BLOCK",
            decision_reason="trivial control always blocks",
            deployable=True,
            uses_population_truth=False,
            benchmark_control_only=True,
            diagnostics={"evidence_hash": evidence.evidence_hash},
        )


class NaivePointEstimate:
    method_id = "naive_point_estimate"

    def evaluate(
        self, evidence: ObservedEvidence, policy: PolicyConfig, method_seed: int = 0
    ) -> MethodDecision:
        del method_seed
        _validate_evidence(evidence, policy)
        summaries: dict[str, dict[str, object]] = {}
        eligible: list[str] = []
        failed: dict[str, list[str]] = {}
        for policy_id in evidence.policy_ids:
            summary = _observed_summary(evidence, policy_id)
            summaries[policy_id] = summary
            passed, reasons = _point_eligible(summary, policy)
            failed[policy_id] = reasons
            if passed:
                eligible.append(policy_id)
        selected = min(
            eligible,
            key=lambda item: (
                _objective(
                    float(summaries[item]["mean_cost"]),
                    float(summaries[item]["mean_latency"]),
                    policy,
                ),
                item,
            ),
            default=None,
        )
        return MethodDecision(
            method_id=self.method_id,
            selected_policy_id=selected,
            certified_policy_ids=tuple(sorted(eligible)),
            decision="PROMOTE" if selected is not None else "BLOCK",
            decision_reason=(
                "selected best observed eligible objective"
                if selected is not None
                else "no candidate passed observed point-estimate gates"
            ),
            deployable=True,
            uses_population_truth=False,
            diagnostics={
                "evidence_hash": evidence.evidence_hash,
                "failed_conditions": failed,
                "observed_summaries": summaries,
            },
        )


class CorrectedPairedBootstrapGate:
    method_id = "corrected_paired_bootstrap_gate"

    def evaluate(
        self, evidence: ObservedEvidence, policy: PolicyConfig, method_seed: int = 0
    ) -> MethodDecision:
        _validate_evidence(evidence, policy)
        diagnostics: dict[str, dict[str, object]] = {}
        eligible: list[str] = []
        for policy_id in evidence.policy_ids:
            rows = evidence.rows_for(policy_id)
            failed: list[str] = []
            candidate_diagnostics: dict[str, object] = {}
            if "overall_quality" in policy.enabled_risks:
                lower = paired_bootstrap_lower_bound(
                    (row.quality_delta for row in rows),
                    policy.confidence_level,
                    policy.bootstrap_resamples,
                    stable_seed(method_seed, policy_id, "overall_quality"),
                )
                candidate_diagnostics["overall_quality_lower_bound"] = lower
                if lower < -policy.quality_noninferiority_margin:
                    failed.append("overall_quality")
            if "group_quality" in policy.enabled_risks:
                group_bounds: dict[str, float | None] = {}
                for group_id in policy.group_ids:
                    group_rows = tuple(row for row in rows if row.group_id == group_id)
                    if not group_rows:
                        group_bounds[group_id] = None
                        failed.append(f"group_quality:{group_id}:missing")
                        continue
                    lower = paired_bootstrap_lower_bound(
                        (row.quality_delta for row in group_rows),
                        policy.confidence_level,
                        policy.bootstrap_resamples,
                        stable_seed(method_seed, policy_id, "group_quality", group_id),
                    )
                    group_bounds[group_id] = lower
                    if lower < -policy.group_quality_noninferiority_margin:
                        failed.append(f"group_quality:{group_id}")
                candidate_diagnostics["group_quality_lower_bounds"] = group_bounds
            binary_bounds: dict[str, float] = {}
            group_binary_bounds: dict[str, dict[str, float | None]] = {}
            for risk, field in RISK_EVIDENCE_FIELDS.items():
                if risk not in policy.enabled_risks:
                    continue
                threshold = policy.binary_threshold(risk)
                upper = one_sided_wilson_upper(
                    sum(int(getattr(row, field)) for row in rows),
                    len(rows),
                    policy.confidence_level,
                )
                binary_bounds[risk] = upper
                if upper > threshold:
                    failed.append(risk)
                if risk in policy.enabled_group_risks:
                    group_binary_bounds[risk] = {}
                    for group_id in policy.group_ids:
                        group_rows = tuple(row for row in rows if row.group_id == group_id)
                        if not group_rows:
                            group_binary_bounds[risk][group_id] = None
                            failed.append(f"{risk}:{group_id}:missing")
                            continue
                        group_upper = one_sided_wilson_upper(
                            sum(int(getattr(row, field)) for row in group_rows),
                            len(group_rows),
                            policy.confidence_level,
                        )
                        group_binary_bounds[risk][group_id] = group_upper
                        if group_upper > threshold:
                            failed.append(f"{risk}:{group_id}")
            candidate_diagnostics["binary_risk_upper_bounds"] = binary_bounds
            candidate_diagnostics["group_binary_risk_upper_bounds"] = group_binary_bounds
            candidate_diagnostics["failed_conditions"] = failed
            candidate_diagnostics["mean_cost"] = _mean(row.cost for row in rows)
            candidate_diagnostics["mean_latency"] = _mean(row.latency for row in rows)
            diagnostics[policy_id] = candidate_diagnostics
            if not failed:
                eligible.append(policy_id)

        selected = min(
            eligible,
            key=lambda item: (
                _objective(
                    float(diagnostics[item]["mean_cost"]),
                    float(diagnostics[item]["mean_latency"]),
                    policy,
                ),
                item,
            ),
            default=None,
        )
        return MethodDecision(
            method_id=self.method_id,
            selected_policy_id=selected,
            certified_policy_ids=tuple(sorted(eligible)),
            decision="PROMOTE" if selected is not None else "BLOCK",
            decision_reason=(
                "selected best bounded-eligible objective"
                if selected is not None
                else "no candidate passed one-sided bounded gates"
            ),
            deployable=True,
            uses_population_truth=False,
            diagnostics={"evidence_hash": evidence.evidence_hash, "candidates": diagnostics},
        )


def oracle_safe_objective(truth: ScenarioTruth, policy: PolicyConfig) -> MethodDecision:
    safe = tuple(
        candidate for candidate in truth.confirmatory_candidates if candidate.truly_promotion_safe
    )
    selected: CandidateTruth | None = min(
        safe,
        key=lambda candidate: (
            _objective(candidate.mean_cost, candidate.mean_latency, policy),
            candidate.policy_id,
        ),
        default=None,
    )
    return MethodDecision(
        method_id="oracle_safe_objective",
        selected_policy_id=selected.policy_id if selected else None,
        certified_policy_ids=tuple(sorted(candidate.policy_id for candidate in safe)),
        decision="PROMOTE" if selected else "BLOCK",
        decision_reason=(
            "benchmark oracle selected the best truly safe objective"
            if selected
            else "benchmark oracle found no truly safe candidate"
        ),
        deployable=False,
        uses_population_truth=True,
        benchmark_control_only=True,
        diagnostics={"truth_protocol_hash": truth.protocol_hash},
    )


def method_registry() -> dict[str, object]:
    return {
        "always_block": AlwaysBlock(),
        "naive_point_estimate": NaivePointEstimate(),
        "corrected_paired_bootstrap_gate": CorrectedPairedBootstrapGate(),
    }


def method_capabilities() -> tuple[MethodCapability, ...]:
    return (
        MethodCapability(
            method_id="always_block",
            supported=True,
            deployable=True,
            uses_population_truth=False,
            benchmark_control_only=True,
            status="supported_trivial_control",
            explanation="Always blocks and certifies no candidates.",
        ),
        MethodCapability(
            method_id="oracle_safe_objective",
            supported=True,
            deployable=False,
            uses_population_truth=True,
            benchmark_control_only=True,
            status="supported_benchmark_control_only",
            explanation="Uses confirmatory population truth and is excluded from deployable summaries.",
        ),
        MethodCapability(
            method_id="naive_point_estimate",
            supported=True,
            deployable=True,
            uses_population_truth=False,
            benchmark_control_only=False,
            status="supported",
            explanation="Applies configured gates to observed point estimates.",
        ),
        MethodCapability(
            method_id="corrected_paired_bootstrap_gate",
            supported=True,
            deployable=True,
            uses_population_truth=False,
            benchmark_control_only=False,
            status="supported",
            explanation=(
                "Uses genuine replacement bootstrap lower bounds for paired quality and "
                "one-sided Wilson upper bounds for binary risks; no family-wise claim."
            ),
        ),
        MethodCapability(
            method_id="current_ragwarrant_adapter",
            supported=False,
            deployable=False,
            uses_population_truth=False,
            benchmark_control_only=False,
            status="unsupported_in_benchmark_v1",
            explanation=(
                "Current selectors consume aggregate evidence and cannot represent the complete "
                "row-level multi-risk and subgroup contract without an invasive production change."
            ),
        ),
    )
