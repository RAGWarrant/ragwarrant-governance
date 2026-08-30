from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ragwarrant.fresh_live_behavioral_governance import (
    FRESH_CRAG_RESULT_CLASSES,
    HOTPOTQA_RESULT_CLASSES,
    SYNTHESIS_RESULT_CLASSES,
    inspect_crag_environment,
    write_crag_acquisition_report,
    write_hotpotqa_acquisition_report,
    write_multi_dataset_synthesis,
)
from ragwarrant.quality_metrics import exact_match, final_hotpotqa_quality, token_f1


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module", autouse=True)
def generate_fresh_live_phase_artifacts() -> None:
    if not (ROOT / "artifacts/fresh_live_crag_behavioral_governance/primary_outcome_statistics.json").exists():
        write_crag_acquisition_report(ROOT, dry_run=True)
    if not (ROOT / "artifacts/hotpotqa_behavioral_governance/primary_outcome_statistics.json").exists():
        write_hotpotqa_acquisition_report(ROOT, dry_run=True)
    if not (ROOT / "results/multi_dataset_behavioral_governance/synthesis_result.json").exists():
        write_multi_dataset_synthesis(ROOT)


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_crag_acquisition_requires_approval_env_var(monkeypatch) -> None:
    monkeypatch.delenv("RAGWARRANT_CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY", raising=False)
    env = inspect_crag_environment()
    assert env["approved_noncommercial_research_only"] is False


def test_crag_outputs_do_not_include_raw_query_text() -> None:
    text = (ROOT / "artifacts/fresh_live_crag_behavioral_governance/live_crag_manifest.json").read_text(encoding="utf-8")
    assert '"query_text"' not in text
    assert "raw_query" not in text


def test_crag_outputs_do_not_include_raw_api_responses() -> None:
    text = (ROOT / "artifacts/fresh_live_crag_behavioral_governance/primary_outcome_statistics.json").read_text(encoding="utf-8")
    assert "api_response" not in text
    assert "raw_response" not in text


def test_hotpotqa_loader_writes_sanitized_manifest_only() -> None:
    manifest = load_json("artifacts/hotpotqa_behavioral_governance/hotpotqa_acquisition_manifest.json")
    assert manifest["question_wording_exported"] is False
    assert manifest["context_paragraphs_exported"] is False
    assert manifest["supporting_fact_sentences_exported"] is False


def test_hotpotqa_outputs_do_not_include_raw_questions() -> None:
    text = (ROOT / "artifacts/hotpotqa_behavioral_governance/primary_outcome_statistics.json").read_text(encoding="utf-8")
    assert "question_text" not in text
    assert "raw_question" not in text


def test_hotpotqa_quality_metric_has_answer_correctness() -> None:
    assert exact_match("The Eiffel Tower", "eiffel tower") == 1.0
    assert token_f1("New York City", "New York") > 0.0


def test_hotpotqa_quality_metric_has_supporting_fact_evidence() -> None:
    score = final_hotpotqa_quality(
        answer_f1=1.0,
        exact_match_score=1.0,
        supporting_fact_title_recall=1.0,
        supporting_fact_sentence_recall=1.0,
        evidence_efficiency=0.5,
        abstention_correctness=1.0,
    )
    assert score > 0.9


def test_behaviorally_distinct_policy_suite_reused() -> None:
    config = (ROOT / "configs/experiments/ragwarrant_fresh_live_crag_mock_api_behavioral_governance_v1.yaml").read_text(encoding="utf-8")
    assert "low_retrieval_single_endpoint" in config
    assert "expanded_retrieval_multi_endpoint" in config
    assert "adaptive_routing_on_insufficient_evidence" in config


def test_fresh_crag_result_class_machine_readable() -> None:
    stats = load_json("artifacts/fresh_live_crag_behavioral_governance/primary_outcome_statistics.json")
    assert stats["result_class"] in FRESH_CRAG_RESULT_CLASSES


def test_hotpotqa_result_class_machine_readable() -> None:
    stats = load_json("artifacts/hotpotqa_behavioral_governance/primary_outcome_statistics.json")
    assert stats["result_class"] in HOTPOTQA_RESULT_CLASSES


def test_multi_dataset_synthesis_result_class_machine_readable() -> None:
    stats = load_json("results/multi_dataset_behavioral_governance/synthesis_result.json")
    assert stats["result_class"] in SYNTHESIS_RESULT_CLASSES


def test_grouped_bootstrap_not_duplicated_when_unavailable() -> None:
    report = (ROOT / "results/multi_dataset_behavioral_governance/paper_ready_summary.md").read_text(encoding="utf-8")
    assert "grouped bootstrap" not in report.lower() or "unavailable" in report.lower()


def test_rag_compass_not_claimed_superior() -> None:
    claim = load_json("results/multi_dataset_behavioral_governance/claim_update.json")
    assert "RAG Compass superiority" in claim["unsupported_claims"]


def test_no_human_validation_claim_without_annotations() -> None:
    claim = load_json("results/multi_dataset_behavioral_governance/claim_update.json")
    assert "human validation" in claim["unsupported_claims"]


def test_no_generative_validation_claim_without_pinned_generator() -> None:
    claim = load_json("results/multi_dataset_behavioral_governance/claim_update.json")
    assert "generative LLM validation" in claim["unsupported_claims"]


def test_publication_validator_includes_new_artifacts() -> None:
    assert (ROOT / "artifacts/fresh_live_crag_behavioral_governance/live_crag_manifest.json").exists()
    assert (ROOT / "artifacts/hotpotqa_behavioral_governance/hotpotqa_acquisition_manifest.json").exists()
    assert (ROOT / "results/multi_dataset_behavioral_governance/synthesis_result.json").exists()
