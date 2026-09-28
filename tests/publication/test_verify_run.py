# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.rc1_maturity import VERIFY_RUN_RESULT_CLASSES, verify_run


ROOT = Path(__file__).resolve().parents[2]


def test_verify_run_script_exists() -> None:
    assert (ROOT / "scripts/verify_ragwarrant_run.py").exists()


def test_verify_run_cli_documented() -> None:
    assert "verify-run" in (ROOT / "docs/artifact_integrity.md").read_text(encoding="utf-8")


def test_verify_run_manifest_schema_exists() -> None:
    assert (ROOT / "schemas/artifact_manifest.schema.json").exists()


def test_verify_run_demo_artifacts_exist() -> None:
    assert (ROOT / "artifacts/verify_run_demo/verify_run_manifest.json").exists()


def test_verify_run_result_class_allowed() -> None:
    payload = json.loads((ROOT / "artifacts/verify_run_demo/verify_run_manifest.json").read_text(encoding="utf-8"))
    assert payload["result_class"] in VERIFY_RUN_RESULT_CLASSES


def test_verify_run_detects_missing_artifact(tmp_path: Path) -> None:
    result = verify_run(ROOT, run_dir=tmp_path / "missing", output_root=tmp_path / "out")
    assert result["result_class"] == "VERIFY_RUN_FAILED_MISSING_ARTIFACT"


def test_verify_run_no_raw_text() -> None:
    payload = json.loads((ROOT / "artifacts/verify_run_demo/verify_run_manifest.json").read_text(encoding="utf-8"))
    assert payload["raw_text_files_present"] is False
