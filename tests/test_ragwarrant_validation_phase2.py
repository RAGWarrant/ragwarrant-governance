from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from ragwarrant.config import SuiteConfig
from ragwarrant.experiments.runner import run_suite
from ragwarrant.phase2 import (
    dataset_capability_rows,
    freeze_prerequisites,
    paired_bootstrap,
    statistical_audit_payload,
)
from ragwarrant.real_rag import issue_real_rag_certificate
from ragwarrant.utils.files import write_json


def _parent_run(tmp_path: Path) -> Path:
    parent = tmp_path / "parent"
    parent.mkdir()
    per_query = pd.DataFrame(
        [
            {
                "seed": seed,
                "example_id": f"q-{idx}",
                "policy_id": policy,
                "source_dataset": "source_a" if idx < 3 else "source_b",
                "per_query_utility_proxy": base + (0.05 if policy == "ragwarrant_no_fork" else 0.0),
            }
            for seed in [1, 2]
            for idx, base in enumerate([0.50, 0.55, 0.60, 0.65])
            for policy in ["ragwarrant_no_fork", "best_single_policy_on_validation"]
        ]
    )
    candidate = pd.DataFrame(
        [
            {"policy_id": "ragwarrant_no_fork", "seed": 1, "raw_quality": 0.8, "cost": 0.2, "latency_p95": 0.1},
            {"policy_id": "best_single_policy_on_validation", "seed": 1, "raw_quality": 0.75, "cost": 0.2, "latency_p95": 0.1},
        ]
    )
    per_query.to_csv(parent / "per_query_metrics.csv", index=False)
    candidate.to_csv(parent / "candidate_policy_metrics.csv", index=False)
    write_json(parent / "run_manifest.json", {"run_id": "parent", "dataset_hash": "abc", "evidence_mode": "offline_public_real_rag"})
    return parent


def _suite_config(tmp_path: Path, suite: str, extra: dict | None = None) -> Path:
    payload = {
        "suite": suite,
        "seed": 20260805,
        "dataset": {},
        "policy_space": {},
        "objectives": {},
        "baselines": [],
        "certificate": {"supported_enabled": False},
        "output": {"append_only": True},
    }
    if extra:
        payload.update(extra)
    path = tmp_path / f"{suite}.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    return path


def test_bootstrap_uses_row_level_input_when_available(tmp_path: Path) -> None:
    payload = statistical_audit_payload(_parent_run(tmp_path), bootstrap_samples=50)
    assert payload["diagnostics"]["rows"] == 8
    assert payload["diagnostics"]["bootstrap_used_row_level_values"] is True


def test_zero_width_ci_requires_explanation(tmp_path: Path) -> None:
    payload = statistical_audit_payload(_parent_run(tmp_path), bootstrap_samples=50)
    assert payload["audit_result"] == "audit_passed_zero_width_legitimate_but_low_information"
    assert "constant additive policy deltas" in payload["zero_width_explanation"]


def test_dataset_blocked_bootstrap_differs_from_scalar_reuse() -> None:
    values = np.array([0.01, 0.03, 0.05])
    report = paired_bootstrap(values, samples=100, seed=1)
    assert report["ci_low"] < report["ci_high"]


def test_probability_of_superiority_known_case(tmp_path: Path) -> None:
    payload = statistical_audit_payload(_parent_run(tmp_path), bootstrap_samples=20)
    assert payload["diagnostics"]["count_positive_deltas"] == payload["diagnostics"]["rows"]


def test_dataset_balanced_weighting_known_case(tmp_path: Path) -> None:
    payload = statistical_audit_payload(_parent_run(tmp_path), bootstrap_samples=20)
    assert payload["resampling_reports"]["dataset_blocked"]["unit_count"] == 2


def test_challenge_unlock_requires_freeze_manifest(tmp_path: Path) -> None:
    config = _suite_config(
        tmp_path,
        "ragwarrant_challenge_unlock_v1",
        {"parent_run": {"run_dir": str(_parent_run(tmp_path))}, "statistical_audit_result": None},
    )
    result = run_suite(suite="ragwarrant_challenge_unlock_v1", config_path=config, output_dir=tmp_path, run_id="challenge")
    assert result["status"] == "Refused"
    assert result["challenge_evaluated"] is False


def test_challenge_refuses_dirty_tree_by_default(tmp_path: Path) -> None:
    cfg = SuiteConfig.from_path(
        _suite_config(
            tmp_path,
            "ragwarrant_challenge_unlock_v1",
            {
                "parent_run": {"run_dir": str(_parent_run(tmp_path))},
                "statistical_audit_result": "audit_passed_row_level_uncertainty_valid",
                "allow_dirty_challenge_unlock": False,
            },
        )
    )
    freeze = freeze_prerequisites(cfg)
    assert "working_tree_clean_or_allowed" in freeze["requirements"]


def test_dataset_acquisition_records_revision(tmp_path: Path) -> None:
    config = _suite_config(
        tmp_path,
        "ragwarrant_public_data_acquisition_v2",
        {"sources": [{"name": "fixture_public", "revision": "abc123", "license": "CC-BY-4.0", "fixture_acquire": True, "redistribution_status": "redistributable"}]},
    )
    result = run_suite(suite="ragwarrant_public_data_acquisition_v2", config_path=config, output_dir=tmp_path, run_id="data")
    revision_lock = json.loads((Path(result["run_dir"]) / "dataset_revision_lock.json").read_text(encoding="utf-8"))
    assert revision_lock["fixture_public"] == "abc123"


def test_unlicensed_dataset_refused_or_excluded() -> None:
    rows = [{"source_name": "x", "license": "unknown", "acquired": False, "redistribution_status": "review_required"}]
    caps = dataset_capability_rows(rows, SuiteConfig("s", 1, {}, {}, {}, [], {}, {}, {"sources": [{"name": "x", "has_corpus": True, "has_queries": True}]}))
    assert caps[0]["has_license_usable_for_research"] is False
    assert caps[0]["end_to_end_corpus_backed_eligible"] is False


def test_response_only_dataset_not_marked_end_to_end_eligible() -> None:
    rows = [{"source_name": "ragtruth", "license": "unknown", "acquired": False, "redistribution_status": "review_required"}]
    cfg = SuiteConfig("s", 1, {}, {}, {}, [], {}, {}, {"sources": [{"name": "ragtruth", "has_generated_responses": True, "has_corpus": False}]})
    assert dataset_capability_rows(rows, cfg)[0]["end_to_end_corpus_backed_eligible"] is False


def test_end_to_end_public_mode_requires_real_corpus(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_suite(
            suite="ragwarrant_end_to_end_public_confirmatory_v1",
            config_path=Path("configs/experiments/ragwarrant_end_to_end_public_confirmatory_v1_development.yaml"),
            output_dir=tmp_path,
            run_id="e2e-public",
        )


def test_end_to_end_smoke_runs_without_external_keys(tmp_path: Path) -> None:
    result = run_suite(
        suite="ragwarrant_end_to_end_public_confirmatory_v1",
        config_path=Path("configs/experiments/ragwarrant_end_to_end_public_confirmatory_v1_smoke.yaml"),
        output_dir=tmp_path,
        run_id="e2e-smoke",
    )
    cert = json.loads((Path(result["run_dir"]) / "certificate.json").read_text(encoding="utf-8"))
    assert cert["status"] == "Inconclusive"


def test_prompt_injection_blocks_promotion(tmp_path: Path) -> None:
    result = run_suite(
        suite="ragwarrant_robustness_security_v1",
        config_path=Path("configs/experiments/ragwarrant_robustness_security_v1.yaml"),
        output_dir=tmp_path,
        run_id="robust",
    )
    report = json.loads((Path(result["run_dir"]) / "security_constraint_report.json").read_text(encoding="utf-8"))
    assert "prompt_injection" in report["blocked_families"]


def test_governance_replay_uses_frozen_outputs(tmp_path: Path) -> None:
    parent = tmp_path / "e2e-parent"
    parent.mkdir()
    pd.DataFrame(
        [
            {"policy_id": "static_default_rag_policy", "raw_quality": 0.9, "cost": 0.1, "latency_p95": 0.1, "protected_subset_score": 0.9, "regression_delta": 0.0, "skipped": False},
            {"policy_id": "ragwarrant_no_fork", "raw_quality": 0.8, "cost": 0.2, "latency_p95": 0.2, "protected_subset_score": 0.8, "regression_delta": 0.0, "skipped": False},
        ]
    ).to_csv(parent / "candidate_policy_metrics.csv", index=False)
    write_json(parent / "run_manifest.json", {"run_id": "e2e-parent", "dataset_hash": "abc"})
    config = _suite_config(tmp_path, "ragwarrant_end_to_end_governance_replay_v1", {"parent_run": {"run_dir": str(parent)}})
    result = run_suite(suite="ragwarrant_end_to_end_governance_replay_v1", config_path=config, output_dir=tmp_path, run_id="replay")
    stages = json.loads((Path(result["run_dir"]) / "end_to_end_governance_stage_results.json").read_text(encoding="utf-8"))
    assert stages["parent_run_dir"] == str(parent)


def test_supported_certificate_disabled_phase2() -> None:
    cert = issue_real_rag_certificate(
        cfg=SuiteConfig("s", 1, {}, {}, {}, [], {}, {}, {"certificate": {"supported_enabled": False}}),
        profile="confirmatory",
        evidence_mode="offline_public_real_rag",
        leakage={"status": "pass"},
        budget={"pass": True},
        baseline_eligibility={"required_missing": []},
        primary_selection={"status": "selected"},
        stats={"paired_bootstrap_ci": {"mean_delta": 0.02, "ci_low": 0.01}, "dataset_balanced": {"mean_delta": 0.02}, "seed_level_win_tie_loss": {"wins": 5, "n": 5}},
        regression={"pass": True},
        sensitivity={"utility_fragile": False},
        no_overwrite_status="append_only_confirmed",
    )
    assert cert["status"] == "Candidate external signal"
    assert cert["supported_enabled"] is False
