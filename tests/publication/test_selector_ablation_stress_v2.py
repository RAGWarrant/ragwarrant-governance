from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.rc1_maturity import SELECTOR_STRESS_V2_RESULT_CLASSES


ROOT = Path(__file__).resolve().parents[2]


def test_selector_ablation_stress_v2_manifest_exists() -> None:
    assert (ROOT / "artifacts/selector_ablation_stress_v2/selector_ablation_stress_manifest.json").exists()


def test_selector_ablation_stress_v2_includes_core_selectors() -> None:
    payload = json.loads((ROOT / "artifacts/selector_ablation_stress_v2/selector_ablation_stress_manifest.json").read_text(encoding="utf-8"))
    assert "quality_only" in payload["selectors"]
    assert "risk_guarded_selector" in payload["selectors"]


def test_selector_ablation_stress_v2_marks_missing_inputs() -> None:
    payload = json.loads((ROOT / "artifacts/selector_ablation_stress_v2/selector_ablation_stress_manifest.json").read_text(encoding="utf-8"))
    assert "input_artifacts" in payload


def test_selector_ablation_stress_v2_no_universal_superiority_claim() -> None:
    payload = json.loads((ROOT / "artifacts/selector_ablation_stress_v2/selector_ablation_stress_manifest.json").read_text(encoding="utf-8"))
    assert payload["universal_superiority_claimed"] is False


def test_selector_ablation_stress_v2_result_class_allowed() -> None:
    payload = json.loads((ROOT / "artifacts/selector_ablation_stress_v2/selector_ablation_stress_manifest.json").read_text(encoding="utf-8"))
    assert payload["result_class"] in SELECTOR_STRESS_V2_RESULT_CLASSES
