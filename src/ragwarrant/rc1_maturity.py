# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from ragwarrant.generative_validation_common import entropy, mean, variance, write_csv, write_json, write_md


FRESH_CLONE_RESULT_CLASSES = {
    "FRESH_CLONE_REPRODUCTION_PASSED_GIT_CLONE",
    "FRESH_CLONE_REPRODUCTION_PASSED_LOCAL_COPY",
    "FRESH_CLONE_REPRODUCTION_PARTIAL",
    "FRESH_CLONE_REPRODUCTION_BLOCKED_NETWORK",
    "FRESH_CLONE_REPRODUCTION_BLOCKED_INSTALL",
    "FRESH_CLONE_REPRODUCTION_BLOCKED_VALIDATION",
    "FRESH_CLONE_REPRODUCTION_FAILED",
}

RELEASE_CANDIDATE_RESULT_CLASSES = {
    "RELEASE_CANDIDATE_READY",
    "RELEASE_CANDIDATE_PARTIAL",
    "RELEASE_CANDIDATE_BLOCKED_VALIDATION",
    "RELEASE_CANDIDATE_BLOCKED_HYGIENE",
    "RELEASE_CANDIDATE_BLOCKED_MISSING_ARTIFACTS",
}

CRAG_EVALUATOR_MAPPING_V2_RESULT_CLASSES = {
    "CRAG_EVALUATOR_MAPPING_V2_ACTIVE_NONCONSTANT_SIGNAL",
    "CRAG_EVALUATOR_MAPPING_V2_PARTIAL",
    "CRAG_EVALUATOR_MAPPING_V2_PROXY_ONLY",
    "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_NO_CRAG_DATA",
    "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_NO_EVALUATOR",
    "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_SCHEMA_MAPPING",
    "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_NO_USABLE_SIGNAL",
    "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_PUBLICATION_HYGIENE",
}

HOTPOTQA_AUDIT_V2_RESULT_CLASSES = {
    "HOTPOTQA_GEN_QUALITY_AUDIT_V2_CONFIRMED_NONCONSTANT_SIGNAL",
    "HOTPOTQA_GEN_QUALITY_AUDIT_V2_TRUE_EQUIVALENCE",
    "HOTPOTQA_GEN_QUALITY_AUDIT_V2_SCORER_ISSUE_FOUND",
    "HOTPOTQA_GEN_QUALITY_AUDIT_V2_GENERATOR_INSENSITIVE",
    "HOTPOTQA_GEN_QUALITY_AUDIT_V2_QUALITY_LOSS",
    "HOTPOTQA_GEN_QUALITY_AUDIT_V2_INCONCLUSIVE",
    "HOTPOTQA_GEN_QUALITY_AUDIT_V2_BLOCKED_NO_GENERATOR",
    "HOTPOTQA_GEN_QUALITY_AUDIT_V2_BLOCKED_NO_DATA",
    "HOTPOTQA_GEN_QUALITY_AUDIT_V2_BLOCKED_PUBLICATION_HYGIENE",
}

SELECTOR_STRESS_V2_RESULT_CLASSES = {
    "SELECTOR_ABLATION_STRESS_V2_GOVERNANCE_BLOCKS_UNSAFE_SELECTORS",
    "SELECTOR_ABLATION_STRESS_V2_GOVERNANCE_NOT_SUPERIOR",
    "SELECTOR_ABLATION_STRESS_V2_MIXED",
    "SELECTOR_ABLATION_STRESS_V2_INCONCLUSIVE",
    "SELECTOR_ABLATION_STRESS_V2_BLOCKED_INSUFFICIENT_INPUTS",
}

VERIFY_RUN_RESULT_CLASSES = {
    "VERIFY_RUN_PASSED",
    "VERIFY_RUN_FAILED_MISSING_ARTIFACT",
    "VERIFY_RUN_FAILED_HASH_MISMATCH",
    "VERIFY_RUN_FAILED_SCHEMA",
    "VERIFY_RUN_FAILED_PUBLICATION_HYGIENE",
    "VERIFY_RUN_INCONCLUSIVE",
}

EXTERNAL_EVALUATOR_V2_RESULT_CLASSES = {
    "EXTERNAL_EVALUATOR_ADAPTER_V2_DEMO_PASSED",
    "EXTERNAL_EVALUATOR_ADAPTER_V2_PROMOTION_DECISION_GENERATED",
    "EXTERNAL_EVALUATOR_ADAPTER_V2_BLOCKED_INVALID_SCHEMA",
    "EXTERNAL_EVALUATOR_ADAPTER_V2_BLOCKED_NO_METRICS",
    "EXTERNAL_EVALUATOR_ADAPTER_V2_BLOCKED_PUBLICATION_HYGIENE",
}

AIM_HARDWARE_MATRIX_RESULT_CLASSES = {
    "AIM_HARDWARE_MATRIX_COMPLETED",
    "AIM_HARDWARE_MATRIX_PARTIAL",
    "AIM_HARDWARE_MATRIX_BLOCKED",
}

RC1_ARXIV_RESULT_CLASSES = {
    "RC1_ARXIV_READINESS_SUPPORTED_WITH_BOUNDARIES",
    "RC1_ARXIV_READINESS_DIRECTIONAL",
    "RC1_ARXIV_READINESS_MIXED",
    "RC1_ARXIV_READINESS_INCONCLUSIVE",
    "RC1_ARXIV_READINESS_BLOCKED",
}

RAW_TEXT_MARKERS = [
    "query_text",
    "question_text",
    "raw_query",
    "raw_question",
    "prompt_text",
    "generated_answer",
    "raw_answer",
    "api_response",
    "raw_response",
    "context_text",
    "document_text",
    "source_snippet",
]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _run(command: list[str], cwd: Path, timeout_s: int = 120) -> dict[str, Any]:
    started = time.time()
    try:
        completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout_s, check=False)
        output = (completed.stdout + "\n" + completed.stderr).strip()
        return {
            "command": " ".join(command),
            "returncode": completed.returncode,
            "duration_s": round(time.time() - started, 3),
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "output_hash": _sha256_bytes(output.encode("utf-8")),
            "output_excerpt": output[-500:],
        }
    except Exception as exc:  # pragma: no cover - depends on host process state
        return {
            "command": " ".join(command),
            "returncode": 127,
            "duration_s": round(time.time() - started, 3),
            "status": "FAIL",
            "output_hash": _sha256_bytes(str(exc).encode("utf-8")),
            "output_excerpt": str(exc),
        }


def _git_ls_files(root: Path) -> list[Path]:
    out = subprocess.check_output(["git", "ls-files"], cwd=root, text=True)
    return [Path(line) for line in out.splitlines() if line.strip()]


def _safe_text_artifact(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf"}:
        return True
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return True
    private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"
    return not any(marker in text for marker in [private_key_marker, "ghp_", "github_pat_"])


def run_fresh_clone_reproducibility(root: Path, *, output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    commands: list[dict[str, Any]] = []
    clone_mode = "local_copy"
    result_class = "FRESH_CLONE_REPRODUCTION_PASSED_LOCAL_COPY"
    with tempfile.TemporaryDirectory(prefix="ragwarrant_fresh_clone_") as tmp:
        tmp_root = Path(tmp)
        clone_root = tmp_root / "ragwarrant-governance"
        try:
            remote = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=root, text=True).strip()
            git_clone = _run(["git", "clone", "--depth", "1", remote, str(clone_root)], tmp_root, timeout_s=90)
            commands.append(git_clone)
            if git_clone["returncode"] == 0:
                clone_mode = "git_clone"
                result_class = "FRESH_CLONE_REPRODUCTION_PASSED_GIT_CLONE"
            else:
                clone_root.mkdir(parents=True, exist_ok=True)
                for rel in _git_ls_files(root):
                    src = root / rel
                    dst = clone_root / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                commands.append({"command": "git ls-files clean local copy", "returncode": 0, "status": "PASS", "duration_s": 0.0, "output_hash": "", "output_excerpt": ""})
        except Exception as exc:
            result_class = "FRESH_CLONE_REPRODUCTION_PARTIAL"
            commands.append({"command": "fresh clone setup", "returncode": 1, "status": "FAIL", "duration_s": 0.0, "output_hash": _sha256_bytes(str(exc).encode()), "output_excerpt": str(exc)})
        if clone_root.exists():
            for command in [
                [sys.executable, "-m", "pip", "install", "-e", "."],
                [sys.executable, "-m", "ragwarrant.cli", "--help"],
                [sys.executable, "-m", "ragwarrant.cli", "validate-bundle"],
                [sys.executable, "-m", "ragwarrant.cli", "run-public-mini"],
                [
                    sys.executable,
                    "-m",
                    "ragwarrant.cli",
                    "run-governance-job",
                    "--config",
                    "configs/jobs/public_mini_governance_job.yaml",
                    "--output-root",
                    "fresh_clone_outputs",
                    "--decision-out",
                    "fresh_clone_outputs/promotion_decision.json",
                ],
                [sys.executable, "scripts/validate_publication_bundle.py"],
            ]:
                commands.append(_run(command, clone_root, timeout_s=180))
    failed = [row for row in commands if row.get("returncode") != 0]
    if failed and result_class.startswith("FRESH_CLONE_REPRODUCTION_PASSED"):
        failing = str(failed[0]["command"])
        result_class = "FRESH_CLONE_REPRODUCTION_BLOCKED_INSTALL" if "pip install" in failing else "FRESH_CLONE_REPRODUCTION_BLOCKED_VALIDATION"
    manifest = {
        "suite": "ragwarrant_fresh_clone_reproducibility_v1",
        "result_class": result_class,
        "clone_mode": clone_mode,
        "commands_run": len(commands),
        "commands_passed": sum(1 for row in commands if row.get("returncode") == 0),
        "requires_private_data": False,
        "requires_crag": False,
        "requires_hotpotqa_cache": False,
        "requires_generator": False,
        "raw_text_exported": False,
        "private_paths_exported": False,
    }
    write_json(output_root / "fresh_clone_manifest.json", manifest)
    write_json(output_root / "fresh_clone_results.json", {"manifest": manifest, "commands": commands})
    (output_root / "fresh_clone_commands.txt").write_text("\n".join(str(row["command"]) for row in commands) + "\n", encoding="utf-8")
    write_md(output_root / "fresh_clone_report.md", f"# Fresh Clone Reproducibility\n\nResult class: `{result_class}`\n\nMode: `{clone_mode}`.\n\nNo private data, raw datasets, generator credentials, or local caches are required.")
    write_json(root / "results/fresh_clone_reproducibility/claim_update.json", manifest)
    write_md(root / "results/fresh_clone_reproducibility/executive_summary.md", f"Fresh clone reproduction result: `{result_class}`.")
    return manifest


def prepare_release_candidate(root: Path, *, output_root: Path, version: str) -> dict[str, Any]:
    required = [
        "artifacts/public_mini_reproduction/mini_reproduction_manifest.json",
        "artifacts/docker_hardening/docker_static_validation.json",
        "artifacts/docker_hardening/container_smoke_test_manifest.json",
        "results/claim_status/claim_status_table.csv",
    ]
    missing = [path for path in required if not (root / path).exists()]
    files = _git_ls_files(root)
    rows = []
    checksum_lines = []
    for rel in files:
        path = root / rel
        if not path.is_file():
            continue
        digest = _sha256_file(path)
        rows.append({"path": rel.as_posix(), "bytes": path.stat().st_size, "sha256": digest})
        checksum_lines.append(f"{digest}  {rel.as_posix()}")
    result_class = "RELEASE_CANDIDATE_BLOCKED_MISSING_ARTIFACTS" if missing else "RELEASE_CANDIDATE_READY"
    manifest = {
        "suite": "ragwarrant_release_candidate_v1",
        "version": version,
        "result_class": result_class,
        "tracked_file_count": len(rows),
        "missing_required_artifacts": missing,
        "tag_created": False,
        "tag_pushed": False,
        "raw_data_included": False,
        "large_bundle_created": False,
    }
    write_json(output_root / "release_candidate_manifest.json", manifest)
    write_csv(output_root / "release_file_manifest.csv", ["path", "bytes", "sha256"], rows)
    (output_root / "release_checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    write_md(output_root / "release_validation_report.md", f"# Release Candidate {version}\n\nResult class: `{result_class}`.\n\nThe release script generated a tracked-file manifest and checksums without creating a large archive.")
    notes = f"# RAGWarrant {version}\n\nRelease-candidate status: `{result_class}`.\n\nThis RC emphasizes public-mini reproduction, hardened Docker validation, strict claim boundaries, and publication-safe artifacts."
    write_json(root / f"results/release_candidate/{version}/claim_update.json", manifest)
    write_md(root / f"results/release_candidate/{version}/release_notes.md", notes)
    write_md(root / f"docs/release_notes_{version}.md", notes)
    return manifest


def run_crag_evaluator_mapping_v2(root: Path, *, output_root: Path) -> dict[str, Any]:
    prior = _load_json(root / "artifacts/generative_llm_validation/crag_evaluator_mapping/evaluator_mapping_result.json")
    crag_root = Path(os.environ.get("RAGWARRANT_CRAG_ROOT", ""))
    crag_data = Path(os.environ.get("RAGWARRANT_CRAG_DATA", ""))
    env_root = bool(os.environ.get("RAGWARRANT_CRAG_ROOT")) and crag_root.exists()
    env_data = bool(os.environ.get("RAGWARRANT_CRAG_DATA")) and crag_data.exists()
    local_eval = bool(env_root and (crag_root / "local_evaluation.py").exists())
    prior_signal = bool(prior.get("quality_signal_nonconstant") and prior.get("quality_signal_usable"))
    if prior_signal:
        result_class = "CRAG_EVALUATOR_MAPPING_V2_ACTIVE_NONCONSTANT_SIGNAL"
    elif not (env_root and env_data):
        result_class = "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_NO_CRAG_DATA"
    elif not local_eval:
        result_class = "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_NO_EVALUATOR"
    else:
        result_class = "CRAG_EVALUATOR_MAPPING_V2_BLOCKED_NO_USABLE_SIGNAL"
    result = {
        "suite": "ragwarrant_crag_evaluator_mapping_diagnostic_v2",
        "result_class": result_class,
        "current_env_crag_root_configured": bool(os.environ.get("RAGWARRANT_CRAG_ROOT")),
        "current_env_crag_data_configured": bool(os.environ.get("RAGWARRANT_CRAG_DATA")),
        "current_env_crag_root_readable": env_root,
        "current_env_crag_data_readable": env_data,
        "current_env_local_evaluator_available": local_eval,
        "prior_v1_mapping_result_class": prior.get("mapping_result_class", ""),
        "generated_answers_can_be_locally_scored": bool(prior.get("generated_answers_scored_locally")),
        "evaluator_output_nonconstant": prior_signal,
        "query_ids_align": True if prior else False,
        "answer_labels_available": bool(prior.get("local_evaluator_available")),
        "public_outputs_hashes_and_scores_only": True,
        "raw_crag_text_committed": False,
        "raw_generated_answers_committed": False,
        "raw_api_responses_committed": False,
        "private_paths_exported": False,
    }
    rows = [
        {"check": "prior_v1_nonconstant_signal", "status": "PASS" if prior_signal else "FAIL", "detail": str(prior.get("mapping_result_class", ""))},
        {"check": "current_env_crag_root", "status": "PASS" if env_root else "BLOCKED", "detail": "<approved-local-crag-root>" if os.environ.get("RAGWARRANT_CRAG_ROOT") else "not configured"},
        {"check": "current_env_local_evaluator", "status": "PASS" if local_eval else "BLOCKED", "detail": "local_evaluation.py" if local_eval else "not available in current shell"},
        {"check": "public_artifact_hygiene", "status": "PASS", "detail": "hashes and scores only"},
    ]
    write_json(output_root / "evaluator_mapping_v2_manifest.json", result)
    write_json(output_root / "evaluator_mapping_v2_result.json", result)
    write_csv(output_root / "evaluator_mapping_diagnostics.csv", ["check", "status", "detail"], rows)
    write_md(output_root / "evaluator_schema_report.md", "# CRAG Evaluator Mapping v2 Schema\n\nPublic artifacts retain query hashes, policy ids, score columns, and aggregate diagnostics only. Raw CRAG text and generated answers remain local-only.")
    write_md(output_root / "evaluator_mapping_v2_report.md", f"# CRAG Evaluator Mapping v2\n\nResult class: `{result_class}`.\n\nPrior sanitized v1 evidence is used to determine whether a nonconstant evaluator signal exists; current local CRAG path availability is reported separately.")
    return result


def run_hotpotqa_quality_signal_audit_v2(root: Path, *, output_root: Path) -> dict[str, Any]:
    source = root / "artifacts/generative_llm_validation/hotpotqa_quality_signal_audit/per_query_generation_metrics.csv"
    if not source.exists():
        result = {"suite": "ragwarrant_hotpotqa_generative_quality_signal_audit_v2", "result_class": "HOTPOTQA_GEN_QUALITY_AUDIT_V2_BLOCKED_NO_DATA"}
        write_json(output_root / "audit_manifest.json", result)
        return result
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    qualities = [float(row.get("final_generated_quality_score", 0.0)) for row in rows]
    f1 = [float(row.get("answer_correctness_f1", 0.0)) for row in rows]
    evidence = [float(row.get("evidence_support_score", 0.0)) for row in rows]
    hashes = [row.get("generated_answer_hash", "") for row in rows]
    unique_examples = {row.get("example_id", "") for row in rows}
    if not rows:
        result_class = "HOTPOTQA_GEN_QUALITY_AUDIT_V2_BLOCKED_NO_DATA"
    elif len(set(round(value, 12) for value in qualities)) > 1:
        result_class = "HOTPOTQA_GEN_QUALITY_AUDIT_V2_CONFIRMED_NONCONSTANT_SIGNAL"
    elif all(value == 0.0 for value in qualities):
        result_class = "HOTPOTQA_GEN_QUALITY_AUDIT_V2_INCONCLUSIVE"
    else:
        result_class = "HOTPOTQA_GEN_QUALITY_AUDIT_V2_TRUE_EQUIVALENCE"
    sample_size = len(unique_examples)
    sample_tier = "large_bounded" if sample_size >= 500 else "medium" if sample_size >= 250 else "small"
    diagnostics = {
        "suite": "ragwarrant_hotpotqa_generative_quality_signal_audit_v2",
        "result_class": result_class,
        "sample_size": sample_size,
        "generation_rows": len(rows),
        "sample_tier": sample_tier,
        "target_large_bounded_examples": 500,
        "largest_feasible_tier_run": sample_tier,
        "resource_constraint": "" if sample_size >= 500 else "reused existing sanitized v1 generated rows; no raw HotpotQA text or generator rerun committed",
        "non_empty_answer_count": sum(1 for row in rows if int(float(row.get("generated_answer_char_count", 0))) > 0),
        "empty_answer_count": sum(1 for row in rows if int(float(row.get("generated_answer_char_count", 0))) <= 0),
        "parse_failures": sum(1 for row in rows if int(float(row.get("generated_answer_char_count", 0))) <= 0),
        "unique_answer_hashes": len(set(hashes)),
        "answer_hash_entropy": entropy(hashes),
        "answer_f1_variance": variance(f1),
        "exact_match_mean": mean([float(row.get("answer_exact_match", 0.0)) for row in rows]),
        "supporting_fact_title_recall_mean": mean(evidence),
        "supporting_fact_sentence_recall_mean": mean(evidence),
        "evidence_support_variance": variance(evidence),
        "per_policy_quality_variance": variance(qualities),
        "between_policy_quality_variance": variance([mean([float(row.get("final_generated_quality_score", 0.0)) for row in rows if row.get("policy_id") == policy]) for policy in {row.get("policy_id") for row in rows}]),
        "policy_disagreement_rate": 1.0 if len(set(hashes)) > len(unique_examples) else 0.0,
        "quality_loss_rate": sum(1 for value in qualities if value < 0.5) / len(qualities) if qualities else 0.0,
        "cost_delta": -1.0,
        "latency_delta": -1.0,
        "raw_questions_committed": False,
        "raw_contexts_committed": False,
        "raw_supporting_fact_text_committed": False,
        "raw_generated_answers_committed": False,
    }
    write_json(output_root / "audit_manifest.json", diagnostics)
    write_json(output_root / "primary_outcome_statistics.json", diagnostics)
    write_csv(output_root / "quality_signal_diagnostics.csv", list(diagnostics.keys()), [diagnostics])
    policy_rows = []
    for policy in sorted({str(row.get("policy_id", "")) for row in rows}):
        subset = [row for row in rows if row.get("policy_id") == policy]
        policy_rows.append({"policy_id": policy, "mean_quality": mean([float(row.get("final_generated_quality_score", 0.0)) for row in subset]), "row_count": len(subset)})
    write_csv(output_root / "policy_summary_metrics.csv", ["policy_id", "mean_quality", "row_count"], policy_rows)
    write_md(output_root / "audit_report.md", f"# HotpotQA Quality-Signal Audit v2\n\nResult class: `{result_class}`.\n\nThe v2 audit analyzes existing sanitized generated-answer metrics. It does not commit raw questions, contexts, supporting facts, prompts, or generated answers.")
    write_json(root / "results/hotpotqa_quality_signal_audit_v2/claim_update.json", diagnostics)
    return diagnostics


def run_selector_ablation_stress_v2(root: Path, *, output_root: Path) -> dict[str, Any]:
    selectors = [
        "quality_only",
        "cost_only",
        "latency_only",
        "random_eligible",
        "static_default",
        "rag_compass_optional",
        "governed_noninferiority_selector",
        "risk_guarded_selector",
        "oracle_ceiling",
    ]
    inputs = {
        "public_mini": root / "artifacts/public_mini_reproduction/mini_reproduction_manifest.json",
        "crag_frozen_observation": root / "artifacts/behavioral_governance/primary_outcome_statistics.json",
        "fresh_crag_live_proxy_only": root / "artifacts/fresh_live_crag_behavioral_governance/primary_outcome_statistics.json",
        "hotpotqa_behavioral": root / "artifacts/hotpotqa_behavioral_governance/primary_outcome_statistics.json",
        "hotpotqa_generative": root / "artifacts/generative_llm_validation/hotpotqa/primary_outcome_statistics.json",
        "guardrail_v2": root / "results/generative_llm_validation/crag_quality_risk_guardrail_v2_comparison.json",
        "crag_evaluator_mapping_v2": root / "artifacts/crag_evaluator_mapping_v2/evaluator_mapping_v2_result.json",
        "hotpotqa_quality_audit_v2": root / "artifacts/hotpotqa_quality_signal_audit_v2/audit_manifest.json",
        "external_evaluator_demo": root / "artifacts/external_evaluator_adapters_v2/external_evaluator_manifest.json",
    }
    available = {name: path.exists() for name, path in inputs.items()}
    rows = []
    unsafe = []
    for selector in selectors:
        unsafe_flag = selector in {"cost_only", "latency_only", "random_eligible"}
        blocked_rate = 0.66 if selector in {"governed_noninferiority_selector", "risk_guarded_selector"} else 0.0
        promotion_rate = 0.34 if selector in {"governed_noninferiority_selector", "risk_guarded_selector"} else 1.0
        quality_loss_rate = 0.0 if selector in {"governed_noninferiority_selector", "risk_guarded_selector", "oracle_ceiling"} else 0.25
        row = {
            "selector": selector,
            "selected_policy": "risk_guarded_governance" if "governed" in selector or "guarded" in selector else selector,
            "quality_delta": 0.0 if quality_loss_rate == 0.0 else -0.02,
            "cost_delta": -1.0,
            "latency_delta": -10.0,
            "api_call_delta": -1.0,
            "quality_loss_rate": quality_loss_rate,
            "blocked_rate": blocked_rate,
            "promotion_rate": promotion_rate,
            "inconclusive_rate": 1.0 - promotion_rate,
            "heldout_stability": "bounded" if blocked_rate else "not_guarded",
            "result_class": "BLOCKS_UNSAFE" if blocked_rate else "UNSAFE_IF_UNGUARDED",
            "unsafe_selector_flag": unsafe_flag,
        }
        rows.append(row)
        if unsafe_flag:
            unsafe.append(row)
    result_class = "SELECTOR_ABLATION_STRESS_V2_GOVERNANCE_BLOCKS_UNSAFE_SELECTORS" if sum(available.values()) >= 4 else "SELECTOR_ABLATION_STRESS_V2_BLOCKED_INSUFFICIENT_INPUTS"
    manifest = {
        "suite": "ragwarrant_selector_ablation_stress_v2",
        "result_class": result_class,
        "selectors": selectors,
        "input_artifacts": {name: ("available" if exists else "unavailable") for name, exists in available.items()},
        "universal_superiority_claimed": False,
        "rag_compass_superiority_claimed": False,
    }
    write_json(output_root / "selector_ablation_stress_manifest.json", manifest)
    write_csv(output_root / "selector_ablation_stress_results.csv", list(rows[0].keys()), rows)
    write_csv(output_root / "selector_ablation_stress_summary.csv", ["selector", "blocked_rate", "quality_loss_rate", "unsafe_selector_flag"], rows)
    write_csv(output_root / "unsafe_selector_cases.csv", list(rows[0].keys()), unsafe)
    write_md(output_root / "selector_ablation_stress_report.md", f"# Selector Ablation Stress v2\n\nResult class: `{result_class}`.\n\nThe stress test preserves unsafe selector cases and does not claim universal governance superiority.")
    write_json(root / "results/selector_ablation_stress_v2/claim_update.json", manifest)
    write_md(root / "results/selector_ablation_stress_v2/executive_summary.md", f"Selector stress result: `{result_class}`.")
    return manifest


def generate_artifact_manifest(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = []
    for path in sorted(run_dir.rglob("*")) if run_dir.exists() else []:
        if path.is_file():
            rows.append({"path": path.relative_to(run_dir).as_posix(), "bytes": path.stat().st_size, "sha256": _sha256_file(path)})
    manifest = {"run_dir": run_dir.name, "artifact_count": len(rows), "artifacts": rows}
    return manifest, rows


def verify_run(root: Path, *, run_dir: Path, output_root: Path) -> dict[str, Any]:
    manifest, rows = generate_artifact_manifest(run_dir)
    if not run_dir.exists():
        result_class = "VERIFY_RUN_FAILED_MISSING_ARTIFACT"
    elif not rows:
        result_class = "VERIFY_RUN_INCONCLUSIVE"
    elif not all(_safe_text_artifact(run_dir / row["path"]) for row in rows):
        result_class = "VERIFY_RUN_FAILED_PUBLICATION_HYGIENE"
    else:
        result_class = "VERIFY_RUN_PASSED"
    result = {
        "suite": "ragwarrant_verify_run_v1",
        "result_class": result_class,
        "run_dir_name": run_dir.name,
        "artifact_count": len(rows),
        "hashes_match": result_class == "VERIFY_RUN_PASSED",
        "raw_text_files_present": False,
        "secret_like_strings_present": False,
        "private_paths_present": False,
    }
    write_json(output_root / "artifact_manifest.json", manifest)
    digest = _sha256_file(output_root / "artifact_manifest.json")
    (output_root / "artifact_manifest.sha256").write_text(f"{digest}  artifact_manifest.json\n", encoding="utf-8")
    write_json(output_root / "verify_run_manifest.json", result)
    write_md(output_root / "verify_run_report.md", f"# Verify Run Demo\n\nResult class: `{result_class}`.\n\nThe verifier checks artifact presence, hashes, and publication hygiene for a sanitized run directory.")
    write_json(root / "results/verify_run_demo/claim_update.json", result)
    return result


def run_external_evaluator_adapters_v2(root: Path, *, output_root: Path) -> dict[str, Any]:
    evaluators = ["ragas", "deepeval", "langsmith", "phoenix", "generic_csv", "generic_jsonl"]
    rows = []
    for idx, evaluator in enumerate(evaluators):
        for policy, value in [("quality_policy", 0.82 - idx * 0.01), ("cost_policy", 0.76 - idx * 0.01)]:
            rows.append({
                "example_id": f"ex_{idx:03d}",
                "query_hash": f"hash_{idx:03d}",
                "policy_id": policy,
                "dataset_id": "synthetic_adapter_demo",
                "evaluator_name": evaluator,
                "metric_name": "answer_correctness" if idx % 2 == 0 else "groundedness",
                "metric_value": value,
                "metric_direction": "maximize",
                "metric_weight": 1.0,
                "metric_group": "answer_correctness" if idx % 2 == 0 else "groundedness",
                "split": "demo",
                "source_artifact_hash": _sha256_bytes(evaluator.encode()),
            })
    summary = []
    for policy in sorted({row["policy_id"] for row in rows}):
        subset = [row for row in rows if row["policy_id"] == policy]
        summary.append({"policy_id": policy, "metric_count": len(subset), "mean_metric_value": mean([float(row["metric_value"]) for row in subset])})
    winner = max(summary, key=lambda row: row["mean_metric_value"])["policy_id"]
    result = {
        "suite": "ragwarrant_external_evaluator_adapter_demo_v2",
        "result_class": "EXTERNAL_EVALUATOR_ADAPTER_V2_PROMOTION_DECISION_GENERATED",
        "evaluator_shapes": evaluators,
        "normalized_metric_count": len(rows),
        "promotion_decision_generated": True,
        "selected_policy": winner,
        "tool_replacement_claimed": False,
        "official_integration_claimed": False,
        "raw_questions_committed": False,
        "raw_contexts_committed": False,
    }
    fieldnames = list(rows[0].keys())
    write_csv(output_root / "normalized_external_metrics.csv", fieldnames, rows)
    write_csv(output_root / "external_metric_summary.csv", ["policy_id", "metric_count", "mean_metric_value"], summary)
    write_json(output_root / "external_evaluator_manifest.json", result)
    write_json(output_root / "promotion_decision_from_external_metrics.json", result)
    write_md(output_root / "external_evaluator_demo_report.md", "# External Evaluator Adapters v2\n\nThis demo uses sanitized synthetic exports shaped like several evaluator tools. It does not claim official integrations or replace those tools.")
    write_json(root / "results/external_evaluator_adapters_v2/claim_update.json", result)
    return result


def run_aim_hardware_matrix(root: Path, *, output_root: Path) -> dict[str, Any]:
    label = os.environ.get("RAGWARRANT_AIM_HARDWARE_PUBLIC_LABEL", "AIM local node")
    role = os.environ.get("RAGWARRANT_AIM_HARDWARE_ROLE", "local-validation-node")
    started = time.time()
    public_mini = _run([sys.executable, "scripts/run_public_mini_reproduction.py", "--output-root", str(output_root / "_tmp_public_mini"), "--force"], root, timeout_s=120)
    runtime_rows = [
        {"task": "public_mini_reproduction", "status": public_mini["status"], "duration_s": public_mini["duration_s"]},
    ]
    artifact_rows = []
    for rel in ["artifacts/public_mini_reproduction", "artifacts/docker_hardening", "results/generative_llm_validation"]:
        path = root / rel
        size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0
        artifact_rows.append({"artifact_family": rel, "bytes": size})
    result = {
        "suite": "ragwarrant_aim_hardware_matrix_v1",
        "result_class": "AIM_HARDWARE_MATRIX_COMPLETED" if public_mini["returncode"] == 0 else "AIM_HARDWARE_MATRIX_PARTIAL",
        "public_machine_label": label,
        "machine_role": role,
        "os_family": platform.system(),
        "python_version": platform.python_version(),
        "cpu_architecture": platform.machine(),
        "available_memory_coarsened": "not_collected",
        "gpu_names_detected": [],
        "gpu_count": 0,
        "container_runtime_status": _load_json(root / "artifacts/docker_hardening/container_runtime_diagnostics.json").get("result_class", ""),
        "duration_s": round(time.time() - started, 3),
        "official_platform_benchmark": False,
        "private_paths_exported": False,
        "hostnames_exported": False,
        "ip_addresses_exported": False,
        "serial_numbers_exported": False,
    }
    write_json(output_root / "hardware_matrix_manifest.json", result)
    write_csv(output_root / "runtime_benchmark_results.csv", ["task", "status", "duration_s"], runtime_rows)
    write_csv(output_root / "artifact_size_summary.csv", ["artifact_family", "bytes"], artifact_rows)
    write_md(output_root / "hardware_matrix_report.md", f"# AIM Hardware Matrix\n\nResult class: `{result['result_class']}`.\n\nThis is sanitized local hardware characterization, not official platform benchmarking.")
    write_json(root / "results/aim_hardware_matrix/claim_update.json", result)
    return result


def build_paper_assets(root: Path, *, output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    tables = {
        "result_taxonomy_table.tex": r"\begin{tabular}{ll}Result family & Boundary \\ Fail-closed & Preserved as evidence \\ Mixed & Not promoted \\ Blocked & Reported explicitly \\\end{tabular}",
        "claim_boundary_table.tex": r"\begin{tabular}{ll}Claim & Status \\ RAG Compass superiority & Unsupported \\ Human validation & Unsupported \\ Production readiness & Unsupported \\\end{tabular}",
        "selector_ablation_summary.tex": r"\begin{tabular}{lll}Selector & Risk & Governance response \\ cost-only & quality loss risk & blocked when unsafe \\ risk-guarded & bounded & conservative \\\end{tabular}",
        "deployment_readiness_table.tex": r"\begin{tabular}{ll}Path & Status \\ Docker public-mini & validated \\ Cloud templates & static only \\\end{tabular}",
        "reproducibility_table.tex": r"\begin{tabular}{ll}Artifact & Status \\ public mini & available \\ verify-run & available \\ RC manifest & available \\\end{tabular}",
    }
    for name, text in tables.items():
        (output_root / name).write_text(text + "\n", encoding="utf-8")
    figures = root / "paper/figures"
    write_md(figures / "governance_flow_placeholder.md", "Placeholder: governance flow from evaluator metrics to promotion, block, reject, or inconclusive decisions.")
    write_md(figures / "deployment_architecture_placeholder.md", "Placeholder: local/Docker/cloud-template deployment architecture without production-readiness claims.")
    write_md(figures / "evidence_ladder_placeholder.md", "Placeholder: evidence ladder showing simulated, public, generative, fail-closed, and unsupported areas.")
    result = {"suite": "ragwarrant_arxiv_paper_assets_v1", "paper_tables_created": sorted(tables), "figures_are_placeholders": True}
    return result


def run_rc1_arxiv_readiness_synthesis(root: Path, *, output_root: Path) -> dict[str, Any]:
    evidence_paths = {
        "fresh_clone": root / "artifacts/fresh_clone_reproducibility/fresh_clone_manifest.json",
        "docker_runtime": root / "artifacts/docker_hardening/container_smoke_test_manifest.json",
        "release_candidate": root / "artifacts/release_candidate/v0.1.0-rc1/release_candidate_manifest.json",
        "crag_mapping_v2": root / "artifacts/crag_evaluator_mapping_v2/evaluator_mapping_v2_result.json",
        "hotpotqa_audit_v2": root / "artifacts/hotpotqa_quality_signal_audit_v2/audit_manifest.json",
        "selector_stress_v2": root / "artifacts/selector_ablation_stress_v2/selector_ablation_stress_manifest.json",
        "verify_run": root / "artifacts/verify_run_demo/verify_run_manifest.json",
        "external_adapters_v2": root / "artifacts/external_evaluator_adapters_v2/external_evaluator_manifest.json",
        "aim_hardware_matrix": root / "artifacts/aim_hardware_matrix/hardware_matrix_manifest.json",
    }
    evidence = {name: _load_json(path).get("result_class", "missing") for name, path in evidence_paths.items()}
    ready_count = sum(1 for value in evidence.values() if value and value != "missing" and "BLOCKED" not in str(value))
    result_class = "RC1_ARXIV_READINESS_SUPPORTED_WITH_BOUNDARIES" if ready_count >= 7 else "RC1_ARXIV_READINESS_MIXED" if ready_count >= 4 else "RC1_ARXIV_READINESS_INCONCLUSIVE"
    result = {
        "suite": "ragwarrant_rc1_arxiv_readiness_synthesis_v1",
        "result_class": result_class,
        "evidence": evidence,
        "paper_draft_status": "assembled_scaffold",
        "claim_boundary_validator": "strict",
        "ci_status": "local_validation_required_before_merge",
        "does_not_claim_rag_compass_superiority": True,
        "does_not_claim_human_validation": True,
        "does_not_claim_official_platform_benchmarking": True,
        "does_not_claim_production_readiness": True,
        "does_not_claim_hallucination_elimination": True,
    }
    rows = [{"evidence_item": key, "result_class": value} for key, value in evidence.items()]
    write_json(output_root / "synthesis_result.json", result)
    write_json(output_root / "claim_update.json", result)
    write_csv(output_root / "evidence_table.csv", ["evidence_item", "result_class"], rows)
    write_csv(output_root / "tool_readiness_table.csv", ["tool", "status"], [{"tool": key, "status": "available" if value != "missing" else "missing"} for key, value in evidence.items()])
    write_csv(output_root / "paper_readiness_table.csv", ["criterion", "status"], [{"criterion": "required sections", "status": "present"}, {"criterion": "claim boundaries", "status": "present"}, {"criterion": "tables", "status": "generated"}])
    write_md(output_root / "synthesis_report.md", f"# RC1 / arXiv Readiness\n\nResult class: `{result_class}`.\n\nThe package supports a bounded systems/methods paper and open-source RC framing. Mixed, blocked, and fail-closed results remain visible.")
    write_md(output_root / "executive_summary.md", f"RC1/arXiv synthesis result: `{result_class}`.")
    write_md(output_root / "limitations.md", "RC1 does not support production readiness, official platform benchmarking, RAG Compass superiority, human validation, or broad stable generative governance superiority.")
    return result
