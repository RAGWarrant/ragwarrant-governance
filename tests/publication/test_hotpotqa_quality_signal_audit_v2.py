# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.rc1_maturity import HOTPOTQA_AUDIT_V2_RESULT_CLASSES


ROOT = Path(__file__).resolve().parents[2]


def test_hotpotqa_quality_signal_audit_v2_manifest_exists() -> None:
    assert (ROOT / "artifacts/hotpotqa_quality_signal_audit_v2/audit_manifest.json").exists()


def test_hotpotqa_quality_signal_audit_v2_reports_sample_tier() -> None:
    payload = json.loads((ROOT / "artifacts/hotpotqa_quality_signal_audit_v2/audit_manifest.json").read_text(encoding="utf-8"))
    assert payload["sample_tier"] in {"small", "medium", "large_bounded"}


def test_hotpotqa_quality_signal_audit_v2_reports_quality_variance() -> None:
    payload = json.loads((ROOT / "artifacts/hotpotqa_quality_signal_audit_v2/audit_manifest.json").read_text(encoding="utf-8"))
    assert "answer_f1_variance" in payload
    assert "evidence_support_variance" in payload


def test_hotpotqa_quality_signal_audit_v2_no_raw_text() -> None:
    payload = json.loads((ROOT / "artifacts/hotpotqa_quality_signal_audit_v2/audit_manifest.json").read_text(encoding="utf-8"))
    assert payload["raw_questions_committed"] is False
    assert payload["raw_generated_answers_committed"] is False


def test_hotpotqa_quality_signal_audit_v2_result_class_allowed() -> None:
    payload = json.loads((ROOT / "artifacts/hotpotqa_quality_signal_audit_v2/audit_manifest.json").read_text(encoding="utf-8"))
    assert payload["result_class"] in HOTPOTQA_AUDIT_V2_RESULT_CLASSES
