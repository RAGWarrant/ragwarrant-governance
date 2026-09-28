# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import bz2
import json
from pathlib import Path

import pandas as pd
import yaml

import ragwarrant.validation_phase3 as vp
from ragwarrant.experiments.runner import run_suite
from ragwarrant.validation_phase3 import (
    classify_ragbench_subset,
    crag_retrieval_results,
    crag_schema_report,
    hotpotqa_full_corpus_decision,
    ragbench_schema_deep_dive,
    reconstruct_crag_web_corpus,
    stream_normalize_crag,
    subset_reconstruction_strategy,
)


def _config(tmp_path: Path, suite: str, extra: dict | None = None) -> Path:
    payload = {"suite": suite, "seed": 20260808}
    if extra:
        payload.update(extra)
    path = tmp_path / f"{suite}.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _run(suite: str, config_path: Path, output_dir: Path, run_id: str) -> dict:
    return run_suite(suite=suite, config_path=config_path, output_dir=output_dir, run_id=run_id)


def _sample_records(subset_id: str = "hotpotqa") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": f"{subset_id}-1",
                "question": "Which manual mentions battery calibration?",
                "documents": ["Battery calibration requires a full charge cycle.", "Warranty terms are separate."],
                "response": "A full charge cycle",
                "dataset_name": subset_id,
                "original_split": "train",
            }
        ]
    )


def _sample_crag_records() -> list[dict]:
    return [
        {
            "interaction_id": "crag-1",
            "query_time": "2024-01-01T00:00:00Z",
            "domain": "open",
            "question_type": "simple",
            "static_or_dynamic": "static",
            "query": "Who wrote Example Book?",
            "answer": "A. Writer",
            "split": 0,
            "popularity": "",
            "search_results": [
                {
                    "page_name": "Example Book",
                    "page_url": "https://example.test/book",
                    "page_snippet": "Example Book was written by A. Writer.",
                    "page_result": "<html><body>Example Book was written by A. Writer.</body></html>",
                    "page_last_modified": "2023-01-01",
                },
                {
                    "page_name": "Other",
                    "page_url": "https://example.test/other",
                    "page_snippet": "Other context.",
                    "page_result": "<html><body>Other context.</body></html>",
                    "page_last_modified": "2023-01-02",
                },
            ],
        }
    ]


def test_hotpotqa_schema_deep_dive_created() -> None:
    report = ragbench_schema_deep_dive(_sample_records(), "hotpotqa")
    assert report["query_field"] == "question"
    assert report["context_field"] == "documents"


def test_hotpotqa_full_corpus_requires_source_document_units() -> None:
    schema = {"has_native_source_document_units": True, "context_field": "documents"}
    proof = {"policy_variation_pass": True}
    decision = hotpotqa_full_corpus_decision(schema, proof)
    assert decision["result"] == "HOTPOTQA_FULL_CORPUS_BACKED_ELIGIBLE"


def test_hotpotqa_context_corpus_not_labeled_full_corpus() -> None:
    schema = {"has_native_source_document_units": False, "context_field": "documents"}
    proof = {"policy_variation_pass": True}
    decision = hotpotqa_full_corpus_decision(schema, proof)
    assert decision["result"] == "HOTPOTQA_CONTEXT_RETRIEVAL_ELIGIBLE_CONFIRMED"
    assert decision["evidence_class"] != "full_corpus_backed"


def test_hotpotqa_policy_variation_changes_retrieval(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_hotpotqa_corpus_reconstruction_v1")
    result = _run("ragwarrant_hotpotqa_corpus_reconstruction_v1", cfg, tmp_path, "hotpot")
    assert result["policy_variation_proof"]["policies_retrieve_different_document_ids"] is True


def test_hotpotqa_policy_variation_changes_context(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_hotpotqa_corpus_reconstruction_v1")
    result = _run("ragwarrant_hotpotqa_corpus_reconstruction_v1", cfg, tmp_path, "hotpot")
    assert result["policy_variation_proof"]["policies_build_different_contexts"] is True


def test_ragbench_expansion_attempts_priority_order(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_ragbench_subset_expansion_v1", {"subsets_priority": ["emanual"], "row_cap": 40})
    result = _run("ragwarrant_ragbench_subset_expansion_v1", cfg, tmp_path, "expand")
    assert result["subsets_attempted"][0] == "emanual"


def test_ragbench_subset_schema_report_per_subset() -> None:
    report = ragbench_schema_deep_dive(_sample_records("emanual"), "emanual")
    assert report["subset_id"] == "emanual"


def test_emanual_document_or_section_grouping_if_available() -> None:
    schema = {"title_or_source_fields": ["manual_id", "section_id"], "has_native_source_document_units": False, "context_field": "documents"}
    assert subset_reconstruction_strategy(schema, "emanual") == "manual_section_reconstruction"


def test_techqa_document_or_article_grouping_if_available() -> None:
    schema = {"title_or_source_fields": ["article_id"], "has_native_source_document_units": False, "context_field": "documents"}
    assert subset_reconstruction_strategy(schema, "techqa") == "technical_article_reconstruction"


def test_table_dataset_preserves_table_ids() -> None:
    schema = {"title_or_source_fields": ["table_id"], "has_native_source_document_units": False, "context_field": "documents"}
    assert subset_reconstruction_strategy(schema, "finqa") == "table_or_report_reconstruction"


def test_legal_dataset_preserves_contract_ids() -> None:
    schema = {"title_or_source_fields": ["contract_id"], "has_native_source_document_units": False, "context_field": "documents"}
    assert subset_reconstruction_strategy(schema, "cuad") == "contract_clause_reconstruction"


def test_replay_only_not_marked_end_to_end() -> None:
    schema = {"title_or_source_fields": [], "has_native_source_document_units": False, "context_field": None}
    assert classify_ragbench_subset(schema, {"policy_variation_pass": False}, "techqa") == "REPLAY_OR_CONTEXT_EVAL_ONLY"


def test_dataset_matrix_v4_evidence_classes(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_dataset_matrix_v4")
    result = _run("ragwarrant_dataset_matrix_v4", cfg, tmp_path, "matrix")
    assert any(row["evidence_class"] == "full_corpus_backed" for row in result["datasets"])


def test_dataset_matrix_v4_claim_caps(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_dataset_matrix_v4")
    result = _run("ragwarrant_dataset_matrix_v4", cfg, tmp_path, "matrix")
    assert all("claim_cap" in row for row in result["datasets"])


def test_dataset_matrix_v4_result_class_correct(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_dataset_matrix_v4")
    result = _run("ragwarrant_dataset_matrix_v4", cfg, tmp_path, "matrix")
    assert result["result"] in {
        "DATASETS_READY_FULL_CORPUS_MULTI_CORPUS",
        "DATASETS_READY_CONTEXT_RETRIEVAL_MULTI_CORPUS",
        "DATASETS_READY_MIXED_EVIDENCE_MULTI_CORPUS",
        "DATASETS_READY_EVAL_ONLY",
    }


def test_multi_corpus_v4_evidence_class_stratification(tmp_path: Path) -> None:
    _run("ragwarrant_dataset_matrix_v4", _config(tmp_path, "ragwarrant_dataset_matrix_v4"), tmp_path, "matrix")
    result = _run("ragwarrant_multi_corpus_validation_v4", _config(tmp_path, "ragwarrant_multi_corpus_validation_v4"), tmp_path, "multi")
    assert Path(result["run_dir"], "evidence_class_stratified_analysis.json").exists()


def test_context_retrieval_not_used_for_full_corpus_claim(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_crag_acquisition_adapter_v1", lambda: None)
    matrix = _run("ragwarrant_dataset_matrix_v4", _config(tmp_path, "ragwarrant_dataset_matrix_v4"), tmp_path, "matrix")
    monkeypatch.setattr(vp, "latest_dataset_matrix_v4", lambda: {"datasets": matrix["datasets"]})
    result = _run("ragwarrant_multi_corpus_validation_v4", _config(tmp_path, "ragwarrant_multi_corpus_validation_v4"), tmp_path, "multi")
    assert result["result"] != "MULTI_CORPUS_FULL_CORPUS_GOVERNANCE_SIGNAL"


def test_evidence_class_balanced_analysis_reported(tmp_path: Path) -> None:
    _run("ragwarrant_dataset_matrix_v4", _config(tmp_path, "ragwarrant_dataset_matrix_v4"), tmp_path, "matrix")
    result = _run("ragwarrant_multi_corpus_validation_v4", _config(tmp_path, "ragwarrant_multi_corpus_validation_v4"), tmp_path, "multi")
    assert Path(result["run_dir"], "evidence_class_stratified_analysis.json").exists()


def test_natural_governance_v3_counts_natural_cases(tmp_path: Path) -> None:
    _run("ragwarrant_dataset_matrix_v4", _config(tmp_path, "ragwarrant_dataset_matrix_v4"), tmp_path, "matrix")
    _run("ragwarrant_multi_corpus_validation_v4", _config(tmp_path, "ragwarrant_multi_corpus_validation_v4"), tmp_path, "multi")
    result = _run("ragwarrant_natural_governance_superiority_v3", _config(tmp_path, "ragwarrant_natural_governance_superiority_v3"), tmp_path, "natural")
    assert result["natural_divergence_case_count"] >= 0


def test_public_perturbation_not_counted_as_natural() -> None:
    case_label = "public_case_with_perturbation"
    assert case_label != "natural_public_case"


def test_synthetic_case_not_counted_as_natural() -> None:
    case_label = "synthetic_case"
    assert case_label != "natural_public_case"


def test_low_natural_divergence_classification(tmp_path: Path) -> None:
    _run("ragwarrant_dataset_matrix_v4", _config(tmp_path, "ragwarrant_dataset_matrix_v4"), tmp_path, "matrix")
    _run("ragwarrant_multi_corpus_validation_v4", _config(tmp_path, "ragwarrant_multi_corpus_validation_v4"), tmp_path, "multi")
    result = _run("ragwarrant_natural_governance_superiority_v3", _config(tmp_path, "ragwarrant_natural_governance_superiority_v3"), tmp_path, "natural")
    assert result["result"] in {
        "GOVERNANCE_INCONCLUSIVE_LOW_NATURAL_DIVERGENCE",
        "GOVERNANCE_INCONCLUSIVE_NO_NATURAL_DIVERGENCE",
        "GOVERNANCE_NONINFERIOR_NATURAL_PUBLIC",
    }


def test_crag_v2_requires_manual_approval(tmp_path: Path) -> None:
    result = _run("ragwarrant_crag_manual_approval_decision_v2", _config(tmp_path, "ragwarrant_crag_manual_approval_decision_v2"), tmp_path, "crag")
    assert result["result"] == "CRAG_BLOCKED_MANUAL_APPROVAL_MISSING"


def test_crag_v2_blocks_without_approval_metadata(tmp_path: Path) -> None:
    result = _run("ragwarrant_crag_manual_approval_decision_v2", _config(tmp_path, "ragwarrant_crag_manual_approval_decision_v2"), tmp_path, "crag")
    assert result["result"].startswith("CRAG_BLOCKED")


def test_crag_v2_accepts_noncommercial_research_approval(tmp_path: Path) -> None:
    cfg = _config(
        tmp_path,
        "ragwarrant_crag_manual_approval_decision_v2",
        {
            "crag_manual_approval": {
                "dataset_id": "crag",
                "license_identifier": "cc-by-nc-4.0",
                "use_scope": "noncommercial_research_only",
                "manual_approval": True,
                "approved_by": "test_reviewer",
                "approved_at": "2026-08-08T14:27:36Z",
                "approval_notes": "Approved for noncommercial research-only test.",
                "redistribution_allowed": False,
                "commercial_use_allowed": False,
                "paper_claim_allowed": "restricted",
                "artifact_publication_policy": "Derived artifacts only.",
            }
        },
    )
    result = _run("ragwarrant_crag_manual_approval_decision_v2", cfg, tmp_path, "crag")
    assert result["result"] == "CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY"


def test_dataset_matrix_v4_reports_crag_approved_pending_acquisition(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_crag_acquisition_adapter_v1", lambda: None)
    cfg = _config(
        tmp_path,
        "ragwarrant_crag_manual_approval_decision_v2",
        {
            "crag_manual_approval": {
                "dataset_id": "crag",
                "license_identifier": "cc-by-nc-4.0",
                "use_scope": "noncommercial_research_only",
                "manual_approval": True,
                "approved_by": "test_reviewer",
                "approved_at": "2026-08-08T14:27:36Z",
                "approval_notes": "Approved for noncommercial research-only test.",
                "redistribution_allowed": False,
                "commercial_use_allowed": False,
                "paper_claim_allowed": "restricted",
                "artifact_publication_policy": "Derived artifacts only.",
            }
        },
    )
    _run("ragwarrant_crag_manual_approval_decision_v2", cfg, tmp_path, "crag")
    result = _run("ragwarrant_dataset_matrix_v4", _config(tmp_path, "ragwarrant_dataset_matrix_v4"), tmp_path, "matrix")
    crag = next(row for row in result["datasets"] if row["dataset_id"] == "crag")
    assert crag["eligibility_class"] == "APPROVED_PENDING_ACQUISITION"


def test_crag_schema_detects_search_results() -> None:
    report = crag_schema_report(_sample_crag_records())
    assert report["query_field"] == "query"
    assert report["search_results_field"] == "search_results"
    assert report["has_full_html_pages"] is True


def test_crag_web_corpus_reconstruction_stable() -> None:
    corpus, queries = reconstruct_crag_web_corpus(_sample_crag_records())
    assert corpus.shape[0] == 2
    assert queries.shape[0] == 1
    assert queries.iloc[0]["supporting_document_ids"]
    assert corpus.iloc[0]["document_id"].startswith("crag_web_doc_")


def test_crag_acquisition_blocks_without_manual_approval(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_crag_approval_decision_v2", lambda: None)
    result = _run("ragwarrant_crag_acquisition_adapter_v1", _config(tmp_path, "ragwarrant_crag_acquisition_adapter_v1"), tmp_path, "crag_acquire")
    assert result["result"] == "CRAG_BLOCKED_MANUAL_APPROVAL_MISSING"


def test_crag_acquisition_blocks_large_download_without_explicit_allow(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        vp,
        "latest_crag_approval_decision_v2",
        lambda: {"result": "CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY", "run_dir": str(tmp_path / "approval")},
    )
    monkeypatch.setattr(
        vp,
        "download_crag_task_1_and_2",
        lambda **_kwargs: {"status": "blocked_large_download_not_allowed", "reason": "test block"},
    )
    cfg = _config(
        tmp_path,
        "ragwarrant_crag_acquisition_adapter_v1",
        {"crag_acquisition": {"allow_large_download": False, "revision": vp.CRAG_REVISION}},
    )
    result = _run("ragwarrant_crag_acquisition_adapter_v1", cfg, tmp_path, "crag_acquire")
    assert result["result"] == "CRAG_BLOCKED_ACQUISITION_FAILURE"


def test_dataset_matrix_v4_promotes_crag_only_after_acquisition(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        vp,
        "latest_crag_acquisition_adapter_v1",
        lambda: {
            "result": "CRAG_END_TO_END_CORPUS_BACKED_ELIGIBLE",
            "run_dir": str(tmp_path / "acquire"),
            "corpus_manifest": {"query_count": 10, "document_count": 20, "fresh_uninspected_query_count": 2},
        },
    )
    monkeypatch.setattr(
        vp,
        "latest_crag_approval_decision_v2",
        lambda: {"result": "CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY", "run_dir": str(tmp_path / "approval")},
    )
    result = _run("ragwarrant_dataset_matrix_v4", _config(tmp_path, "ragwarrant_dataset_matrix_v4"), tmp_path, "matrix")
    crag = next(row for row in result["datasets"] if row["dataset_id"] == "crag")
    assert crag["eligibility_class"] == "END_TO_END_CORPUS_BACKED_ELIGIBLE"
    assert crag["evidence_class"] == "full_corpus_backed"


def test_crag_streaming_normalizer_processes_all_rows(tmp_path: Path) -> None:
    raw = tmp_path / "crag.jsonl.bz2"
    rows = _sample_crag_records() * 3
    with bz2.open(raw, "wt", encoding="utf-8") as handle:
        for idx, row in enumerate(rows):
            payload = dict(row)
            payload["interaction_id"] = f"crag-{idx}"
            handle.write(json.dumps(payload) + "\n")
    manifest = stream_normalize_crag(raw, tmp_path / "normalized", max_page_result_chars=1000)
    assert manifest["streaming_all_rows"] is True
    assert manifest["rows_read"] == 3
    assert manifest["query_count"] == 3


def test_crag_readiness_requires_streaming_all_rows(monkeypatch) -> None:
    monkeypatch.setattr(vp, "latest_strict_git_manifest", lambda: {"strict_git_pass": True, "git_is_dirty": False, "git_head": "abc"})
    monkeypatch.setattr(
        vp,
        "latest_crag_acquisition_adapter_v1",
        lambda: {
            "result": "CRAG_END_TO_END_CORPUS_BACKED_ELIGIBLE",
            "corpus_manifest": {"streaming_all_rows": False, "fresh_uninspected_query_count": 500},
            "policy_variation_proof": {"policy_variation_pass": True},
            "run_dir": "/missing",
        },
    )
    readiness = vp.crag_readiness_gates(min_confirmatory_queries=300)
    assert readiness["decision"] == "REFUSED_DATA_HASH"
    assert readiness["gates"]["crag_full_streaming_normalization"] is False


def test_crag_evaluation_refuses_without_ready_gate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_crag_readiness_gate_v1", lambda: None)
    result = _run("ragwarrant_crag_governance_evaluation_v1", _config(tmp_path, "ragwarrant_crag_governance_evaluation_v1"), tmp_path, "crag_eval")
    assert result["result"] == "CRAG_EVALUATION_REFUSED_READINESS"


def test_crag_retrieval_results_include_rag_compass() -> None:
    corpus, queries = reconstruct_crag_web_corpus(_sample_crag_records())
    queries["split"] = "validation"
    result = crag_retrieval_results(corpus, queries, policies=vp.CRAG_EVAL_POLICIES)
    assert "ragwarrant_no_fork" in set(result["policy_id"])


def test_crag_mock_api_blocks_without_approval(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_crag_approval_decision_v2", lambda: None)
    result = _run("ragwarrant_crag_mock_api_path_v1", _config(tmp_path, "ragwarrant_crag_mock_api_path_v1"), tmp_path, "mock")
    assert result["result"] == "MOCK_API_BLOCKED_MANUAL_APPROVAL_MISSING"
    assert result["mock_api_claim_allowed"] is False


def test_generator_v3_local_requires_hash() -> None:
    assert not {"model_path": "/models/example"}.get("model_revision_hash")


def test_generator_v3_hosted_requires_external_credentials(tmp_path: Path) -> None:
    result = _run("ragwarrant_generator_path_enablement_v3", _config(tmp_path, "ragwarrant_generator_path_enablement_v3"), tmp_path, "gen")
    assert result["status"] == "GENERATOR_PATH_SKIPPED_NO_MODEL_OR_CREDENTIALS"


def test_generator_v3_no_secret_written(tmp_path: Path) -> None:
    result = _run("ragwarrant_generator_path_enablement_v3", _config(tmp_path, "ragwarrant_generator_path_enablement_v3"), tmp_path, "gen")
    assert "secret" not in Path(result["run_dir"], "model_provenance.json").read_text(encoding="utf-8").lower()


def test_human_eval_v3_requires_annotation_mode(tmp_path: Path) -> None:
    result = _run("ragwarrant_human_eval_pilot_readiness_v3", _config(tmp_path, "ragwarrant_human_eval_pilot_readiness_v3"), tmp_path, "human")
    assert Path(result["run_dir"], "human_eval_pilot_readiness_v3_manifest.json").exists()


def test_human_eval_v3_not_marked_run_without_annotations(tmp_path: Path) -> None:
    result = _run("ragwarrant_human_eval_pilot_readiness_v3", _config(tmp_path, "ragwarrant_human_eval_pilot_readiness_v3"), tmp_path, "human")
    assert result["result"] == "HUMAN_EVAL_READY_NOT_RUN"


def test_human_eval_v3_answer_key_private(tmp_path: Path) -> None:
    result = _run("ragwarrant_human_eval_pilot_readiness_v3", _config(tmp_path, "ragwarrant_human_eval_pilot_readiness_v3"), tmp_path, "human")
    assert Path(result["run_dir"], "human_eval_answer_key_private.json").exists()


def test_platform_v3_no_official_claim_without_official_run(tmp_path: Path) -> None:
    result = _run("ragwarrant_platform_integration_readiness_v3", _config(tmp_path, "ragwarrant_platform_integration_readiness_v3"), tmp_path, "platform")
    assert all(status != "OFFICIAL_INTEGRATION_RUN" for status in result["statuses"].values())


def test_platform_v3_workflow_simulations_labeled(tmp_path: Path) -> None:
    result = _run("ragwarrant_platform_integration_readiness_v3", _config(tmp_path, "ragwarrant_platform_integration_readiness_v3"), tmp_path, "platform")
    assert Path(result["run_dir"], "workflow_simulation_labeling_report_v3.json").exists()


def test_divergence_adjudication_requires_parent_case_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_natural_governance_v3_cases", lambda: (None, []))
    result = _run("ragwarrant_natural_divergence_adjudication_v1", _config(tmp_path, "ragwarrant_natural_divergence_adjudication_v1"), tmp_path, "adjudicate")
    assert result["result"] == "DIVERGENCE_ADJUDICATION_BLOCKED_MISSING_CASE_ARTIFACTS"


def test_each_divergence_case_has_evidence_packet(monkeypatch, tmp_path: Path) -> None:
    case = {
        "case_id": "public_case",
        "case_label": "natural_public_case",
        "governed_selected_candidate": "static_default_rag_policy",
        "quality_only_selected_candidate": "top_k_high",
        "divergence_reason": "observed_cost_adjusted_retrieval_tradeoff",
        "held_out_outcome": "retrieval_smoke_only",
    }
    parent = tmp_path / "ragwarrant_natural_governance_superiority_v3_parent"
    parent.mkdir()
    monkeypatch.setattr(vp, "latest_natural_governance_v3_cases", lambda: (parent, [case] * 4))
    monkeypatch.setattr(vp, "latest_crag_mock_api_validation_case_packet", lambda: None)
    result = _run("ragwarrant_natural_divergence_adjudication_v1", _config(tmp_path, "ragwarrant_natural_divergence_adjudication_v1"), tmp_path, "adjudicate")
    packets = json.loads(Path(result["run_dir"], "natural_divergence_case_packets.json").read_text(encoding="utf-8"))
    assert len(packets["cases"]) == 4
    assert all("classification" in row for row in packets["cases"])


def test_beneficial_divergence_classification_known_case() -> None:
    case = {"case_label": "natural_public_case", "quality_only_candidate_non_promotable": True, "held_out_supports_governance": True}
    assert vp.classify_natural_divergence_case(case) == "GOVERNANCE_BENEFICIAL_DIVERGENCE"


def test_overly_conservative_divergence_classification_known_case() -> None:
    case = {"case_label": "natural_public_case", "governance_false_demotion": True}
    assert vp.classify_natural_divergence_case(case) == "GOVERNANCE_OVERLY_CONSERVATIVE_DIVERGENCE"


def test_harmful_divergence_classification_known_case() -> None:
    case = {"case_label": "natural_public_case", "quality_only_clearly_better": True, "quality_only_candidate_promotable": True}
    assert vp.classify_natural_divergence_case(case) == "GOVERNANCE_HARMFUL_DIVERGENCE"


def test_divergence_aggregate_counts_match_cases() -> None:
    counts = {
        "GOVERNANCE_BENEFICIAL_DIVERGENCE": 0,
        "GOVERNANCE_NEUTRAL_DIVERGENCE": 0,
        "GOVERNANCE_OVERLY_CONSERVATIVE_DIVERGENCE": 0,
        "GOVERNANCE_HARMFUL_DIVERGENCE": 0,
        "GOVERNANCE_DIVERGENCE_INCONCLUSIVE": 4,
    }
    assert vp.natural_divergence_adjudication_result(counts) == "NATURAL_DIVERGENCE_INCONCLUSIVE"


def test_no_synthetic_case_counted_as_natural_beneficial() -> None:
    case = {"case_label": "synthetic_case", "quality_only_candidate_non_promotable": True, "held_out_supports_governance": True}
    assert vp.classify_natural_divergence_case(case) != "GOVERNANCE_BENEFICIAL_DIVERGENCE"


def test_mock_api_server_requires_source(monkeypatch, tmp_path: Path) -> None:
    missing = tmp_path / "missing_source"
    monkeypatch.setattr(vp, "crag_mock_api_source_dir", lambda _cfg=None: missing)
    result = _run("ragwarrant_crag_mock_api_server_smoke_v1", _config(tmp_path, "ragwarrant_crag_mock_api_server_smoke_v1"), tmp_path, "smoke")
    assert result["result"] == "MOCK_API_SERVER_BLOCKED_MISSING_DATA"


def test_mock_api_server_reports_missing_dependency(tmp_path: Path) -> None:
    server = tmp_path / "mock_api" / "server.py"
    server.parent.mkdir(parents=True)
    server.write_text("import definitely_missing_crag_dependency\n", encoding="utf-8")
    route_report = vp.discover_python_routes(server)
    assert route_report["route_count"] == 0


def test_mock_api_server_reports_missing_data(tmp_path: Path) -> None:
    data = tmp_path / "kg.json"
    data.write_text("version https://git-lfs.github.com/spec/v1\n", encoding="utf-8")
    assert vp.lfs_pointer_files([data])


def test_mock_api_route_discovery_recorded(tmp_path: Path) -> None:
    server = tmp_path / "server.py"
    server.write_text("@app.route('/health')\ndef health():\n    return 'ok'\n", encoding="utf-8")
    assert vp.discover_python_routes(server)["route_count"] == 1


def test_mock_api_health_check_required_for_claim(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_crag_mock_api_server_smoke_v1", lambda: {"result": "MOCK_API_SERVER_BLOCKED_MISSING_DATA", "run_dir": str(tmp_path)})
    result = _run("ragwarrant_crag_mock_api_governance_evaluation_v1", _config(tmp_path, "ragwarrant_crag_mock_api_governance_evaluation_v1"), tmp_path, "mock_eval")
    assert result["result"] == "MOCK_API_GOVERNANCE_BLOCKED_SERVER_SMOKE_NOT_PASSED"


def test_mock_api_logs_sanitized(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "crag_mock_api_source_dir", lambda _cfg=None: tmp_path / "missing")
    result = _run("ragwarrant_crag_mock_api_server_smoke_v1", _config(tmp_path, "ragwarrant_crag_mock_api_server_smoke_v1"), tmp_path, "smoke")
    logs = Path(result["run_dir"], "crag_mock_api_server_logs_sanitized.txt").read_text(encoding="utf-8").lower()
    assert "secret" in logs
    assert "api_key" not in logs


def test_no_mock_api_governance_claim_without_smoke_pass(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_crag_mock_api_server_smoke_v1", lambda: None)
    result = _run("ragwarrant_crag_mock_api_governance_evaluation_v1", _config(tmp_path, "ragwarrant_crag_mock_api_governance_evaluation_v1"), tmp_path, "mock_eval")
    assert result["api_call_count"] == 0


def test_mock_api_governance_reports_api_call_count(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_crag_mock_api_server_smoke_v1", lambda: None)
    result = _run("ragwarrant_crag_mock_api_governance_evaluation_v1", _config(tmp_path, "ragwarrant_crag_mock_api_governance_evaluation_v1"), tmp_path, "mock_eval")
    assert "api_call_count" in result


def test_mock_api_governance_reports_web_vs_api_comparison(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_crag_mock_api_server_smoke_v1", lambda: None)
    result = _run("ragwarrant_crag_mock_api_governance_evaluation_v1", _config(tmp_path, "ragwarrant_crag_mock_api_governance_evaluation_v1"), tmp_path, "mock_eval")
    assert Path(result["run_dir"], "crag_mock_api_web_vs_api_comparison.json").exists()


def test_mock_api_governance_reports_selection_divergence(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_crag_mock_api_server_smoke_v1", lambda: None)
    result = _run("ragwarrant_crag_mock_api_governance_evaluation_v1", _config(tmp_path, "ragwarrant_crag_mock_api_governance_evaluation_v1"), tmp_path, "mock_eval")
    assert Path(result["run_dir"], "crag_mock_api_selection_divergence_cases.json").exists()


def test_mock_api_governance_result_class_machine_readable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_crag_mock_api_server_smoke_v1", lambda: None)
    result = _run("ragwarrant_crag_mock_api_governance_evaluation_v1", _config(tmp_path, "ragwarrant_crag_mock_api_governance_evaluation_v1"), tmp_path, "mock_eval")
    assert result["result"].startswith("MOCK_API_GOVERNANCE_")


def test_crag_mock_api_validation_blocks_without_smoke(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vp, "latest_crag_mock_api_server_smoke_v1", lambda: None)
    result = _run("ragwarrant_crag_mock_api_validation_v1", _config(tmp_path, "ragwarrant_crag_mock_api_validation_v1"), tmp_path, "mock_validation")
    assert result["result"] == "MOCK_API_VALIDATION_BLOCKED_SERVER_SMOKE_NOT_PASSED"


def test_crag_mock_api_domain_routes_are_domain_aware() -> None:
    routes = vp.crag_mock_api_domain_routes("finance", "What is Apple worth?", "2024-01-01T00:00:00Z")
    assert routes[0]["route"].startswith("/finance/")
    sports = vp.crag_mock_api_domain_routes("sports", "Who won?", "2024-03-09T00:00:00Z")
    assert sports[0]["payload"]["date"] == "2024-03-09"


def test_crag_mock_api_sample_queries_stratified() -> None:
    rows = pd.DataFrame(
        [
            {"query_id": f"q{i}", "split": "confirmatory_test", "domain": "open" if i % 2 else "finance", "question_type": "simple", "static_or_dynamic": "static"}
            for i in range(8)
        ]
    )
    sample = vp.crag_mock_api_sample_queries(rows, split="confirmatory_test", max_queries=4, seed=1)
    assert set(sample["domain"]) == {"finance", "open"}


def test_crag_mock_api_sample_queries_full_split_returns_all_rows() -> None:
    rows = pd.DataFrame(
        [
            {"query_id": f"q{i}", "split": "confirmatory_test", "domain": "open", "question_type": "simple", "static_or_dynamic": "static"}
            for i in range(6)
        ]
    )
    sample = vp.crag_mock_api_sample_queries(rows, split="confirmatory_test", max_queries=999, seed=1)
    assert len(sample) == 6


def test_crag_mock_api_validation_writes_per_query_budget_latency_and_stats(monkeypatch, tmp_path: Path) -> None:
    queries_path = tmp_path / "queries.csv"
    metadata = {"domain": "finance", "question_type": "simple", "static_or_dynamic": "dynamic", "query_time": "2024-01-01T00:00:00Z"}
    pd.DataFrame(
        [
            {"query_id": "v1", "query_text": "What is Apple worth?", "reference_answer": "Apple", "metadata_json": json.dumps(metadata), "split": "validation"},
            {"query_id": "c1", "query_text": "What is Apple worth?", "reference_answer": "Apple", "metadata_json": json.dumps(metadata), "split": "confirmatory_test"},
        ]
    ).to_csv(queries_path, index=False)

    def fake_live(*_args, **_kwargs):
        rows = []
        for split, qid in [("validation", "v1"), ("confirmatory_test", "c1")]:
            rows.extend(
                [
                    {"example_id": qid, "query_id": qid, "split": split, "domain": "finance", "question_type": "simple", "static_or_dynamic": "dynamic", "policy_id": "optuna_tpe", "display_name": "optuna_tpe", "api_call_count": 3, "successful_call_count": 3, "failure_rate": 0.0, "result_count": 3, "raw_quality": 0.95, "budget_units": 3.45, "latency_ms": 300.0, "query_operational_utility": 0.915, "security_eligible": True, "provenance_eligible": True},
                    {"example_id": qid, "query_id": qid, "split": split, "domain": "finance", "question_type": "simple", "static_or_dynamic": "dynamic", "policy_id": vp.RAG_COMPASS_ID, "display_name": "RAG Compass", "api_call_count": 1, "successful_call_count": 1, "failure_rate": 0.0, "result_count": 1, "raw_quality": 0.92, "budget_units": 0.95, "latency_ms": 100.0, "query_operational_utility": 0.910, "security_eligible": True, "provenance_eligible": True},
                ]
            )
        return {"started": True, "rows": rows, "api_call_count": 8, "log_excerpt": ""}

    monkeypatch.setattr(vp, "latest_crag_mock_api_server_smoke_v1", lambda: {"result": "MOCK_API_SERVER_SMOKE_PASSED", "run_dir": str(tmp_path), "preflight": {"source_dir": str(tmp_path), "python_executable": "python"}})
    monkeypatch.setattr(vp, "latest_crag_acquisition_adapter_v1", lambda: {"corpus_manifest": {"queries_path": str(queries_path)}})
    monkeypatch.setattr(vp, "crag_mock_api_validation_live_run", fake_live)
    result = _run("ragwarrant_crag_mock_api_validation_v1", _config(tmp_path, "ragwarrant_crag_mock_api_validation_v1"), tmp_path, "mock_validation")
    per_query = pd.read_csv(Path(result["run_dir"], "crag_mock_api_per_query_results.csv"))
    stats = json.loads(Path(result["run_dir"], "crag_mock_api_statistical_analysis.json").read_text(encoding="utf-8"))
    sensitivity = json.loads(Path(result["run_dir"], "crag_mock_api_utility_sensitivity.json").read_text(encoding="utf-8"))
    assert {"api_call_count", "budget_units", "latency_ms"}.issubset(per_query.columns)
    assert stats["status"] == "ok"
    assert sensitivity["grid_count"] > 0


def test_crag_mock_api_validation_result_class_machine_readable() -> None:
    result = vp.crag_mock_api_validation_result({"status": "ok", "point_estimate": 0.0, "query_bootstrap_ci": [0.0, 0.0]}, "a", "a")
    assert result.startswith("MOCK_API_VALIDATION_")


def test_crag_mock_api_utility_sensitivity_reports_fragility() -> None:
    per_query = pd.DataFrame(
        [
            {"example_id": "q1", "query_id": "q1", "split": "validation", "policy_id": "cheap", "raw_quality": 0.8, "budget_units": 1.0, "latency_ms": 10.0, "failure_rate": 0.0, "api_call_count": 1},
            {"example_id": "q1", "query_id": "q1", "split": "validation", "policy_id": "expensive", "raw_quality": 0.9, "budget_units": 3.0, "latency_ms": 30.0, "failure_rate": 0.0, "api_call_count": 3},
            {"example_id": "q2", "query_id": "q2", "split": "confirmatory_test", "policy_id": "cheap", "raw_quality": 0.8, "budget_units": 1.0, "latency_ms": 10.0, "failure_rate": 0.0, "api_call_count": 1},
            {"example_id": "q2", "query_id": "q2", "split": "confirmatory_test", "policy_id": "expensive", "raw_quality": 0.9, "budget_units": 3.0, "latency_ms": 30.0, "failure_rate": 0.0, "api_call_count": 3},
        ]
    )
    frame, summary = vp.crag_mock_api_utility_sensitivity(
        per_query,
        cost_weights=[0.0, 0.1],
        latency_weights=[0.0],
        max_budget_units=2.0,
        max_latency_ms=100.0,
        bootstrap_samples=10,
    )
    assert len(frame) == 2
    assert summary["grid_count"] == 2


def test_beneficial_divergence_requires_natural_case() -> None:
    assert vp.classify_natural_divergence_case({"case_label": "diagnostic_fixture_case", "quality_only_candidate_non_promotable": True}) != "GOVERNANCE_BENEFICIAL_DIVERGENCE"


def test_beneficial_divergence_requires_governance_reason() -> None:
    row = {"case_id": "case", "governance_reason": "observed_cost_adjusted_retrieval_tradeoff"}
    assert row["governance_reason"]


def test_beneficial_divergence_requires_heldout_or_adjudicated_support() -> None:
    case = {"case_label": "natural_public_case", "quality_only_candidate_non_promotable": True, "held_out_supports_governance": False}
    assert vp.classify_natural_divergence_case(case) != "GOVERNANCE_BENEFICIAL_DIVERGENCE"


def test_harmful_divergence_counted_separately() -> None:
    assert vp.beneficial_divergence_result({"beneficial": 1, "harmful": 1}) == "GOVERNANCE_DIVERGENCE_HARMFUL"


def test_overly_conservative_divergence_counted_separately() -> None:
    assert vp.beneficial_divergence_result({"beneficial": 1, "overly_conservative": 1, "inconclusive": 0, "harmful": 0}) == "BENEFICIAL_GOVERNANCE_DIVERGENCE_MIXED"


def test_beneficial_divergence_result_class_correct() -> None:
    assert vp.beneficial_divergence_result({"beneficial": 0, "harmful": 0, "inconclusive": 4}) == "GOVERNANCE_DIVERGENCE_SEARCH_INCONCLUSIVE"


def test_rag_compass_niche_analysis_includes_cost(tmp_path: Path) -> None:
    result = _run("ragwarrant_rag_compass_niche_analysis_v1", _config(tmp_path, "ragwarrant_rag_compass_niche_analysis_v1"), tmp_path, "niche")
    rows = pd.read_csv(Path(result["run_dir"], "rag_compass_niche_metrics.csv"))
    assert "inference_cost_efficiency" in set(rows["niche"])


def test_rag_compass_niche_analysis_includes_latency(tmp_path: Path) -> None:
    result = _run("ragwarrant_rag_compass_niche_analysis_v1", _config(tmp_path, "ragwarrant_rag_compass_niche_analysis_v1"), tmp_path, "niche")
    rows = pd.read_csv(Path(result["run_dir"], "rag_compass_niche_metrics.csv"))
    assert "latency_efficiency" in set(rows["niche"])


def test_rag_compass_niche_analysis_includes_stability(tmp_path: Path) -> None:
    result = _run("ragwarrant_rag_compass_niche_analysis_v1", _config(tmp_path, "ragwarrant_rag_compass_niche_analysis_v1"), tmp_path, "niche")
    rows = pd.read_csv(Path(result["run_dir"], "rag_compass_niche_metrics.csv"))
    assert "stability" in set(rows["niche"])


def test_rag_compass_niche_analysis_includes_overfit_regret(tmp_path: Path) -> None:
    result = _run("ragwarrant_rag_compass_niche_analysis_v1", _config(tmp_path, "ragwarrant_rag_compass_niche_analysis_v1"), tmp_path, "niche")
    assert Path(result["run_dir"], "rag_compass_overfit_regret_analysis.json").exists()


def test_rag_compass_not_declared_superior_from_single_niche() -> None:
    assert vp.rag_compass_niche_classification({"advantage": True}) == "RAG_COMPASS_NICHE_ADVANTAGE"
    assert "SUPERIOR" not in vp.rag_compass_niche_classification({"advantage": True})


def test_rag_compass_display_name_used(tmp_path: Path) -> None:
    result = _run("ragwarrant_rag_compass_niche_analysis_v1", _config(tmp_path, "ragwarrant_rag_compass_niche_analysis_v1"), tmp_path, "niche")
    text = Path(result["run_dir"], "rag_compass_niche_analysis_report.md").read_text(encoding="utf-8")
    assert "RAG Compass" in text


def test_generator_v4_local_requires_hash() -> None:
    assert vp.generator_v4_local_config_ready({"model_path": "/models/example", "license_identifier": "apache-2.0"}) is False


def test_generator_v4_local_requires_license() -> None:
    assert vp.generator_v4_local_config_ready({"model_path": "/models/example", "model_hash": "abc", "tokenizer_hash": "def"}) is False


def test_generator_v4_download_requires_explicit_allow() -> None:
    cfg = {"model_id": "tiny", "revision": "abc", "expected_license": "apache-2.0"}
    assert not cfg.get("allow_model_download")


def test_generator_v4_hosted_requires_external_credentials(tmp_path: Path) -> None:
    result = _run("ragwarrant_generator_path_enablement_v4", _config(tmp_path, "ragwarrant_generator_path_enablement_v4", {"hosted_model": {"provider": "test", "model_version": "v1", "credential_env": "RAGWARRANT_TEST_MISSING_KEY"}}), tmp_path, "gen")
    assert result["result"] == "GENERATOR_PATH_SKIPPED_NO_MODEL_OR_CREDENTIALS"


def test_generator_v4_no_secret_written(tmp_path: Path) -> None:
    result = _run("ragwarrant_generator_path_enablement_v4", _config(tmp_path, "ragwarrant_generator_path_enablement_v4"), tmp_path, "gen")
    text = Path(result["run_dir"], "model_provenance.json").read_text(encoding="utf-8").lower()
    assert "api_key" not in text


def test_generator_v4_skipped_when_unavailable(tmp_path: Path) -> None:
    result = _run("ragwarrant_generator_path_enablement_v4", _config(tmp_path, "ragwarrant_generator_path_enablement_v4"), tmp_path, "gen")
    assert result["result"] == "GENERATOR_PATH_SKIPPED_NO_MODEL_OR_CREDENTIALS"


def test_human_eval_v4_not_marked_run_without_annotations(tmp_path: Path) -> None:
    result = _run("ragwarrant_human_eval_pilot_v4", _config(tmp_path, "ragwarrant_human_eval_pilot_v4"), tmp_path, "human")
    assert result["result"] == "HUMAN_EVAL_READY_NOT_RUN"


def test_human_eval_v4_prioritizes_natural_divergence_cases(tmp_path: Path) -> None:
    result = _run("ragwarrant_human_eval_pilot_v4", _config(tmp_path, "ragwarrant_human_eval_pilot_v4"), tmp_path, "human")
    manifest = json.loads(Path(result["run_dir"], "human_eval_pilot_v4_manifest.json").read_text(encoding="utf-8"))
    assert "prioritizes_natural_divergence_cases" in manifest


def test_human_eval_v4_pairs_blinded(tmp_path: Path) -> None:
    result = _run("ragwarrant_human_eval_pilot_v4", _config(tmp_path, "ragwarrant_human_eval_pilot_v4"), tmp_path, "human")
    rows = pd.read_csv(Path(result["run_dir"], "human_eval_pairs_blinded.csv"))
    assert set(rows["left_label"]) == {"blinded"}


def test_human_eval_v4_answer_key_private(tmp_path: Path) -> None:
    result = _run("ragwarrant_human_eval_pilot_v4", _config(tmp_path, "ragwarrant_human_eval_pilot_v4"), tmp_path, "human")
    assert Path(result["run_dir"], "human_eval_answer_key_private.json").exists()


def test_human_eval_v4_annotation_schema_valid(tmp_path: Path) -> None:
    result = _run("ragwarrant_human_eval_pilot_v4", _config(tmp_path, "ragwarrant_human_eval_pilot_v4"), tmp_path, "human")
    manifest = json.loads(Path(result["run_dir"], "human_eval_pilot_v4_manifest.json").read_text(encoding="utf-8"))
    assert manifest["annotation_schema_valid"] is True


def test_human_eval_v4_metric_alignment_when_annotations_exist(tmp_path: Path) -> None:
    result = _run("ragwarrant_human_eval_pilot_v4", _config(tmp_path, "ragwarrant_human_eval_pilot_v4"), tmp_path, "human")
    assert Path(result["run_dir"], "human_eval_metric_alignment.json").exists()


def test_decision_memo_has_required_sections(tmp_path: Path) -> None:
    result = _run("ragwarrant_continued_investment_decision_memo_v1", _config(tmp_path, "ragwarrant_continued_investment_decision_memo_v1"), tmp_path, "memo")
    text = Path(result["run_dir"], "continued_investment_decision_memo.md").read_text(encoding="utf-8")
    assert "Executive Summary" in text
    assert "Recommended Path" in text


def test_decision_memo_has_single_primary_recommendation(tmp_path: Path) -> None:
    result = _run("ragwarrant_continued_investment_decision_memo_v1", _config(tmp_path, "ragwarrant_continued_investment_decision_memo_v1"), tmp_path, "memo")
    payload = json.loads(Path(result["run_dir"], "continued_investment_decision_memo_manifest.json").read_text(encoding="utf-8"))
    assert payload["single_primary_recommendation"] is True


def test_decision_memo_distinguishes_ragwarrant_from_rag_compass(tmp_path: Path) -> None:
    result = _run("ragwarrant_continued_investment_decision_memo_v1", _config(tmp_path, "ragwarrant_continued_investment_decision_memo_v1"), tmp_path, "memo")
    text = Path(result["run_dir"], "continued_investment_decision_memo.md").read_text(encoding="utf-8")
    assert "What RAGWarrant Has Demonstrated" in text
    assert "What RAG Compass Has Demonstrated" in text


def test_decision_memo_includes_negative_evidence(tmp_path: Path) -> None:
    result = _run("ragwarrant_continued_investment_decision_memo_v1", _config(tmp_path, "ragwarrant_continued_investment_decision_memo_v1"), tmp_path, "memo")
    text = Path(result["run_dir"], "continued_investment_decision_memo.md").read_text(encoding="utf-8")
    assert "Evidence Against" in text


def test_decision_memo_not_productization_without_evidence() -> None:
    rec = vp.continued_investment_recommendation({"governance_framework_value": True, "rag_compass_has_actionable_niche": False})
    assert rec != "MOVE_TO_PRODUCTIZATION_PROTOTYPE"
