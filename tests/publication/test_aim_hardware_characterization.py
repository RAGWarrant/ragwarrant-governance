# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_aim_hardware_characterization_config_exists() -> None:
    assert (ROOT / "configs/experiments/ragwarrant_aim_hardware_characterization_v1.yaml").exists()


def test_aim_hardware_characterization_script_exists() -> None:
    assert (ROOT / "scripts/run_aim_hardware_characterization.py").exists()


def test_aim_hardware_characterization_result_class_machine_readable() -> None:
    manifest = json.loads((ROOT / "artifacts/aim_hardware_characterization/hardware_manifest.json").read_text(encoding="utf-8"))
    assert manifest["result_class"] in {
        "AIM_HARDWARE_CHARACTERIZATION_COMPLETED",
        "AIM_HARDWARE_CHARACTERIZATION_PARTIAL",
        "AIM_HARDWARE_CHARACTERIZATION_BLOCKED",
    }


def test_aim_hardware_characterization_does_not_export_private_paths() -> None:
    manifest = json.loads((ROOT / "artifacts/aim_hardware_characterization/hardware_manifest.json").read_text(encoding="utf-8"))
    assert manifest["private_paths_exported"] is False
    assert manifest["hostnames_exported"] is False


def test_aim_hardware_characterization_not_official_platform_benchmark() -> None:
    text = (ROOT / "docs/aim_hardware_characterization.md").read_text(encoding="utf-8")
    assert "not official platform benchmarking" in text
