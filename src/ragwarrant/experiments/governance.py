from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ragwarrant.config import SuiteConfig
from ragwarrant.experiments.common import finalize_policy_suite
from ragwarrant.metrics import apply_utilities, rank_policies, utility_sensitivity

ABLATION_STAGES = [
    "quality_only_search",
    "quality_plus_cost",
    "quality_plus_cost_plus_latency",
    "quality_cost_latency_plus_regression",
    "plus_refusal_gate",
    "plus_matched_cost_baseline_qualification",
    "plus_certificate_and_audit_requirements",
]


def governance_ablation_table(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    stage_params = {
        "quality_only_search": (0.0, 0.0, -1.0),
        "quality_plus_cost": (0.25, 0.0, -1.0),
        "quality_plus_cost_plus_latency": (0.25, 0.10, -1.0),
        "quality_cost_latency_plus_regression": (0.25, 0.10, -0.03),
        "plus_refusal_gate": (0.25, 0.10, -0.03),
        "plus_matched_cost_baseline_qualification": (0.25, 0.10, -0.03),
        "plus_certificate_and_audit_requirements": (0.25, 0.10, -0.03),
    }
    for stage in ABLATION_STAGES:
        cost, latency, threshold = stage_params[stage]
        scored = apply_utilities(
            metrics,
            lambda_cost=cost,
            lambda_latency=latency,
            regression_threshold=threshold,
        )
        ranked = rank_policies(scored)
        winner = ranked.iloc[0]
        rows.append(
            {
                "stage": stage,
                "winner": winner["policy_id"],
                "raw_quality": float(winner["raw_quality"]),
                "cost": float(winner["cost"]),
                "latency": float(winner["latency_p95"]),
                "protected_subset_score": float(winner["protected_subset_score"]),
                "cost_adjusted_utility": float(winner["cost_adjusted_utility"]),
                "regression_flags": bool(winner["regression_flags"]),
                "promotion_decision": "promote" if bool(winner["eligible_for_promotion"]) else "refuse",
                "certificate_class": "fixture_inconclusive",
                "reason": "stage recomputed on deterministic fixture candidate metrics",
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
    result = finalize_policy_suite(
        cfg=cfg,
        config_path=config_path,
        output_dir=output_dir,
        run_id=run_id,
        resume=resume,
        force_new_run_id=force_new_run_id,
    )
    run_dir = Path(result["run_dir"])
    metrics = pd.read_csv(run_dir / "candidate_policy_metrics.csv")
    ablation = governance_ablation_table(metrics)
    ablation.to_csv(run_dir / "governance_ablation.csv", index=False)
    (run_dir / "governance_ablation.json").write_text(
        ablation.to_json(orient="records", indent=2),
        encoding="utf-8",
    )
    sensitivity = utility_sensitivity(metrics)
    (run_dir / "utility_sensitivity.json").write_text(
        __import__("json").dumps(sensitivity, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result

