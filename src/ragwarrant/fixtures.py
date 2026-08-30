from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ragwarrant.utils.files import write_json
from ragwarrant.utils.hashing import stable_hash


def governance_fixture(seed: int = 12345, rows: int = 240) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = np.arange(rows)
    protected = idx % 7 == 0
    difficulty = rng.beta(2.0, 2.5, rows)
    return pd.DataFrame(
        {
            "example_id": [f"gov-{seed}-{i}" for i in idx],
            "query": [f"Question {i}" for i in idx],
            "reference": [f"Reference answer {i}" for i in idx],
            "difficulty": difficulty,
            "retrieval_confidence": np.clip(1.0 - difficulty + rng.normal(0, 0.05, rows), 0, 1),
            "protected_group": protected,
            "split_key": idx,
        }
    )


def deterministic_split(
    frame: pd.DataFrame,
    *,
    seed: int,
    train: float = 0.6,
    validation: float = 0.2,
) -> pd.DataFrame:
    shuffled = frame.copy()
    order = np.random.default_rng(seed).permutation(len(frame))
    split = np.full(len(frame), "test", dtype=object)
    train_end = int(len(frame) * train)
    validation_end = train_end + int(len(frame) * validation)
    split[order[:train_end]] = "train"
    split[order[train_end:validation_end]] = "validation"
    shuffled["split"] = split
    return shuffled.sort_values("example_id").reset_index(drop=True)


def dataset_manifest(frame: pd.DataFrame, *, name: str, fixture: bool = True) -> dict[str, Any]:
    digest = stable_hash(frame.to_json(orient="records"), 16)
    return {
        "name": name,
        "row_count": len(frame),
        "fixture": fixture,
        "dataset_hash": digest,
        "license": "fixture-internal",
        "publication_caveat": "Fixture data is not benchmark evidence.",
    }


def write_dataset_artifacts(run_dir: Path, frame: pd.DataFrame, manifest: dict[str, Any]) -> None:
    write_json(run_dir / "dataset_manifest.json", manifest)
    split_counts = frame["split"].value_counts().sort_index().to_dict() if "split" in frame else {}
    write_json(
        run_dir / "split_manifest.json",
        {
            "split_counts": split_counts,
            "split_assignment_stored": True,
            "separation_rule": [
                "train",
                "validation",
                "test",
                "protected regression subset",
                "calibration/null-control subset",
            ],
        },
    )


def candidate_policy_metrics(seed: int = 12345) -> pd.DataFrame:
    rows = [
        {
            "policy_id": "static_default_rag_policy",
            "baseline_name": "static_default_rag_policy",
            "raw_quality": 0.710,
            "cost": 0.20,
            "latency_p95": 0.20,
            "protected_subset_score": 0.700,
            "regression_delta": 0.000,
            "skipped": False,
            "skip_reason": "",
        },
        {
            "policy_id": "quality_only_search",
            "baseline_name": "uniform_random_search",
            "raw_quality": 0.785,
            "cost": 1.20,
            "latency_p95": 1.10,
            "protected_subset_score": 0.610,
            "regression_delta": -0.090,
            "skipped": False,
            "skip_reason": "",
        },
        {
            "policy_id": "best_single_policy_on_validation",
            "baseline_name": "best_single_policy_on_validation",
            "raw_quality": 0.760,
            "cost": 0.55,
            "latency_p95": 0.45,
            "protected_subset_score": 0.705,
            "regression_delta": 0.005,
            "skipped": False,
            "skip_reason": "",
        },
        {
            "policy_id": "greedy_regression_aware_search",
            "baseline_name": "greedy_regression_aware_search",
            "raw_quality": 0.752,
            "cost": 0.42,
            "latency_p95": 0.34,
            "protected_subset_score": 0.725,
            "regression_delta": 0.020,
            "skipped": False,
            "skip_reason": "",
        },
        {
            "policy_id": "ragwarrant_no_fork",
            "baseline_name": "ragwarrant_no_fork",
            "raw_quality": 0.765,
            "cost": 0.34,
            "latency_p95": 0.28,
            "protected_subset_score": 0.735,
            "regression_delta": 0.030,
            "skipped": False,
            "skip_reason": "",
        },
        {
            "policy_id": "ragwarrant_adaptive_compute_optional",
            "baseline_name": "ragwarrant_adaptive_compute_optional",
            "raw_quality": 0.772,
            "cost": 0.78,
            "latency_p95": 0.74,
            "protected_subset_score": 0.720,
            "regression_delta": 0.015,
            "skipped": False,
            "skip_reason": "",
        },
        {
            "policy_id": "ragwarrant_full_optional",
            "baseline_name": "ragwarrant_full_optional",
            "raw_quality": 0.778,
            "cost": 1.35,
            "latency_p95": 1.25,
            "protected_subset_score": 0.718,
            "regression_delta": 0.018,
            "skipped": False,
            "skip_reason": "",
        },
        {
            "policy_id": "optuna_tpe_optional",
            "baseline_name": "optuna_tpe_optional",
            "raw_quality": 0.0,
            "cost": 0.0,
            "latency_p95": 0.0,
            "protected_subset_score": 0.0,
            "regression_delta": 0.0,
            "skipped": True,
            "skip_reason": "optional dependency or implementation not required for fixture smoke",
        },
    ]
    frame = pd.DataFrame(rows)
    frame["seed"] = seed
    frame["latency_p50"] = frame["latency_p95"] * 0.55
    frame["latency_p99"] = frame["latency_p95"] * 1.15
    return frame
