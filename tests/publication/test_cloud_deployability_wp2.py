# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ragwarrant.mounted_job_contract import check_mounted_job_contract, exercise_storage_mode


ROOT = Path(__file__).resolve().parents[2]


def _test_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return env


def test_mounted_contract_docs_exist_and_define_exit_codes() -> None:
    text = (ROOT / "docs" / "deployment_contract.md").read_text(encoding="utf-8")
    assert "promotion_decision.json" in text
    assert "`0`" in text
    assert "`2`" in text
    assert "`3`" in text
    assert "FALLBACK_*_UNAVAILABLE" in text
    assert "No real cloud deployment" in text


def test_contract_check_uses_sanitized_path_labels(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "inputs"
    output_dir = tmp_path / "outputs"
    input_dir.mkdir()
    monkeypatch.setenv("RAGWARRANT_INPUT_DIR", str(input_dir))
    monkeypatch.setenv("RAGWARRANT_OUTPUT_DIR", str(output_dir))
    status, report = check_mounted_job_contract(output_root=output_dir)
    assert status == 0
    assert report["input_mount"] == "<configured-mounted-path>"
    assert report["output_mount"] == "<configured-mounted-path>"
    assert report["private_paths_exported"] is False
    assert (output_dir / "mounted_job_contract_report.json").exists()


def test_storage_modes_are_local_or_explicit_fallback(tmp_path: Path) -> None:
    local = exercise_storage_mode("local", output_root=tmp_path / "local")
    assert local["available"] is True
    assert local["uri"] == "file://local/sample_artifact.json"
    for mode in ("s3", "azure_blob", "gcs"):
        result = exercise_storage_mode(mode, output_root=tmp_path / mode)
        assert result["available"] is False
        assert result["fallback"] == f"FALLBACK_{mode.upper()}_UNAVAILABLE"
        assert result["secrets_logged"] is False
        assert result["raw_text_exported"] is False


def test_cli_missing_config_writes_block_decision(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ragwarrant.cli",
            "run-governance-job",
            "--config",
            str(tmp_path / "missing.yaml"),
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=_test_env(),
    )
    assert result.returncode == 2
    decision = json.loads((output_root / "promotion_decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "BLOCK"
    assert decision["result_class"] == "BLOCK_MISSING_INPUTS"


def test_cli_output_env_and_flag_precedence(tmp_path: Path, monkeypatch) -> None:
    env_out = tmp_path / "env_out"
    flag_out = tmp_path / "flag_out"
    monkeypatch.setenv("RAGWARRANT_OUTPUT_DIR", str(env_out))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ragwarrant.cli",
            "check-mounted-contract",
            "--output-root",
            str(flag_out),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=_test_env(),
    )
    assert result.returncode in {0, 2}
    assert (flag_out / "mounted_job_contract_report.json").exists()
    assert not (env_out / "mounted_job_contract_report.json").exists()
