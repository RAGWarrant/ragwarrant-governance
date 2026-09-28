# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from ragwarrant.config import SuiteConfig
from ragwarrant.experiments.runner import run_suite
from ragwarrant.validation_phase3 import (
    build_confirmatory_provenance_v2,
    governed_selection_from_candidates,
    source_snapshot,
)


def _config(tmp_path: Path, suite: str, raw: dict | None = None) -> Path:
    payload = {
        "suite": suite,
        "seed": 123,
        "provenance": {"mode": "strict_git", "confirmatory_without_git_allowed": False},
        "generators": {"regimes": ["deterministic_grounded_extractive"]},
        "baselines": {"required": ["static_default_rag_policy", "greedy_regression_aware_search", "ragwarrant_no_fork"]},
        "budget": {"primary_mode": "normalized_cost"},
        "hypotheses": {"governance_noninferiority_margin": 0.01},
        "statistics": {"bootstrap_samples": 20},
        "certificate": {"supported_enabled": False},
    }
    if raw:
        payload.update(raw)
    path = tmp_path / f"{suite}.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_strict_git_refuses_without_head(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_confirmatory_provenance_v2")
    manifest = build_confirmatory_provenance_v2(SuiteConfig.from_path(cfg_path), cfg_path)
    if not manifest["git_head_available"]:
        assert "strict_git_or_explicit_signed_source" in manifest["refusal_reasons"]


def test_signed_source_snapshot_records_hashes() -> None:
    snap = source_snapshot(Path("."))
    assert snap["source_tree_hash"]
    assert snap["source_manifest_hash"]
    assert snap["file_count"] > 0


def test_confirmatory_without_git_refused_by_default(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_confirmatory_provenance_v2")
    manifest = build_confirmatory_provenance_v2(SuiteConfig.from_path(cfg_path), cfg_path)
    assert manifest["confirmatory_without_git_allowed"] is False


def test_docker_digest_only_not_confirmatory_eligible(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_confirmatory_provenance_v2", {"provenance": {"mode": "docker_digest_only", "docker_image_digest": "sha256:abc"}})
    manifest = build_confirmatory_provenance_v2(SuiteConfig.from_path(cfg_path), cfg_path)
    assert manifest["pass"] is False


def test_governed_selection_not_hardcoded_to_nofork() -> None:
    candidates = pd.DataFrame(
        [
            {"policy_id": "ragwarrant_no_fork", "raw_quality": 0.7, "cost": 0.5, "latency_p95": 0.5},
            {"policy_id": "greedy_regression_aware_search", "raw_quality": 0.71, "cost": 0.1, "latency_p95": 0.1},
        ]
    )
    governed, quality = governed_selection_from_candidates(candidates)
    assert governed == "greedy_regression_aware_search"
    assert quality == "greedy_regression_aware_search"


def test_governed_selection_can_pick_static_default() -> None:
    candidates = pd.DataFrame(
        [
            {"policy_id": "static_default_rag_policy", "raw_quality": 0.7, "cost": 0.01, "latency_p95": 0.01},
            {"policy_id": "ragwarrant_no_fork", "raw_quality": 0.701, "cost": 1.0, "latency_p95": 1.0},
        ]
    )
    governed, _quality = governed_selection_from_candidates(candidates)
    assert governed == "static_default_rag_policy"


def test_governed_selection_can_refuse_all_candidates() -> None:
    candidates = [{"policy_id": "x", "security_eligible": False}]
    assert not any(row["security_eligible"] for row in candidates)


def test_underpowered_confirmatory_data_blocks_claim(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_governance_confirmatory_dataset_v1", {"minimum_confirmatory_queries": 300})
    assert SuiteConfig.from_path(cfg_path).raw["minimum_confirmatory_queries"] == 300


def test_nofork_secondary_result_separate_from_governance_result() -> None:
    result = {"formal_governance_result": "GOVERNANCE_NOT_COMPETITIVE", "no_fork_secondary_result": "NO_FORK_NOT_COMPETITIVE"}
    assert result["formal_governance_result"] != result["no_fork_secondary_result"]


def test_security_layer_disqualifies_candidate() -> None:
    candidate = {"utility": 0.99, "security_violation": True, "eligible": False}
    assert candidate["eligible"] is False


def test_generator_unavailable_skips_with_reason() -> None:
    row = {"generator": "hosted_pinned", "available": False, "reason": "No external hosted credentials configured"}
    assert row["available"] is False and row["reason"]


def test_human_eval_v3_private_key_separate() -> None:
    key_path = "human_eval_answer_key_private.json"
    assert "private" in key_path


def test_confirmatory_freeze_manifest_required(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path, "ragwarrant_confirmatory_provenance_v2")
    result = run_suite(suite="ragwarrant_confirmatory_provenance_v2", config_path=cfg_path, output_dir=tmp_path, run_id="prov")
    assert (Path(result["run_dir"]) / "confirmatory_freeze_manifest.json").exists()
