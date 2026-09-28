# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_crag_evaluator_mapping_manifest_exists() -> None:
    assert (ROOT / "artifacts/generative_llm_validation/crag_evaluator_mapping/evaluator_mapping_manifest.json").exists()


def test_crag_evaluator_mapping_result_class_machine_readable_new() -> None:
    result = json.loads((ROOT / "artifacts/generative_llm_validation/crag_evaluator_mapping/evaluator_mapping_result.json").read_text(encoding="utf-8"))
    assert result["mapping_result_class"].startswith("CRAG_GENERATED_QUALITY_")


def test_crag_evaluator_mapping_does_not_export_raw_text() -> None:
    result = json.loads((ROOT / "artifacts/generative_llm_validation/crag_evaluator_mapping/evaluator_mapping_result.json").read_text(encoding="utf-8"))
    assert result["raw_crag_text_committed"] is False
    assert result["raw_generated_answers_committed"] is False
    assert result["raw_api_responses_committed"] is False


def test_crag_no_success_when_quality_signal_constant_zero_new() -> None:
    result = json.loads((ROOT / "artifacts/generative_llm_validation/crag_evaluator_mapping/evaluator_mapping_result.json").read_text(encoding="utf-8"))
    if not result["quality_signal_usable"]:
        assert result["mapping_result_class"] != "CRAG_GENERATED_QUALITY_LOCAL_EVALUATOR_ACTIVE"


def test_crag_local_files_not_committed() -> None:
    tracked_like = list((ROOT / "artifacts/generative_llm_validation/crag_evaluator_mapping").rglob("*"))
    assert all(".local_data" not in path.as_posix() for path in tracked_like)
