# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragwarrant.crag_generative_validation import run_crag_generative_validation
from ragwarrant.generated_answer_quality import GENERATED_QUALITY_CLASSES, assess_quality_signal, generated_quality_score
from ragwarrant.generative_validation_common import GEN_LLM_RESULT_CLASSES, GEN_LLM_SYNTHESIS_CLASSES
from ragwarrant.generative_validation_synthesis import synthesize_generative_validation
from ragwarrant.generators.base import GenerationResult, GeneratorUnavailable
from ragwarrant.generators.factory import discover_generator
from ragwarrant.generators.hosted_openai import HostedOpenAIGenerator
from ragwarrant.generators.azure_openai import AzureOpenAIGenerator
from ragwarrant.generators.util import hash_text
from ragwarrant.hotpotqa_generative_validation import run_hotpotqa_generative_validation


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module", autouse=True)
def generate_generative_artifacts() -> None:
    if not (ROOT / "artifacts/generative_llm_validation/crag/primary_outcome_statistics.json").exists():
        run_crag_generative_validation(ROOT, output_root=ROOT / "artifacts/generative_llm_validation/crag", dry_run=True)
    if not (ROOT / "artifacts/generative_llm_validation/hotpotqa/primary_outcome_statistics.json").exists():
        run_hotpotqa_generative_validation(ROOT, output_root=ROOT / "artifacts/generative_llm_validation/hotpotqa", dry_run=True)
    if not (ROOT / "results/generative_llm_validation/synthesis_result.json").exists():
        synthesize_generative_validation(ROOT, output_root=ROOT / "results/generative_llm_validation")


def load_json(path: str) -> dict[str, object]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_generator_factory_blocks_without_generator(monkeypatch) -> None:
    monkeypatch.delenv("RAGWARRANT_GENERATOR_PROVIDER", raising=False)
    discovery = discover_generator(dry_run=True)
    assert discovery.available is False
    assert discovery.status == "GEN_LLM_VALIDATION_BLOCKED_NO_GENERATOR"


def test_ollama_adapter_does_not_require_network_when_dry_run(monkeypatch) -> None:
    monkeypatch.setenv("RAGWARRANT_GENERATOR_PROVIDER", "ollama")
    monkeypatch.setenv("RAGWARRANT_GENERATOR_MODEL", "llama3.1:8b")
    discovery = discover_generator(dry_run=True)
    assert discovery.provider == "ollama"
    assert discovery.status == "dry_run_not_called"


def test_openai_adapter_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(GeneratorUnavailable):
        HostedOpenAIGenerator()


def test_azure_openai_adapter_requires_endpoint_key_and_deployment(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    with pytest.raises(GeneratorUnavailable):
        AzureOpenAIGenerator()


def test_generation_result_stores_hash_not_raw_answer() -> None:
    result = GenerationResult(
        provider="none",
        model="none",
        model_version_or_digest="none",
        prompt_hash=hash_text("prompt"),
        answer_hash=hash_text("answer"),
        answer_char_count=6,
        answer_token_estimate=1,
        latency_ms=0.0,
        input_token_estimate=1,
        output_token_estimate=1,
        cost_units=0.0,
        finish_reason="blocked",
        error_type="",
        raw_answer_local_path=".local_data/generative_answers/x.txt",
    )
    sanitized = result.sanitized_dict()
    assert sanitized["answer_hash"] != "answer"
    assert sanitized["raw_answer_local_path"] == "<gitignored-local-answer-path>"


def test_prompt_hash_present() -> None:
    manifest = load_json("artifacts/generative_llm_validation/crag/generative_crag_manifest.json")
    assert manifest["raw_prompts_committed"] is False


def test_raw_generated_answers_not_committed() -> None:
    for path in [
        "artifacts/generative_llm_validation/crag/generative_crag_manifest.json",
        "artifacts/generative_llm_validation/hotpotqa/generative_hotpotqa_manifest.json",
    ]:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "raw_generated_answer_text" not in text
        assert "raw_answer_text" not in text


def test_crag_generative_result_class_machine_readable() -> None:
    stats = load_json("artifacts/generative_llm_validation/crag/primary_outcome_statistics.json")
    assert stats["result_class"] in GEN_LLM_RESULT_CLASSES


def test_hotpotqa_generative_result_class_machine_readable() -> None:
    stats = load_json("artifacts/generative_llm_validation/hotpotqa/primary_outcome_statistics.json")
    assert stats["result_class"] in GEN_LLM_RESULT_CLASSES


def test_generated_quality_metric_has_answer_component() -> None:
    score = generated_quality_score(
        answer_correctness_f1=1.0,
        answer_exact_match=1.0,
        answer_containment=1.0,
        evidence_support_score=0.0,
        citation_support_score=0.0,
        abstention_correctness=0.0,
    )
    assert score >= 0.6


def test_generated_quality_metric_has_evidence_component() -> None:
    score = generated_quality_score(
        answer_correctness_f1=0.0,
        answer_exact_match=0.0,
        answer_containment=0.0,
        evidence_support_score=1.0,
        citation_support_score=1.0,
        abstention_correctness=0.0,
    )
    assert score == pytest.approx(0.3)


def test_generated_quality_blocks_constant_zero_signal() -> None:
    signal = assess_quality_signal([0.0, 0.0])
    assert signal.quality_class in GENERATED_QUALITY_CLASSES
    assert signal.usable is False


def test_generative_synthesis_result_class_machine_readable() -> None:
    stats = load_json("results/generative_llm_validation/synthesis_result.json")
    assert stats["result_class"] in GEN_LLM_SYNTHESIS_CLASSES


def test_no_official_platform_benchmark_claim_from_local_generator() -> None:
    text = (ROOT / "results/generative_llm_validation/limitations.md").read_text(encoding="utf-8").lower()
    assert "not official platform benchmarking" in text


def test_no_human_validation_claim_without_annotations() -> None:
    claim = load_json("results/generative_llm_validation/claim_update.json")
    assert "human validation" in claim["unsupported_claims"]


def test_no_rag_compass_superiority_claim() -> None:
    claim = load_json("results/generative_llm_validation/claim_update.json")
    assert "RAG Compass superiority" in claim["unsupported_claims"]


def test_publication_validator_checks_generative_artifacts() -> None:
    assert (ROOT / "artifacts/generative_llm_validation/crag/generative_crag_manifest.json").exists()
    assert (ROOT / "artifacts/generative_llm_validation/hotpotqa/generative_hotpotqa_manifest.json").exists()
    assert (ROOT / "results/generative_llm_validation/synthesis_result.json").exists()
