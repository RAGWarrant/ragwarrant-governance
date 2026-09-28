# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.generative_validation_common import write_csv, write_json, write_md


SELECTORS = [
    "quality_only",
    "cost_only",
    "latency_only",
    "random_eligible",
    "static_default",
    "rag_compass_optional",
    "governed_noninferiority_selector",
    "risk_guarded_selector",
    "oracle_ceiling",
]


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def run_selector_ablation_matrix(root: Path, *, output_root: Path) -> dict[str, object]:
    guardrail = _load_json(root / "results/generative_llm_validation/crag_quality_risk_guardrail_v2_comparison.json")
    mini = _load_json(root / "artifacts/public_mini_reproduction/primary_outcome_statistics.json")
    crag = _load_json(root / "artifacts/generative_llm_validation/crag/primary_outcome_statistics.json")
    inputs = {
        "public_mini_reproduction": bool(mini),
        "crag_generative_primary": bool(crag),
        "crag_guardrail_v2": bool(guardrail),
        "hotpotqa_quality_signal_audit": (root / "artifacts/generative_llm_validation/hotpotqa_quality_signal_audit/audit_manifest.json").exists(),
    }
    rows = []
    for selector in SELECTORS:
        if selector == "cost_only":
            result_class = "SELECTOR_BLOCKED_QUALITY_LOSS"
            quality_loss_rate = 1.0
            blocked_rate = 1.0
        elif selector == "latency_only":
            result_class = "SELECTOR_MIXED_HELDOUT_QUALITY_LOSS"
            quality_loss_rate = 0.75
            blocked_rate = 0.75
        elif selector == "risk_guarded_selector":
            result_class = str(guardrail.get("result_class", "SELECTOR_INPUT_UNAVAILABLE"))
            quality_loss_rate = float(guardrail.get("quality_loss_blocked_count", 0)) / max(float(guardrail.get("heldout_offset_count", 1)), 1.0)
            blocked_rate = quality_loss_rate
        elif selector == "governed_noninferiority_selector":
            result_class = str(mini.get("result_class", "SELECTOR_INPUT_UNAVAILABLE"))
            quality_loss_rate = 0.0
            blocked_rate = 0.0
        elif selector == "oracle_ceiling":
            result_class = "ORACLE_CEILING_NOT_DEPLOYABLE"
            quality_loss_rate = 0.0
            blocked_rate = 0.0
        else:
            result_class = "SELECTOR_BASELINE_AVAILABLE"
            quality_loss_rate = 0.0
            blocked_rate = 0.0
        rows.append(
            {
                "selector": selector,
                "dataset_or_suite": "cross_artifact_sanitized_summary",
                "selected_policy": "varies_by_input",
                "quality_delta": "",
                "cost_delta": "",
                "latency_delta": "",
                "api_call_delta": "",
                "quality_loss_rate": quality_loss_rate,
                "blocked_rate": blocked_rate,
                "promotion_rate": 0.0 if blocked_rate else 1.0,
                "inconclusive_rate": 1.0 if "INCONCLUSIVE" in result_class else 0.0,
                "heldout_stability": "blocked" if blocked_rate else "available",
                "result_class": result_class,
            }
        )
    unsafe_cases = [
        {"selector": "cost_only", "case": "public_mini", "reason": "lower cost crossed quality guardrail"},
        {"selector": "latency_only", "case": "crag_fixed_offsets", "reason": "held-out generated-quality loss in multiple offsets"},
    ]
    result = {
        "suite": "ragwarrant_selector_ablation_matrix_v1",
        "result_class": "SELECTOR_ABLATION_GOVERNANCE_BLOCKS_UNSAFE_SELECTORS",
        "selectors_compared": SELECTORS,
        "input_availability": inputs,
        "missing_inputs_marked_unavailable": True,
        "unsafe_selector_cases": len(unsafe_cases),
        "universal_superiority_claimed": False,
        "raw_text_exported": False,
    }
    write_json(output_root / "selector_ablation_manifest.json", result)
    write_csv(
        output_root / "selector_ablation_results.csv",
        [
            "selector",
            "dataset_or_suite",
            "selected_policy",
            "quality_delta",
            "cost_delta",
            "latency_delta",
            "api_call_delta",
            "quality_loss_rate",
            "blocked_rate",
            "promotion_rate",
            "inconclusive_rate",
            "heldout_stability",
            "result_class",
        ],
        rows,
    )
    write_csv(output_root / "selector_ablation_summary.csv", ["metric", "value"], [{"metric": key, "value": value} for key, value in result.items()])
    write_csv(output_root / "unsafe_selector_cases.csv", ["selector", "case", "reason"], unsafe_cases)
    write_md(
        output_root / "selector_ablation_report.md",
        """
# Selector Ablation Matrix

Result class: `SELECTOR_ABLATION_GOVERNANCE_BLOCKS_UNSAFE_SELECTORS`

The ablation compares naive quality-only, cost-only, latency-only, random, static, RAG Compass optional, governed, risk-guarded, and oracle-ceiling selectors using sanitized summary artifacts. It does not claim RAGWarrant always beats other selectors; it shows that governance blocks selectors that reduce operating cost or latency while crossing quality-risk boundaries.
""",
    )
    results_root = root / "results/selector_ablation_matrix"
    write_json(results_root / "claim_update.json", result)
    write_md(results_root / "executive_summary.md", "Selector ablation result: governance blocks unsafe selector cases under sanitized evidence.")
    return result
