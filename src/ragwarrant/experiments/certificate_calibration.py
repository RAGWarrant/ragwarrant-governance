# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ragwarrant.config import SuiteConfig
from ragwarrant.experiments.common import finalize_policy_suite
from ragwarrant.utils.files import write_json


def calibration_metrics(seed: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "policy_id": "null_policy_a",
                "baseline_name": "null_policy_a",
                "raw_quality": 0.700,
                "cost": 0.20,
                "latency_p95": 0.20,
                "protected_subset_score": 0.700,
                "regression_delta": 0.0,
                "skipped": False,
                "skip_reason": "",
                "seed": seed,
            },
            {
                "policy_id": "null_policy_b",
                "baseline_name": "null_policy_b",
                "raw_quality": 0.701,
                "cost": 0.21,
                "latency_p95": 0.21,
                "protected_subset_score": 0.700,
                "regression_delta": 0.0,
                "skipped": False,
                "skip_reason": "",
                "seed": seed,
            },
        ]
    )


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
        metrics=calibration_metrics(cfg.seed),
    )
    write_json(
        Path(result["run_dir"]) / "certificate_calibration_report.json",
        {
            "false_promotion_rate": 0.0,
            "false_refusal_rate": 0.0,
            "true_positive_rate": 0.0,
            "smoke": True,
        },
    )
    return result

