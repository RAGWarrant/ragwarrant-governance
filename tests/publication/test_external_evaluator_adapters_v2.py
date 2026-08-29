from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.rc1_maturity import EXTERNAL_EVALUATOR_V2_RESULT_CLASSES


ROOT = Path(__file__).resolve().parents[2]


def test_external_evaluator_adapters_v2_manifest_exists() -> None:
    assert (ROOT / "artifacts/external_evaluator_adapters_v2/external_evaluator_manifest.json").exists()


def test_external_evaluator_adapters_v2_normalizes_multiple_formats() -> None:
    payload = json.loads((ROOT / "artifacts/external_evaluator_adapters_v2/external_evaluator_manifest.json").read_text(encoding="utf-8"))
    assert len(payload["evaluator_shapes"]) >= 5


def test_external_evaluator_adapters_v2_generates_promotion_decision() -> None:
    payload = json.loads((ROOT / "artifacts/external_evaluator_adapters_v2/external_evaluator_manifest.json").read_text(encoding="utf-8"))
    assert payload["promotion_decision_generated"] is True


def test_external_evaluator_adapters_v2_does_not_claim_tool_replacement() -> None:
    payload = json.loads((ROOT / "artifacts/external_evaluator_adapters_v2/external_evaluator_manifest.json").read_text(encoding="utf-8"))
    assert payload["tool_replacement_claimed"] is False


def test_external_evaluator_adapters_v2_result_class_allowed() -> None:
    payload = json.loads((ROOT / "artifacts/external_evaluator_adapters_v2/external_evaluator_manifest.json").read_text(encoding="utf-8"))
    assert payload["result_class"] in EXTERNAL_EVALUATOR_V2_RESULT_CLASSES
