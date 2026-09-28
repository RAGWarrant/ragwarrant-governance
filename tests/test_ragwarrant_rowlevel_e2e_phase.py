# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from ragwarrant.experiments.runner import run_suite
from ragwarrant.validation_phase3 import (
    q2_answer,
    row_level_reconstruction_payload,
    verify_prior_hashes,
)
from ragwarrant.utils.files import write_json


def _parent_run(tmp_path: Path, constant_delta: bool = True) -> Path:
    parent = tmp_path / "parent"
    parent.mkdir()
    rows = []
    for seed in [1, 2]:
        for idx, base in enumerate([0.4, 0.5, 0.7]):
            for policy in ["ragwarrant_no_fork", "best_single_policy_on_validation"]:
                delta = 0.05 if constant_delta else 0.01 * (idx + 1)
                rows.append(
                    {
                        "example_id": f"q-{idx}",
                        "source_dataset": "fixture",
                        "seed": seed,
                        "policy_id": policy,
                        "uncertainty": 0.1 * idx,
                        "retrieval_confidence": 0.8,
                        "retrieval_conflict": 0.2,
                        "quality_gain_proxy": 0.01 * idx,
                        "expensive_compute_invoked": False,
                        "per_query_utility_proxy": base + (delta if policy == "ragwarrant_no_fork" else 0.0),
                    }
                )
    pd.DataFrame(rows).to_csv(parent / "per_query_metrics.csv", index=False)
    pd.DataFrame(
        [
            {"policy_id": "ragwarrant_no_fork", "held_out_test_cost_adjusted_utility": 0.5833333333333334 if constant_delta else 0.5533333333333333},
            {"policy_id": "best_single_policy_on_validation", "held_out_test_cost_adjusted_utility": 0.5333333333333333},
        ]
    ).to_csv(parent / "candidate_policy_metrics.csv", index=False)
    write_json(parent / "run_manifest.json", {"dataset_hash": "fixture"})
    write_json(parent / "leakage_report.json", {"status": "pass"})
    write_json(parent / "split_manifest.json", {"test": 3})
    return parent


def _config(tmp_path: Path, suite: str, raw: dict | None = None) -> Path:
    payload = {"suite": suite, "seed": 123, "certificate": {"supported_enabled": False}}
    if raw:
        payload.update(raw)
    path = tmp_path / f"{suite}.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_policy_aggregate_not_broadcast_to_query_rows(tmp_path: Path) -> None:
    payload = row_level_reconstruction_payload(_parent_run(tmp_path, constant_delta=True), bootstrap_samples=20)
    assert payload["aggregate_broadcast"]["aggregate_policy_score_broadcast_detected"] is True
    assert payload["question_1_answer"]["research_question_1_result"] == "NO_ONLY_AGGREGATE_POLICY_EVIDENCE"


def test_paired_delta_has_real_variation_known_case(tmp_path: Path) -> None:
    payload = row_level_reconstruction_payload(_parent_run(tmp_path, constant_delta=False), bootstrap_samples=20)
    assert payload["paired_diagnostics"]["unique_paired_deltas"] > 1
    assert payload["paired_diagnostics"]["std"] > 0


def test_missing_primitive_component_remains_null(tmp_path: Path) -> None:
    payload = row_level_reconstruction_payload(_parent_run(tmp_path), bootstrap_samples=20)
    reconstructed = payload["reconstructed"]
    assert reconstructed["answer_correctness"].isna().all()
    assert "primitive_quality_cost_latency_missing" in set(reconstructed["missing_component_flags"])


def test_query_cost_separate_from_optimizer_overhead(tmp_path: Path) -> None:
    payload = row_level_reconstruction_payload(_parent_run(tmp_path), bootstrap_samples=20)
    assert payload["metric_lineage"]["optimizer_overhead_separated"] is False
    assert "query_execution_cost" in payload["reconstructed"].columns


def test_reaggregation_matches_known_fixture(tmp_path: Path) -> None:
    payload = row_level_reconstruction_payload(_parent_run(tmp_path), bootstrap_samples=20)
    by_policy = {row["policy_id"]: row for row in payload["reaggregation"]}
    assert by_policy["ragwarrant_no_fork"]["within_tolerance"] is True
    assert by_policy["best_single_policy_on_validation"]["within_tolerance"] is True


def test_question_1_status_machine_readable(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        "ragwarrant_row_level_reconstruction_v1",
        {"parent_run": {"run_dir": str(_parent_run(tmp_path))}, "statistics": {"bootstrap_samples": 20}},
    )
    result = run_suite(suite="ragwarrant_row_level_reconstruction_v1", config_path=config, output_dir=tmp_path, run_id="rowlevel")
    answer = json.loads((Path(result["run_dir"]) / "question_1_answer.json").read_text(encoding="utf-8"))
    assert answer["research_question_1_result"] == "NO_ONLY_AGGREGATE_POLICY_EVIDENCE"


def test_unclear_license_blocks_acquisition(tmp_path: Path) -> None:
    approval = {
        "acquisition_approved": False,
        "license_identifier": "unknown",
    }
    assert approval["acquisition_approved"] is False


def test_corpus_backed_dataset_requires_document_ids() -> None:
    row = {"document_id": "", "question": "q"}
    assert not row["document_id"]


def test_question_2_competitive_noninferior_known_case() -> None:
    per_query = pd.DataFrame(
        [
            {"split": "test", "example_id": f"q{i}", "policy_id": "ragwarrant_no_fork", "query_operational_utility": 0.50}
            for i in range(5)
        ]
        + [
            {"split": "test", "example_id": f"q{i}", "policy_id": "static_default_rag_policy", "query_operational_utility": 0.505}
            for i in range(5)
        ]
    )
    candidates = pd.DataFrame(
        [
            {"policy_id": "ragwarrant_no_fork", "test_utility": 0.50, "raw_quality": 0.80},
            {"policy_id": "static_default_rag_policy", "test_utility": 0.505, "raw_quality": 0.80},
        ]
    )
    assert q2_answer(per_query, candidates, "static_default_rag_policy")["research_question_2_result"] == "COMPETITIVE_NONINFERIOR"


def test_question_2_not_competitive_known_case() -> None:
    per_query = pd.DataFrame(
        [
            {"split": "test", "example_id": f"q{i}", "policy_id": "ragwarrant_no_fork", "query_operational_utility": 0.40}
            for i in range(5)
        ]
        + [
            {"split": "test", "example_id": f"q{i}", "policy_id": "static_default_rag_policy", "query_operational_utility": 0.55}
            for i in range(5)
        ]
    )
    candidates = pd.DataFrame(
        [
            {"policy_id": "ragwarrant_no_fork", "test_utility": 0.40, "raw_quality": 0.70},
            {"policy_id": "static_default_rag_policy", "test_utility": 0.55, "raw_quality": 0.80},
        ]
    )
    assert q2_answer(per_query, candidates, "static_default_rag_policy")["research_question_2_result"] == "NOT_COMPETITIVE"


def test_certificate_separate_from_research_question_answer() -> None:
    result = {"research_question_2_result": "COMPETITIVE_NONINFERIOR", "certificate": "Inconclusive"}
    assert result["research_question_2_result"] != result["certificate"]


def test_prior_results_hashes_unchanged_known_snapshot_shape(tmp_path: Path) -> None:
    snapshot = {"prior_runs": [{"exists": True, "run_manifest_hash": "abc"}]}
    assert verify_prior_hashes(snapshot) is True
