from __future__ import annotations

from typing import Any


def pareto_frontier(
    rows: list[dict[str, Any]],
    *,
    maximize: tuple[str, ...],
    minimize: tuple[str, ...],
) -> list[str]:
    def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
        at_least = True
        strictly = False
        for field in maximize:
            lv = float(left[field])
            rv = float(right[field])
            at_least = at_least and lv >= rv
            strictly = strictly or lv > rv
        for field in minimize:
            lv = float(left[field])
            rv = float(right[field])
            at_least = at_least and lv <= rv
            strictly = strictly or lv < rv
        return at_least and strictly

    frontier: list[str] = []
    for row in rows:
        if not any(dominates(other, row) for other in rows if other is not row):
            frontier.append(str(row["policy_id"]))
    return sorted(frontier)


def quality_only_winner(rows: list[dict[str, Any]]) -> str:
    return str(sorted(rows, key=lambda row: (-float(row["final_quality_score"]), str(row["policy_id"])))[0]["policy_id"])


def cost_minimizer_at_quality_floor(rows: list[dict[str, Any]], margin: float) -> str:
    best = max(float(row["final_quality_score"]) for row in rows)
    floor = best - margin
    eligible = [row for row in rows if float(row["final_quality_score"]) >= floor]
    return str(sorted(eligible, key=lambda row: (float(row["measured_cost_units"]), float(row["p95_latency_ms"]), str(row["policy_id"])))[0]["policy_id"])


def constrained_quality_winner(rows: list[dict[str, Any]], constraints: dict[str, float]) -> str:
    eligible = [
        row
        for row in rows
        if float(row["measured_cost_units"]) <= constraints["max_mean_cost_units"]
        and float(row["p95_latency_ms"]) <= constraints["max_p95_latency_ms"]
        and float(row["failure_rate"]) <= constraints["max_failure_rate"]
        and float(row["evidence_support_score"]) >= constraints["min_evidence_support_score"]
    ]
    if not eligible:
        return ""
    return str(
        sorted(
            eligible,
            key=lambda row: (
                -float(row["final_quality_score"]),
                float(row["measured_cost_units"]),
                float(row["p95_latency_ms"]),
                str(row["policy_id"]),
            ),
        )[0]["policy_id"]
    )
