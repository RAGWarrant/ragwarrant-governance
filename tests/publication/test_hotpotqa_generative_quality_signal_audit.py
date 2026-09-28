# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_hotpotqa_quality_signal_audit_manifest_exists_new() -> None:
    manifest = json.loads((ROOT / "artifacts/generative_llm_validation/hotpotqa_quality_signal_audit/audit_manifest.json").read_text(encoding="utf-8"))
    assert manifest["suite"] == "ragwarrant_hotpotqa_generative_quality_signal_audit_v1"
    assert "configured_larger_sample_target" in manifest


def test_hotpotqa_quality_signal_diagnostics_exists() -> None:
    assert (ROOT / "artifacts/generative_llm_validation/hotpotqa_quality_signal_audit/quality_signal_diagnostics.csv").exists()


def test_hotpotqa_quality_signal_audit_reports_answer_hash_diversity_new() -> None:
    manifest = json.loads((ROOT / "artifacts/generative_llm_validation/hotpotqa_quality_signal_audit/audit_manifest.json").read_text(encoding="utf-8"))
    assert int(manifest["unique_answer_hash_count"]) >= 0


def test_hotpotqa_quality_signal_audit_reports_quality_variance_new() -> None:
    manifest = json.loads((ROOT / "artifacts/generative_llm_validation/hotpotqa_quality_signal_audit/audit_manifest.json").read_text(encoding="utf-8"))
    assert float(manifest["quality_variance"]) >= 0.0


def test_hotpotqa_constant_zero_quality_not_auto_promoted_new() -> None:
    stats = json.loads((ROOT / "artifacts/generative_llm_validation/hotpotqa_quality_signal_audit/primary_outcome_statistics.json").read_text(encoding="utf-8"))
    if float(stats.get("quality_variance", 0.0)) == 0.0:
        assert stats["result_class"] != "GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY"


def test_hotpotqa_raw_text_not_committed_new() -> None:
    with (ROOT / "artifacts/generative_llm_validation/hotpotqa_quality_signal_audit/per_query_generation_metrics.csv").open(newline="", encoding="utf-8") as handle:
        fields = csv.DictReader(handle).fieldnames or []
    assert "question_text" not in fields
    assert "context_text" not in fields
    assert "generated_answer" not in fields
