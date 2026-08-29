from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.rc1_maturity import CRAG_EVALUATOR_MAPPING_V2_RESULT_CLASSES


ROOT = Path(__file__).resolve().parents[2]


def test_crag_evaluator_mapping_v2_manifest_exists() -> None:
    assert (ROOT / "artifacts/crag_evaluator_mapping_v2/evaluator_mapping_v2_manifest.json").exists()


def test_crag_evaluator_mapping_v2_result_class_allowed() -> None:
    payload = json.loads((ROOT / "artifacts/crag_evaluator_mapping_v2/evaluator_mapping_v2_result.json").read_text(encoding="utf-8"))
    assert payload["result_class"] in CRAG_EVALUATOR_MAPPING_V2_RESULT_CLASSES


def test_crag_evaluator_mapping_v2_no_raw_text() -> None:
    payload = json.loads((ROOT / "artifacts/crag_evaluator_mapping_v2/evaluator_mapping_v2_result.json").read_text(encoding="utf-8"))
    assert payload["raw_crag_text_committed"] is False
    assert payload["raw_generated_answers_committed"] is False


def test_crag_evaluator_mapping_v2_reports_blocker_or_signal() -> None:
    payload = json.loads((ROOT / "artifacts/crag_evaluator_mapping_v2/evaluator_mapping_v2_result.json").read_text(encoding="utf-8"))
    assert "BLOCKED" in payload["result_class"] or payload["evaluator_output_nonconstant"] is True
