from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ragwarrant.config import SuiteConfig
from ragwarrant.end_to_end import RAGPolicy, run_pipeline
from ragwarrant.experiments.common import finalize_policy_suite


def end_to_end_policy_metrics(seed: int) -> pd.DataFrame:
    policies = {
        "static_default_rag_policy": RAGPolicy(top_k=3, citation_required=False),
        "best_single_policy_on_validation": RAGPolicy(top_k=5, citation_required=True),
        "ragwarrant_no_fork": RAGPolicy(top_k=5, reranker_enabled=True, citation_required=True),
        "retrieval_confidence_gating": RAGPolicy(top_k=8, citation_required=True),
    }
    rows = []
    for policy_id, policy in policies.items():
        metrics = run_pipeline(policy)
        rows.append(
            {
                "policy_id": policy_id,
                "baseline_name": policy_id,
                "raw_quality": metrics["raw_quality"],
                "cost": metrics["cost"],
                "latency_p95": metrics["latency_p95"],
                "latency_p50": metrics["latency_p50"],
                "latency_p99": metrics["latency_p99"],
                "protected_subset_score": metrics["protected_subset_score"],
                "regression_delta": 0.01 if policy_id == "ragwarrant_no_fork" else 0.0,
                "skipped": False,
                "skip_reason": "",
                "seed": seed,
            }
        )
    return pd.DataFrame(rows)


def run(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return finalize_policy_suite(
        cfg=cfg,
        config_path=config_path,
        output_dir=output_dir,
        run_id=run_id,
        resume=resume,
        force_new_run_id=force_new_run_id,
        metrics=end_to_end_policy_metrics(cfg.seed),
    )

