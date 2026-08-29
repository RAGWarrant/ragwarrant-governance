from __future__ import annotations

from typing import Any

import pandas as pd


def weighted_utility(
    row: pd.Series | dict[str, Any],
    *,
    lambda_cost: float = 0.25,
    lambda_latency: float = 0.10,
) -> float:
    return float(row["raw_quality"] - lambda_cost * row["cost"] - lambda_latency * row["latency_p95"])


def apply_utilities(
    frame: pd.DataFrame,
    *,
    lambda_cost: float = 0.25,
    lambda_latency: float = 0.10,
    regression_threshold: float = -0.03,
) -> pd.DataFrame:
    out = frame.copy()
    out["overall_utility"] = out.apply(
        lambda row: weighted_utility(row, lambda_cost=lambda_cost, lambda_latency=lambda_latency),
        axis=1,
    )
    out["regression_flags"] = out["regression_delta"].lt(regression_threshold)
    out["eligible_for_promotion"] = ~out["regression_flags"] & ~out.get("skipped", False).astype(bool)
    out["cost_adjusted_utility"] = out["overall_utility"].where(
        out["eligible_for_promotion"], out["overall_utility"] - 10.0
    )
    return out


def rank_policies(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(
        ["eligible_for_promotion", "cost_adjusted_utility", "raw_quality", "policy_id"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)


def constrained_winner(frame: pd.DataFrame, *, max_cost: float, max_latency: float) -> str | None:
    eligible = frame[(frame["cost"] <= max_cost) & (frame["latency_p95"] <= max_latency)]
    if eligible.empty:
        return None
    return str(rank_policies(eligible).iloc[0]["policy_id"])


def protected_regression_gate(
    frame: pd.DataFrame, *, regression_threshold: float = -0.03
) -> pd.DataFrame:
    out = frame.copy()
    out["promotion_blocked"] = out["regression_delta"].lt(regression_threshold)
    return out


def pareto_frontier(
    frame: pd.DataFrame,
    *,
    maximize: tuple[str, ...] = ("raw_quality", "protected_subset_score"),
    minimize: tuple[str, ...] = ("cost", "latency_p95"),
) -> pd.DataFrame:
    rows = []
    for idx, row in frame.iterrows():
        dominated = False
        for other_idx, other in frame.iterrows():
            if idx == other_idx:
                continue
            at_least_equal = all(other[col] >= row[col] for col in maximize) and all(
                other[col] <= row[col] for col in minimize
            )
            strictly_better = any(other[col] > row[col] for col in maximize) or any(
                other[col] < row[col] for col in minimize
            )
            if at_least_equal and strictly_better:
                dominated = True
                break
        rows.append(not dominated)
    out = frame.copy()
    out["pareto_frontier"] = rows
    return out


def utility_sensitivity(frame: pd.DataFrame) -> dict[str, Any]:
    rows = []
    winners = []
    for lambda_cost in [0.0, 0.1, 0.25, 0.5, 1.0, 2.0]:
        for lambda_latency in [0.0, 0.1, 0.25, 0.5, 1.0]:
            scored = apply_utilities(
                frame,
                lambda_cost=lambda_cost,
                lambda_latency=lambda_latency,
            )
            ranked = rank_policies(scored)
            winner = str(ranked.iloc[0]["policy_id"])
            winners.append(winner)
            rows.append(
                {
                    "lambda_cost": lambda_cost,
                    "lambda_latency": lambda_latency,
                    "winner": winner,
                    "winner_utility": float(ranked.iloc[0]["cost_adjusted_utility"]),
                }
            )
    return {
        "grid": rows,
        "number_of_winner_changes": max(0, len(set(winners)) - 1),
        "robust_winners": sorted({winner for winner in winners if winners.count(winner) >= 3}),
    }

