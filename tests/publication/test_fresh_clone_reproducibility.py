from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.rc1_maturity import FRESH_CLONE_RESULT_CLASSES


ROOT = Path(__file__).resolve().parents[2]


def test_fresh_clone_reproducibility_script_exists() -> None:
    assert (ROOT / "scripts/run_fresh_clone_reproducibility_drill.py").exists()


def test_fresh_clone_reproducibility_config_exists() -> None:
    assert (ROOT / "configs/experiments/ragwarrant_fresh_clone_reproducibility_v1.yaml").exists()


def test_fresh_clone_result_class_machine_readable() -> None:
    payload = json.loads((ROOT / "artifacts/fresh_clone_reproducibility/fresh_clone_manifest.json").read_text(encoding="utf-8"))
    assert payload["result_class"] in FRESH_CLONE_RESULT_CLASSES


def test_fresh_clone_outputs_no_private_paths() -> None:
    text = (ROOT / "artifacts/fresh_clone_reproducibility/fresh_clone_report.md").read_text(encoding="utf-8")
    assert "/Users/" not in text
    assert "Documents/New project" not in text


def test_fresh_clone_report_exists() -> None:
    assert (ROOT / "artifacts/fresh_clone_reproducibility/fresh_clone_report.md").exists()
