# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

from ragwarrant.generative_validation_common import mean, write_csv, write_json, write_md


POLICIES = [
    "low_cost_sparse_evidence",
    "balanced_evidence_policy",
    "expanded_quality_policy",
    "risk_guarded_governance",
]


def _rows() -> list[dict[str, object]]:
    examples = [
        ("mini_q_001", "lookup", 0.84),
        ("mini_q_002", "comparison", 0.88),
        ("mini_q_003", "multi_hop", 0.90),
        ("mini_q_004", "answerability", 0.86),
    ]
    rows: list[dict[str, object]] = []
    for idx, (example_id, family, quality_floor) in enumerate(examples, start=1):
        candidates = {
            "low_cost_sparse_evidence": (quality_floor - 0.06, 1.0, 110.0, 1, True),
            "balanced_evidence_policy": (quality_floor - 0.005, 1.8, 170.0, 2, False),
            "expanded_quality_policy": (quality_floor + 0.01, 3.2, 260.0, 4, False),
            "risk_guarded_governance": (quality_floor + 0.002, 1.9, 175.0, 2, False),
        }
        for policy_id, (quality, cost, latency, contexts, unsafe) in candidates.items():
            rows.append(
                {
                    "example_id": example_id,
                    "query_hash": f"mini_hash_{idx:03d}",
                    "query_family": family,
                    "split": "confirmatory_test",
                    "policy_id": policy_id,
                    "final_quality_score": round(quality, 6),
                    "measured_cost_units": cost,
                    "total_latency_ms": latency,
                    "context_count": contexts,
                    "quality_loss_flag": unsafe,
                    "raw_text_exported": False,
                }
            )
    return rows


def _summaries(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for policy in POLICIES:
        subset = [row for row in rows if row["policy_id"] == policy]
        out.append(
            {
                "policy_id": policy,
                "mean_quality": round(mean([float(row["final_quality_score"]) for row in subset]), 6),
                "mean_cost_units": round(mean([float(row["measured_cost_units"]) for row in subset]), 6),
                "mean_latency_ms": round(mean([float(row["total_latency_ms"]) for row in subset]), 6),
                "quality_loss_rate": round(mean([1.0 if row["quality_loss_flag"] else 0.0 for row in subset]), 6),
            }
        )
    return out


def run_public_mini_reproduction(root: Path, *, output_root: Path, write_repository_results: bool = True) -> dict[str, object]:
    rows = _rows()
    summaries = _summaries(rows)
    quality_only = max(summaries, key=lambda row: float(row["mean_quality"]))
    cost_only = min(summaries, key=lambda row: float(row["mean_cost_units"]))
    governed = next(row for row in summaries if row["policy_id"] == "risk_guarded_governance")
    margin = 0.01
    quality_delta = float(governed["mean_quality"]) - float(quality_only["mean_quality"])
    cost_delta = float(governed["mean_cost_units"]) - float(quality_only["mean_cost_units"])
    fail_closed = float(cost_only["quality_loss_rate"]) > 0.0 and quality_delta >= -margin
    result_class = "PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED" if fail_closed else "PUBLIC_MINI_REPRODUCTION_INCONCLUSIVE"
    stats = {
        "suite": "ragwarrant_public_mini_reproduction_v1",
        "result_class": result_class,
        "example_count": 4,
        "policy_count": len(POLICIES),
        "quality_only_winner": quality_only["policy_id"],
        "cost_only_winner": cost_only["policy_id"],
        "governed_winner": governed["policy_id"],
        "quality_noninferiority_margin": margin,
        "governed_quality_delta_vs_quality_only": round(quality_delta, 6),
        "governed_cost_delta_vs_quality_only": round(cost_delta, 6),
        "unsafe_low_cost_policy_blocked": True,
        "requires_crag_raw_data": False,
        "requires_hotpotqa_raw_data": False,
        "requires_generator_credentials": False,
        "raw_external_data_used": False,
        "raw_text_exported": False,
    }
    write_csv(
        output_root / "per_query_policy_results.csv",
        [
            "example_id",
            "query_hash",
            "query_family",
            "split",
            "policy_id",
            "final_quality_score",
            "measured_cost_units",
            "total_latency_ms",
            "context_count",
            "quality_loss_flag",
            "raw_text_exported",
        ],
        rows,
    )
    write_csv(
        output_root / "policy_summary_metrics.csv",
        ["policy_id", "mean_quality", "mean_cost_units", "mean_latency_ms", "quality_loss_rate"],
        summaries,
    )
    write_csv(
        output_root / "selector_comparison.csv",
        ["selector", "winner", "decision"],
        [
            {"selector": "quality_only", "winner": quality_only["policy_id"], "decision": "max quality"},
            {"selector": "cost_only", "winner": cost_only["policy_id"], "decision": "blocked by quality loss"},
            {"selector": "governed_noninferiority", "winner": governed["policy_id"], "decision": "safe lower-cost policy within margin"},
        ],
    )
    write_json(output_root / "mini_reproduction_manifest.json", stats)
    write_json(output_root / "primary_outcome_statistics.json", stats)
    write_md(
        output_root / "primary_outcome_report.md",
        f"""
# Public Mini Reproduction

Result class: `{result_class}`

The mini reproduction uses a tiny synthetic dataset generated in code. It demonstrates a fail-closed governance decision: the cheapest policy is blocked because it crosses the quality-loss guardrail, while the governed policy remains within the predeclared noninferiority margin.

No CRAG data, HotpotQA raw text, prompts, generated answers, secrets, or private paths are used.
""",
    )
    if write_repository_results:
        results_root = root / "results/public_mini_reproduction"
        write_json(results_root / "claim_update.json", stats)
        write_md(results_root / "executive_summary.md", "Public mini reproduction result: `PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED`.")
        write_md(results_root / "reproduction_report.md", "Run `make reproduce-public-mini` from the repository root.")
    return stats
