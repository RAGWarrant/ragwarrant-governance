# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any

from ragwarrant.config import SuiteConfig
from ragwarrant.real_rag import run_real_rag_governance


def run(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_real_rag_governance(
        cfg,
        config_path,
        output_dir,
        run_id,
        resume=resume,
        force_new_run_id=force_new_run_id,
    )
