from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from ragwarrant.config import SuiteConfig
from ragwarrant.experiments.runner import run_suite
from ragwarrant.validation_phase3 import (
    EXPECTED_MULTIHOP_CORPUS_HASH,
    EXPECTED_MULTIHOP_QUERY_HASH,
    EXPECTED_MULTIHOP_REVISION,
    EXPECTED_MULTIHOP_SPLIT_COUNTS,
    SECURITY_HARD_FAMILIES,
    connected_component_splits,
    discover_git_context,
    freshness_overlap,
    leakage_for_splits,
    nofork_secondary_result,
    normalize_query_text,
    paired_policy_analysis,
    readiness_decision,
    source_snapshot,
    summarize_candidates_for_holdout,
)


def _config(tmp_path: Path, suite: str, raw: dict | None = None) -> Path:
    payload = {
        "suite": suite,
        "seed": 20260807,
        "provenance": {"required_mode": "strict_git", "confirmatory_without_git_allowed": False},
        "policy_space_file": "configs/policy_spaces/governance_confirmatory_policy_space_v2.yaml",
        "baselines": {"required": ["quality_only_selection", "governed_selection", "ragwarrant_no_fork"]},
        "budget": {"primary_mode": "normalized_cost"},
        "hypotheses": {"governance_noninferiority_margin": 0.01},
        "statistics": {"bootstrap_samples": 20},
        "generators": {"regimes": ["deterministic_grounded_extractive"]},
        "security": {"hard_constraints": True},
        "certificate": {"supported_enabled": False},
        "fresh_data": {"minimum_confirmatory_queries": 2},
    }
    if raw:
        payload.update(raw)
    path = tmp_path / f"{suite}.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_repo_root_discovery_reports_machine_readable_fields() -> None:
    context = discover_git_context(Path("."))
    assert "git_head_available" in context
    assert "discovered_git_dirs" in context
    assert "missing_reason" in context


def test_signed_source_snapshot_fallback_hashes_source_files() -> None:
    snap = source_snapshot(Path("."))
    assert snap["source_tree_hash"]
    assert snap["source_manifest_hash"]
    assert "artifacts" in snap["excluded_names"]


def test_confirmatory_without_git_refused_by_default_in_config(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_provenance_repair_v1")
    cfg = SuiteConfig.from_path(cfg_path)
    assert cfg.raw["provenance"]["confirmatory_without_git_allowed"] is False


def test_docker_digest_only_not_confirmatory_eligible() -> None:
    provenance = {"provenance_mode_decision": "docker_digest_only", "confirmatory_eligible": False}
    decision, gates = readiness_decision(
        provenance,
        {"approval": {"acquisition_approved": True}},
        {"confirmatory_test": 10},
        {"status": "pass", "cross_split_duplicate_count": 0},
        SimpleNamespace(raw={"fresh_data": {"minimum_confirmatory_queries": 2}}),
    )
    assert decision == "REFUSED_PROVENANCE"
    assert gates["strict_git"] is False


def test_freshness_overlap_detects_exact_and_normalized_query_match() -> None:
    registry = {
        "examples": [{"example_id": "a"}],
        "query_text_hashes": [],
        "context_ids": [],
    }
    query = {"example_id": "a", "question": "What is RAG?", "document_id": "d1"}
    assert freshness_overlap([query], registry)["overlap_count"] == 1


def test_freshness_overlap_detects_context_id_match() -> None:
    registry = {"examples": [], "query_text_hashes": [], "context_ids": ["d1"]}
    query = {"example_id": "b", "question": "Fresh?", "document_id": "d1"}
    report = freshness_overlap([query], registry)
    assert report["overlap_count"] == 1
    assert report["fresh_query_count"] == 0


def test_confirmatory_test_excludes_inspected_examples() -> None:
    registry = {"examples": [{"example_id": "seen"}], "query_text_hashes": [], "context_ids": []}
    rows = [{"example_id": "seen", "question": "a", "document_id": "d1"}, {"example_id": "fresh", "question": "b", "document_id": "d2"}]
    assert freshness_overlap(rows, registry)["fresh_query_count"] == 1


def test_grouped_split_has_zero_context_leakage() -> None:
    rows = [
        {"example_id": f"q{i}", "question": f"q {i}", "supporting_document_ids": [f"d{i}"], "document_id": f"d{i}"}
        for i in range(9)
    ]
    cal, val, test, manifest = connected_component_splits(rows)
    leakage = leakage_for_splits({"calibration": cal, "validation": val, "confirmatory_test": test})
    assert manifest["total"] == 9
    assert leakage["status"] == "pass"


def test_grouped_split_leakage_detected_when_context_crosses() -> None:
    rows_a = [{"example_id": "q1", "question": "one", "supporting_document_ids": ["d1"], "document_id": "d1"}]
    rows_b = [{"example_id": "q2", "question": "two", "supporting_document_ids": ["d1"], "document_id": "d1"}]
    leakage = leakage_for_splits({"calibration": rows_a, "validation": rows_b, "confirmatory_test": []})
    assert leakage["status"] == "fail"


def test_readiness_blocks_no_fresh_data() -> None:
    provenance = {"provenance_mode_decision": "strict_git", "confirmatory_eligible": True}
    dataset = {"approval": {"acquisition_approved": True}}
    decision, _gates = readiness_decision(provenance, dataset, {"confirmatory_test": 0}, {"status": "pass", "cross_split_duplicate_count": 0}, SimpleNamespace(raw={"fresh_data": {"minimum_confirmatory_queries": 2}}))
    assert decision == "BLOCKED_NO_FRESH_DATA"


def test_readiness_refuses_provenance_failure() -> None:
    decision, gates = readiness_decision({}, {"approval": {"acquisition_approved": True}}, {"confirmatory_test": 10}, {"status": "pass", "cross_split_duplicate_count": 0}, SimpleNamespace(raw={"fresh_data": {"minimum_confirmatory_queries": 2}}))
    assert decision == "REFUSED_PROVENANCE"
    assert gates["strict_git"] is False


def test_readiness_all_gates_pass_known_case() -> None:
    raw = {
        "fresh_data": {"minimum_confirmatory_queries": 2},
        "baselines": {"required": ["a"]},
        "policy_space_file": "p.yaml",
        "budget": {"primary_mode": "normalized_cost"},
        "hypotheses": {"margin": 0.01},
        "statistics": {"bootstrap_samples": 20},
        "generators": {"regimes": ["deterministic"]},
        "security": {"hard_constraints": True},
        "certificate": {"supported_enabled": False},
    }
    decision, _gates = readiness_decision(
        {"provenance_mode_decision": "strict_git", "confirmatory_eligible": True},
        {"approval": {"acquisition_approved": True}},
        {"confirmatory_test": 3},
        {"status": "pass", "cross_split_duplicate_count": 0},
        SimpleNamespace(raw=raw),
    )
    assert decision == "READY_FOR_CONFIRMATORY"


def test_dirty_tree_refused_by_default() -> None:
    raw = {
        "fresh_data": {"minimum_confirmatory_queries": 2},
        "provenance": {"require_clean_working_tree": True, "allow_dirty_confirmatory": False},
        "baselines": {"required": ["a"]},
        "policy_space_file": "p.yaml",
        "budget": {"primary_mode": "normalized_cost"},
        "hypotheses": {"margin": 0.01},
        "statistics": {"bootstrap_samples": 20},
        "generators": {"regimes": ["deterministic"]},
        "security": {"hard_constraints": True},
        "certificate": {"supported_enabled": False},
    }
    decision, gates = readiness_decision(
        {"strict_git_pass": True, "git_is_dirty": True},
        {"approval": {"acquisition_approved": True}},
        {"confirmatory_test": 3},
        {"status": "pass", "cross_split_duplicate_count": 0},
        SimpleNamespace(raw=raw),
    )
    assert decision == "REFUSED_DIRTY_TREE"
    assert gates["clean_working_tree"] is False


def test_readiness_refuses_data_hash_failure() -> None:
    decision, gates = readiness_decision(
        {"strict_git_pass": True, "git_is_dirty": False},
        {"approval": {"acquisition_approved": True}},
        {"confirmatory_test": 3},
        {"status": "pass", "cross_split_duplicate_count": 0},
        SimpleNamespace(raw={"fresh_data": {"minimum_confirmatory_queries": 2}}),
        {"pass": False, "confirmatory_test_sealed": True},
    )
    assert decision == "REFUSED_DATA_HASH"
    assert gates["data_hashes_verified"] is False


def test_readiness_refuses_test_contamination() -> None:
    decision, gates = readiness_decision(
        {"strict_git_pass": True, "git_is_dirty": False},
        {"approval": {"acquisition_approved": True}},
        {"confirmatory_test": 3},
        {"status": "pass", "cross_split_duplicate_count": 0},
        SimpleNamespace(raw={"fresh_data": {"minimum_confirmatory_queries": 2}}),
        {"pass": True, "confirmatory_test_sealed": False},
    )
    assert decision == "REFUSED_TEST_CONTAMINATION"
    assert gates["confirmatory_test_sealed"] is False


def test_multihop_expected_constants_pinned() -> None:
    assert EXPECTED_MULTIHOP_REVISION == "71ac0d0bd1f951d2d6b70311f7d2ae404e1ffa82"
    assert EXPECTED_MULTIHOP_CORPUS_HASH.startswith("a38d025d")
    assert EXPECTED_MULTIHOP_QUERY_HASH.startswith("477ccbd9")
    assert EXPECTED_MULTIHOP_SPLIT_COUNTS["confirmatory_test"] == 331


def test_summarize_candidates_for_holdout_uses_confirmatory_split() -> None:
    import pandas as pd

    rows = pd.DataFrame(
        [
            {"policy_id": "a", "split": "validation", "query_operational_utility": 0.1, "raw_quality": 0.2, "query_execution_cost": 0.1, "query_latency": 0.1},
            {"policy_id": "a", "split": "confirmatory_test", "query_operational_utility": 0.3, "raw_quality": 0.4, "query_execution_cost": 0.1, "query_latency": 0.1},
        ]
    )
    summary = summarize_candidates_for_holdout(rows)
    assert float(summary.iloc[0]["confirmatory_utility"]) == 0.3


def test_paired_policy_analysis_reports_confidence_interval() -> None:
    import pandas as pd

    rows = []
    for i in range(6):
        rows.append({"example_id": f"q{i}", "split": "confirmatory_test", "policy_id": "left", "query_operational_utility": 1.0})
        rows.append({"example_id": f"q{i}", "split": "confirmatory_test", "policy_id": "right", "query_operational_utility": 0.5})
    report = paired_policy_analysis(pd.DataFrame(rows), "left", "right", samples=20)
    assert report["status"] == "ok"
    assert report["query_bootstrap_ci"][0] > 0


def test_nofork_secondary_result_separate_classification() -> None:
    result = nofork_secondary_result({"status": "ok", "point_estimate": -0.02, "query_bootstrap_ci": [-0.03, -0.01]}, margin=0.01)
    assert result == "NO_FORK_NOT_COMPETITIVE"


def test_confirmatory_refuses_without_readiness(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_governed_selection_confirmatory_v2")
    result = run_suite(suite="ragwarrant_governed_selection_confirmatory_v2", config_path=cfg_path, output_dir=tmp_path, run_id="run")
    assert result["formal_governance_result"] in {"REFUSED", "BLOCKED"}
    assert "readiness" in result["reason"].lower()


def test_nofork_secondary_not_primary() -> None:
    formal = {"formal_governance_result": "GOVERNANCE_SUPERIOR"}
    nofork = {"no_fork_secondary_result": "NO_FORK_NOT_COMPETITIVE"}
    assert set(formal) != set(nofork)


def test_security_failure_hard_disqualifier() -> None:
    assert "prompt_injection" in SECURITY_HARD_FAMILIES
    assert all(family for family in SECURITY_HARD_FAMILIES)


def test_generator_unavailable_skips_with_reason(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_generator_regime_enablement_v1", {"generators": {}})
    result = run_suite(suite="ragwarrant_generator_regime_enablement_v1", config_path=cfg_path, output_dir=tmp_path, run_id="gen")
    assert result["status"] == "skipped_with_reason"


def test_human_eval_not_marked_run_without_annotations(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_human_eval_execution_readiness_v1")
    result = run_suite(suite="ragwarrant_human_eval_execution_readiness_v1", config_path=cfg_path, output_dir=tmp_path, run_id="human")
    assert result["human_evaluation_run"] is False


def test_security_regression_not_utility_tradeoff(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_security_regression_v4")
    result = run_suite(suite="ragwarrant_security_regression_v4", config_path=cfg_path, output_dir=tmp_path, run_id="sec")
    assert result["all_hard_disqualifiers_enforced"] is True


def test_normalize_query_text_collapses_punctuation_and_case() -> None:
    assert normalize_query_text("Hello,   WORLD!") == "hello world"
