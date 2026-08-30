from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def cli_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing else os.pathsep.join([src_path, existing])
    env.update(overrides)
    return env


def test_import_ragwarrant_succeeds() -> None:
    assert importlib.util.find_spec("ragwarrant") is not None


def test_legacy_source_namespace_absent() -> None:
    legacy_namespace = "rag" + "tune"
    assert not (ROOT / "src" / legacy_namespace).exists()


def test_ragwarrant_cli_help_succeeds() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ragwarrant.cli", "--help"],
        cwd=ROOT,
        env=cli_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "run-public-mini" in result.stdout
    assert "run-governance-job" in result.stdout
    assert "verify-run" in result.stdout


def test_ragwarrant_run_public_mini_succeeds(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ragwarrant.cli", "run-public-mini", "--output-root", str(tmp_path)],
        cwd=ROOT,
        env=cli_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    manifest = json.loads((tmp_path / "mini_reproduction_manifest.json").read_text(encoding="utf-8"))
    assert manifest["result_class"] == "PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED"


def test_ragwarrant_env_output_root_is_honored(tmp_path: Path) -> None:
    env_output = tmp_path / "env-output"
    result = subprocess.run(
        [sys.executable, "-m", "ragwarrant.cli", "inspect-environment"],
        cwd=ROOT,
        env=cli_env(RAGWARRANT_OUTPUT_ROOT=str(env_output)),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert (env_output / "environment_inspection.json").exists()


def test_cli_output_root_flag_overrides_env_default(tmp_path: Path) -> None:
    env_output = tmp_path / "env-output"
    flag_output = tmp_path / "flag-output"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ragwarrant.cli",
            "inspect-environment",
            "--output-root",
            str(flag_output),
        ],
        cwd=ROOT,
        env=cli_env(RAGWARRANT_OUTPUT_ROOT=str(env_output)),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert (flag_output / "environment_inspection.json").exists()
    assert not (env_output / "environment_inspection.json").exists()
