from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

import ragwarrant.validation_phase3 as vp
from ragwarrant.experiments.runner import run_suite

PARENT_ID = "ragwarrant_crag_mock_api_validation_v1_20260809-165415-92d8c0edd4"


@pytest.fixture(autouse=True)
def _isolate_artifact_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)


def _config(tmp_path: Path, suite: str, extra: dict | None = None) -> Path:
    payload = {"suite": suite, "seed": 20260809, "parent_run": {"run_id": PARENT_ID}}
    if extra:
        payload.update(extra)
    path = tmp_path / f"{suite}.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fake_parent(root: Path, run_id: str = PARENT_ID) -> Path:
    run = root / run_id
    run.mkdir(parents=True)
    _write_json(
        run / "crag_mock_api_validation_manifest.json",
        {
            "result": "MOCK_API_VALIDATION_GOVERNANCE_SUPERIOR",
            "governed_winner": "top_k_low",
            "quality_only_winner": "greedy_regression_aware_search",
            "validation_query_count": 6,
            "confirmatory_query_count": 6,
            "api_call_count": 36,
            "rag_compass_rank": 3,
            "certificate": "Candidate external signal",
        },
    )
    _write_json(
        run / "crag_mock_api_statistical_analysis.json",
        {
            "status": "ok",
            "point_estimate": 0.005,
            "query_bootstrap_ci": [0.004, 0.006],
            "query_win_tie_loss": {"win": 6, "tie": 0, "loss": 0},
        },
    )
    _write_json(run / "crag_mock_api_budget_latency_report.json", {"api_call_count": 36, "failure_rate_mean": 0.0})
    _write_json(run / "crag_mock_api_utility_sensitivity.json", {"governance_superior_frequency": 14, "grid_count": 15})
    _write_json(run / "crag_mock_api_validation_freeze_manifest.json", {"queries_sha256": "abc", "query_ids": [f"q{i}" for i in range(12)], "seed": 20260809})
    rows = []
    sample = []
    for idx in range(12):
        split = "validation" if idx < 6 else "confirmatory_test"
        qid = f"q{idx}"
        sample.append({"query_id": qid, "query_text": f"FAKE_SYNTHETIC_QUERY_FOR_TESTING_{idx}", "domain": "finance", "question_type": "simple", "static_or_dynamic": "slow"})
        for policy, raw, budget, latency, calls in [
            ("top_k_low", 0.80, 0.50, 1.0, 1),
            ("greedy_regression_aware_search", 0.81, 2.00, 10.0, 2),
            ("rag_compass", 0.79, 0.60, 2.0, 1),
        ]:
            rows.append(
                {
                    "example_id": qid,
                    "query_id": qid,
                    "split": split,
                    "domain": "finance",
                    "question_type": "simple",
                    "static_or_dynamic": "slow",
                    "policy_id": policy,
                    "display_name": vp.optimizer_display_name(policy),
                    "route_plan": "/finance/get_company_name",
                    "domain_route_plan": "finance",
                    "api_call_count": calls,
                    "successful_call_count": calls,
                    "failure_rate": 0.0,
                    "result_count": 10,
                    "raw_quality": raw,
                    "budget_units": budget,
                    "latency_ms": latency,
                    "query_operational_utility": raw - 0.01 * budget - 0.001 * (latency / 1000.0),
                    "security_eligible": True,
                    "provenance_eligible": True,
                    "seed": 20260809,
                    "query_order": idx,
                }
            )
    per_query = pd.DataFrame(rows)
    per_query.to_csv(run / "crag_mock_api_per_query_results.csv", index=False)
    pd.DataFrame(sample).to_csv(run / "crag_mock_api_domain_task_sample.csv", index=False)
    metrics = vp.crag_mock_api_policy_metrics(per_query, split="validation")
    metrics.to_csv(run / "crag_mock_api_candidate_metrics.csv", index=False)
    vp.crag_mock_api_policy_metrics(per_query, split="confirmatory_test").to_csv(run / "crag_mock_api_confirmatory_candidate_metrics.csv", index=False)
    pd.DataFrame().to_csv(run / "crag_mock_api_utility_sensitivity.csv", index=False)
    return run


def test_docker_reproduction_requires_parent_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(vp, "RUN_ROOT", tmp_path / "runs")
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_docker_reproduction_v1")
    result = run_suite(suite="ragwarrant_crag_mock_api_docker_reproduction_v1", config_path=cfg, output_dir=tmp_path, run_id="repro")
    assert result["result"] == "DOCKER_REPRO_BLOCKED_MISSING_DATA"


def test_docker_reproduction_records_image_digest(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    parent = _fake_parent(root)
    rerun = _fake_parent(root, "ragwarrant_crag_mock_api_validation_v1_20990101-000000-docker")
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_docker_reproduction_v1", {"reproduction": {"rerun_run_id": rerun.name}})
    result = run_suite(suite="ragwarrant_crag_mock_api_docker_reproduction_v1", config_path=cfg, output_dir=tmp_path, run_id="repro")
    assert "image_digest" in result
    assert result["parent_run"] == str(parent)


def test_docker_reproduction_records_git_head(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    rerun = _fake_parent(root, "ragwarrant_crag_mock_api_validation_v1_20990101-000000-docker")
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_docker_reproduction_v1", {"reproduction": {"rerun_run_id": rerun.name}})
    run_suite(suite="ragwarrant_crag_mock_api_docker_reproduction_v1", config_path=cfg, output_dir=tmp_path, run_id="repro")
    assert (tmp_path / "repro" / "docker_build_report.json").exists()


def test_docker_reproduction_requires_crag_hash_match(tmp_path: Path) -> None:
    parent = {"crag_raw_or_query_hash": "a", "result": "x", "governed_winner": "g", "quality_only_winner": "q", "validation_query_count": 1, "confirmatory_query_count": 1, "failure_rate": 0.0, "win_tie_loss": {"win": 1}, "split_manifest_hash": "s", "certificate": "c", "governance_delta": 1.0, "bootstrap_ci": [1.0, 1.0], "api_call_count": 1}
    rerun = {**parent, "crag_raw_or_query_hash": "b"}
    comparison = vp.compare_crag_mock_api_validation_runs(parent, rerun, tolerance=1e-9)
    assert comparison["result"] != "DOCKER_REPRO_EXACT_MATCH"


def test_docker_reproduction_compares_governed_winner() -> None:
    parent = {"result": "r", "governed_winner": "a", "quality_only_winner": "b", "validation_query_count": 1, "confirmatory_query_count": 1, "failure_rate": 0.0, "win_tie_loss": {}, "crag_raw_or_query_hash": "h", "split_manifest_hash": "s", "certificate": "c", "governance_delta": 1.0, "bootstrap_ci": [1.0, 1.0], "api_call_count": 1}
    comparison = vp.compare_crag_mock_api_validation_runs(parent, {**parent, "governed_winner": "x"}, tolerance=1e-9)
    assert comparison["exact_field_matches"]["governed_winner"] is False


def test_docker_reproduction_compares_quality_only_winner() -> None:
    parent = {"result": "r", "governed_winner": "a", "quality_only_winner": "b", "validation_query_count": 1, "confirmatory_query_count": 1, "failure_rate": 0.0, "win_tie_loss": {}, "crag_raw_or_query_hash": "h", "split_manifest_hash": "s", "certificate": "c", "governance_delta": 1.0, "bootstrap_ci": [1.0, 1.0], "api_call_count": 1}
    comparison = vp.compare_crag_mock_api_validation_runs(parent, {**parent, "quality_only_winner": "x"}, tolerance=1e-9)
    assert comparison["exact_field_matches"]["quality_only_winner"] is False


def test_docker_reproduction_compares_win_tie_loss() -> None:
    parent = {"result": "r", "governed_winner": "a", "quality_only_winner": "b", "validation_query_count": 1, "confirmatory_query_count": 1, "failure_rate": 0.0, "win_tie_loss": {"win": 1}, "crag_raw_or_query_hash": "h", "split_manifest_hash": "s", "certificate": "c", "governance_delta": 1.0, "bootstrap_ci": [1.0, 1.0], "api_call_count": 1}
    comparison = vp.compare_crag_mock_api_validation_runs(parent, {**parent, "win_tie_loss": {"loss": 1}}, tolerance=1e-9)
    assert comparison["exact_field_matches"]["win_tie_loss"] is False


def test_docker_reproduction_result_class_machine_readable(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    rerun = _fake_parent(root, "ragwarrant_crag_mock_api_validation_v1_20990101-000000-docker")
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_docker_reproduction_v1", {"reproduction": {"rerun_run_id": rerun.name}})
    result = run_suite(suite="ragwarrant_crag_mock_api_docker_reproduction_v1", config_path=cfg, output_dir=tmp_path, run_id="repro")
    assert result["result"].startswith("DOCKER_REPRO_")


def test_no_docker_repro_claim_without_completed_run(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_docker_reproduction_v1")
    result = run_suite(suite="ragwarrant_crag_mock_api_docker_reproduction_v1", config_path=cfg, output_dir=tmp_path, run_id="repro")
    assert result["result"] == "DOCKER_REPRO_INCONCLUSIVE"


def test_ablation_requires_parent_validation_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(vp, "RUN_ROOT", tmp_path / "runs")
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_ablation_v1")
    result = run_suite(suite="ragwarrant_crag_mock_api_ablation_v1", config_path=cfg, output_dir=tmp_path, run_id="ablation")
    assert result["result"] == "ABLATION_INCONCLUSIVE"


def test_ablation_compares_top_k_low_vs_greedy(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_ablation_v1")
    result = run_suite(suite="ragwarrant_crag_mock_api_ablation_v1", config_path=cfg, output_dir=tmp_path, run_id="ablation")
    assert result["left_policy"] == "top_k_low"
    assert result["right_policy"] == "greedy_regression_aware_search"


def test_ablation_reports_cost_latency(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_ablation_v1")
    result = run_suite(suite="ragwarrant_crag_mock_api_ablation_v1", config_path=cfg, output_dir=tmp_path, run_id="ablation")
    assert "cost_contribution" in result and "latency_contribution" in result


def test_ablation_reports_api_efficiency(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_ablation_v1")
    run_suite(suite="ragwarrant_crag_mock_api_ablation_v1", config_path=cfg, output_dir=tmp_path, run_id="ablation")
    assert (tmp_path / "ablation" / "api_efficiency_analysis.json").exists()


def test_ablation_reports_retrieval_noise(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_ablation_v1")
    run_suite(suite="ragwarrant_crag_mock_api_ablation_v1", config_path=cfg, output_dir=tmp_path, run_id="ablation")
    assert (tmp_path / "ablation" / "retrieval_noise_analysis.json").exists()


def test_ablation_reports_overfit_generalization(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_ablation_v1")
    run_suite(suite="ragwarrant_crag_mock_api_ablation_v1", config_path=cfg, output_dir=tmp_path, run_id="ablation")
    assert (tmp_path / "ablation" / "overfit_generalization_analysis.json").exists()


def test_ablation_counterfactual_layers_ordered(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_ablation_v1")
    run_suite(suite="ragwarrant_crag_mock_api_ablation_v1", config_path=cfg, output_dir=tmp_path, run_id="ablation")
    layers = json.loads((tmp_path / "ablation" / "counterfactual_governance_layers.json").read_text())["layers"]
    assert layers[0]["layer"] == "quality_only_no_cost_no_latency"


def test_ablation_result_class_machine_readable() -> None:
    assert vp.crag_ablation_result_class({"utility_delta": 0.1, "cost_contribution": 0.2, "latency_contribution": 0.1, "api_call_delta": -1, "raw_quality_delta": -0.01}).startswith("ABLATION_")


def test_case_pack_requires_parent_validation_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(vp, "RUN_ROOT", tmp_path / "runs")
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_case_explanation_pack_v1")
    result = run_suite(suite="ragwarrant_crag_mock_api_case_explanation_pack_v1", config_path=cfg, output_dir=tmp_path, run_id="cases")
    assert result["result"] == "CASE_PACK_BLOCKED_MISSING_PARENT_ARTIFACTS"


def test_case_pack_has_required_fields(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_case_explanation_pack_v1")
    run_suite(suite="ragwarrant_crag_mock_api_case_explanation_pack_v1", config_path=cfg, output_dir=tmp_path, run_id="cases")
    case = json.loads((tmp_path / "cases" / "crag_mock_api_case_packets.json").read_text())["cases"][0]
    assert {"case_id", "query_id", "query_text_hash", "query_text_redacted", "sanitized_query_summary", "governed_selected_policy", "quality_only_selected_policy"} <= set(case)
    assert "query_text" not in case


def test_case_pack_includes_cost_latency_utility(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_case_explanation_pack_v1")
    run_suite(suite="ragwarrant_crag_mock_api_case_explanation_pack_v1", config_path=cfg, output_dir=tmp_path, run_id="cases")
    case = json.loads((tmp_path / "cases" / "crag_mock_api_case_packets.json").read_text())["cases"][0]
    assert "budget_delta" in case and "latency_ms_delta" in case and "utility_delta" in case


def test_case_pack_includes_governance_rule_explanation(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_case_explanation_pack_v1")
    run_suite(suite="ragwarrant_crag_mock_api_case_explanation_pack_v1", config_path=cfg, output_dir=tmp_path, run_id="cases")
    case = json.loads((tmp_path / "cases" / "crag_mock_api_case_packets.json").read_text())["cases"][0]
    assert "governance_rule_explanation" in case


def test_case_pack_sanitizes_query_text() -> None:
    public = vp.crag_public_query_columns(pd.DataFrame([{"query_id": "q1", "query_text": "FAKE_SYNTHETIC_QUERY_FOR_TESTING", "domain": "finance", "question_type": "simple", "static_or_dynamic": "dynamic"}]))
    assert "query_text" not in public.columns
    assert bool(public.loc[0, "query_text_redacted"]) is True
    assert len(public.loc[0, "query_text_hash"]) == 64


def test_case_pack_creates_executive_and_technical_versions(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_case_explanation_pack_v1")
    run_suite(suite="ragwarrant_crag_mock_api_case_explanation_pack_v1", config_path=cfg, output_dir=tmp_path, run_id="cases")
    assert (tmp_path / "cases" / "crag_mock_api_executive_case_pack.md").exists()
    assert (tmp_path / "cases" / "crag_mock_api_technical_case_pack.md").exists()


def test_case_pack_result_class_machine_readable(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_case_explanation_pack_v1")
    result = run_suite(suite="ragwarrant_crag_mock_api_case_explanation_pack_v1", config_path=cfg, output_dir=tmp_path, run_id="cases")
    assert result["result"].startswith("CASE_PACK_")


def test_repeat_validation_requires_new_split_or_seed() -> None:
    assert vp.deterministic_repeat_split("q1", 1) in {"validation", "confirmatory_test"}
    assert vp.deterministic_repeat_split("q1", 1) == vp.deterministic_repeat_split("q1", 1)


def test_repeat_validation_requires_zero_leakage(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_repeat_validation_v1", {"data": {"minimum_confirmatory_rows": 1}, "repeat": {"seeds": [1], "max_repeats": 1}})
    run_suite(suite="ragwarrant_crag_mock_api_repeat_validation_v1", config_path=cfg, output_dir=tmp_path, run_id="repeat")
    report = json.loads((tmp_path / "repeat" / "repeat_leakage_report.json").read_text())
    assert report["zero_leakage"] is True


def test_repeat_validation_records_raw_hash(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_repeat_validation_v1", {"data": {"minimum_confirmatory_rows": 1}, "repeat": {"seeds": [1], "max_repeats": 1}})
    run_suite(suite="ragwarrant_crag_mock_api_repeat_validation_v1", config_path=cfg, output_dir=tmp_path, run_id="repeat")
    manifest = json.loads((tmp_path / "repeat" / "repeat_split_manifest.json").read_text())
    assert manifest["raw_hash"] == "abc"


def test_repeat_validation_reports_governed_and_quality_winners(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_repeat_validation_v1", {"data": {"minimum_confirmatory_rows": 1}, "repeat": {"seeds": [1], "max_repeats": 1}})
    run_suite(suite="ragwarrant_crag_mock_api_repeat_validation_v1", config_path=cfg, output_dir=tmp_path, run_id="repeat")
    frame = pd.read_csv(tmp_path / "repeat" / "repeat_validation_results.csv")
    assert {"governed_winner", "quality_only_winner"} <= set(frame.columns)


def test_repeat_validation_reports_parent_comparison(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_repeat_validation_v1", {"data": {"minimum_confirmatory_rows": 1}, "repeat": {"seeds": [1], "max_repeats": 1}})
    run_suite(suite="ragwarrant_crag_mock_api_repeat_validation_v1", config_path=cfg, output_dir=tmp_path, run_id="repeat")
    assert (tmp_path / "repeat" / "repeat_parent_comparison.json").exists()


def test_repeat_validation_result_class_machine_readable(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_repeat_validation_v1", {"data": {"minimum_confirmatory_rows": 1}, "repeat": {"seeds": [1], "max_repeats": 1}})
    result = run_suite(suite="ragwarrant_crag_mock_api_repeat_validation_v1", config_path=cfg, output_dir=tmp_path, run_id="repeat")
    assert result["result"].startswith("REPEAT_VALIDATION_")


def test_repeat_underpowered_classification(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_repeat_validation_v1", {"data": {"minimum_confirmatory_rows": 9999}, "repeat": {"seeds": [1], "max_repeats": 1}})
    result = run_suite(suite="ragwarrant_crag_mock_api_repeat_validation_v1", config_path=cfg, output_dir=tmp_path, run_id="repeat")
    assert result["result"] == "REPEAT_VALIDATION_BLOCKED_UNDERPOWERED"


def test_evidence_synthesis_requires_parent_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(vp, "RUN_ROOT", tmp_path / "runs")
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_evidence_synthesis_v1")
    result = run_suite(suite="ragwarrant_crag_mock_api_evidence_synthesis_v1", config_path=cfg, output_dir=tmp_path, run_id="synth")
    assert "parent" in result


def test_evidence_synthesis_includes_docker_reproduction(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    docker = root / "ragwarrant_crag_mock_api_docker_reproduction_v1_20990101"
    docker.mkdir()
    _write_json(docker / "docker_reproduction_result.json", {"result": "DOCKER_REPRO_EXACT_MATCH", "supports_parent_result": True})
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_evidence_synthesis_v1")
    result = run_suite(suite="ragwarrant_crag_mock_api_evidence_synthesis_v1", config_path=cfg, output_dir=tmp_path, run_id="synth")
    assert result["docker"]["result"] == "DOCKER_REPRO_EXACT_MATCH"


def test_evidence_synthesis_includes_repeat_validation_status(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    repeat = root / "ragwarrant_crag_mock_api_repeat_validation_v1_20990101"
    repeat.mkdir()
    _write_json(repeat / "crag_mock_api_repeat_validation_manifest.json", {"result": "REPEAT_VALIDATION_REPLICATES_SUPERIORITY"})
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_evidence_synthesis_v1")
    result = run_suite(suite="ragwarrant_crag_mock_api_evidence_synthesis_v1", config_path=cfg, output_dir=tmp_path, run_id="synth")
    assert result["repeat"]["result"] == "REPEAT_VALIDATION_REPLICATES_SUPERIORITY"


def test_evidence_synthesis_includes_claim_boundaries(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_evidence_synthesis_v1")
    run_suite(suite="ragwarrant_crag_mock_api_evidence_synthesis_v1", config_path=cfg, output_dir=tmp_path, run_id="synth")
    report = (tmp_path / "synth" / "crag_mock_api_evidence_synthesis_report.md").read_text()
    assert "Claim boundaries" in report


def test_evidence_synthesis_does_not_claim_rag_compass_superiority(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setattr(vp, "RUN_ROOT", root)
    _fake_parent(root)
    cfg = _config(tmp_path, "ragwarrant_crag_mock_api_evidence_synthesis_v1")
    run_suite(suite="ragwarrant_crag_mock_api_evidence_synthesis_v1", config_path=cfg, output_dir=tmp_path, run_id="synth")
    claims = pd.read_csv(tmp_path / "synth" / "claim_status_table.csv")
    assert claims[claims["claim"] == "RAG Compass superiority"].iloc[0]["status"] == "unsupported"


def test_evidence_synthesis_result_class_machine_readable() -> None:
    assert vp.crag_mock_api_evidence_class("DOCKER_REPRO_EXACT_MATCH", "REPEAT_VALIDATION_REPLICATES_SUPERIORITY") == "CRAG_MOCK_API_GOVERNANCE_SUPERIOR_REPRODUCED_AND_REPLICATED"
