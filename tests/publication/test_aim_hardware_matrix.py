from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.rc1_maturity import AIM_HARDWARE_MATRIX_RESULT_CLASSES


ROOT = Path(__file__).resolve().parents[2]


def test_aim_hardware_matrix_manifest_exists() -> None:
    assert (ROOT / "artifacts/aim_hardware_matrix/hardware_matrix_manifest.json").exists()


def test_aim_hardware_matrix_no_private_paths() -> None:
    text = (ROOT / "artifacts/aim_hardware_matrix/hardware_matrix_manifest.json").read_text(encoding="utf-8")
    assert "/Users/" not in text
    assert "Documents/New project" not in text


def test_aim_hardware_matrix_no_hostnames() -> None:
    payload = json.loads((ROOT / "artifacts/aim_hardware_matrix/hardware_matrix_manifest.json").read_text(encoding="utf-8"))
    assert payload["hostnames_exported"] is False


def test_aim_hardware_matrix_not_official_platform_benchmark() -> None:
    payload = json.loads((ROOT / "artifacts/aim_hardware_matrix/hardware_matrix_manifest.json").read_text(encoding="utf-8"))
    assert payload["official_platform_benchmark"] is False


def test_aim_hardware_matrix_result_class_allowed() -> None:
    payload = json.loads((ROOT / "artifacts/aim_hardware_matrix/hardware_matrix_manifest.json").read_text(encoding="utf-8"))
    assert payload["result_class"] in AIM_HARDWARE_MATRIX_RESULT_CLASSES
