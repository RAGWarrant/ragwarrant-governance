from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def paired_bootstrap_ci(
    a: list[float] | np.ndarray,
    b: list[float] | np.ndarray,
    *,
    seed: int = 12345,
    samples: int = 500,
    alpha: float = 0.05,
) -> dict[str, float]:
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if len(arr_a) != len(arr_b):
        raise ValueError("paired bootstrap inputs must have equal length")
    if len(arr_a) == 0:
        return {"mean_delta": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(samples):
        idx = rng.integers(0, len(arr_a), len(arr_a))
        deltas.append(float((arr_a[idx] - arr_b[idx]).mean()))
    return {
        "mean_delta": float((arr_a - arr_b).mean()),
        "ci_low": float(np.quantile(deltas, alpha / 2)),
        "ci_high": float(np.quantile(deltas, 1 - alpha / 2)),
    }


def win_tie_loss(frame: pd.DataFrame, *, contender: str, baseline: str) -> dict[str, Any]:
    a = frame[frame["policy_id"] == contender].set_index("seed")["cost_adjusted_utility"]
    b = frame[frame["policy_id"] == baseline].set_index("seed")["cost_adjusted_utility"]
    joined = pd.concat([a, b], axis=1, keys=["contender", "baseline"]).dropna()
    delta = joined["contender"] - joined["baseline"]
    return {
        "contender": contender,
        "baseline": baseline,
        "wins": int(delta.gt(1e-12).sum()),
        "ties": int(delta.abs().le(1e-12).sum()),
        "losses": int(delta.lt(-1e-12).sum()),
        "n": len(delta),
    }
