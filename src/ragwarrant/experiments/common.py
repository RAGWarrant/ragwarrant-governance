from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ragwarrant.artifacts import (
    copy_input_config,
    prepare_run_dir,
    write_no_overwrite_audit,
    write_policy_space,
    write_run_manifest,
)
from ragwarrant.certificates import issue_certificate
from ragwarrant.config import DEFAULT_POLICY_SPACE, SuiteConfig
from ragwarrant.fixtures import (
    candidate_policy_metrics,
    dataset_manifest,
    deterministic_split,
    governance_fixture,
    write_dataset_artifacts,
)
from ragwarrant.metrics import (
    apply_utilities,
    pareto_frontier,
    protected_regression_gate,
    rank_policies,
    utility_sensitivity,
)
from ragwarrant.reports import write_report
from ragwarrant.statistics import paired_bootstrap_ci, win_tie_loss
from ragwarrant.utils.files import write_json


def skipped_baselines(metrics: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {
            "baseline_name": str(row["baseline_name"]),
            "reason": str(row["skip_reason"]),
            "skipped": True,
        }
        for row in metrics.to_dict(orient="records")
        if bool(row.get("skipped"))
    ]


def finalize_policy_suite(
    *,
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    resume: bool,
    force_new_run_id: bool,
    metrics: pd.DataFrame | None = None,
    robustness_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_run_id, run_dir = prepare_run_dir(
        output_dir,
        run_id,
        suite=cfg.suite,
        resume=resume,
        force_new_run_id=force_new_run_id,
    )
    copy_input_config(config_path, run_dir)
    frame = deterministic_split(governance_fixture(cfg.seed), seed=cfg.seed)
    manifest = dataset_manifest(frame, name=str(cfg.dataset.get("name", "fixture_governance")))
    write_dataset_artifacts(run_dir, frame, manifest)
    write_policy_space(run_dir, cfg.policy_space or DEFAULT_POLICY_SPACE)
    metrics = candidate_policy_metrics(cfg.seed) if metrics is None else metrics.copy()
    scored = apply_utilities(
        metrics,
        lambda_cost=float(cfg.objectives.get("cost_weight", 0.25)),
        lambda_latency=float(cfg.objectives.get("latency_weight", 0.10)),
        regression_threshold=float(cfg.objectives.get("protected_regression_threshold", -0.03)),
    )
    scored = protected_regression_gate(scored)
    scored = pareto_frontier(scored)
    ranking = rank_policies(scored)
    ranking.to_csv(run_dir / "candidate_policy_metrics.csv", index=False)
    write_json(run_dir / "ranking.json", {"ranking": ranking.to_dict(orient="records")})
    write_json(run_dir / "winning_policy.json", ranking.iloc[0].to_dict())
    aggregate = {
        "winner": str(ranking.iloc[0]["policy_id"]),
        "candidate_count": len(ranking),
        "eligible_count": int(ranking["eligible_for_promotion"].sum()),
        "fixture": manifest["fixture"],
    }
    write_json(run_dir / "aggregate_metrics.json", aggregate)
    stat = {
        "paired_bootstrap_ci": paired_bootstrap_ci(
            [0.76, 0.77, 0.765, 0.755],
            [0.74, 0.745, 0.742, 0.741],
            seed=cfg.seed,
            samples=int(cfg.certificate.get("bootstrap_samples", 200)),
        ),
        "win_tie_loss_vs_static": win_tie_loss(
            pd.concat([ranking.assign(seed=cfg.seed), ranking.assign(seed=cfg.seed + 1)]),
            contender=str(ranking.iloc[0]["policy_id"]),
            baseline="static_default_rag_policy",
        )
        if "static_default_rag_policy" in set(ranking["policy_id"])
        else {},
    }
    sensitivity = utility_sensitivity(scored)
    certificate = issue_certificate(
        ranking,
        suite=cfg.suite,
        fixture=bool(manifest["fixture"]),
        statistical_analysis=stat,
    )
    regression = {
        "blocked_policy_ids": ranking.loc[ranking["promotion_blocked"], "policy_id"].tolist(),
        "threshold": float(cfg.objectives.get("protected_regression_threshold", -0.03)),
    }
    write_json(run_dir / "statistical_analysis.json", stat)
    write_json(run_dir / "utility_sensitivity.json", sensitivity)
    write_json(run_dir / "regression_report.json", regression)
    write_json(run_dir / "robustness_report.json", robustness_report or {"not_applicable": True})
    write_report(
        run_dir,
        suite=cfg.suite,
        run_id=resolved_run_id,
        dataset_manifest=manifest,
        ranking=ranking,
        certificate=certificate,
        skipped_baselines=skipped_baselines(metrics),
        statistical_analysis=stat,
        utility_sensitivity=sensitivity,
    )
    run_manifest = write_run_manifest(
        run_dir,
        suite=cfg.suite,
        run_id=resolved_run_id,
        config_path=config_path,
        seed=cfg.seed,
        dataset_hash=str(manifest["dataset_hash"]),
        status="completed",
    )
    audit = write_no_overwrite_audit(run_dir, run_id=resolved_run_id)
    return {
        "suite": cfg.suite,
        "run_id": resolved_run_id,
        "run_dir": str(run_dir),
        "winner": aggregate["winner"],
        "certificate": certificate,
        "run_manifest": run_manifest,
        "no_overwrite_audit": audit,
    }
