from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


BINARY_RISKS = (
    "safety_violation_probability",
    "execution_failure_probability",
    "insufficient_evidence_probability",
)

ENABLED_RISKS = (
    "overall_quality",
    "group_quality",
    *BINARY_RISKS,
)


def pairs(values: Mapping[str, float]) -> tuple[tuple[str, float], ...]:
    return tuple(sorted((str(key), float(value)) for key, value in values.items()))


def pair_value(values: tuple[tuple[str, float], ...], key: str) -> float:
    for candidate_key, value in values:
        if candidate_key == key:
            return value
    raise KeyError(key)


@dataclass(frozen=True)
class EvidenceRow:
    example_id: str
    group_id: str
    policy_id: str
    incumbent_quality: float
    candidate_quality: float
    quality_delta: float
    safety_violation: int
    execution_failure: int
    insufficient_evidence: int
    cost: float
    latency: float

    def as_dict(self) -> dict[str, object]:
        return {
            "example_id": self.example_id,
            "group_id": self.group_id,
            "policy_id": self.policy_id,
            "incumbent_quality": self.incumbent_quality,
            "candidate_quality": self.candidate_quality,
            "quality_delta": self.quality_delta,
            "safety_violation": self.safety_violation,
            "execution_failure": self.execution_failure,
            "insufficient_evidence": self.insufficient_evidence,
            "cost": self.cost,
            "latency": self.latency,
        }


@dataclass(frozen=True)
class ObservedEvidence:
    scenario_id: str
    phase: str
    trial_index: int
    sample_size: int
    rows: tuple[EvidenceRow, ...]
    evidence_hash: str

    def rows_for(self, policy_id: str) -> tuple[EvidenceRow, ...]:
        return tuple(row for row in self.rows if row.policy_id == policy_id)

    @property
    def policy_ids(self) -> tuple[str, ...]:
        return tuple(sorted({row.policy_id for row in self.rows}))


@dataclass(frozen=True)
class CandidateTruth:
    policy_id: str
    phase: str
    overall_quality_delta_vs_incumbent: float
    quality_delta_by_group: tuple[tuple[str, float], ...]
    safety_violation_probability: float
    safety_violation_probability_by_group: tuple[tuple[str, float], ...]
    execution_failure_probability: float
    execution_failure_probability_by_group: tuple[tuple[str, float], ...]
    insufficient_evidence_probability: float
    insufficient_evidence_probability_by_group: tuple[tuple[str, float], ...]
    mean_cost: float
    mean_cost_by_group: tuple[tuple[str, float], ...]
    mean_latency: float
    mean_latency_by_group: tuple[tuple[str, float], ...]
    truly_promotion_safe: bool
    overall_safe_but_subgroup_unsafe: bool
    failed_truth_conditions: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "phase": self.phase,
            "overall_quality_delta_vs_incumbent": self.overall_quality_delta_vs_incumbent,
            "quality_delta_by_group": dict(self.quality_delta_by_group),
            "safety_violation_probability": self.safety_violation_probability,
            "safety_violation_probability_by_group": dict(
                self.safety_violation_probability_by_group
            ),
            "execution_failure_probability": self.execution_failure_probability,
            "execution_failure_probability_by_group": dict(
                self.execution_failure_probability_by_group
            ),
            "insufficient_evidence_probability": self.insufficient_evidence_probability,
            "insufficient_evidence_probability_by_group": dict(
                self.insufficient_evidence_probability_by_group
            ),
            "mean_cost": self.mean_cost,
            "mean_cost_by_group": dict(self.mean_cost_by_group),
            "mean_latency": self.mean_latency,
            "mean_latency_by_group": dict(self.mean_latency_by_group),
            "truly_promotion_safe": self.truly_promotion_safe,
            "overall_safe_but_subgroup_unsafe": self.overall_safe_but_subgroup_unsafe,
            "failed_truth_conditions": list(self.failed_truth_conditions),
        }


@dataclass(frozen=True)
class ScenarioTruth:
    scenario_id: str
    base_scenario_id: str
    family: str
    sample_size: int
    group_prevalence: tuple[tuple[str, float], ...]
    enabled_risks: tuple[str, ...]
    enabled_group_risks: tuple[str, ...]
    development_candidates: tuple[CandidateTruth, ...]
    confirmatory_candidates: tuple[CandidateTruth, ...]
    protocol_hash: str

    def confirmatory_candidate(self, policy_id: str) -> CandidateTruth:
        for candidate in self.confirmatory_candidates:
            if candidate.policy_id == policy_id:
                return candidate
        raise KeyError(policy_id)

    @property
    def safe_policy_ids(self) -> tuple[str, ...]:
        return tuple(
            candidate.policy_id
            for candidate in self.confirmatory_candidates
            if candidate.truly_promotion_safe
        )


@dataclass(frozen=True)
class SimulatedTrial:
    truth: ScenarioTruth
    development_evidence: ObservedEvidence
    confirmatory_evidence: ObservedEvidence
    trial_identity: str
    seed_fingerprint: str


@dataclass(frozen=True)
class PolicyConfig:
    quality_noninferiority_margin: float
    group_quality_noninferiority_margin: float
    max_safety_violation_probability: float
    max_execution_failure_probability: float
    max_insufficient_evidence_probability: float
    cost_weight: float
    latency_weight: float
    confidence_level: float
    bootstrap_resamples: int
    enabled_risks: tuple[str, ...]
    enabled_group_risks: tuple[str, ...]
    group_ids: tuple[str, ...]

    def binary_threshold(self, risk: str) -> float:
        thresholds = {
            "safety_violation_probability": self.max_safety_violation_probability,
            "execution_failure_probability": self.max_execution_failure_probability,
            "insufficient_evidence_probability": self.max_insufficient_evidence_probability,
        }
        try:
            return thresholds[risk]
        except KeyError as exc:
            raise ValueError(f"unknown binary risk: {risk}") from exc


@dataclass(frozen=True)
class MethodDecision:
    method_id: str
    selected_policy_id: str | None
    certified_policy_ids: tuple[str, ...]
    decision: str
    decision_reason: str
    deployable: bool
    uses_population_truth: bool
    benchmark_control_only: bool = False
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def public_research_metadata(self) -> dict[str, bool]:
        """Return public research-role flags without implying production approval.

        ``deployable`` remains an internal compatibility flag for the original
        method contract. Public artifacts use the explicit fields below.
        """

        truth_isolated = not self.uses_population_truth
        return {
            "observed_evidence_only": self.deployable and truth_isolated,
            "truth_isolated": truth_isolated,
            "benchmark_control_only": self.benchmark_control_only,
            "research_only": True,
            "production_integrated": False,
        }


@dataclass(frozen=True)
class MethodCapability:
    method_id: str
    supported: bool
    deployable: bool
    uses_population_truth: bool
    benchmark_control_only: bool
    status: str
    explanation: str

    def as_dict(self) -> dict[str, object]:
        truth_isolated = self.supported and not self.uses_population_truth
        return {
            "method_id": self.method_id,
            "supported": self.supported,
            "observed_evidence_only": self.deployable and truth_isolated,
            "truth_isolated": truth_isolated,
            "benchmark_control_only": self.benchmark_control_only,
            "research_only": True,
            "production_integrated": False,
            "status": self.status,
            "explanation": self.explanation,
        }


def public_research_artifact(
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    """Translate a legacy internal warrant mapping at the public output boundary."""

    output = dict(artifact)
    deployable = bool(output.pop("deployable", False))
    uses_population_truth = bool(output.pop("uses_population_truth", False))
    truth_isolated = not uses_population_truth
    output.update(
        {
            "observed_evidence_only": deployable and truth_isolated,
            "truth_isolated": truth_isolated,
            "benchmark_control_only": bool(
                output.get("benchmark_control_only", False)
            ),
            "research_only": True,
            "production_integrated": False,
        }
    )
    return output
