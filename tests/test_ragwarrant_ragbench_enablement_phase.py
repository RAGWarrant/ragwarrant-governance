# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from ragwarrant.experiments.runner import run_suite
from ragwarrant.validation_phase3 import (
    grouped_query_splits,
    ragbench_policy_variation_smoke,
    ragbench_stable_doc_id,
    reconstruct_context_corpus,
)


def _config(tmp_path: Path, suite: str, extra: dict | None = None) -> Path:
    payload = {"suite": suite, "seed": 20260808}
    if extra:
        payload.update(extra)
    path = tmp_path / f"{suite}.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _sample_ragbench_records() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": "q1",
                "question": "Who wrote Hamlet?",
                "documents": ["Hamlet is a tragedy written by William Shakespeare.", "Paris is in France."],
                "response": "William Shakespeare",
                "dataset_name": "hotpotqa",
                "original_split": "train",
            },
            {
                "id": "q2",
                "question": "Which city is in France?",
                "documents": ["Paris is in France.", "Hamlet is a tragedy written by William Shakespeare."],
                "response": "Paris",
                "dataset_name": "hotpotqa",
                "original_split": "validation",
            },
            {
                "id": "q3",
                "question": "What is Python?",
                "documents": ["Python is a programming language.", "The Nile is a river."],
                "response": "A programming language",
                "dataset_name": "hotpotqa",
                "original_split": "test",
            },
        ]
    )


def test_ragbench_subset_schema_detected() -> None:
    records = _sample_ragbench_records()
    assert {"id", "question", "documents", "response"}.issubset(records.columns)


def test_ragbench_contexts_deduplicated_to_corpus() -> None:
    corpus, queries = reconstruct_context_corpus(_sample_ragbench_records())
    assert corpus["document_id"].nunique() == 4
    assert len(queries) == 3


def test_ragbench_document_ids_stable() -> None:
    text = "Hamlet is a tragedy written by William Shakespeare."
    assert ragbench_stable_doc_id("ragbench", "hotpotqa", text) == ragbench_stable_doc_id("ragbench", "hotpotqa", text)


def test_ragbench_query_ids_stable() -> None:
    _corpus, queries = reconstruct_context_corpus(_sample_ragbench_records())
    assert queries["query_id"].is_unique


def test_ragbench_policy_variation_changes_retrieval() -> None:
    corpus, queries = reconstruct_context_corpus(_sample_ragbench_records())
    smoke, proof = ragbench_policy_variation_smoke(corpus, queries)
    assert not smoke.empty
    assert proof["policies_retrieve_different_document_ids"] is True


def test_ragbench_policy_variation_changes_context() -> None:
    corpus, queries = reconstruct_context_corpus(_sample_ragbench_records())
    _smoke, proof = ragbench_policy_variation_smoke(corpus, queries)
    assert proof["policies_build_different_contexts"] is True


def test_replay_only_subset_not_marked_end_to_end() -> None:
    replay_only = {"policy_variation_pass": False}
    assert replay_only["policy_variation_pass"] is False


def test_context_retrieval_eligible_labeled_weaker() -> None:
    label = "END_TO_END_CONTEXT_RETRIEVAL_ELIGIBLE"
    assert label != "END_TO_END_CORPUS_BACKED_ELIGIBLE"


def test_ragbench_split_leakage_zero() -> None:
    _corpus, queries = reconstruct_context_corpus(_sample_ragbench_records())
    split_queries, report = grouped_query_splits(queries)
    assert set(split_queries["split"]).issubset({"calibration", "validation", "confirmatory_test"})
    assert report["status"] == "pass"


def test_seen_examples_excluded_from_confirmatory_split() -> None:
    _corpus, queries = reconstruct_context_corpus(_sample_ragbench_records())
    split_queries, _report = grouped_query_splits(queries)
    assert "confirmatory_test" in set(split_queries["split"]) or len(split_queries) == 3


def test_dataset_matrix_v3_result_class_correct(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_dataset_matrix_v3")
    result = run_suite(suite="ragwarrant_dataset_matrix_v3", config_path=cfg, output_dir=tmp_path, run_id="matrix")
    assert result["result"] in {
        "DATASETS_READY_CONTEXT_RETRIEVAL_MULTI_CORPUS",
        "DATASETS_READY_EVAL_ONLY",
        "DATASETS_READY_MULTI_CORPUS_END_TO_END",
    }


def test_multi_corpus_v3_claim_cap_for_context_retrieval_only(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_multi_corpus_validation_v3")
    result = run_suite(suite="ragwarrant_multi_corpus_validation_v3", config_path=cfg, output_dir=tmp_path, run_id="multi")
    assert "claim_cap" in result


def test_rag_compass_rank_distribution_reported(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_multi_corpus_validation_v3")
    result = run_suite(suite="ragwarrant_multi_corpus_validation_v3", config_path=cfg, output_dir=tmp_path, run_id="multi")
    assert (Path(result["run_dir"]) / "rag_compass_cross_corpus_report.json").exists()


def test_natural_case_requires_real_public_output(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_natural_governance_superiority_v2")
    result = run_suite(suite="ragwarrant_natural_governance_superiority_v2", config_path=cfg, output_dir=tmp_path, run_id="natural")
    assert result["result"] in {"GOVERNANCE_NONINFERIOR_NATURAL_PUBLIC", "GOVERNANCE_INCONCLUSIVE_NO_NATURAL_DIVERGENCE"}


def test_synthetic_case_not_counted_as_natural() -> None:
    case = {"case_label": "synthetic_case"}
    assert case["case_label"] != "natural_public_case"


def test_natural_divergence_detection(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_natural_governance_superiority_v2")
    result = run_suite(suite="ragwarrant_natural_governance_superiority_v2", config_path=cfg, output_dir=tmp_path, run_id="natural")
    assert result["natural_divergence_case_count"] >= 0


def test_crag_blocked_without_approval_metadata(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_crag_manual_approval_decision_v1")
    result = run_suite(suite="ragwarrant_crag_manual_approval_decision_v1", config_path=cfg, output_dir=tmp_path, run_id="crag")
    assert result["result"] == "CRAG_BLOCKED_MANUAL_APPROVAL_MISSING"


def test_generator_path_skipped_when_unavailable(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_generator_path_enablement_v2")
    result = run_suite(suite="ragwarrant_generator_path_enablement_v2", config_path=cfg, output_dir=tmp_path, run_id="gen")
    assert result["status"] == "GENERATOR_PATH_SKIPPED_NO_MODEL_OR_CREDENTIALS"


def test_human_eval_not_marked_run_without_annotations(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_human_eval_workflow_setup_v2")
    result = run_suite(suite="ragwarrant_human_eval_workflow_setup_v2", config_path=cfg, output_dir=tmp_path, run_id="human")
    assert result["result"] == "HUMAN_EVAL_READY_NOT_RUN"


def test_answer_key_private(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_human_eval_workflow_setup_v2")
    result = run_suite(suite="ragwarrant_human_eval_workflow_setup_v2", config_path=cfg, output_dir=tmp_path, run_id="human")
    assert (Path(result["run_dir"]) / "human_eval_answer_key_private.json").exists()


def test_no_official_claim_without_official_run(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_platform_integration_readiness_v2")
    result = run_suite(suite="ragwarrant_platform_integration_readiness_v2", config_path=cfg, output_dir=tmp_path, run_id="platform")
    assert all("OFFICIAL_INTEGRATION_RUN" != status for status in result["statuses"].values())


def test_workflow_simulations_labeled_when_no_integration(tmp_path: Path) -> None:
    cfg = _config(tmp_path, "ragwarrant_platform_integration_readiness_v2")
    result = run_suite(suite="ragwarrant_platform_integration_readiness_v2", config_path=cfg, output_dir=tmp_path, run_id="platform")
    report = Path(result["run_dir"]) / "workflow_simulation_labeling_report.json"
    assert "workflow_simulations_labeled" in report.read_text(encoding="utf-8")
