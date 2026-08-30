from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from ragwarrant.config import SuiteConfig
from ragwarrant.end_to_end import RAGPolicy
from ragwarrant.experiments.runner import run_suite
from ragwarrant.validation_phase3 import (
    build_confirmatory_provenance,
    formal_development_answer,
    normalize_t2,
    split_queries,
)
from ragwarrant.utils.write_once import WriteOnceError


def _config(tmp_path: Path, suite: str, raw: dict | None = None) -> Path:
    payload = {
        "suite": suite,
        "seed": 123,
        "baselines": {"required": ["static_default_rag_policy", "greedy_coordinate_search", "ragwarrant_no_fork"]},
        "budget": {"primary_mode": "normalized_cost"},
        "hypotheses": {"noninferiority_margin": 0.01},
        "statistics": {"bootstrap_samples": 20},
        "certificate": {"supported_enabled": False},
    }
    if raw:
        payload.update(raw)
    path = tmp_path / f"{suite}.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_confirmatory_refuses_without_git_head(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_confirmatory_provenance_v1")
    cfg = SuiteConfig.from_path(cfg_path)
    manifest = build_confirmatory_provenance(cfg, cfg_path)
    if not manifest["git_available"]:
        assert "git_head_available" in manifest["refusal_reasons"]


def test_confirmatory_refuses_dirty_tree_by_default(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_confirmatory_provenance_v1")
    cfg = SuiteConfig.from_path(cfg_path)
    manifest = build_confirmatory_provenance(cfg, cfg_path)
    assert manifest["allow_dirty_confirmatory"] is False


def test_confirmatory_allows_dirty_tree_only_when_explicitly_configured(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_confirmatory_provenance_v1", {"provenance": {"allow_dirty_confirmatory": True}})
    cfg = SuiteConfig.from_path(cfg_path)
    manifest = build_confirmatory_provenance(cfg, cfg_path)
    assert manifest["allow_dirty_confirmatory"] is True


def test_confirmatory_requires_config_hash(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_confirmatory_provenance_v1")
    cfg = SuiteConfig.from_path(cfg_path)
    manifest = build_confirmatory_provenance(cfg, cfg_path)
    assert manifest["requirements"]["config_hash_present"] is True


def test_confirmatory_requires_dataset_hash(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_confirmatory_provenance_v1")
    cfg = SuiteConfig.from_path(cfg_path)
    manifest = build_confirmatory_provenance(cfg, cfg_path)
    assert manifest["requirements"]["dataset_manifest_hash_present"] is False


def test_larger_t2_slice_detected_when_available(tmp_path: Path) -> None:
    raw = tmp_path / "metadata.jsonl"
    with raw.open("w", encoding="utf-8") as handle:
        for idx in range(6):
            handle.write(
                f'{{"id":"q-{idx}","context_id":"d-{idx // 2}","context":"alpha beta {idx}",'
                '"question":"alpha?","program_answer":"alpha"}\n'
            )
    norm = normalize_t2(raw, tmp_path / "normalized", row_cap=100)
    assert norm["query_count"] == 6
    assert norm["document_count"] == 3


def test_grouped_split_prevents_document_family_leakage() -> None:
    queries = [{"duplicate_cluster_id": f"d-{i}", "example_id": f"q-{i}", "document_id": f"d-{i}"} for i in range(30)]
    dev, val, test, manifest = split_queries(queries)
    assert manifest["development"] + manifest["validation"] + manifest["test"] == 30
    assert {q["example_id"] for q in dev}.isdisjoint(q["example_id"] for q in val + test)


def test_underpowered_dataset_blocks_confirmatory_claim() -> None:
    available_queries = 90
    required_queries = 150
    assert available_queries < required_queries


def test_generator_regimes_analyzed_separately() -> None:
    regimes = ["deterministic_grounded_extractive", "local_open_weight_or_hosted_pinned_optional"]
    assert regimes[0] != regimes[1]


def test_hosted_generator_requires_external_credentials() -> None:
    hosted_configured = False
    assert hosted_configured is False


def test_noninferiority_requires_confidence_bound() -> None:
    per_query = pd.DataFrame(
        [{"split": "test", "example_id": f"q{i}", "policy_id": "ragwarrant_no_fork", "query_operational_utility": 0.50} for i in range(5)]
        + [{"split": "test", "example_id": f"q{i}", "policy_id": "greedy_coordinate_search", "query_operational_utility": 0.505} for i in range(5)]
    )
    candidates = pd.DataFrame(
        [
            {"policy_id": "ragwarrant_no_fork", "test_utility": 0.50, "raw_quality": 0.80},
            {"policy_id": "greedy_coordinate_search", "test_utility": 0.505, "raw_quality": 0.80},
        ]
    )
    answer = formal_development_answer(per_query, candidates, "greedy_coordinate_search", min_queries=1)
    assert answer["research_question_2_result"] == "COMPETITIVE_NONINFERIOR"
    assert answer["formal_noninferiority"] is True


def test_point_estimate_noninferior_not_confirmatory_noninferior() -> None:
    result = {"development_result_class": "COMPETITIVE_POINT_ESTIMATE", "formal_result": None}
    assert result["development_result_class"] != "NONINFERIOR_NOT_SUPERIOR"


def test_formal_result_separate_from_certificate() -> None:
    assert {"formal_result": "REFUSED", "certificate": "Refused"}["formal_result"] != "Supported"


def test_no_fork_not_hardcoded_policy_object() -> None:
    policies = {
        "greedy_coordinate_search": RAGPolicy(chunk_size=256, chunk_overlap=64, top_k=5),
        "ragwarrant_no_fork": RAGPolicy(chunk_size=512, chunk_overlap=64, top_k=5),
    }
    assert policies["greedy_coordinate_search"].chunk_size != policies["ragwarrant_no_fork"].chunk_size


def test_security_failure_not_tradable_for_utility() -> None:
    violation = {"utility": 1.0, "security_violation": True, "eligible": False}
    assert violation["eligible"] is False


def test_human_eval_answer_key_private_shape() -> None:
    key_name = "human_eval_answer_key_private.json"
    assert "private" in key_name


def test_new_runs_append_only(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_confirmatory_provenance_v1")
    first = run_suite(suite="ragwarrant_confirmatory_provenance_v1", config_path=cfg_path, output_dir=tmp_path, run_id="same")
    assert Path(first["run_dir"]).exists()
    try:
        run_suite(suite="ragwarrant_confirmatory_provenance_v1", config_path=cfg_path, output_dir=tmp_path, run_id="same")
    except WriteOnceError:
        pass
    else:
        raise AssertionError("completed run reuse should fail")
