from __future__ import annotations

import json
import os
import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing else os.pathsep.join([src_path, existing])
    return env


def test_cli_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ragwarrant.cli", "--help"],
        cwd=ROOT,
        env=cli_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "run-governance-job" in result.stdout


def test_import_ragwarrant_package() -> None:
    assert importlib.util.find_spec("ragwarrant") is not None


def test_legacy_package_is_not_importable() -> None:
    legacy_package = "rag" + "tune"
    assert importlib.util.find_spec(legacy_package) is None


def test_cli_export_decision_writes_machine_readable_json(tmp_path: Path) -> None:
    out = tmp_path / "promotion_decision.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ragwarrant.cli",
            "export-decision",
            "--decision-out",
            str(out),
            "--result-class",
            "PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED",
        ],
        cwd=ROOT,
        env=cli_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["decision"] == "BLOCK"


def test_cli_inspect_environment_sanitized(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ragwarrant.cli", "inspect-environment", "--output-root", str(tmp_path)],
        cwd=ROOT,
        env=cli_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["secrets_exported"] is False
    assert payload["private_paths_exported"] is False
