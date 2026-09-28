# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ragwarrant.research import benchmark as benchmark_module
from ragwarrant.research.benchmark import EVENT_FIELDS, run_benchmark
from ragwarrant.research.simulator import load_config


CONFIG = Path("configs/research/false_promotion_benchmark_v1.yaml")


def _tiny_config() -> dict:
    config = load_config(CONFIG)
    selected = {"one_clearly_safe", "hidden_group_regression"}
    config["scenarios"] = [
        scenario for scenario in config["scenarios"] if scenario["scenario_id"] in selected
    ]
    for scenario in config["scenarios"]:
        scenario["sample_sizes"] = [16, 32]
    config["profiles"]["CI"] = {"replicate_count": 3, "bootstrap_resamples": 16}
    config["trial_sample_limit"] = 3
    return config


def test_same_config_and_seed_produce_identical_aggregates() -> None:
    config = _tiny_config()
    first = run_benchmark(copy.deepcopy(config), "CI", master_seed=123)
    repeat = run_benchmark(copy.deepcopy(config), "CI", master_seed=123)
    assert first == repeat


def test_different_seed_changes_canonical_evidence() -> None:
    config = _tiny_config()
    first = run_benchmark(copy.deepcopy(config), "CI", master_seed=123)
    different = run_benchmark(copy.deepcopy(config), "CI", master_seed=124)
    first_hashes = {row["evidence_hash"] for row in first["trial_summary_sample_rows"]}
    different_hashes = {row["evidence_hash"] for row in different["trial_summary_sample_rows"]}
    assert first_hashes != different_hashes


def test_method_order_does_not_change_results() -> None:
    config = _tiny_config()
    first = run_benchmark(copy.deepcopy(config), "CI", master_seed=123)
    reordered = copy.deepcopy(config)
    reordered["methods"].reverse()
    second = run_benchmark(reordered, "CI", master_seed=123)
    assert first["method_summary_rows"] == second["method_summary_rows"]
    assert first["trial_summary_sample_rows"] == second["trial_summary_sample_rows"]


def test_every_executed_method_in_trial_uses_same_evidence_hash() -> None:
    result = run_benchmark(_tiny_config(), "CI", master_seed=123)
    by_trial: dict[str, set[str]] = {}
    for row in result["trial_summary_sample_rows"]:
        key = str(row["evidence_trial_identity"])
        by_trial.setdefault(key, set()).add(str(row["evidence_hash"]))
        assert key.startswith("v2|CI|")
        assert row["seed_schedule_version"] == 2
    assert by_trial
    assert all(len(hashes) == 1 for hashes in by_trial.values())


def test_public_method_roles_and_unsupported_denominators_are_explicit() -> None:
    result = run_benchmark(_tiny_config(), "CI", master_seed=123)
    manifest = result["manifest"]
    assert "oracle_safe_objective" not in manifest["truth_isolated_method_ids"]
    assert "current_ragwarrant_adapter" not in manifest["executed_method_ids"]
    assert manifest["truth_access_method_ids"] == ["oracle_safe_objective"]
    assert manifest["truth_isolated_method_accessed_population_truth"] is False
    assert manifest["research_candidate_method_ids"] == []
    assert {
        "always_block",
        "oracle_safe_objective",
        "naive_point_estimate",
        "corrected_paired_bootstrap_gate",
    } == set(manifest["benchmark_control_method_ids"])
    assert all(
        row["method_id"] != "current_ragwarrant_adapter"
        for row in result["method_summary_rows"]
    )


def test_reclassified_comparators_still_execute_and_produce_result_rows() -> None:
    result = run_benchmark(_tiny_config(), "CI", master_seed=123)
    comparator_ids = {"naive_point_estimate", "corrected_paired_bootstrap_gate"}
    assert comparator_ids <= set(result["manifest"]["executed_method_ids"])
    assert comparator_ids <= set(result["manifest"]["benchmark_control_method_ids"])
    rows = [
        row
        for row in result["method_summary_rows"]
        if row["method_id"] in comparator_ids
    ]
    assert {row["method_id"] for row in rows} == comparator_ids
    assert all(row["trial_count"] > 0 for row in rows)
    assert all(row["benchmark_control_only"] is True for row in rows)


def test_aggregate_count_rate_identities_hold() -> None:
    result = run_benchmark(_tiny_config(), "CI", master_seed=123)
    assert result["manifest"]["trial_count_total"] == 12
    assert result["manifest"]["method_trial_row_count_total"] == 48
    for row in result["method_summary_rows"]:
        for event in EVENT_FIELDS:
            assert row[f"{event}_rate"] == row[f"{event}_count"] / row["trial_count"]


def test_shift_summary_lists_only_candidates_with_changed_truth() -> None:
    config = load_config(CONFIG)
    config["scenarios"] = [
        scenario
        for scenario in config["scenarios"]
        if scenario["scenario_id"] == "development_confirmatory_shift"
    ]
    config["scenarios"][0]["sample_sizes"] = [12, 24]
    config["profiles"]["CI"] = {"replicate_count": 1, "bootstrap_resamples": 8}
    result = run_benchmark(config, "CI", master_seed=5)
    summary = json.loads(result["scenario_summary_rows"][0]["scenario_truth_summary"])
    assert summary["development_to_confirmatory_truth_changed_policy_ids"] == [
        "shifted_candidate"
    ]


def test_deployable_methods_receive_only_opaque_candidate_and_scenario_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _tiny_config()
    config["profiles"]["CI"] = {"replicate_count": 1, "bootstrap_resamples": 8}
    original_registry = benchmark_module.method_registry()
    delegate = original_registry["naive_point_estimate"]
    seen: list[tuple[str, tuple[str, ...]]] = []

    class SpyMethod:
        def evaluate(self, evidence, policy, method_seed=0):
            seen.append((evidence.scenario_id, evidence.policy_ids))
            return delegate.evaluate(evidence, policy, method_seed)

    original_registry["naive_point_estimate"] = SpyMethod()
    monkeypatch.setattr(benchmark_module, "method_registry", lambda: original_registry)
    result = benchmark_module.run_benchmark(config, "CI", master_seed=81)

    assert seen
    for scenario_id, policy_ids in seen:
        assert scenario_id == "scenario_opaque"
        assert all(policy_id.startswith("policy_") for policy_id in policy_ids)
        joined = " ".join(policy_ids).lower()
        assert "safe" not in joined
        assert "unsafe" not in joined
        assert "inferior" not in joined
        assert "harm" not in joined
    naive_rows = [
        row
        for row in result["trial_summary_sample_rows"]
        if row["method_id"] == "naive_point_estimate"
    ]
    assert all("policy_" not in str(row["certified_policy_ids"]) for row in naive_rows)
    assert all(
        str(row["evidence_trial_identity"]).startswith("v2|CI|")
        for row in naive_rows
    )


@pytest.mark.parametrize("invalid_seed", [True, 1.5, "7"])
def test_master_seed_is_not_silently_coerced(invalid_seed) -> None:
    with pytest.raises(ValueError, match="nonnegative integer"):
        run_benchmark(_tiny_config(), "CI", master_seed=invalid_seed)


def test_trial_sample_limit_is_not_silently_coerced() -> None:
    config = _tiny_config()
    config["trial_sample_limit"] = True
    with pytest.raises(ValueError, match="nonnegative integer"):
        run_benchmark(config, "CI")
