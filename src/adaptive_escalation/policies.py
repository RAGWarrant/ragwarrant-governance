# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EscalationDecision:
    tier: int
    reason: str
    expected_roi: float
    estimated_cost: float


def decide_escalation(
    *,
    uncertainty: float,
    retrieval_conflict: float,
    hallucination_risk: float,
    budget_pressure: float,
    claim_risk: float = 0.0,
) -> EscalationDecision:
    risk = max(uncertainty, retrieval_conflict, hallucination_risk, claim_risk)
    expected_roi = 0.55 * risk + 0.25 * retrieval_conflict + 0.20 * claim_risk - 0.45 * budget_pressure
    if budget_pressure > 0.85 and expected_roi < 0.45:
        return EscalationDecision(1, "budget_guarded_no_fork", expected_roi, 0.25)
    if retrieval_conflict > 0.82 and hallucination_risk > 0.65 and expected_roi > 0.50:
        return EscalationDecision(3, "rare_high_conflict_full_fork_merge", expected_roi, 1.25)
    if risk > 0.68 and expected_roi > 0.25:
        return EscalationDecision(2, "hard_subset_adaptive_compute", expected_roi, 0.70)
    return EscalationDecision(1, "no_fork_default", expected_roi, 0.25)

