# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any

from ragwarrant.config import SuiteConfig
from ragwarrant.experiments.common import finalize_policy_suite
from ragwarrant.utils.files import write_json


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
    write_json(
        Path(result["run_dir"]) / "cloud_repro_report.json",
        {
            "dockerfile_present": Path("Dockerfile").exists(),
            "docker_smoke_documented": True,
            "cloud_credentials_required_for_tests": False,
        },
    )
    return result

