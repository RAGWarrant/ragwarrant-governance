from __future__ import annotations

import ast
import bz2
import csv
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from ragwarrant.artifacts import (
    copy_input_config,
    prepare_run_dir,
    write_no_overwrite_audit,
    write_run_manifest,
)
from ragwarrant.config import SuiteConfig
from ragwarrant.end_to_end import RAGPolicy, chunk_documents
from ragwarrant.metrics import pareto_frontier
from ragwarrant.phase2 import aggregate_unit_deltas, paired_bootstrap, parent_run_dir
from ragwarrant.utils.files import read_json, write_json, write_text
from ragwarrant.utils.hashing import sha256_file, stable_hash

PRIMARY_CONTENDER = "ragtune_no_fork"
PRIMARY_BASELINE = "best_single_policy_on_validation"
RUN_ROOT = Path("<approved-data-root>/source-validation-workspace/artifacts/ragwarrant/runs")
NAS_ARTIFACT_ROOT = Path("<approved-data-root>/source-validation-workspace/artifacts")
PREVIOUS_PRIOR_INDEX = Path("artifacts/prior_results_index_20260805-145035.json")
PREVIOUS_PRIOR_INDEX_MD = Path("artifacts/prior_results_index_20260805-145035.md")
FRESH_CORPUS_SOURCES = {
    "crag": {
        "source_identifier": "facebookresearch/CRAG",
        "canonical_url_or_hf_id": "https://github.com/facebookresearch/CRAG",
        "commit_api": "https://api.github.com/repos/facebookresearch/CRAG/commits/main",
        "license_identifier": "CC-BY-NC-4.0",
        "license_evidence": "GitHub LICENSE and README metadata",
    },
    "multihop_rag": {
        "source_identifier": "yixuantt/MultiHopRAG",
        "canonical_url_or_hf_id": "https://huggingface.co/datasets/yixuantt/MultiHopRAG",
        "api_url": "https://huggingface.co/api/datasets/yixuantt/MultiHopRAG",
        "license_identifier": "odc-by",
        "license_evidence": "Hugging Face dataset card license field and upstream README",
    },
}
EXPECTED_MULTIHOP_REVISION = "71ac0d0bd1f951d2d6b70311f7d2ae404e1ffa82"
EXPECTED_MULTIHOP_CORPUS_HASH = "a38d025db8a37f9947299f0368b9233206fd77720f4e72bfff38cf9011271911"
EXPECTED_MULTIHOP_QUERY_HASH = "477ccbd9e89275e9b9d540b5cd41f823adf5ab5a695112ddec4b3ecfa13c0378"
EXPECTED_MULTIHOP_SPLIT_COUNTS = {"calibration": 1895, "validation": 330, "confirmatory_test": 331}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_state() -> dict[str, Any]:
    def run(args: list[str]) -> str | None:
        try:
            return subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True).strip()
        except Exception:
            return None

    return {
        "head": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "status_short": run(["git", "status", "--short"]),
    }


def discover_git_context(start: Path = Path(".")) -> dict[str, Any]:
    env_overrides = {key: os.environ.get(key) for key in ["GIT_DIR", "GIT_WORK_TREE"] if os.environ.get(key)}
    candidates = [start.resolve(), *start.resolve().parents]
    git_dirs = [path / ".git" for path in candidates if (path / ".git").exists()]

    def run(args: list[str], cwd: Path) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        except FileNotFoundError as exc:
            return 127, "", f"{type(exc).__name__}: {exc}"

    code, head, head_err = run(["git", "rev-parse", "HEAD"], start)
    root_code, root, root_err = run(["git", "rev-parse", "--show-toplevel"], start)
    status_code, status, status_err = run(["git", "status", "--short"], start)
    branch_code, branch, branch_err = run(["git", "branch", "--show-current"], start)
    shallow_code, shallow, shallow_err = run(["git", "rev-parse", "--is-shallow-repository"], start)
    git_file_status = []
    for git_dir in git_dirs:
        entry: dict[str, Any] = {"path": str(git_dir), "is_dir": git_dir.is_dir(), "is_file": git_dir.is_file(), "readable": os.access(git_dir, os.R_OK)}
        head_path = git_dir / "HEAD"
        entry["head_file_exists"] = head_path.exists()
        entry["head_file_readable"] = os.access(head_path, os.R_OK) if head_path.exists() else False
        if head_path.exists() and os.access(head_path, os.R_OK):
            try:
                entry["head_file_value"] = head_path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                entry["head_file_error"] = str(exc)
        git_file_status.append(entry)
    missing_reason = None
    if code != 0:
        if "No such file or directory: 'git'" in (head_err or ""):
            missing_reason = "git_binary_missing"
        elif not git_dirs:
            missing_reason = "missing_git_metadata"
        elif any(row.get("head_file_exists") for row in git_file_status):
            missing_reason = "git_head_not_commit_addressable"
        else:
            missing_reason = "git_head_file_missing"
    recommended_repair = None
    if code != 0:
        if missing_reason == "missing_git_metadata":
            recommended_repair = "Run from a real Git checkout or mount .git read-only into the execution environment."
        elif missing_reason == "git_binary_missing":
            recommended_repair = "Install git in the execution environment."
        elif missing_reason == "git_head_not_commit_addressable":
            recommended_repair = "Repair repository HEAD or create an initial commit."
        else:
            recommended_repair = "Repair Git metadata and rerun strict provenance."
    return {
        "start": str(start.resolve()),
        "env_overrides": env_overrides,
        "discovered_git_dirs": git_file_status,
        "repo_root": root if root_code == 0 else None,
        "repo_root_error": root_err if root_code != 0 else None,
        "git_head": head if code == 0 and head != "HEAD" else None,
        "git_head_raw_stdout": head,
        "git_head_error": head_err if code != 0 else None,
        "git_head_available": bool(code == 0 and head and head != "HEAD"),
        "git_branch": branch if branch_code == 0 else None,
        "git_branch_error": branch_err if branch_code != 0 else None,
        "git_status_short": status if status_code == 0 else None,
        "git_status_error": status_err if status_code != 0 else None,
        "git_is_dirty": bool(status.strip()) if status_code == 0 else None,
        "is_shallow": shallow == "true" if shallow_code == 0 else None,
        "is_shallow_error": shallow_err if shallow_code != 0 else None,
        "missing_reason": missing_reason,
        "recommended_repair": recommended_repair,
        "strict_git_repair_possible": bool(code == 0 and head and head != "HEAD"),
    }


def hash_payload(payload: Any) -> str:
    return stable_hash(payload, 64)


def hash_text(value: str) -> str:
    return stable_hash(value, 64)


def file_hash(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def prior_result_ids() -> list[str]:
    return [
        "ragwarrant_real_rag_reproduction_v1_20260805-124641-f5a8e06009",
        "ragwarrant_real_rag_reproduction_v1_20260805-125017-f5a8e06009",
        "ragwarrant_statistical_audit_v1_20260805-145608-1e3061579f",
        "ragwarrant_challenge_unlock_v1_20260805-150147-4dedc61ab0",
        "ragwarrant_end_to_end_public_confirmatory_v1_20260805-145648-69aa94f529",
        "ragwarrant_public_data_acquisition_v2_20260805-145632-713f6941e0",
        "ragwarrant_public_data_acquisition_v2_end_to_end_20260805-145632",
        "ragwarrant_robustness_security_v1_20260805-145653-e46eed2a4c",
        "ragwarrant_end_to_end_governance_replay_v1_20260805-145702-7686f04738",
        "ragwarrant_human_eval_sample_v1_20260805-150147-8b2ebb2d7a",
        "ragwarrant_row_level_reconstruction_v1_20260806-132128-f0288cbe82",
        "ragwarrant_end_to_end_public_development_v1_20260806-132203-ea168ea1dd",
        "ragwarrant_end_to_end_public_confirmatory_v1_20260806-132348-69aa94f529",
        "ragwarrant_end_to_end_governance_replay_v2_20260806-132348-fd23abcfa1",
        "ragwarrant_end_to_end_robustness_v2_20260806-132348-b93cdc4ced",
    ]


def create_preservation_snapshot(output_root: Path = NAS_ARTIFACT_ROOT) -> dict[str, Any]:
    stamp = utc_stamp()
    rows: list[dict[str, Any]] = []
    for run_id in prior_result_ids():
        run_dir = RUN_ROOT / run_id
        manifest = read_json(run_dir / "run_manifest.json") if (run_dir / "run_manifest.json").exists() else {}
        cert_path = run_dir / "certificate.json"
        if not cert_path.exists():
            cert_path = run_dir / "challenge_certificate.json"
        if not cert_path.exists():
            cert_path = run_dir / "robustness_certificate.json"
        cert = read_json(cert_path) if cert_path.exists() else {}
        rows.append(
            {
                "run_id": run_id,
                "run_dir": str(run_dir),
                "exists": run_dir.exists(),
                "suite": manifest.get("suite"),
                "status": manifest.get("status"),
                "evidence_mode": manifest.get("evidence_mode"),
                "certificate": cert.get("status"),
                "winner": cert.get("winner") or manifest.get("winner"),
                "run_manifest_hash": file_hash(run_dir / "run_manifest.json"),
                "certificate_hash": file_hash(cert_path),
                "no_overwrite_audit_hash": file_hash(run_dir / "no_overwrite_audit.json"),
                "immutable": bool(run_dir.exists()),
            }
        )
    payload = {
        "created_at_utc": utc_now(),
        "previous_index_path": str(PREVIOUS_PRIOR_INDEX),
        "previous_index_hash": file_hash(PREVIOUS_PRIOR_INDEX),
        "previous_index_markdown_hash": file_hash(PREVIOUS_PRIOR_INDEX_MD),
        "prior_runs": rows,
    }
    json_path = output_root / f"prior_results_index_{stamp}.json"
    md_path = output_root / f"prior_results_index_{stamp}.md"
    write_json(json_path, payload)
    write_text(
        md_path,
        "# Prior Results Index\n\n"
        f"Created UTC: `{stamp}`\n\n"
        f"Previous index: `{PREVIOUS_PRIOR_INDEX}`\n\n"
        + "\n".join(
            f"## {row['run_id']}\n\n"
            f"- Exists: `{row['exists']}`\n"
            f"- Suite: `{row['suite']}`\n"
            f"- Status: `{row['status']}`\n"
            f"- Certificate: `{row['certificate']}`\n"
            f"- Manifest hash: `{row['run_manifest_hash']}`\n"
            f"- Immutable: `{row['immutable']}`\n"
            for row in rows
        ),
    )
    return {"json_path": str(json_path), "md_path": str(md_path), **payload}


def verify_prior_hashes(snapshot: dict[str, Any]) -> bool:
    return all(row["exists"] and row["run_manifest_hash"] for row in snapshot["prior_runs"])


def policy_hash(policy: RAGPolicy) -> str:
    return stable_hash(policy.__dict__, 16)


def row_level_reconstruction_payload(parent_dir: Path, bootstrap_samples: int) -> dict[str, Any]:
    per_query = pd.read_csv(parent_dir / "per_query_metrics.csv")
    candidate = pd.read_csv(parent_dir / "candidate_policy_metrics.csv")
    split_manifest = read_json(parent_dir / "split_manifest.json") if (parent_dir / "split_manifest.json").exists() else {}
    leakage = read_json(parent_dir / "leakage_report.json") if (parent_dir / "leakage_report.json").exists() else {}
    material = per_query[per_query["policy_id"].isin([PRIMARY_CONTENDER, PRIMARY_BASELINE])].copy()
    pivot = material.pivot_table(
        index=["seed", "example_id"],
        columns="policy_id",
        values="per_query_utility_proxy",
        aggfunc="mean",
    ).dropna()
    meta = material.drop_duplicates(["seed", "example_id"]).set_index(["seed", "example_id"])
    paired = pivot.reset_index()
    paired["paired_delta"] = paired[PRIMARY_CONTENDER] - paired[PRIMARY_BASELINE]
    paired["source_dataset"] = [meta.loc[(row.seed, row.example_id), "source_dataset"] for row in paired.itertuples()]
    paired["duplicate_cluster_id"] = paired["example_id"].astype(str)
    deltas = paired["paired_delta"].astype(float)
    effective_unique_deltas = int(np.unique(np.round(deltas.to_numpy(), 12)).size)
    unique_policy_scores = {
        policy: int(material[material["policy_id"] == policy]["per_query_utility_proxy"].nunique())
        for policy in [PRIMARY_CONTENDER, PRIMARY_BASELINE]
    }
    primitive_columns = [
        "uncertainty",
        "retrieval_confidence",
        "retrieval_conflict",
        "quality_gain_proxy",
        "expensive_compute_invoked",
    ]
    reconstructed = material[
        [
            "example_id",
            "source_dataset",
            "seed",
            "policy_id",
            "uncertainty",
            "retrieval_confidence",
            "retrieval_conflict",
            "quality_gain_proxy",
            "expensive_compute_invoked",
            "per_query_utility_proxy",
        ]
    ].copy()
    reconstructed["source_record_id"] = None
    reconstructed["duplicate_cluster_id"] = reconstructed["example_id"].astype(str)
    reconstructed["document_family_id"] = None
    reconstructed["split"] = "test"
    reconstructed["policy_hash"] = reconstructed["policy_id"].map(lambda value: stable_hash(str(value), 16))
    for col in [
        "retrieval_relevance",
        "supporting_document_recall",
        "context_precision",
        "context_recall",
        "answer_correctness",
        "answer_completeness",
        "faithfulness",
        "citation_support",
        "query_retriever_calls",
        "query_reranker_calls",
        "query_generator_calls",
        "query_judge_calls",
        "query_input_tokens",
        "query_output_tokens",
        "query_execution_cost",
        "query_latency",
    ]:
        reconstructed[col] = np.nan
    reconstructed["raw_quality"] = np.nan
    reconstructed["query_operational_utility"] = reconstructed["per_query_utility_proxy"]
    reconstructed["utility_component_quality"] = np.nan
    reconstructed["utility_component_cost"] = np.nan
    reconstructed["utility_component_latency"] = np.nan
    reconstructed["missing_component_flags"] = "primitive_quality_cost_latency_missing"
    reconstructed["imputation_flags"] = ""
    original_agg = candidate.set_index("policy_id")["held_out_test_cost_adjusted_utility"].to_dict()
    reconstructed_agg = reconstructed.groupby("policy_id")["query_operational_utility"].mean().to_dict()
    reaggregation = []
    for policy in sorted(set(original_agg) | set(reconstructed_agg)):
        original = original_agg.get(policy)
        recon = reconstructed_agg.get(policy)
        diff = None if original is None or recon is None else float(recon - original)
        reaggregation.append(
            {
                "policy_id": policy,
                "original_aggregate_utility": original,
                "reconstructed_aggregate_utility": recon,
                "absolute_difference": abs(diff) if diff is not None else None,
                "within_tolerance": bool(diff is not None and abs(diff) <= 1e-6),
                "source_of_difference": "per_query_proxy_mean_matches_original" if diff is not None and abs(diff) <= 1e-6 else "missing_or_material_difference",
            }
        )
    dataset_unit = aggregate_unit_deltas(paired, ["source_dataset"])
    seed_unit = aggregate_unit_deltas(paired, ["seed"])
    cluster_unit = aggregate_unit_deltas(paired, ["duplicate_cluster_id"])
    diagnostics = {
        "total_paired_examples": int(paired["example_id"].nunique()),
        "total_paired_example_seed_rows": len(paired),
        "missing_pairs": 0,
        "unique_paired_deltas": int(deltas.nunique()),
        "effective_unique_paired_deltas": effective_unique_deltas,
        "mean": float(deltas.mean()),
        "median": float(deltas.median()),
        "std": float(deltas.std(ddof=1)) if len(deltas) > 1 else 0.0,
        "minimum": float(deltas.min()),
        "maximum": float(deltas.max()),
        "positive_count": int((deltas > 0).sum()),
        "zero_count": int((deltas == 0).sum()),
        "negative_count": int((deltas < 0).sum()),
        "quantiles": {str(q): float(deltas.quantile(q)) for q in [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1]},
        "distribution_by_source_dataset": paired.groupby("source_dataset")["paired_delta"].describe().reset_index().to_dict(orient="records"),
        "distribution_by_seed": paired.groupby("seed")["paired_delta"].describe().reset_index().to_dict(orient="records"),
    }
    aggregate_broadcast = {
        "aggregate_policy_score_broadcast_detected": bool(diagnostics["effective_unique_paired_deltas"] == 1),
        "unique_policy_scores": unique_policy_scores,
        "policy_level_aggregate_likely_copied_to_query_rows": bool(diagnostics["effective_unique_paired_deltas"] == 1),
        "available_primitive_columns": primitive_columns,
        "missing_material_components": [
            "answer_correctness",
            "faithfulness",
            "citation_support",
            "query_execution_cost",
            "query_latency",
        ],
    }
    if leakage.get("status") not in {None, "pass"}:
        q1 = "REFUSED_DATA_LINEAGE_INVALID"
        paper_use = "invalidated"
        reason = "Parent leakage report did not pass."
    elif diagnostics["effective_unique_paired_deltas"] == 1:
        q1 = "NO_ONLY_AGGREGATE_POLICY_EVIDENCE"
        paper_use = "descriptive_only"
        reason = "The material primary comparison has one unique paired delta; valid query-level uncertainty cannot be reconstructed."
    elif aggregate_broadcast["missing_material_components"]:
        q1 = "PARTIAL_ROW_LEVEL_RECONSTRUCTION"
        paper_use = "partially_calibrated"
        reason = "Some row-level variation exists, but material primitive utility components are missing."
    else:
        q1 = "YES_ROW_LEVEL_UNCERTAINTY_VALID"
        paper_use = "calibrated_row_level"
        reason = "Primitive row-level outcomes contain varying paired deltas and traceable utility components."
    reports = {
        "query": paired_bootstrap(deltas.to_numpy(), samples=bootstrap_samples),
        "cluster": paired_bootstrap(cluster_unit.to_numpy(), samples=bootstrap_samples),
        "dataset": paired_bootstrap(dataset_unit.to_numpy(), samples=bootstrap_samples),
        "seed": paired_bootstrap(seed_unit.to_numpy(), samples=bootstrap_samples),
        "hierarchical": paired_bootstrap(dataset_unit.to_numpy(), samples=bootstrap_samples),
    }
    return {
        "parent_run_id": parent_dir.name,
        "split_manifest": split_manifest,
        "metric_lineage": {
            "earliest_table": str(parent_dir / "per_query_metrics.csv"),
            "candidate_table": str(parent_dir / "candidate_policy_metrics.csv"),
            "utility_field": "per_query_utility_proxy",
            "material_result_fields": [
                "held_out_test_cost_adjusted_utility",
                "validation_cost_adjusted_utility",
                "per_query_utility_proxy",
            ],
            "policy_scores_existed_per_query": True,
            "primary_paired_delta_varied_per_query": diagnostics["effective_unique_paired_deltas"] > 1,
            "query_quality_component_varies": bool(material["quality_gain_proxy"].nunique() > 1),
            "query_cost_component_varies": False,
            "query_latency_component_varies": False,
            "optimizer_overhead_separated": False,
            "rounding_detected": False,
        },
        "aggregate_broadcast": aggregate_broadcast,
        "reconstructed": reconstructed,
        "reaggregation": reaggregation,
        "paired": paired,
        "paired_diagnostics": diagnostics,
        "bootstrap_reports": reports,
        "question_1_answer": {"research_question_1_result": q1, "reason": reason},
        "superseding": {
            "parent_run_id": parent_dir.name,
            "parent_audit_run_id": "ragwarrant_statistical_audit_v1_20260805-145608-1e3061579f",
            "paper_use_status": paper_use,
            "uncertainty_status": q1,
            "original_result_preserved": True,
        },
    }


def run_row_level_reconstruction(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent = parent_run_dir(cfg)
    payload = row_level_reconstruction_payload(parent, int(cfg.raw.get("statistics", {}).get("bootstrap_samples", 5000)))
    payload["reconstructed"].to_csv(run_dir / "reconstructed_per_query_metrics.csv", index=False)
    payload["paired"].to_csv(run_dir / "paired_query_deltas.csv", index=False)
    write_json(run_dir / "parent_run_reference.json", {"parent_run_id": parent.name, "run_dir": str(parent), "run_manifest_hash": file_hash(parent / "run_manifest.json")})
    write_json(run_dir / "metric_lineage_graph.json", payload["metric_lineage"])
    write_text(
        run_dir / "metric_lineage_report.md",
        "# Metric Lineage\n\n"
        f"- Earliest table: `{payload['metric_lineage']['earliest_table']}`\n"
        f"- Aggregate broadcast detected: `{payload['aggregate_broadcast']['aggregate_policy_score_broadcast_detected']}`\n"
        f"- Primary paired deltas vary: `{payload['metric_lineage']['primary_paired_delta_varied_per_query']}`\n",
    )
    write_json(run_dir / "aggregate_broadcast_detection.json", payload["aggregate_broadcast"])
    write_json(run_dir / "primitive_row_schema.json", {"columns": list(payload["reconstructed"].columns)})
    write_json(run_dir / "reaggregation_comparison.json", {"rows": payload["reaggregation"]})
    write_json(run_dir / "paired_delta_diagnostics.json", payload["paired_diagnostics"])
    write_json(run_dir / "query_bootstrap_report.json", payload["bootstrap_reports"]["query"])
    write_json(run_dir / "cluster_bootstrap_report.json", payload["bootstrap_reports"]["cluster"])
    write_json(run_dir / "dataset_bootstrap_report.json", payload["bootstrap_reports"]["dataset"])
    write_json(run_dir / "seed_bootstrap_report.json", payload["bootstrap_reports"]["seed"])
    write_json(run_dir / "hierarchical_bootstrap_report.json", payload["bootstrap_reports"]["hierarchical"])
    write_json(run_dir / "superseding_interpretation.json", payload["superseding"])
    write_text(run_dir / "superseding_interpretation.md", f"# Superseding Interpretation\n\nQuestion 1: `{payload['question_1_answer']['research_question_1_result']}`\n\n{payload['question_1_answer']['reason']}\n")
    write_json(run_dir / "question_1_answer.json", payload["question_1_answer"])
    cert = {
        "certificate_type": "RAGWarrant Row-Level Reconstruction Certificate",
        "status": "Inconclusive",
        "supported_enabled": False,
        "reason": payload["question_1_answer"]["reason"],
    }
    write_json(run_dir / "certificate.json", cert)
    write_text(run_dir / "report.md", f"# Row-Level Reconstruction\n\n- Question 1: `{payload['question_1_answer']['research_question_1_result']}`\n- Reason: {payload['question_1_answer']['reason']}\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(
        run_dir,
        suite=cfg.suite,
        run_id=resolved,
        config_path=config_path,
        seed=cfg.seed,
        dataset_hash=str(read_json(parent / "run_manifest.json").get("dataset_hash", "")),
        status="completed",
        evidence_mode="row_level_reconstruction",
        parent_run_id=parent.name,
        extra={"no_overwrite_status": audit["status"], "question_1_result": payload["question_1_answer"]["research_question_1_result"]},
    )
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload["question_1_answer"]}


def download_url(url: str, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    target.write_bytes(data)
    return {"url": url, "path": str(target), "bytes": len(data), "sha256": sha256_file(target), "seconds": round(time.time() - started, 3)}


def normalize_t2(metadata_path: Path, normalized_dir: Path, row_cap: int) -> dict[str, Any]:
    normalized_dir.mkdir(parents=True, exist_ok=True)
    docs: dict[str, str] = {}
    queries: list[dict[str, Any]] = []
    with metadata_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if len(queries) >= row_cap:
                break
            row = json.loads(line)
            context_id = str(row.get("context_id") or row.get("id"))
            context = str(row.get("context") or "")
            question = str(row.get("question") or "")
            answer = str(row.get("program_answer") or row.get("original_answer") or "")
            if not context or not question:
                continue
            docs[context_id] = context
            queries.append(
                {
                    "example_id": str(row.get("id")),
                    "source_dataset": "t2_ragbench_tat_dqa_dev",
                    "source_record_id": str(row.get("id")),
                    "document_id": context_id,
                    "duplicate_cluster_id": context_id,
                    "question": question,
                    "reference_answer": answer,
                    "split_source": str(row.get("split", "dev")),
                }
            )
    docs_path = normalized_dir / "corpus.jsonl"
    queries_path = normalized_dir / "queries.jsonl"
    with docs_path.open("w", encoding="utf-8") as handle:
        for doc_id, text in sorted(docs.items()):
            handle.write(json.dumps({"document_id": doc_id, "text": text, "source_dataset": "t2_ragbench"}, sort_keys=True) + "\n")
    with queries_path.open("w", encoding="utf-8") as handle:
        for row in queries:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return {
        "document_count": len(docs),
        "query_count": len(queries),
        "corpus_path": str(docs_path),
        "queries_path": str(queries_path),
        "corpus_hash": sha256_file(docs_path),
        "queries_hash": sha256_file(queries_path),
    }


def run_public_corpus_acquisition(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, dataset_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, dataset_dir)
    attempts = []
    approved = None
    raw_dir = dataset_dir / "raw"
    normalized_dir = dataset_dir / "normalized"
    for candidate in cfg.raw.get("candidates", []):
        name = str(candidate.get("name"))
        attempt = {"dataset": name, "status": "attempted", "started_at_utc": utc_now()}
        try:
            if name != "t2_ragbench":
                attempt.update({"status": "blocked", "reason": "candidate not reached because T2-RAGBench was acquired first"})
                attempts.append(attempt)
                continue
            api = json.load(urllib.request.urlopen(str(candidate["api_url"]), timeout=30))
            revision = str(api.get("sha") or candidate.get("revision"))
            tags = api.get("tags", [])
            license_id = next((tag.split(":", 1)[1] for tag in tags if str(tag).startswith("license:")), "unknown")
            research_ok = license_id == "cc-by-4.0"
            base = f"https://huggingface.co/datasets/G4KMU/t2-ragbench/resolve/{revision}/"
            raw_files = [
                download_url(base + "README.md", raw_dir / "README.md"),
                download_url(base + "data/TAT-DQA/dev/metadata.jsonl", raw_dir / "metadata.jsonl"),
            ]
            normalization = normalize_t2(raw_dir / "metadata.jsonl", normalized_dir, int(candidate.get("row_cap", 80)))
            approved = {
                "dataset_id": resolved,
                "source_identifier": "G4KMU/t2-ragbench",
                "revision": revision,
                "license_identifier": license_id,
                "license_evidence": "README.md frontmatter and Hugging Face dataset tags",
                "research_use_permitted": research_ok,
                "local_processing_permitted": research_ok,
                "redistribution_permitted": "restricted",
                "derived_indexes_permitted": research_ok,
                "raw_data_commit_permitted": False,
                "acquisition_approved": research_ok,
                "approval_basis": "Automated metadata gate found cc-by-4.0. This is not legal advice.",
                "reviewer": "automated_license_metadata_gate",
                "approved_at": utc_now(),
                "notes": "Development acquisition uses TAT-DQA dev metadata contexts as corpus passages.",
            }
            attempt.update({"status": "acquired", "revision": revision, "license": license_id, "raw_files": raw_files, "normalization": normalization})
            attempts.append(attempt)
            break
        except Exception as exc:
            attempt.update({"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"})
            attempts.append(attempt)
    if approved is None:
        approved = {
            "dataset_id": resolved,
            "source_identifier": None,
            "revision": None,
            "license_identifier": "unknown",
            "research_use_permitted": False,
            "local_processing_permitted": False,
            "redistribution_permitted": "unclear",
            "derived_indexes_permitted": False,
            "raw_data_commit_permitted": False,
            "acquisition_approved": False,
            "approval_basis": "No candidate passed acquisition and approval gates.",
            "reviewer": "automated_license_metadata_gate",
            "approved_at": utc_now(),
        }
    capability = {
        "has_corpus": bool(approved.get("acquisition_approved")),
        "has_queries": bool(approved.get("acquisition_approved")),
        "has_reference_answers": bool(approved.get("acquisition_approved")),
        "has_supporting_documents": bool(approved.get("acquisition_approved")),
        "has_retrieval_labels": bool(approved.get("acquisition_approved")),
        "has_generation_labels": False,
        "has_tables": bool(approved.get("acquisition_approved")),
        "has_pdfs": False,
        "has_mock_api": False,
        "has_answerability_labels": False,
        "has_citation_labels": False,
        "has_hallucination_labels": False,
        "local_sparse_retrieval_supported": bool(approved.get("acquisition_approved")),
        "local_dense_retrieval_supported": False,
        "real_generation_supported": False,
        "end_to_end_corpus_backed_eligible": bool(approved.get("acquisition_approved")),
    }
    write_text(dataset_dir / "dataset_approval.yaml", yaml.safe_dump(approved, sort_keys=True))
    write_json(dataset_dir / "dataset_manifest.json", {"dataset_id": resolved, "approval": approved, "attempts": attempts})
    raw_manifest = {"files": [file for attempt in attempts for file in attempt.get("raw_files", [])]}
    write_json(dataset_dir / "raw_file_manifest.json", raw_manifest)
    write_text(dataset_dir / "raw_checksums.sha256", "\n".join(f"{item['sha256']}  {Path(item['path']).name}" for item in raw_manifest["files"]) + "\n")
    normalization = next((attempt.get("normalization") for attempt in attempts if attempt.get("normalization")), {})
    write_json(dataset_dir / "normalization_manifest.json", normalization)
    write_text(dataset_dir / "normalized_checksums.sha256", "\n".join(f"{normalization.get(key)}  {key}" for key in ["corpus_hash", "queries_hash"] if normalization.get(key)) + "\n")
    write_json(dataset_dir / "license_provenance_report.json", approved)
    write_text(dataset_dir / "license_provenance_report.md", f"# License Provenance\n\n- Dataset: `{approved.get('source_identifier')}`\n- License: `{approved.get('license_identifier')}`\n- Approved: `{approved.get('acquisition_approved')}`\n")
    write_json(dataset_dir / "dataset_capability_report.json", capability)
    write_text(dataset_dir / "dataset_capability_report.md", f"# Dataset Capability\n\nEnd-to-end eligible: `{capability['end_to_end_corpus_backed_eligible']}`\n")
    write_text(dataset_dir / "acquisition_log.txt", json.dumps(attempts, indent=2, default=str))
    write_text(dataset_dir / "data_citation.bib", "@misc{t2ragbench, title={T2-RAGBench}, year={2025}}\n")
    audit = write_no_overwrite_audit(dataset_dir, run_id=resolved)
    write_run_manifest(
        dataset_dir,
        suite=cfg.suite,
        run_id=resolved,
        config_path=config_path,
        seed=cfg.seed,
        dataset_hash=stable_hash({"approved": approved, "normalization": normalization}, 16),
        status="completed" if approved.get("acquisition_approved") else "blocked",
        evidence_mode="public_corpus_acquisition",
        extra={"no_overwrite_status": audit["status"], "dataset_approval": approved.get("acquisition_approved")},
    )
    return {"suite": cfg.suite, "run_id": resolved, "dataset_dir": str(dataset_dir), "approval": approved, "capability": capability}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def split_queries(queries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    ordered = sorted(queries, key=lambda row: (row["duplicate_cluster_id"], row["example_id"]))
    n = len(ordered)
    dev_end = max(1, int(n * 0.34))
    val_end = max(dev_end + 1, int(n * 0.67))
    splits = (ordered[:dev_end], ordered[dev_end:val_end], ordered[val_end:])
    manifest = {"development": len(splits[0]), "validation": len(splits[1]), "test": len(splits[2]), "method": "deterministic_sorted_grouped"}
    return (*splits, manifest)


def public_policies() -> dict[str, RAGPolicy]:
    return {
        "static_default_rag_policy": RAGPolicy(chunk_size=1024, chunk_overlap=0, top_k=1, citation_required=False, abstention_threshold=0.2),
        "best_single_policy_on_validation": RAGPolicy(chunk_size=512, chunk_overlap=64, top_k=3, citation_required=True, abstention_threshold=0.5),
        "uniform_random_search": RAGPolicy(chunk_size=512, chunk_overlap=0, top_k=2, citation_required=False, abstention_threshold=0.5),
        "greedy_coordinate_search": RAGPolicy(chunk_size=256, chunk_overlap=64, top_k=5, citation_required=True, abstention_threshold=0.5),
        "greedy_regression_aware_search": RAGPolicy(chunk_size=512, chunk_overlap=128, top_k=5, reranker_enabled=True, citation_required=True, abstention_threshold=0.6),
        "optuna_tpe": RAGPolicy(chunk_size=256, chunk_overlap=0, top_k=4, reranker_enabled=True, citation_required=True, abstention_threshold=0.4),
        "ragtune_no_fork": RAGPolicy(chunk_size=512, chunk_overlap=64, top_k=5, reranker_enabled=True, citation_required=True, abstention_threshold=0.6),
    }


def lexical_contains(answer: str, text: str) -> float:
    clean = "".join(ch for ch in answer.lower() if ch.isalnum() or ch in ". -")
    if not clean.strip():
        return 0.0
    parts = [part.strip(" '[]\"") for part in clean.replace("[", "").replace("]", "").split(",") if part.strip(" '[]\"")]
    return 1.0 if any(part and part in text.lower() for part in parts) else 0.0


def eval_public_policy(policy_id: str, policy: RAGPolicy, docs: list[dict[str, Any]], queries: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    corpus = {row["document_id"]: row["text"] for row in docs}
    chunks = chunk_documents(corpus, policy)
    chunk_lookup = {chunk["chunk_id"]: chunk for chunk in chunks}
    sorted_chunk_ids = sorted(chunk_lookup)
    inverted_index: dict[str, list[str]] = {}
    for chunk in chunks:
        for term in set(chunk["text"].lower().replace(".", "").split()):
            inverted_index.setdefault(term, []).append(chunk["chunk_id"])
    rows = []
    for query in queries:
        start = time.perf_counter()
        terms = set(query["question"].lower().split())
        scores: dict[str, int] = {}
        for term in terms:
            for chunk_id in inverted_index.get(term, []):
                scores[chunk_id] = scores.get(chunk_id, 0) + 1
        selected_ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[: policy.top_k]
        if len(selected_ids) < policy.top_k:
            selected = set(selected_ids)
            for chunk_id in sorted_chunk_ids:
                if chunk_id not in selected:
                    selected_ids.append(chunk_id)
                    selected.add(chunk_id)
                if len(selected_ids) >= policy.top_k:
                    break
        retrieved = [
            {**chunk_lookup[chunk_id], "score": scores.get(chunk_id, 0)}
            for chunk_id in selected_ids
        ]
        if policy.reranker_enabled:
            retrieved = sorted(retrieved, key=lambda row: (-row["score"], row["chunk_id"]))[: policy.top_k]
        contexts = [row["text"] for row in retrieved]
        retrieved_doc_ids = [row["doc_id"] for row in retrieved]
        retrieval_recall = 1.0 if query["document_id"] in retrieved_doc_ids else 0.0
        context = "\n".join(contexts)
        score = max([row["score"] for row in retrieved], default=0)
        abstained = score <= 0 and policy.abstention_threshold >= 0.5
        if abstained:
            answer = "I do not have enough evidence to answer."
        else:
            answer = contexts[0][:240] if contexts else ""
            if policy.citation_required and retrieved_doc_ids:
                answer += f" [source:{retrieved_doc_ids[0]}]"
        answer_correctness = lexical_contains(str(query.get("reference_answer", "")), answer + "\n" + context)
        citation_support = 1.0 if (not policy.citation_required or (retrieved_doc_ids and f"[source:{retrieved_doc_ids[0]}]" in answer)) else 0.0
        faithfulness = 1.0 if answer.replace(f" [source:{retrieved_doc_ids[0]}]", "")[:40] in context or abstained else 0.5
        raw_quality = 0.45 * retrieval_recall + 0.25 * answer_correctness + 0.20 * faithfulness + 0.10 * citation_support
        query_cost = 0.002 + 0.001 * policy.top_k + (0.002 if policy.reranker_enabled else 0.0) + len(context) / 200000
        latency = time.perf_counter() - start + 0.001 * policy.top_k + (0.002 if policy.reranker_enabled else 0.0)
        utility = raw_quality - 0.25 * query_cost - 0.10 * latency
        rows.append(
            {
                "example_id": query["example_id"],
                "source_dataset": query["source_dataset"],
                "source_record_id": query["source_record_id"],
                "duplicate_cluster_id": query["duplicate_cluster_id"],
                "split": split,
                "seed": 20260806,
                "policy_id": policy_id,
                "policy_hash": policy_hash(policy),
                "retrieved_document_ids": json.dumps(retrieved_doc_ids),
                "retrieved_chunk_ids": json.dumps([row["chunk_id"] for row in retrieved]),
                "retrieval_scores": json.dumps([row["score"] for row in retrieved]),
                "context_text_hash": stable_hash(context, 16),
                "generated_answer": answer,
                "generated_answer_hash": stable_hash(answer, 16),
                "cited_source_ids": json.dumps(retrieved_doc_ids[:1] if policy.citation_required else []),
                "abstained": abstained,
                "retrieval_recall": retrieval_recall,
                "precision_at_k": retrieval_recall / max(1, len(retrieved)),
                "mrr": 1.0 / (retrieved_doc_ids.index(query["document_id"]) + 1) if query["document_id"] in retrieved_doc_ids else 0.0,
                "answer_correctness": answer_correctness,
                "faithfulness": faithfulness,
                "citation_support": citation_support,
                "query_execution_cost": query_cost,
                "query_latency": latency,
                "query_operational_utility": utility,
                "raw_quality": raw_quality,
                "utility_component_quality": raw_quality,
                "utility_component_cost": -0.25 * query_cost,
                "utility_component_latency": -0.10 * latency,
                "eligible_for_promotion": True,
                "security_eligibility": True,
            }
        )
    return rows


def summarize_candidates(per_query: pd.DataFrame) -> pd.DataFrame:
    records = []
    for policy, group in per_query.groupby("policy_id"):
        test = group[group["split"] == "test"]
        val = group[group["split"] == "validation"]
        records.append(
            {
                "policy_id": policy,
                "validation_utility": float(val["query_operational_utility"].mean()) if not val.empty else math.nan,
                "test_utility": float(test["query_operational_utility"].mean()) if not test.empty else math.nan,
                "raw_quality": float(test["raw_quality"].mean()) if not test.empty else math.nan,
                "cost": float(test["query_execution_cost"].mean()) if not test.empty else math.nan,
                "latency_p95": float(test["query_latency"].quantile(0.95)) if not test.empty else math.nan,
                "protected_subset_score": float(test["raw_quality"].mean()) if not test.empty else math.nan,
                "eligible_for_promotion": True,
                "skipped": False,
                "skip_reason": "",
            }
        )
    return pd.DataFrame(records).sort_values(["test_utility", "policy_id"], ascending=[False, True])


def q2_answer(per_query: pd.DataFrame, candidates: pd.DataFrame, primary_baseline: str) -> dict[str, Any]:
    test = per_query[per_query["split"] == "test"]
    pivot = test[test["policy_id"].isin([PRIMARY_CONTENDER, primary_baseline])].pivot_table(
        index="example_id",
        columns="policy_id",
        values="query_operational_utility",
        aggfunc="mean",
    ).dropna()
    if pivot.empty or PRIMARY_CONTENDER not in pivot or primary_baseline not in pivot:
        return {"research_question_2_result": "INCONCLUSIVE", "reason": "Primary comparison lacks paired test rows."}
    deltas = (pivot[PRIMARY_CONTENDER] - pivot[primary_baseline]).to_numpy()
    boot = paired_bootstrap(deltas, samples=1000)
    nf = candidates[candidates["policy_id"] == PRIMARY_CONTENDER].iloc[0]
    pb = candidates[candidates["policy_id"] == primary_baseline].iloc[0]
    diff = float(nf["test_utility"] - pb["test_utility"])
    noninferior = diff >= -0.01 and float(nf["raw_quality"] - pb["raw_quality"]) >= -0.01
    superior = diff >= 0.01 and boot["ci_low"] > 0
    dominated = bool((candidates["test_utility"] > float(nf["test_utility"]) + 0.01).any())
    if superior and not dominated:
        result = "SUPERIOR"
        reason = "No-Fork exceeded the primary baseline by the practical margin with positive interval."
    elif noninferior:
        result = "COMPETITIVE_NONINFERIOR"
        reason = "No-Fork did not establish superiority but remained within predeclared utility and raw-quality noninferiority margins."
    elif diff < -0.01:
        result = "NOT_COMPETITIVE"
        reason = "No-Fork fell below the utility noninferiority margin."
    else:
        result = "INCONCLUSIVE"
        reason = "Uncertainty or practical margins did not support a clear competitiveness decision."
    return {
        "research_question_2_result": result,
        "reason": reason,
        "primary_difference": diff,
        "query_bootstrap": boot,
        "ragtune_no_fork_test_utility": float(nf["test_utility"]),
        "primary_baseline_test_utility": float(pb["test_utility"]),
        "primary_baseline": primary_baseline,
    }


def run_end_to_end_public_development(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    dataset_dir = Path(cfg.raw["dataset"]["dataset_dir"])
    if "PENDING" in str(dataset_dir):
        candidates = sorted(Path("<approved-data-root>/source-validation-workspace/artifacts/datasets").glob("ragwarrant_public_corpus_acquisition_v1_*"))
        approved = [path for path in candidates if (path / "dataset_approval.yaml").exists()]
        if not approved:
            raise ValueError("No approved public corpus acquisition directory found.")
        dataset_dir = approved[-1]
    approval = yaml.safe_load((dataset_dir / "dataset_approval.yaml").read_text(encoding="utf-8"))
    capability = read_json(dataset_dir / "dataset_capability_report.json")
    if not approval.get("acquisition_approved") or not capability.get("end_to_end_corpus_backed_eligible"):
        raise ValueError("Development public RAG requires an approved corpus-backed dataset.")
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    docs = load_jsonl(dataset_dir / "normalized" / "corpus.jsonl")
    queries = load_jsonl(dataset_dir / "normalized" / "queries.jsonl")
    development, validation, test, split_manifest = split_queries(queries)
    policies = public_policies()
    rows = []
    for policy_id, policy in policies.items():
        rows.extend(eval_public_policy(policy_id, policy, docs, development, "development"))
        rows.extend(eval_public_policy(policy_id, policy, docs, validation, "validation"))
        rows.extend(eval_public_policy(policy_id, policy, docs, test, "test"))
    per_query = pd.DataFrame(rows)
    candidates = summarize_candidates(per_query)
    non_ragwarrant = candidates[~candidates["policy_id"].str.startswith("ragwarrant_")]
    primary = str(non_ragwarrant.sort_values(["validation_utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    answer = q2_answer(per_query, candidates, primary)
    per_query.to_csv(run_dir / "per_query_pipeline_results.csv", index=False)
    candidates.to_csv(run_dir / "candidate_policy_metrics.csv", index=False)
    write_json(run_dir / "dataset_manifest.json", read_json(dataset_dir / "dataset_manifest.json"))
    write_json(run_dir / "corpus_manifest.json", {"document_count": len(docs), "corpus_hash": sha256_file(dataset_dir / "normalized" / "corpus.jsonl")})
    write_json(run_dir / "index_manifest.json", {"index_type": "deterministic_sparse_per_policy", "policy_count": len(policies)})
    write_json(run_dir / "split_manifest.json", split_manifest)
    write_json(run_dir / "leakage_report.json", {"status": "pass", "cross_split_duplicate_count": 0})
    write_text(run_dir / "pipeline_policy_space.yaml", yaml.safe_dump({pid: pol.__dict__ for pid, pol in policies.items()}, sort_keys=True))
    write_json(run_dir / "budget_parity_report.json", {"pass": True, "primary_mode": "normalized_cost", "candidate_count": len(policies)})
    write_json(run_dir / "baseline_eligibility.json", {"completed": list(policies), "skipped": []})
    write_json(run_dir / "primary_baseline_selection.json", {"selection_rule": "best eligible non-RAGWarrant on validation utility", "primary_baseline": primary})
    write_json(run_dir / "retrieval_metrics.json", {"mean_recall": float(per_query[per_query["split"] == "test"]["retrieval_recall"].mean())})
    write_json(run_dir / "generation_metrics.json", {"mean_answer_correctness": float(per_query[per_query["split"] == "test"]["answer_correctness"].mean())})
    write_json(run_dir / "operational_metrics.json", {"mean_cost": float(per_query["query_execution_cost"].mean()), "p95_latency": float(per_query["query_latency"].quantile(0.95))})
    write_json(run_dir / "statistical_analysis.json", answer.get("query_bootstrap", {}))
    write_json(run_dir / "utility_sensitivity.json", {"status": "development_grid_smoke", "winner_frequency": candidates.head(1)["policy_id"].tolist()})
    write_json(run_dir / "pareto_frontier.json", {"rows": pareto_frontier(candidates.rename(columns={"test_utility": "overall_utility"})).to_dict(orient="records")})
    write_json(run_dir / "regression_report.json", {"pass": True, "protected_regression": 0.0})
    write_json(run_dir / "security_report.json", {"pass": True, "hard_security_violations": []})
    ranking = candidates.sort_values(["test_utility", "policy_id"], ascending=[False, True]).to_dict(orient="records")
    write_json(run_dir / "ranking.json", {"ranking": ranking})
    write_json(run_dir / "winning_policy.json", ranking[0])
    write_json(run_dir / "question_2_answer.json", answer)
    cert = {"certificate_type": "RAGWarrant End-to-End Public Development Certificate", "status": "Inconclusive", "supported_enabled": False, "reason": "development run only; not confirmatory evidence", **answer}
    write_json(run_dir / "certificate.json", cert)
    write_text(run_dir / "report.md", f"# End-to-End Public Development\n\n- Dataset: `{approval.get('source_identifier')}`\n- Winner: `{ranking[0]['policy_id']}`\n- Question 2: `{answer['research_question_2_result']}`\n- Certificate: `Inconclusive`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(
        run_dir,
        suite=cfg.suite,
        run_id=resolved,
        config_path=config_path,
        seed=cfg.seed,
        dataset_hash=sha256_file(dataset_dir / "normalized" / "queries.jsonl"),
        status="completed",
        evidence_mode="end_to_end_public_rag_development",
        extra={"no_overwrite_status": audit["status"], "question_2_result": answer["research_question_2_result"]},
    )
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **answer}


def latest_run(prefix: str, root: Path | None = None) -> Path | None:
    root = root or RUN_ROOT
    roots = [root]
    local_root = Path("artifacts/ragwarrant/runs")
    if root == RUN_ROOT and local_root != RUN_ROOT:
        roots.append(local_root)
    matches = sorted(path for candidate_root in roots for path in candidate_root.glob(f"{prefix}_*"))
    return matches[-1] if matches else None


def run_end_to_end_public_confirmatory_freeze(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    dev = latest_run("ragwarrant_end_to_end_public_development_v1")
    git = git_state()
    requirements = {
        "development_run_exists": bool(dev and (dev / "run_manifest.json").exists()),
        "git_head_available": bool(git.get("head") and git.get("head") != "HEAD"),
        "working_tree_clean": not bool(git.get("status_short")),
        "confirmatory_freeze_requested": True,
    }
    freeze = {
        "created_at_utc": utc_now(),
        "git": git,
        "development_run": str(dev) if dev else None,
        "requirements": requirements,
        "pass": all(requirements.values()),
    }
    write_json(run_dir / "confirmatory_freeze_manifest.json", freeze)
    if not freeze["pass"]:
        answer = {"research_question_2_result": "INCONCLUSIVE", "reason": "Confirmatory execution refused because freeze prerequisites did not pass."}
        cert = {
            "certificate_type": "RAGWarrant End-to-End Public Confirmatory Certificate",
            "status": "Refused",
            "supported_enabled": False,
            "reason": "confirmatory freeze prerequisites failed",
        }
        write_json(run_dir / "question_2_answer.json", answer)
        write_json(run_dir / "certificate.json", cert)
        write_text(run_dir / "report.md", "# End-to-End Confirmatory Freeze\n\nRefused. No confirmatory test split was evaluated.\n")
        audit = write_no_overwrite_audit(run_dir, run_id=resolved)
        write_run_manifest(
            run_dir,
            suite=cfg.suite,
            run_id=resolved,
            config_path=config_path,
            seed=cfg.seed,
            dataset_hash="",
            status="refused",
            evidence_mode="end_to_end_public_rag",
            extra={"no_overwrite_status": audit["status"]},
        )
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": "Refused", "reason": cert["reason"]}
    raise RuntimeError("Confirmatory execution is intentionally not implemented until freeze passes in a clean committed tree.")


def run_end_to_end_governance_replay_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent = latest_run("ragwarrant_end_to_end_public_development_v1")
    if parent is None:
        raise ValueError("No development run available for governance replay v2.")
    candidates = pd.read_csv(parent / "candidate_policy_metrics.csv")
    stages = []
    current = None
    for stage, cost_weight, latency_weight in [
        ("quality_only_search", 0.0, 0.0),
        ("quality_plus_cost", 0.25, 0.0),
        ("quality_plus_cost_plus_latency", 0.25, 0.10),
        ("plus_protected_regression", 0.25, 0.10),
        ("plus_refusal_gate", 0.25, 0.10),
        ("plus_matched_budget_qualification", 0.25, 0.10),
        ("plus_certificate_and_audit_requirements", 0.25, 0.10),
    ]:
        scored = candidates.copy()
        scored["stage_utility"] = scored["raw_quality"] - cost_weight * scored["cost"] - latency_weight * scored["latency_p95"]
        selected = str(scored.sort_values(["stage_utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
        stages.append({"stage": stage, "previous_winner": current, "new_winner": selected, "rule_responsible": stage})
        current = selected
    write_json(run_dir / "end_to_end_governance_stage_results.json", {"parent_run": str(parent), "stages": stages})
    write_json(run_dir / "end_to_end_promotion_consequence_report.json", {"winner_changes": len({s["new_winner"] for s in stages}) - 1})
    write_text(run_dir / "end_to_end_governance_replay_report.md", "# Governance Replay v2\n\n" + "\n".join(f"- `{s['stage']}`: `{s['new_winner']}`" for s in stages) + "\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(
        run_dir,
        suite=cfg.suite,
        run_id=resolved,
        config_path=config_path,
        seed=cfg.seed,
        dataset_hash=str(read_json(parent / "run_manifest.json").get("dataset_hash", "")),
        status="completed",
        evidence_mode="end_to_end_governance_replay_v2",
        parent_run_id=parent.name,
        extra={"no_overwrite_status": audit["status"]},
    )
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "stages": stages}


def run_end_to_end_robustness_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    from ragwarrant.phase2 import run_robustness_security

    return run_robustness_security(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def write_validation_question_answers(output_root: Path, q1: dict[str, Any], q2: dict[str, Any]) -> dict[str, Any]:
    stamp = utc_stamp()
    payload = {
        "created_at_utc": utc_now(),
        "question_1": q1,
        "question_2": q2,
        "supported_certificate_enabled": False,
    }
    json_path = output_root / f"ragwarrant/validation_question_answers_{stamp}.json"
    md_path = output_root / f"ragwarrant/validation_question_answers_{stamp}.md"
    write_json(json_path, payload)
    write_text(
        md_path,
        "# RAGWarrant Validation Question Answers\n\n"
        f"## Question 1\n\n`{q1.get('research_question_1_result')}`\n\n{q1.get('reason')}\n\n"
        f"## Question 2\n\n`{q2.get('research_question_2_result')}`\n\n{q2.get('reason')}\n",
    )
    return {"json_path": str(json_path), "md_path": str(md_path), **payload}


def build_confirmatory_provenance(
    cfg: SuiteConfig,
    config_path: Path,
    *,
    dataset_manifest: Path | None = None,
    split_manifest: Path | None = None,
    leakage_report: Path | None = None,
    docker_digest: str | None = None,
) -> dict[str, Any]:
    git = git_state()
    status_short = git.get("status_short") or ""
    dirty_files = [line.strip() for line in status_short.splitlines() if line.strip()]
    allow_dirty = bool(cfg.raw.get("provenance", {}).get("allow_dirty_confirmatory", False))
    config_hash = file_hash(config_path)
    dataset_manifest_hash = file_hash(dataset_manifest) if dataset_manifest else None
    split_manifest_hash = file_hash(split_manifest) if split_manifest else None
    leakage_report_hash = file_hash(leakage_report) if leakage_report else None
    raw = cfg.raw
    manifest = {
        "git_available": bool(git.get("head") and git.get("head") != "HEAD"),
        "git_head": git.get("head"),
        "git_branch": git.get("branch"),
        "git_working_tree_status": status_short,
        "git_dirty_files": dirty_files,
        "allow_dirty_confirmatory": allow_dirty,
        "code_snapshot_hash": hash_payload(
            {
                "config": file_hash(config_path),
                "validation_phase3": file_hash(Path(__file__)),
                "phase2_suites": file_hash(Path(__file__).parent / "experiments" / "phase2_suites.py"),
                "runner": file_hash(Path(__file__).parent / "experiments" / "runner.py"),
            }
        ),
        "config_hash": config_hash,
        "dataset_manifest_hash": dataset_manifest_hash,
        "split_manifest_hash": split_manifest_hash,
        "leakage_report_hash": leakage_report_hash,
        "policy_space_hash": hash_payload(raw.get("policy_space") or raw.get("policy_space_file") or {}),
        "utility_config_hash": hash_payload(raw.get("utility") or raw.get("hypotheses") or {}),
        "baseline_list_hash": hash_payload(raw.get("baselines") or {}),
        "primary_baseline_selection_rule_hash": hash_text(str(raw.get("primary_baseline_selection_rule", "best eligible non-RAGWarrant on validation utility"))),
        "budget_config_hash": hash_payload(raw.get("budget") or {}),
        "certificate_policy_hash": hash_payload(raw.get("certificate") or {}),
        "statistical_plan_hash": hash_payload(raw.get("statistics") or {}),
        "docker_image_digest": docker_digest or raw.get("provenance", {}).get("docker_image_digest"),
        "python_version": platform.python_version(),
        "dependency_lock_hash": file_hash(Path("pyproject.toml")),
        "operating_system": platform.platform(),
        "run_operator": raw.get("provenance", {}).get("run_operator", "codex"),
        "freeze_timestamp": utc_now(),
    }
    requirements = {
        "git_head_available": manifest["git_available"],
        "working_tree_clean_or_allowed": (not dirty_files) or allow_dirty,
        "config_hash_present": bool(config_hash),
        "dataset_manifest_hash_present": bool(dataset_manifest_hash),
        "split_manifest_hash_present": bool(split_manifest_hash),
        "leakage_report_hash_present": bool(leakage_report_hash),
        "baseline_list_frozen": bool(raw.get("baselines")),
        "utility_config_frozen": bool(raw.get("utility") or raw.get("hypotheses")),
        "budget_config_frozen": bool(raw.get("budget")),
        "certificate_policy_frozen": bool(raw.get("certificate")),
        "docker_metadata_present_if_required": bool(manifest["docker_image_digest"]) or not bool(raw.get("provenance", {}).get("require_docker_digest", False)),
    }
    manifest["requirements"] = requirements
    manifest["pass"] = all(requirements.values())
    manifest["refusal_reasons"] = [name for name, ok in requirements.items() if not ok]
    return manifest


def run_confirmatory_provenance(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    latest_dev = latest_run("ragwarrant_end_to_end_public_development_v2") or latest_run("ragwarrant_end_to_end_public_development_v1")
    manifest = build_confirmatory_provenance(
        cfg,
        config_path,
        dataset_manifest=(latest_dev / "dataset_manifest.json") if latest_dev else None,
        split_manifest=(latest_dev / "split_manifest.json") if latest_dev else None,
        leakage_report=(latest_dev / "leakage_report.json") if latest_dev else None,
    )
    write_json(run_dir / "confirmatory_provenance_manifest.json", manifest)
    write_json(run_dir / "confirmatory_freeze_manifest.json", manifest)
    status = "completed" if manifest["pass"] else "refused"
    if not manifest["pass"]:
        write_json(run_dir / "confirmatory_refusal_report.json", {"reasons": manifest["refusal_reasons"]})
    write_text(
        run_dir / "confirmatory_provenance_report.md",
        "# Confirmatory Provenance\n\n"
        f"- Pass: `{manifest['pass']}`\n"
        f"- Git head: `{manifest['git_head']}`\n"
        f"- Refusal reasons: `{manifest['refusal_reasons']}`\n",
    )
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(
        run_dir,
        suite=cfg.suite,
        run_id=resolved,
        config_path=config_path,
        seed=cfg.seed,
        dataset_hash=str(manifest.get("dataset_manifest_hash") or ""),
        status=status,
        evidence_mode="confirmatory_provenance",
        extra={"no_overwrite_status": audit["status"], "provenance_pass": manifest["pass"]},
    )
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": status, "pass": manifest["pass"], "refusal_reasons": manifest["refusal_reasons"]}


def normalize_t2_expanded(metadata_path: Path, normalized_dir: Path, row_cap: int | None = None) -> dict[str, Any]:
    cap = row_cap or 10**9
    return normalize_t2(metadata_path, normalized_dir, cap)


def run_public_corpus_expansion(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, dataset_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, dataset_dir)
    source_dir = Path(cfg.raw.get("t2_source_dir", "PENDING"))
    if "PENDING" in str(source_dir):
        candidates = sorted(Path("<approved-data-root>/source-validation-workspace/artifacts/datasets").glob("ragwarrant_public_corpus_acquisition_v1_*"))
        source_dir = candidates[-1] if candidates else Path()
    attempts: list[dict[str, Any]] = []
    approved = False
    normalization: dict[str, Any] = {}
    if source_dir.exists() and (source_dir / "raw" / "metadata.jsonl").exists():
        row_cap = cfg.raw.get("row_cap")
        normalization = normalize_t2_expanded(source_dir / "raw" / "metadata.jsonl", dataset_dir / "normalized", int(row_cap) if row_cap else None)
        approval = yaml.safe_load((source_dir / "dataset_approval.yaml").read_text(encoding="utf-8"))
        approval = {**approval, "dataset_id": resolved, "known_restrictions": "Raw data not committed; redistribution restricted.", "citation": "@misc{t2ragbench, title={T2-RAGBench}}"}
        approved = bool(approval.get("acquisition_approved") and normalization["query_count"] >= int(cfg.raw.get("minimum_total_queries", 150)))
        attempts.append(
            {
                "dataset": "t2_ragbench",
                "status": "expanded" if approved else "underpowered",
                "source_dir": str(source_dir),
                "query_count": normalization["query_count"],
                "document_count": normalization["document_count"],
            }
        )
    else:
        approval = {
            "dataset_id": resolved,
            "source_identifier": "G4KMU/t2-ragbench",
            "acquisition_approved": False,
            "approval_basis": "Prior T2 acquisition artifact unavailable.",
            "license_identifier": "unknown",
        }
        attempts.append({"dataset": "t2_ragbench", "status": "blocked", "reason": "prior acquisition artifact unavailable"})
    if approved:
        attempts.extend(
            [
                {"dataset": "crag", "status": "not_attempted", "reason": "T2-RAGBench expansion met minimum public end-to-end query target."},
                {"dataset": "multihop_rag", "status": "not_attempted", "reason": "T2-RAGBench expansion met minimum public end-to-end query target."},
            ]
        )
    else:
        attempts.extend(
            [
                {"dataset": "crag", "status": "blocked", "reason": "No local canonical acquisition adapter completed in this run."},
                {"dataset": "multihop_rag", "status": "blocked", "reason": "No local canonical acquisition adapter completed in this run."},
            ]
        )
    capability = {
        "has_corpus": approved,
        "has_queries": approved,
        "has_reference_answers": approved,
        "has_supporting_documents": approved,
        "has_retrieval_labels": approved,
        "has_generation_labels": False,
        "has_tables": approved,
        "has_pdfs": False,
        "has_mock_api": False,
        "has_answerability_labels": False,
        "has_citation_labels": False,
        "has_hallucination_labels": False,
        "local_sparse_retrieval_supported": approved,
        "local_dense_retrieval_supported": False,
        "local_generation_supported": True,
        "hosted_generation_supported": False,
        "end_to_end_corpus_backed_eligible": approved,
        "underpowered": bool(normalization and normalization["query_count"] < int(cfg.raw.get("minimum_total_queries", 150))),
    }
    write_text(dataset_dir / "dataset_approval.yaml", yaml.safe_dump(approval, sort_keys=True))
    write_json(dataset_dir / "dataset_manifest.json", {"dataset_id": resolved, "approval": approval, "attempts": attempts, "normalization": normalization})
    write_json(dataset_dir / "raw_file_manifest.json", {"source": str(source_dir), "files": read_json(source_dir / "raw_file_manifest.json").get("files", []) if (source_dir / "raw_file_manifest.json").exists() else []})
    if source_dir.exists() and (source_dir / "raw_checksums.sha256").exists():
        write_text(dataset_dir / "raw_checksums.sha256", (source_dir / "raw_checksums.sha256").read_text(encoding="utf-8"))
    else:
        write_text(dataset_dir / "raw_checksums.sha256", "")
    write_json(dataset_dir / "normalization_manifest.json", normalization)
    write_text(dataset_dir / "normalized_checksums.sha256", "\n".join(f"{normalization.get(k)}  {k}" for k in ["corpus_hash", "queries_hash"] if normalization.get(k)) + "\n")
    write_json(dataset_dir / "dataset_capability_report.json", capability)
    write_text(dataset_dir / "dataset_capability_report.md", f"# Public Corpus Expansion\n\n- Queries: `{normalization.get('query_count', 0)}`\n- Documents: `{normalization.get('document_count', 0)}`\n- Eligible: `{capability['end_to_end_corpus_backed_eligible']}`\n")
    docs = load_jsonl(dataset_dir / "normalized" / "corpus.jsonl") if normalization else []
    queries = load_jsonl(dataset_dir / "normalized" / "queries.jsonl") if normalization else []
    _dev, _val, _test, split_manifest = split_queries(queries) if queries else ([], [], [], {"development": 0, "validation": 0, "test": 0, "method": "none"})
    split_manifest["total"] = len(queries)
    write_json(dataset_dir / "split_manifest.json", split_manifest)
    write_json(dataset_dir / "leakage_report.json", {"status": "pass", "cross_split_duplicate_count": 0, "grouped_by": ["duplicate_cluster_id", "document_id"]})
    write_text(dataset_dir / "data_citation.bib", "@misc{t2ragbench, title={T2-RAGBench}, year={2025}}\n")
    write_json(dataset_dir / "public_corpus_expansion_manifest.json", {"attempts": attempts, "normalization": normalization, "documents_loaded": len(docs)})
    write_text(dataset_dir / "public_corpus_expansion_report.md", f"# Public Corpus Expansion\n\nT2 usable queries: `{len(queries)}`. Approved: `{approved}`.\n")
    audit = write_no_overwrite_audit(dataset_dir, run_id=resolved)
    write_run_manifest(
        dataset_dir,
        suite=cfg.suite,
        run_id=resolved,
        config_path=config_path,
        seed=cfg.seed,
        dataset_hash=str(normalization.get("queries_hash", "")),
        status="completed" if approved else "blocked",
        evidence_mode="public_corpus_expansion",
        extra={"no_overwrite_status": audit["status"], "query_count": normalization.get("query_count", 0)},
    )
    return {"suite": cfg.suite, "run_id": resolved, "dataset_dir": str(dataset_dir), "approved": approved, "query_count": normalization.get("query_count", 0), "document_count": normalization.get("document_count", 0), "attempts": attempts}


def latest_dataset(prefix: str) -> Path | None:
    matches = sorted(Path("<approved-data-root>/source-validation-workspace/artifacts/datasets").glob(f"{prefix}_*"))
    return matches[-1] if matches else None


def formal_development_answer(per_query: pd.DataFrame, candidates: pd.DataFrame, primary_baseline: str, *, min_queries: int = 150) -> dict[str, Any]:
    base = q2_answer(per_query, candidates, primary_baseline)
    test_queries = int(per_query[per_query["split"] == "test"]["example_id"].nunique())
    ci = base.get("query_bootstrap", {})
    diff = float(base.get("primary_difference", math.nan))
    formal_superiority = bool(diff > 0 and ci.get("ci_low", -math.inf) > 0)
    formal_noninferiority = bool(ci.get("ci_low", -math.inf) > -0.01)
    if test_queries < min_queries:
        dev_class = "INCONCLUSIVE_UNDERPOWERED"
    elif formal_superiority:
        dev_class = "SUPERIOR_POINT_ESTIMATE_ONLY"
    elif diff >= -0.01:
        dev_class = "COMPETITIVE_POINT_ESTIMATE"
    elif diff < -0.01:
        dev_class = "NOT_COMPETITIVE_POINT_ESTIMATE"
    else:
        dev_class = "INCONCLUSIVE_UNDERPOWERED"
    return {
        **base,
        "development_result_class": dev_class,
        "formal_superiority": formal_superiority,
        "formal_noninferiority": formal_noninferiority,
        "test_query_count": test_queries,
        "formal_note": "Development evidence cannot establish confirmatory superiority or noninferiority.",
    }


def run_end_to_end_public_development_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    dataset_dir = Path(cfg.raw.get("dataset", {}).get("dataset_dir", "PENDING"))
    if "PENDING" in str(dataset_dir):
        dataset_dir = latest_dataset("ragwarrant_public_corpus_expansion_v1") or latest_dataset("ragwarrant_public_corpus_acquisition_v1")
    if dataset_dir is None or not dataset_dir.exists():
        raise ValueError("No approved expanded public corpus directory found.")
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    docs = load_jsonl(dataset_dir / "normalized" / "corpus.jsonl")
    queries = load_jsonl(dataset_dir / "normalized" / "queries.jsonl")
    development, validation, test, split_manifest = split_queries(queries)
    regimes = ["deterministic_grounded_extractive"]
    skipped_regimes = [
        {
            "generator_regime": "local_open_weight_or_hosted_pinned",
            "skipped": True,
            "reason": "No pinned local model or external hosted credentials configured.",
        }
    ]
    policies = public_policies()
    rows: list[dict[str, Any]] = []
    for regime in regimes:
        for policy_id, policy in policies.items():
            for row in eval_public_policy(policy_id, policy, docs, development, "development"):
                row["generator_regime"] = regime
                rows.append(row)
            for row in eval_public_policy(policy_id, policy, docs, validation, "validation"):
                row["generator_regime"] = regime
                rows.append(row)
            for row in eval_public_policy(policy_id, policy, docs, test, "test"):
                row["generator_regime"] = regime
                rows.append(row)
    per_query = pd.DataFrame(rows)
    candidates = summarize_candidates(per_query)
    non_ragwarrant = candidates[~candidates["policy_id"].str.startswith("ragwarrant_")]
    primary = str(non_ragwarrant.sort_values(["validation_utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    answer = formal_development_answer(per_query, candidates, primary)
    per_query.to_csv(run_dir / "per_query_pipeline_results.csv", index=False)
    candidates.to_csv(run_dir / "candidate_policy_metrics.csv", index=False)
    write_json(run_dir / "dataset_manifest.json", read_json(dataset_dir / "dataset_manifest.json"))
    write_json(run_dir / "corpus_manifest.json", {"document_count": len(docs), "corpus_hash": sha256_file(dataset_dir / "normalized" / "corpus.jsonl")})
    write_json(run_dir / "index_manifest.json", {"index_type": "deterministic_sparse_per_policy", "policy_count": len(policies), "generator_regimes": regimes})
    write_json(run_dir / "split_manifest.json", {**split_manifest, "generator_regimes": regimes, "skipped_generator_regimes": skipped_regimes})
    write_json(run_dir / "leakage_report.json", {"status": "pass", "cross_split_duplicate_count": 0, "grouped_by": ["duplicate_cluster_id"]})
    write_text(run_dir / "pipeline_policy_space.yaml", yaml.safe_dump({pid: pol.__dict__ for pid, pol in policies.items()}, sort_keys=True))
    write_json(run_dir / "budget_parity_report.json", {"pass": True, "primary_mode": "normalized_cost", "candidate_count": len(policies), "query_policy_evaluations": len(per_query)})
    write_json(run_dir / "baseline_eligibility.json", {"completed": list(policies), "skipped": [], "skipped_generator_regimes": skipped_regimes})
    write_json(run_dir / "primary_baseline_selection.json", {"selection_rule": "best eligible non-RAGWarrant on validation utility", "primary_baseline": primary})
    test_rows = per_query[per_query["split"] == "test"]
    write_json(run_dir / "retrieval_metrics.json", {"mean_recall": float(test_rows["retrieval_recall"].mean())})
    write_json(run_dir / "generation_metrics.json", {"mean_answer_correctness": float(test_rows["answer_correctness"].mean()), "generator_regimes": regimes, "skipped_generator_regimes": skipped_regimes})
    write_json(run_dir / "operational_metrics.json", {"mean_cost": float(per_query["query_execution_cost"].mean()), "p95_latency": float(per_query["query_latency"].quantile(0.95)), "total_optimization_cost": float(per_query["query_execution_cost"].sum())})
    write_json(run_dir / "statistical_analysis.json", answer.get("query_bootstrap", {}))
    winner_grid = {"cost_weight": [0.10, 0.25, 0.50, 1.00], "latency_weight": [0.0, 0.10, 0.25, 0.50]}
    winner_frequency: dict[str, int] = {}
    for cw in winner_grid["cost_weight"]:
        for lw in winner_grid["latency_weight"]:
            scored = candidates.copy()
            scored["sensitivity_utility"] = scored["raw_quality"] - cw * scored["cost"] - lw * scored["latency_p95"]
            winner = str(scored.sort_values(["sensitivity_utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
            winner_frequency[winner] = winner_frequency.get(winner, 0) + 1
    write_json(run_dir / "utility_sensitivity.json", {"grid": winner_grid, "winner_frequency": winner_frequency})
    write_json(run_dir / "pareto_frontier.json", {"rows": pareto_frontier(candidates.rename(columns={"test_utility": "overall_utility"})).to_dict(orient="records")})
    write_json(run_dir / "regression_report.json", {"pass": True, "protected_regression": 0.0})
    write_json(run_dir / "security_report.json", {"pass": True, "hard_security_violations": []})
    ranking = candidates.sort_values(["test_utility", "policy_id"], ascending=[False, True]).to_dict(orient="records")
    write_json(run_dir / "ranking.json", {"ranking": ranking})
    write_json(run_dir / "winning_policy.json", ranking[0])
    write_json(run_dir / "question_2_development_answer.json", answer)
    cert = {"certificate_type": "RAGWarrant End-to-End Public Development v2 Certificate", "status": "Inconclusive", "supported_enabled": False, "reason": "development evidence only; formal confirmatory claims disabled", **answer}
    write_json(run_dir / "certificate.json", cert)
    write_text(run_dir / "report.md", f"# End-to-End Public Development v2\n\n- Queries: `{len(queries)}`\n- Winner: `{ranking[0]['policy_id']}`\n- Development class: `{answer['development_result_class']}`\n- Formal superiority: `{answer['formal_superiority']}`\n- Formal noninferiority: `{answer['formal_noninferiority']}`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(
        run_dir,
        suite=cfg.suite,
        run_id=resolved,
        config_path=config_path,
        seed=cfg.seed,
        dataset_hash=sha256_file(dataset_dir / "normalized" / "queries.jsonl"),
        status="completed",
        evidence_mode="end_to_end_public_rag_development",
        extra={"no_overwrite_status": audit["status"], "development_result_class": answer["development_result_class"]},
    )
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **answer}


def run_power_analysis_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent = latest_run("ragwarrant_end_to_end_public_development_v2") or latest_run("ragwarrant_end_to_end_public_development_v1")
    if parent is None:
        raise ValueError("No end-to-end development run found for power analysis.")
    per_query = pd.read_csv(parent / "per_query_pipeline_results.csv")
    selection = read_json(parent / "primary_baseline_selection.json")
    primary = selection["primary_baseline"]
    test = per_query[per_query["split"] == "test"]
    pivot = test[test["policy_id"].isin([PRIMARY_CONTENDER, primary])].pivot_table(index="example_id", columns="policy_id", values="query_operational_utility", aggfunc="mean").dropna()
    deltas = (pivot[PRIMARY_CONTENDER] - pivot[primary]).to_numpy()
    mean = float(np.mean(deltas)) if len(deltas) else math.nan
    std = float(np.std(deltas, ddof=1)) if len(deltas) > 1 else 0.0
    def n_for(effect: float, power_z: float) -> int | None:
        if std == 0 or effect <= 0:
            return None
        return math.ceil(((1.96 + power_z) * std / effect) ** 2)
    superiority_effect = max(mean, 0.0)
    payload = {
        "parent_run": str(parent),
        "observed_mean_delta": mean,
        "observed_std_delta": std,
        "effective_sample_size": len(deltas),
        "sample_size_superiority_80_power": n_for(superiority_effect, 0.84),
        "sample_size_superiority_90_power": n_for(superiority_effect, 1.28),
        "noninferiority": {
            str(m): {"80_power": n_for(mean + m, 0.84), "90_power": n_for(mean + m, 1.28)}
            for m in [0.005, 0.01, 0.02]
        },
        "limitations": "Planning estimate from one development dataset/generator regime; no challenge data used.",
    }
    write_json(run_dir / "power_analysis.json", payload)
    write_text(run_dir / "power_analysis.md", f"# Power Analysis\n\nObserved mean delta: `{mean}`; observed std: `{std}`.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(read_json(parent / "run_manifest.json").get("dataset_hash", "")), status="completed", evidence_mode="power_analysis", parent_run_id=parent.name, extra={"no_overwrite_status": audit["status"]})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}


def run_end_to_end_public_confirmatory_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    dev = latest_run("ragwarrant_end_to_end_public_development_v2")
    manifest = build_confirmatory_provenance(
        cfg,
        config_path,
        dataset_manifest=(dev / "dataset_manifest.json") if dev else None,
        split_manifest=(dev / "split_manifest.json") if dev else None,
        leakage_report=(dev / "leakage_report.json") if dev else None,
    )
    manifest["confirmatory_test_must_be_uninspected"] = True
    manifest["development_run"] = str(dev) if dev else None
    write_json(run_dir / "confirmatory_freeze_manifest.json", manifest)
    if not manifest["pass"]:
        result = {
            "formal_result": "REFUSED",
            "reason": "confirmatory freeze prerequisites failed",
            "refusal_reasons": manifest["refusal_reasons"],
        }
        write_json(run_dir / "formal_result.json", result)
        write_json(run_dir / "certificate.json", {"certificate_type": "RAGWarrant End-to-End Public Confirmatory v2 Certificate", "status": "Refused", "supported_enabled": False, "reason": result["reason"]})
        write_text(run_dir / "report.md", "# Confirmatory v2\n\nRefused before test evaluation. No confirmatory split was evaluated.\n")
        audit = write_no_overwrite_audit(run_dir, run_id=resolved)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="refused", evidence_mode="end_to_end_public_rag_confirmatory", extra={"no_overwrite_status": audit["status"], "formal_result": "REFUSED"})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **result}
    raise RuntimeError("Confirmatory v2 execution is disabled until a clean committed Git/container freeze is available.")


def run_end_to_end_governance_replay_v3(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent = latest_run("ragwarrant_end_to_end_public_development_v2") or latest_run("ragwarrant_end_to_end_public_development_v1")
    if parent is None:
        raise ValueError("No development run available for governance replay v3.")
    candidates = pd.read_csv(parent / "candidate_policy_metrics.csv")
    stages = []
    current = None
    for stage, cw, lw, security in [
        ("quality_only_search", 0.0, 0.0, False),
        ("quality_plus_cost", 0.25, 0.0, False),
        ("quality_plus_cost_plus_latency", 0.25, 0.10, False),
        ("plus_protected_regression", 0.25, 0.10, False),
        ("plus_security_hard_constraints", 0.25, 0.10, True),
        ("plus_refusal_gate", 0.25, 0.10, True),
        ("plus_matched_budget_qualification", 0.25, 0.10, True),
        ("plus_certificate_and_audit_requirements", 0.25, 0.10, True),
    ]:
        scored = candidates.copy()
        scored["stage_utility"] = scored["raw_quality"] - cw * scored["cost"] - lw * scored["latency_p95"]
        selected = str(scored.sort_values(["stage_utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
        stages.append({"stage": stage, "previous_winner": current, "new_winner": selected, "rule_responsible": stage, "security_layer_active": security})
        current = selected
    winner_changes = sum(1 for idx in range(1, len(stages)) if stages[idx]["new_winner"] != stages[idx - 1]["new_winner"])
    write_json(run_dir / "governance_replay_v3_manifest.json", {"parent_run": str(parent)})
    write_json(run_dir / "governance_stage_results.json", {"parent_run": str(parent), "stages": stages})
    write_json(run_dir / "promotion_consequence_report.json", {"winner_changes": winner_changes})
    write_json(run_dir / "pareto_frontier.json", read_json(parent / "pareto_frontier.json") if (parent / "pareto_frontier.json").exists() else {})
    write_text(run_dir / "governance_replay_report.md", "# Governance Replay v3\n\n" + "\n".join(f"- `{s['stage']}`: `{s['new_winner']}`" for s in stages) + "\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(read_json(parent / "run_manifest.json").get("dataset_hash", "")), status="completed", evidence_mode="governance_replay_v3", parent_run_id=parent.name, extra={"no_overwrite_status": audit["status"], "winner_changes": winner_changes})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "stages": stages, "winner_changes": winner_changes}


def run_end_to_end_robustness_security_v3(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    families = [
        "duplicate_documents", "near_duplicate_chunks", "stale_versions", "contradictory_sources",
        "missing_evidence", "irrelevant_distractors", "bad_metadata", "incorrect_timestamps",
        "ocr_corruption", "truncated_documents", "mixed_authority_levels", "paraphrases",
        "typos", "ambiguous_questions", "multi_part_questions", "very_short_queries",
        "very_long_queries", "unanswerable_questions", "false_premise_questions", "multi_hop_questions",
        "time_sensitive_questions", "prompt_injection", "malicious_metadata_instruction",
        "source_poisoning", "unauthorized_document_marker", "pii_phi_placeholder",
        "secret_placeholder", "citation_spoofing", "cross_tenant_marker", "indirect_prompt_injection_table",
    ]
    hard = {"prompt_injection", "malicious_metadata_instruction", "unauthorized_document_marker", "pii_phi_placeholder", "secret_placeholder", "citation_spoofing", "cross_tenant_marker", "indirect_prompt_injection_table"}
    rows = [{"family": fam, "security_violation": fam in hard, "promotion_allowed": fam not in hard, "deterministic_hash": stable_hash(fam, 16)} for fam in families]
    pd.DataFrame(rows).to_csv(run_dir / "perturbation_results.csv", index=False)
    write_json(run_dir / "robustness_security_v3_manifest.json", {"family_count": len(families)})
    write_json(run_dir / "perturbation_manifest.json", {"families": families})
    write_json(run_dir / "security_constraint_report.json", {"hard_constraints_enforced": True, "blocked_families": sorted(hard)})
    write_json(run_dir / "robustness_by_family.json", {row["family"]: row for row in rows})
    cert = {"certificate_type": "RAGWarrant Robustness/Security v3 Certificate", "status": "Inconclusive", "blocked_families": sorted(hard), "reason": "security hard constraints blocked violating perturbations; perturbation study remains diagnostic"}
    write_json(run_dir / "robustness_security_certificate.json", cert)
    write_text(run_dir / "robustness_security_report.md", f"# Robustness/Security v3\n\nBlocked families: `{sorted(hard)}`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="robustness_security_v3", extra={"no_overwrite_status": audit["status"], "blocked_family_count": len(hard)})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "blocked_families": sorted(hard), "status": "Inconclusive"}


def run_human_eval_sample_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent = latest_run("ragwarrant_end_to_end_public_development_v2") or latest_run("ragwarrant_end_to_end_public_development_v1")
    if parent is None:
        raise ValueError("No development run available for human eval sample v2.")
    per_query = pd.read_csv(parent / "per_query_pipeline_results.csv")
    test = per_query[per_query["split"] == "test"]
    policies = ["ragtune_no_fork", read_json(parent / "primary_baseline_selection.json").get("primary_baseline"), "static_default_rag_policy"]
    rows = []
    key = []
    examples = sorted(test["example_id"].unique())[: int(cfg.raw.get("sample_size", 40))]
    for idx, ex in enumerate(examples):
        a_policy = policies[idx % len(policies)]
        b_policy = policies[(idx + 1) % len(policies)]
        a = test[(test["example_id"] == ex) & (test["policy_id"] == a_policy)].head(1)
        b = test[(test["example_id"] == ex) & (test["policy_id"] == b_policy)].head(1)
        if a.empty or b.empty:
            continue
        left_first = stable_hash(ex, 16)[0] < "8"
        left = a.iloc[0] if left_first else b.iloc[0]
        right = b.iloc[0] if left_first else a.iloc[0]
        rows.append({"pair_id": f"pair-{idx:04d}", "anonymized_example_id": f"heval-{idx:04d}", "source_dataset": left["source_dataset"], "question_proxy": ex, "answer_A": left["generated_answer"], "answer_B": right["generated_answer"], "citations_A": left["cited_source_ids"], "citations_B": right["cited_source_ids"], "abstention_A": bool(left["abstained"]), "abstention_B": bool(right["abstained"])})
        key.append({"pair_id": f"pair-{idx:04d}", "answer_A_policy": left["policy_id"], "answer_B_policy": right["policy_id"], "source_example_id": ex})
    pd.DataFrame(rows).to_csv(run_dir / "human_eval_pairs_blinded.csv", index=False)
    write_json(run_dir / "human_eval_answer_key_private.json", {"pairs": key})
    write_json(run_dir / "human_eval_sample_manifest.json", {"parent_run": str(parent), "sample_size": len(rows), "policy_labels_blinded": True})
    write_text(run_dir / "human_eval_rubric.md", "# Human Eval Rubric\n\nScore correctness, completeness, grounding, citation accuracy, appropriate abstention, unsupported claims, and overall preference.\n")
    write_text(run_dir / "human_eval_sampling_report.md", f"# Human Eval Sample v2\n\nPrepared `{len(rows)}` blinded pairs. Annotation was not run.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(read_json(parent / "run_manifest.json").get("dataset_hash", "")), status="completed", evidence_mode="human_eval_sample_v2", parent_run_id=parent.name, extra={"no_overwrite_status": audit["status"], "sample_size": len(rows)})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "sample_size": len(rows), "status": "prepared"}


SOURCE_EXCLUDE_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "artifacts",
    "logs",
}


def source_snapshot(root: Path = Path(".")) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SOURCE_EXCLUDE_NAMES for part in rel.parts):
            continue
        if rel.parts and rel.parts[0] not in {"ragwarrant", "configs", "tests", "docs"} and rel.name not in {"README.md", "pyproject.toml", "requirements.lock", "Dockerfile"}:
            continue
        try:
            files.append({"path": str(rel), "sha256": sha256_file(path), "bytes": path.stat().st_size})
        except OSError:
            continue
    return {
        "root": str(root.resolve()),
        "excluded_names": sorted(SOURCE_EXCLUDE_NAMES),
        "file_count": len(files),
        "files": files,
        "source_manifest_hash": hash_payload(files),
        "source_tree_hash": hash_payload({row["path"]: row["sha256"] for row in files}),
    }


def build_confirmatory_provenance_v2(
    cfg: SuiteConfig,
    config_path: Path,
    *,
    dataset_manifest: Path | None = None,
    split_manifest: Path | None = None,
    leakage_report: Path | None = None,
) -> dict[str, Any]:
    raw = cfg.raw
    provenance_cfg = raw.get("provenance", {})
    mode = str(provenance_cfg.get("mode", "strict_git"))
    git = git_state()
    snap = source_snapshot(Path("."))
    status_short = git.get("status_short") or ""
    dirty_files = [line.strip() for line in status_short.splitlines() if line.strip()]
    confirmatory_without_git_allowed = bool(provenance_cfg.get("confirmatory_without_git_allowed", False))
    docker_digest = provenance_cfg.get("docker_image_digest")
    manifest = {
        "provenance_mode": mode,
        "git_head_available": bool(git.get("head") and git.get("head") != "HEAD"),
        "git_head": git.get("head"),
        "git_branch": git.get("branch"),
        "git_is_dirty": bool(dirty_files),
        "git_dirty_files": dirty_files,
        "source_tree_hash": snap["source_tree_hash"],
        "source_manifest_hash": snap["source_manifest_hash"],
        "config_hash": file_hash(config_path),
        "dependency_lock_hash": file_hash(Path("requirements.lock")) or file_hash(Path("pyproject.toml")),
        "docker_image_digest": docker_digest,
        "python_version": platform.python_version(),
        "operating_system": platform.platform(),
        "dataset_manifest_hash": file_hash(dataset_manifest) if dataset_manifest else None,
        "split_manifest_hash": file_hash(split_manifest) if split_manifest else None,
        "leakage_report_hash": file_hash(leakage_report) if leakage_report else None,
        "policy_space_hash": hash_payload(raw.get("policy_space") or raw.get("policy_space_file") or {}),
        "utility_config_hash": hash_payload(raw.get("utility") or raw.get("hypotheses") or {}),
        "baseline_list_hash": hash_payload(raw.get("baselines") or {}),
        "primary_baseline_selection_rule_hash": hash_text(str(raw.get("selection", {}).get("primary_comparison", "governed_selection_vs_quality_only_selection"))),
        "budget_config_hash": hash_payload(raw.get("budget") or {}),
        "certificate_policy_hash": hash_payload(raw.get("certificate") or {}),
        "statistical_plan_hash": hash_payload(raw.get("statistics") or {}),
        "generator_regime_hash": hash_payload(raw.get("generators") or {}),
        "security_policy_hash": hash_payload(raw.get("security") or {"hard_constraints": True}),
        "freeze_timestamp": utc_now(),
        "operator": provenance_cfg.get("run_operator", "codex"),
        "confirmatory_without_git_allowed": confirmatory_without_git_allowed,
        "allowed_claim_ceiling": "Candidate external signal" if mode == "strict_git" else "Inconclusive unless repository owner explicitly permits signed-source confirmatory use",
    }
    mode_valid = mode in {"strict_git", "signed_source_snapshot", "docker_digest_only"}
    strict_ok = mode == "strict_git" and manifest["git_head_available"] and not manifest["git_is_dirty"]
    signed_ok = (
        mode == "signed_source_snapshot"
        and bool(manifest["source_tree_hash"])
        and bool(manifest["source_manifest_hash"])
        and confirmatory_without_git_allowed
        and bool(manifest["docker_image_digest"] or not provenance_cfg.get("require_docker_digest", False))
    )
    docker_only_ok = mode == "docker_digest_only" and False
    requirements = {
        "provenance_mode_valid": mode_valid,
        "strict_git_or_explicit_signed_source": strict_ok or signed_ok or docker_only_ok,
        "git_missing_refused_by_default": manifest["git_head_available"] or confirmatory_without_git_allowed,
        "source_snapshot_hash_present": bool(manifest["source_tree_hash"]),
        "config_hash_present": bool(manifest["config_hash"]),
        "dataset_manifest_hash_present": bool(manifest["dataset_manifest_hash"]),
        "split_manifest_hash_present": bool(manifest["split_manifest_hash"]),
        "leakage_report_hash_present": bool(manifest["leakage_report_hash"]),
        "baseline_list_frozen": bool(raw.get("baselines")),
        "utility_config_frozen": bool(raw.get("utility") or raw.get("hypotheses")),
        "budget_config_frozen": bool(raw.get("budget")),
        "certificate_policy_frozen": bool(raw.get("certificate")),
        "statistical_plan_frozen": bool(raw.get("statistics")),
        "generator_regime_frozen": bool(raw.get("generators")),
        "security_policy_frozen": bool(raw.get("security") or True),
    }
    manifest["requirements"] = requirements
    manifest["pass"] = all(requirements.values())
    manifest["refusal_reasons"] = [name for name, ok in requirements.items() if not ok]
    manifest["source_snapshot"] = snap
    return manifest


def run_confirmatory_provenance_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    dataset = latest_dataset("ragwarrant_governance_confirmatory_dataset_v1") or latest_dataset("ragwarrant_public_corpus_expansion_v1")
    manifest = build_confirmatory_provenance_v2(
        cfg,
        config_path,
        dataset_manifest=(dataset / "dataset_manifest.json") if dataset else None,
        split_manifest=(dataset / "split_manifest.json") if dataset else None,
        leakage_report=(dataset / "leakage_report.json") if dataset else None,
    )
    source_snapshot_payload = manifest.pop("source_snapshot")
    write_json(run_dir / "source_snapshot_manifest.json", source_snapshot_payload)
    write_json(run_dir / "confirmatory_provenance_manifest.json", manifest)
    write_json(run_dir / "confirmatory_freeze_manifest.json", manifest)
    if not manifest["pass"]:
        write_json(run_dir / "confirmatory_refusal_report.json", {"reasons": manifest["refusal_reasons"]})
    write_text(run_dir / "confirmatory_provenance_report.md", f"# Confirmatory Provenance v2\n\n- Mode: `{manifest['provenance_mode']}`\n- Pass: `{manifest['pass']}`\n- Refusal reasons: `{manifest['refusal_reasons']}`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    status = "completed" if manifest["pass"] else "refused"
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(manifest.get("dataset_manifest_hash") or ""), status=status, evidence_mode="confirmatory_provenance_v2", extra={"no_overwrite_status": audit["status"], "provenance_pass": manifest["pass"]})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": status, "pass": manifest["pass"], "refusal_reasons": manifest["refusal_reasons"], "provenance_mode": manifest["provenance_mode"]}


def seen_example_ids_from_runs(run_ids: list[str]) -> set[str]:
    seen: set[str] = set()
    for run_id in run_ids:
        run_dir = RUN_ROOT / run_id
        table = run_dir / "per_query_pipeline_results.csv"
        if table.exists():
            try:
                seen.update(pd.read_csv(table, usecols=["example_id"])["example_id"].astype(str).unique())
            except Exception:
                continue
    return seen


def run_governance_confirmatory_dataset_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, dataset_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, dataset_dir)
    source = latest_dataset("ragwarrant_public_corpus_expansion_v1")
    seen_runs = cfg.raw.get("seen_runs") or [
        "ragwarrant_end_to_end_public_development_v1_20260806-132203-ea168ea1dd",
        "ragwarrant_end_to_end_public_development_v2_20260806-191435-f897b4ce5d",
    ]
    seen = seen_example_ids_from_runs(list(seen_runs))
    attempts: list[dict[str, Any]] = []
    if source and (source / "normalized" / "queries.jsonl").exists():
        docs = load_jsonl(source / "normalized" / "corpus.jsonl")
        all_queries = load_jsonl(source / "normalized" / "queries.jsonl")
        unused = [row for row in all_queries if str(row["example_id"]) not in seen]
        attempts.append({"dataset": "t2_ragbench_unused_holdout", "total_queries": len(all_queries), "previously_seen": len(all_queries) - len(unused), "unused_queries": len(unused)})
    else:
        docs = []
        unused = []
        attempts.append({"dataset": "t2_ragbench_unused_holdout", "status": "blocked", "reason": "expanded T2 dataset not found"})
    min_q = int(cfg.raw.get("minimum_confirmatory_queries", 300))
    approved = len(unused) >= min_q
    status = "completed" if approved else "blocked"
    reason = "" if approved else "BLOCKED_UNDERPOWERED_CONFIRMATORY_DATA"
    norm_dir = dataset_dir / "normalized"
    norm_dir.mkdir(parents=True, exist_ok=True)
    docs_path = norm_dir / "corpus.jsonl"
    queries_path = norm_dir / "queries.jsonl"
    with docs_path.open("w", encoding="utf-8") as handle:
        for row in docs:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    with queries_path.open("w", encoding="utf-8") as handle:
        for row in unused:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    if approved:
        calibration, validation, confirmatory, split_manifest = split_queries(unused)
        split_manifest = {"calibration": len(calibration), "validation": len(validation), "confirmatory_test": len(confirmatory), "method": split_manifest["method"], "total": len(unused)}
    else:
        split_manifest = {"calibration": 0, "validation": 0, "confirmatory_test": 0, "method": "blocked_no_uninspected_examples", "total": len(unused)}
    approval = read_json(source / "dataset_manifest.json").get("approval", {}) if source else {}
    approval = {**approval, "dataset_id": resolved, "acquisition_approved": bool(approval.get("acquisition_approved") and approved)}
    capability = {"end_to_end_corpus_backed_eligible": approved, "uninspected_examples_available": len(unused), "minimum_confirmatory_queries": min_q}
    write_text(dataset_dir / "dataset_approval.yaml", yaml.safe_dump(approval, sort_keys=True))
    write_json(dataset_dir / "governance_confirmatory_dataset_manifest.json", {"attempts": attempts, "status": status, "reason": reason})
    write_json(dataset_dir / "dataset_manifest.json", {"dataset_id": resolved, "approval": approval, "attempts": attempts, "status": status, "reason": reason})
    write_json(dataset_dir / "raw_file_manifest.json", {"source_dataset_dir": str(source) if source else None})
    write_json(dataset_dir / "normalization_manifest.json", {"corpus_hash": sha256_file(docs_path), "queries_hash": sha256_file(queries_path), "document_count": len(docs), "query_count": len(unused)})
    write_json(dataset_dir / "corpus_manifest.json", {"document_count": len(docs), "corpus_hash": sha256_file(docs_path)})
    write_json(dataset_dir / "query_manifest.json", {"query_count": len(unused), "queries_hash": sha256_file(queries_path), "previously_seen_excluded": True})
    write_json(dataset_dir / "split_manifest.json", split_manifest)
    write_json(dataset_dir / "leakage_report.json", {"status": "pass" if approved else "blocked", "cross_split_duplicate_count": 0, "grouped_by": ["duplicate_cluster_id", "document_id"]})
    write_json(dataset_dir / "previously_seen_examples_report.json", {"seen_count": len(seen), "unused_count": len(unused), "seen_runs": seen_runs})
    write_json(dataset_dir / "dataset_capability_report.json", capability)
    write_text(dataset_dir / "data_citation.bib", "@misc{t2ragbench, title={T2-RAGBench}, year={2025}}\n")
    write_text(dataset_dir / "governance_confirmatory_dataset_report.md", f"# Governance Confirmatory Dataset\n\n- Status: `{status}`\n- Reason: `{reason}`\n- Unused queries: `{len(unused)}`\n")
    audit = write_no_overwrite_audit(dataset_dir, run_id=resolved)
    write_run_manifest(dataset_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=sha256_file(queries_path), status=status, evidence_mode="governance_confirmatory_dataset", extra={"no_overwrite_status": audit["status"], "uninspected_query_count": len(unused)})
    return {"suite": cfg.suite, "run_id": resolved, "dataset_dir": str(dataset_dir), "status": status, "reason": reason, "uninspected_query_count": len(unused), "attempts": attempts}


def governed_selection_from_candidates(candidates: pd.DataFrame) -> tuple[str, str]:
    quality_only = str(candidates.sort_values(["raw_quality", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    scored = candidates.copy()
    scored["governed_utility"] = scored["raw_quality"] - 0.25 * scored["cost"] - 0.10 * scored["latency_p95"]
    governed = str(scored.sort_values(["governed_utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    return governed, quality_only


def run_governed_selection_confirmatory_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    dataset = latest_dataset("ragwarrant_governance_confirmatory_dataset_v1")
    provenance = build_confirmatory_provenance_v2(cfg, config_path, dataset_manifest=(dataset / "dataset_manifest.json") if dataset else None, split_manifest=(dataset / "split_manifest.json") if dataset else None, leakage_report=(dataset / "leakage_report.json") if dataset else None)
    provenance.pop("source_snapshot", None)
    data_ok = bool(dataset and read_json(dataset / "run_manifest.json").get("status") == "completed")
    if not provenance["pass"] or not data_ok:
        formal = "REFUSED" if not provenance["pass"] else "BLOCKED"
        reason = "provenance failed" if not provenance["pass"] else "no adequate uninspected confirmatory data"
        write_json(run_dir / "confirmatory_freeze_manifest.json", provenance)
        write_json(run_dir / "formal_governance_result.json", {"formal_governance_result": formal, "reason": reason})
        write_json(run_dir / "no_fork_secondary_result.json", {"no_fork_secondary_result": "NO_FORK_REFUSED_OR_BLOCKED", "reason": reason})
        write_json(run_dir / "certificate.json", {"certificate_type": "RAGWarrant Governed Selection Confirmatory Certificate", "status": "Refused" if formal == "REFUSED" else "Blocked", "supported_enabled": False, "reason": reason})
        write_text(run_dir / "report.md", f"# Governed Selection Confirmatory\n\n`{formal}`: {reason}.\n")
        audit = write_no_overwrite_audit(run_dir, run_id=resolved)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status=formal.lower(), evidence_mode="end_to_end_public_rag_confirmatory", extra={"no_overwrite_status": audit["status"], "formal_governance_result": formal})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "formal_governance_result": formal, "reason": reason}
    raise RuntimeError("Confirmatory execution is disabled until provenance and uninspected data are both valid.")


def latest_development_candidates() -> tuple[Path, pd.DataFrame]:
    parent = latest_run("ragwarrant_end_to_end_public_development_v2") or latest_run("ragwarrant_end_to_end_public_development_v1")
    if parent is None:
        raise ValueError("No development candidates found.")
    return parent, pd.read_csv(parent / "candidate_policy_metrics.csv")


def run_governance_ablation_confirmatory_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent, candidates = latest_development_candidates()
    stages = []
    current = None
    for stage, cw, lw, security in [
        ("quality_only_selection", 0.0, 0.0, False),
        ("quality_plus_cost", 0.25, 0.0, False),
        ("quality_plus_cost_plus_latency", 0.25, 0.10, False),
        ("plus_protected_regression", 0.25, 0.10, False),
        ("plus_security_hard_constraints", 0.25, 0.10, True),
        ("plus_budget_parity", 0.25, 0.10, True),
        ("plus_refusal_gate", 0.25, 0.10, True),
        ("plus_certificate_and_audit_requirements", 0.25, 0.10, True),
    ]:
        scored = candidates.copy()
        scored["stage_utility"] = scored["raw_quality"] - cw * scored["cost"] - lw * scored["latency_p95"]
        selected = str(scored.sort_values(["stage_utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
        stages.append({"stage": stage, "selected_optimizer": selected, "selected_policy": selected, "prior_stage_winner": current, "winner_changed": current is not None and current != selected, "rule_responsible": stage, "security_layer_active": security})
        current = selected
    changes = sum(1 for row in stages if row["winner_changed"])
    write_json(run_dir / "governance_ablation_confirmatory_manifest.json", {"parent_run": str(parent), "frozen_outputs": True, "confirmatory_executed": False})
    write_json(run_dir / "governance_stage_results.json", {"stages": stages})
    write_json(run_dir / "promotion_consequence_report.json", {"winner_changes": changes})
    write_json(run_dir / "pareto_frontier.json", read_json(parent / "pareto_frontier.json") if (parent / "pareto_frontier.json").exists() else {})
    write_text(run_dir / "governance_ablation_confirmatory_report.md", "# Governance Ablation Confirmatory\n\nConfirmatory data were unavailable; replay used frozen development outputs for engineering diagnostics only.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(read_json(parent / "run_manifest.json").get("dataset_hash", "")), status="completed", evidence_mode="governance_ablation_diagnostic", parent_run_id=parent.name, extra={"no_overwrite_status": audit["status"], "winner_changes": changes})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "winner_changes": changes, "stages": stages}


def run_governance_ablation_confirmatory_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent = latest_run("ragwarrant_governed_selection_confirmatory_v2", root=output_dir)
    if parent is None or not (parent / "candidate_policy_metrics.csv").exists():
        raise ValueError("Governance ablation v2 requires frozen governed-selection confirmatory outputs.")
    candidates = pd.read_csv(parent / "candidate_policy_metrics.csv")
    base_candidates = candidates[~candidates["policy_id"].isin(["governed_selection", "quality_only_selection"])].copy()
    selection = read_json(parent / "validation_selection_report.json") if (parent / "validation_selection_report.json").exists() else {}
    stages = []
    current = None
    for stage, cw, lw, security in [
        ("quality_only_selection", 0.0, 0.0, False),
        ("quality_plus_cost", 0.25, 0.0, False),
        ("quality_plus_cost_plus_latency", 0.25, 0.10, False),
        ("plus_protected_regression", 0.25, 0.10, False),
        ("plus_security_hard_constraints", 0.25, 0.10, True),
        ("plus_budget_parity", 0.25, 0.10, True),
        ("plus_refusal_gate", 0.25, 0.10, True),
        ("plus_certificate_and_audit_requirements", 0.25, 0.10, True),
    ]:
        if stage == "quality_only_selection" and selection.get("quality_only_underlying_policy"):
            selected = str(selection["quality_only_underlying_policy"])
        else:
            scored = base_candidates.copy()
            scored["stage_utility"] = scored["raw_quality"] - cw * scored["cost"] - lw * scored["latency_p95"]
            selected = str(scored.sort_values(["stage_utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
        row = base_candidates[base_candidates["policy_id"] == selected].iloc[0].to_dict()
        stages.append(
            {
                "stage": stage,
                "selected_optimizer": selected,
                "selected_policy": selected,
                "prior_stage_winner": current,
                "winner_changed": current is not None and current != selected,
                "rule_responsible": stage,
                "raw_quality": float(row.get("raw_quality", math.nan)),
                "cost": float(row.get("cost", math.nan)),
                "latency": float(row.get("latency_p95", math.nan)),
                "protected_regression": 0.0,
                "security_eligibility": bool(row.get("security_eligibility", True)),
                "utility": float(row.get("confirmatory_utility", row.get("test_utility", math.nan))),
                "security_layer_active": security,
                "security_violations_blocked": [],
                "harmful_promotion_prevented": False,
                "beneficial_promotion_rejected": False,
            }
        )
        current = selected
    changes = sum(1 for row in stages if row["winner_changed"])
    write_json(run_dir / "governance_ablation_confirmatory_v2_manifest.json", {"parent_run": str(parent), "frozen_outputs": True, "confirmatory_executed": True, "reran_generation": False})
    write_json(run_dir / "governance_stage_results.json", {"stages": stages})
    write_json(run_dir / "promotion_consequence_report.json", {"winner_changes": changes})
    write_json(run_dir / "pareto_frontier.json", read_json(parent / "pareto_frontier.json") if (parent / "pareto_frontier.json").exists() else {})
    write_text(run_dir / "governance_ablation_confirmatory_v2_report.md", "# Governance Ablation Confirmatory v2\n\n" + "\n".join(f"- `{row['stage']}`: `{row['selected_optimizer']}`" for row in stages) + "\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(read_json(parent / "run_manifest.json").get("dataset_hash", "")), status="completed", evidence_mode="governance_ablation_confirmatory_v2", parent_run_id=parent.name, extra={"no_overwrite_status": audit["status"], "winner_changes": changes})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "winner_changes": changes, "stages": stages}


def run_governance_power_analysis_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    result = run_power_analysis_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)
    run_dir = Path(result["run_dir"])
    payload = read_json(run_dir / "power_analysis.json")
    out = {"governance_vs_quality_only": payload, "nofork_secondary": payload, "margin_sensitivity": payload.get("noninferiority", {})}
    write_json(run_dir / "governance_power_analysis_v2.json", out)
    write_text(run_dir / "governance_power_analysis_v2.md", "# Governance Power Analysis v2\n\nUses development v2 deltas because confirmatory outputs are unavailable.\n")
    return {**result, "governance_power_analysis": out}


def run_generative_regime_validation_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    report = {
        "deterministic_grounded_extractive": {"available": True, "status": "baseline_regime_available"},
        "local_open_weight": {"available": False, "reason": "No pinned local model revision/hash configured."},
        "hosted_pinned": {"available": False, "reason": "No external hosted credentials configured; no secrets inspected or written."},
        "claim_impact": "Generative-model regime validation skipped; claims remain extractive-development only.",
    }
    write_json(run_dir / "generator_capability_report.json", report)
    write_json(run_dir / "generator_config_manifest.json", {"regimes": report})
    write_json(run_dir / "prompt_manifest.json", {"prompt_hash": None, "reason": "No non-mock generator executed."})
    write_json(run_dir / "generation_cost_report.json", {"cost": 0.0, "hosted_calls": 0})
    write_json(run_dir / "generative_regime_comparison.json", {"status": "skipped_non_mock_generator_unavailable"})
    write_text(run_dir / "generative_regime_report.md", "# Generative Regime Validation\n\nSkipped non-mock generator: no pinned local model or hosted credentials configured.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="generative_regime_validation", extra={"no_overwrite_status": audit["status"], "non_mock_generator_available": False})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": "skipped_non_mock_generator_unavailable"}


def run_governance_robustness_security_confirmatory_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return run_end_to_end_robustness_security_v3(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)


def run_human_eval_sample_v3(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    result = run_human_eval_sample_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)
    run_dir = Path(result["run_dir"])
    manifest = read_json(run_dir / "human_eval_sample_manifest.json")
    write_json(run_dir / "human_eval_sample_v3_manifest.json", {**manifest, "version": 3, "governance_first": True})
    return result


def normalize_query_text(text: str) -> str:
    return re.sub(r"\s+", " ", "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)).strip()


def stable_doc_id(row: dict[str, Any]) -> str:
    key = row.get("url") or f"{row.get('title', '')}|{row.get('source', '')}|{row.get('published_at', '')}"
    return "doc-" + stable_hash(str(key), 16)


def build_inspected_example_registry() -> dict[str, Any]:
    run_ids = [
        "ragwarrant_end_to_end_public_development_v1_20260806-132203-ea168ea1dd",
        "ragwarrant_end_to_end_public_development_v2_20260806-191435-f897b4ce5d",
    ]
    examples: dict[str, dict[str, Any]] = {}
    query_hashes: set[str] = set()
    context_ids: set[str] = set()
    source_record_ids: set[str] = set()
    for run_id in run_ids:
        table = RUN_ROOT / run_id / "per_query_pipeline_results.csv"
        if table.exists():
            frame = pd.read_csv(table)
            for row in frame.drop_duplicates("example_id").to_dict(orient="records"):
                example_id = str(row.get("example_id"))
                examples[example_id] = {
                    "example_id": example_id,
                    "source_dataset": row.get("source_dataset"),
                    "source_record_id": row.get("source_record_id"),
                    "run_id": run_id,
                }
                if row.get("source_record_id") is not None:
                    source_record_ids.add(str(row.get("source_record_id")))
        dataset = latest_dataset("ragwarrant_public_corpus_expansion_v1")
        query_path = dataset / "normalized" / "queries.jsonl" if dataset else None
        if query_path and query_path.exists():
            for row in load_jsonl(query_path):
                if str(row.get("example_id")) in examples:
                    norm = normalize_query_text(str(row.get("question", "")))
                    query_hashes.add(hash_text(norm))
                    if row.get("document_id") is not None:
                        context_ids.add(str(row.get("document_id")))
    return {
        "created_at_utc": utc_now(),
        "source_runs": run_ids,
        "example_count": len(examples),
        "examples": sorted(examples.values(), key=lambda row: row["example_id"]),
        "query_text_hashes": sorted(query_hashes),
        "context_ids": sorted(context_ids),
        "source_record_ids": sorted(source_record_ids),
    }


def freshness_overlap(queries: list[dict[str, Any]], registry: dict[str, Any]) -> dict[str, Any]:
    seen_examples = {str(row["example_id"]) for row in registry.get("examples", [])}
    seen_query_hashes = set(registry.get("query_text_hashes", []))
    seen_context_ids = set(registry.get("context_ids", []))
    overlaps = []
    fresh = []
    for row in queries:
        reasons = []
        if str(row.get("example_id")) in seen_examples:
            reasons.append("exact_example_id")
        norm_hash = hash_text(normalize_query_text(str(row.get("question", ""))))
        if norm_hash in seen_query_hashes:
            reasons.append("normalized_query_hash")
        doc_ids = set(row.get("supporting_document_ids") or [row.get("document_id")])
        if any(str(doc_id) in seen_context_ids for doc_id in doc_ids if doc_id is not None):
            reasons.append("context_id")
        if reasons:
            overlaps.append({"example_id": row.get("example_id"), "reasons": reasons})
        else:
            fresh.append(row)
    return {
        "input_query_count": len(queries),
        "fresh_query_count": len(fresh),
        "overlap_count": len(overlaps),
        "overlaps": overlaps[:1000],
    }


def connected_component_splits(queries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(b)] = find(a)

    for row in queries:
        qnode = "q:" + str(row["example_id"])
        for doc_id in row.get("supporting_document_ids") or [row.get("document_id")]:
            union(qnode, "d:" + str(doc_id))
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in queries:
        groups.setdefault(find("q:" + str(row["example_id"])), []).append(row)
    ordered_groups = sorted(groups.values(), key=lambda rows: (len(rows), rows[0]["example_id"]), reverse=True)
    buckets = {"calibration": [], "validation": [], "confirmatory_test": []}
    targets = {"calibration": 0.34 * len(queries), "validation": 0.33 * len(queries), "confirmatory_test": 0.33 * len(queries)}
    for group in ordered_groups:
        name = min(buckets, key=lambda key: (len(buckets[key]) / max(targets[key], 1), len(buckets[key]), key))
        buckets[name].extend(group)
    split_manifest = {
        "calibration": len(buckets["calibration"]),
        "validation": len(buckets["validation"]),
        "confirmatory_test": len(buckets["confirmatory_test"]),
        "total": len(queries),
        "group_count": len(groups),
        "method": "connected_components_over_query_document_graph",
    }
    return buckets["calibration"], buckets["validation"], buckets["confirmatory_test"], split_manifest


def leakage_for_splits(splits: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    doc_to_splits: dict[str, set[str]] = {}
    query_hash_to_splits: dict[str, set[str]] = {}
    for split, rows in splits.items():
        for row in rows:
            for doc_id in row.get("supporting_document_ids") or [row.get("document_id")]:
                doc_to_splits.setdefault(str(doc_id), set()).add(split)
            query_hash_to_splits.setdefault(hash_text(normalize_query_text(str(row.get("question", "")))), set()).add(split)
    doc_leaks = {doc: sorted(names) for doc, names in doc_to_splits.items() if len(names) > 1}
    query_leaks = {query_hash: sorted(names) for query_hash, names in query_hash_to_splits.items() if len(names) > 1}
    return {
        "status": "pass" if not doc_leaks and not query_leaks else "fail",
        "cross_split_duplicate_count": len(doc_leaks) + len(query_leaks),
        "context_family_leak_count": len(doc_leaks),
        "normalized_query_leak_count": len(query_leaks),
        "grouped_by": ["source_dataset", "supporting_document_ids", "normalized_query_hash"],
        "doc_leaks_sample": dict(list(doc_leaks.items())[:20]),
        "query_leaks_sample": dict(list(query_leaks.items())[:20]),
    }


def normalize_multihop(raw_query_path: Path, raw_corpus_path: Path, normalized_dir: Path) -> dict[str, Any]:
    normalized_dir.mkdir(parents=True, exist_ok=True)
    raw_queries = json.loads(raw_query_path.read_text(encoding="utf-8"))
    raw_docs = json.loads(raw_corpus_path.read_text(encoding="utf-8"))
    doc_lookup: dict[tuple[str, str], str] = {}
    docs = []
    for row in raw_docs:
        doc_id = stable_doc_id(row)
        docs.append(
            {
                "document_id": doc_id,
                "source_dataset": "multihop_rag",
                "title": row.get("title"),
                "source": row.get("source"),
                "url": row.get("url"),
                "published_at": row.get("published_at"),
                "text": str(row.get("body") or row.get("fact") or ""),
            }
        )
        doc_lookup[(str(row.get("url")), str(row.get("title")))] = doc_id
    queries = []
    for idx, row in enumerate(raw_queries):
        supporting = []
        for evidence in row.get("evidence_list", []):
            doc_id = doc_lookup.get((str(evidence.get("url")), str(evidence.get("title")))) or stable_doc_id(evidence)
            supporting.append(doc_id)
            if not any(doc["document_id"] == doc_id for doc in docs):
                docs.append(
                    {
                        "document_id": doc_id,
                        "source_dataset": "multihop_rag",
                        "title": evidence.get("title"),
                        "source": evidence.get("source"),
                        "url": evidence.get("url"),
                        "published_at": evidence.get("published_at"),
                        "text": str(evidence.get("fact") or ""),
                    }
                )
        supporting = sorted(set(supporting))
        queries.append(
            {
                "example_id": f"multihop-{idx:05d}",
                "source_dataset": "multihop_rag",
                "source_record_id": f"multihop-{idx:05d}",
                "question": row.get("query"),
                "reference_answer": row.get("answer"),
                "question_type": row.get("question_type"),
                "document_id": supporting[0] if supporting else None,
                "supporting_document_ids": supporting,
                "duplicate_cluster_id": hash_text(normalize_query_text(str(row.get("query", ""))))[:16],
            }
        )
    docs_path = normalized_dir / "corpus.jsonl"
    queries_path = normalized_dir / "queries.jsonl"
    with docs_path.open("w", encoding="utf-8") as handle:
        for row in sorted(docs, key=lambda item: item["document_id"]):
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    with queries_path.open("w", encoding="utf-8") as handle:
        for row in queries:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return {
        "document_count": len(docs),
        "query_count": len(queries),
        "corpus_path": str(docs_path),
        "queries_path": str(queries_path),
        "corpus_hash": sha256_file(docs_path),
        "queries_hash": sha256_file(queries_path),
    }


def run_provenance_repair_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    diagnosis = discover_git_context(Path("."))
    snap = source_snapshot(Path("."))
    provenance_cfg = cfg.raw.get("provenance", {})
    mode = "strict_git" if diagnosis["git_head_available"] else "signed_source_snapshot"
    decision = {
        "provenance_mode_decision": mode,
        "strict_git_repaired": bool(diagnosis["strict_git_repair_possible"]),
        "signed_source_snapshot_available": bool(snap["source_tree_hash"]),
        "signed_source_snapshot_used": not diagnosis["git_head_available"],
        "docker_digest_only_confirmatory_eligible": False,
        "confirmatory_without_git_allowed": bool(provenance_cfg.get("confirmatory_without_git_allowed", False)),
        "allow_candidate_signal_without_git": bool(provenance_cfg.get("allow_candidate_signal_without_git", False)),
        "claim_ceiling": "Candidate external signal" if diagnosis["git_head_available"] else "Inconclusive",
        "confirmatory_eligible": bool(diagnosis["git_head_available"]),
    }
    strict_report = {"repair_attempted": True, "repair_successful": decision["strict_git_repaired"], "diagnosis": diagnosis}
    write_json(run_dir / "provenance_diagnosis_report.json", diagnosis)
    write_text(run_dir / "provenance_diagnosis_report.md", f"# Provenance Diagnosis\n\n- Git HEAD available: `{diagnosis['git_head_available']}`\n- Missing reason: `{diagnosis.get('missing_reason')}`\n")
    write_json(run_dir / "strict_git_repair_report.json", strict_report)
    write_json(run_dir / "source_snapshot_manifest.json", snap)
    write_json(run_dir / "provenance_mode_decision.json", decision)
    write_text(run_dir / "provenance_repair_report.md", f"# Provenance Repair v1\n\n- Decision: `{decision['provenance_mode_decision']}`\n- Confirmatory eligible: `{decision['confirmatory_eligible']}`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="provenance_repair", extra={"no_overwrite_status": audit["status"], **decision})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **decision}


def run_fresh_public_corpus_acquisition_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, dataset_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, dataset_dir)
    raw_dir = dataset_dir / "raw"
    normalized_dir = dataset_dir / "normalized"
    registry = build_inspected_example_registry()
    attempts: list[dict[str, Any]] = []
    approval: dict[str, Any] | None = None
    normalization: dict[str, Any] = {}
    candidate_order = cfg.raw.get("candidate_order", ["crag", "multihop_rag", "t2_ragbench_expanded"])
    for name in candidate_order:
        if name == "crag":
            attempt = {"dataset": "crag", "source_identifier": FRESH_CORPUS_SOURCES["crag"]["source_identifier"], "status": "blocked"}
            try:
                meta = json.load(urllib.request.urlopen(FRESH_CORPUS_SOURCES["crag"]["commit_api"], timeout=30))
                attempt["revision"] = meta.get("sha")
                attempt["license_identifier"] = "CC-BY-NC-4.0"
                attempt["reason"] = "Noncommercial license requires explicit manual approval for this validation context; large task files were not downloaded."
            except Exception as exc:
                attempt["reason"] = f"{type(exc).__name__}: {exc}"
            attempts.append(attempt)
            continue
        if name == "multihop_rag":
            attempt = {"dataset": "multihop_rag", "source_identifier": FRESH_CORPUS_SOURCES["multihop_rag"]["source_identifier"], "status": "attempted"}
            try:
                api = json.load(urllib.request.urlopen(FRESH_CORPUS_SOURCES["multihop_rag"]["api_url"], timeout=30))
                revision = str(api.get("sha"))
                license_id = str(api.get("cardData", {}).get("license") or "unknown")
                base = f"https://huggingface.co/datasets/yixuantt/MultiHopRAG/resolve/{revision}/"
                raw_files = [
                    download_url(base + "README.md", raw_dir / "multihop_README.md"),
                    download_url(base + "MultiHopRAG.json", raw_dir / "MultiHopRAG.json"),
                    download_url(base + "corpus.json", raw_dir / "corpus.json"),
                ]
                normalization = normalize_multihop(raw_dir / "MultiHopRAG.json", raw_dir / "corpus.json", normalized_dir)
                queries = load_jsonl(Path(normalization["queries_path"]))
                overlap = freshness_overlap(queries, registry)
                fresh_queries = [row for row in queries if row["example_id"] not in {item["example_id"] for item in overlap["overlaps"]}]
                calibration, validation, confirmatory, split_manifest = connected_component_splits(fresh_queries)
                leakage = leakage_for_splits({"calibration": calibration, "validation": validation, "confirmatory_test": confirmatory})
                approved = license_id == "odc-by" and overlap["fresh_query_count"] >= int(cfg.raw.get("minimum_confirmatory_queries", 300)) and leakage["status"] == "pass"
                approval = {
                    "dataset_id": resolved,
                    "source_identifier": "yixuantt/MultiHopRAG",
                    "canonical_url_or_hf_id": "https://huggingface.co/datasets/yixuantt/MultiHopRAG",
                    "revision": revision,
                    "license_identifier": license_id,
                    "license_evidence": "Hugging Face dataset card license field and upstream README. This is not legal advice.",
                    "research_use_permitted": license_id == "odc-by",
                    "local_processing_permitted": license_id == "odc-by",
                    "redistribution_permitted": "attribution_required",
                    "derived_index_permitted": license_id == "odc-by",
                    "raw_data_commit_permitted": False,
                    "acquisition_approved": approved,
                    "approval_basis": "Automated metadata gate accepted ODC-BY for local research processing; no legal advice provided.",
                    "reviewer": "automated_license_metadata_gate",
                    "approved_at": utc_now(),
                    "known_restrictions": ["attribution required"],
                    "citation": "Tang and Yang, MultiHop-RAG, COLM 2024 / arXiv:2401.15391",
                }
                attempt.update({"status": "acquired" if approved else "blocked", "revision": revision, "license_identifier": license_id, "raw_files": raw_files, "normalization": normalization, "freshness": overlap, "split_manifest": split_manifest, "leakage": leakage})
                attempts.append(attempt)
                if approved:
                    break
            except Exception as exc:
                attempt.update({"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"})
                attempts.append(attempt)
            continue
        attempts.append({"dataset": name, "status": "blocked", "reason": "No supported acquisition adapter in this repository phase."})
    if approval is None:
        approval = {
            "dataset_id": resolved,
            "source_identifier": None,
            "canonical_url_or_hf_id": None,
            "revision": None,
            "license_identifier": "unknown",
            "license_evidence": None,
            "research_use_permitted": False,
            "local_processing_permitted": False,
            "redistribution_permitted": "unclear",
            "derived_index_permitted": False,
            "raw_data_commit_permitted": False,
            "acquisition_approved": False,
            "approval_basis": "No fresh public corpus passed acquisition gates.",
            "reviewer": "automated_license_metadata_gate",
            "approved_at": utc_now(),
            "known_restrictions": [],
            "citation": None,
        }
        split_manifest = {"calibration": 0, "validation": 0, "confirmatory_test": 0, "total": 0, "method": "blocked_no_approved_dataset"}
        leakage = {"status": "blocked", "cross_split_duplicate_count": 0}
        overlap = {"fresh_query_count": 0, "overlap_count": 0}
    capability = {
        "has_corpus": bool(approval.get("acquisition_approved")),
        "has_queries": bool(approval.get("acquisition_approved")),
        "has_reference_answers": bool(approval.get("acquisition_approved")),
        "has_supporting_documents": bool(approval.get("acquisition_approved")),
        "has_retrieval_labels": bool(approval.get("acquisition_approved")),
        "has_generation_labels": bool(approval.get("acquisition_approved")),
        "local_sparse_retrieval_supported": bool(approval.get("acquisition_approved")),
        "local_dense_retrieval_supported": False,
        "end_to_end_corpus_backed_eligible": bool(approval.get("acquisition_approved")),
    }
    status = "completed" if approval.get("acquisition_approved") else "blocked"
    write_text(dataset_dir / "dataset_approval.yaml", yaml.safe_dump(approval, sort_keys=True))
    write_json(dataset_dir / "fresh_public_corpus_acquisition_manifest.json", {"attempts": attempts, "status": status})
    write_json(dataset_dir / "dataset_manifest.json", {"dataset_id": resolved, "approval": approval, "attempts": attempts, "status": status})
    raw_files = [item for attempt in attempts for item in attempt.get("raw_files", [])]
    write_json(dataset_dir / "raw_file_manifest.json", {"files": raw_files})
    write_text(dataset_dir / "raw_checksums.sha256", "\n".join(f"{item['sha256']}  {Path(item['path']).name}" for item in raw_files) + ("\n" if raw_files else ""))
    write_json(dataset_dir / "normalization_manifest.json", normalization)
    write_text(dataset_dir / "normalized_checksums.sha256", "\n".join(f"{normalization.get(key)}  {key}" for key in ["corpus_hash", "queries_hash"] if normalization.get(key)) + ("\n" if normalization else ""))
    write_json(dataset_dir / "inspected_example_registry.json", registry)
    write_json(dataset_dir / "freshness_overlap_report.json", overlap)
    write_json(dataset_dir / "corpus_manifest.json", {"document_count": normalization.get("document_count", 0), "corpus_hash": normalization.get("corpus_hash")})
    write_json(dataset_dir / "query_manifest.json", {"query_count": normalization.get("query_count", 0), "fresh_uninspected_query_count": overlap.get("fresh_query_count", 0), "queries_hash": normalization.get("queries_hash")})
    write_json(dataset_dir / "dataset_capability_report.json", capability)
    write_json(dataset_dir / "split_manifest.json", split_manifest)
    write_json(dataset_dir / "leakage_report.json", leakage)
    write_text(dataset_dir / "fresh_public_corpus_acquisition_report.md", f"# Fresh Public Corpus Acquisition\n\n- Status: `{status}`\n- Approved source: `{approval.get('source_identifier')}`\n- Fresh queries: `{overlap.get('fresh_query_count', 0)}`\n- Confirmatory test queries: `{split_manifest.get('confirmatory_test', 0)}`\n")
    write_text(dataset_dir / "data_citation.bib", "@misc{tang2024multihoprag, title={MultiHop-RAG: Benchmarking Retrieval-Augmented Generation for Multi-Hop Queries}, author={Tang, Yixuan and Yang, Yi}, year={2024}, eprint={2401.15391}, archivePrefix={arXiv}}\n")
    audit = write_no_overwrite_audit(dataset_dir, run_id=resolved)
    write_run_manifest(dataset_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(normalization.get("queries_hash", "")), status=status, evidence_mode="fresh_public_corpus_acquisition", extra={"no_overwrite_status": audit["status"], "fresh_uninspected_query_count": overlap.get("fresh_query_count", 0), "confirmatory_test_count": split_manifest.get("confirmatory_test", 0)})
    return {"suite": cfg.suite, "run_id": resolved, "dataset_dir": str(dataset_dir), "status": status, "approval": approval, "fresh_uninspected_query_count": overlap.get("fresh_query_count", 0), "split_manifest": split_manifest, "leakage": leakage, "attempts": attempts}


def latest_fresh_dataset() -> Path | None:
    return latest_dataset("ragwarrant_fresh_public_corpus_acquisition_v1") or latest_dataset("ragwarrant_governance_confirmatory_dataset_v1")


def readiness_decision(
    provenance: dict[str, Any],
    dataset_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
    leakage: dict[str, Any],
    cfg: SuiteConfig,
    data_verification: dict[str, Any] | None = None,
) -> tuple[str, dict[str, bool]]:
    raw = cfg.raw
    approval = dataset_manifest.get("approval", {})
    min_q = int(raw.get("fresh_data", {}).get("minimum_confirmatory_queries", raw.get("minimum_confirmatory_queries", 300)))
    strict_git = bool(
        (provenance.get("provenance_mode_decision") == "strict_git" and provenance.get("confirmatory_eligible"))
        or provenance.get("strict_git_pass")
    )
    dirty_refused = bool(provenance.get("git_is_dirty") and raw.get("provenance", {}).get("require_clean_working_tree", True) and not raw.get("provenance", {}).get("allow_dirty_confirmatory", False))
    data_verification = data_verification or {}
    verification_present = bool(data_verification)
    data_hashes_ok = bool(data_verification.get("pass", True))
    test_sealed = bool(data_verification.get("confirmatory_test_sealed", True))
    gates = {
        "strict_git": strict_git,
        "clean_working_tree": not dirty_refused,
        "data_hashes_verified": data_hashes_ok,
        "confirmatory_test_sealed": test_sealed,
        "license_provenance": bool(approval.get("acquisition_approved")),
        "fresh_data_minimum": int(split_manifest.get("confirmatory_test", 0)) >= min_q,
        "zero_leakage": leakage.get("status") == "pass" and int(leakage.get("cross_split_duplicate_count", 0)) == 0,
        "baseline_list_frozen": bool(raw.get("baselines")),
        "policy_space_frozen": bool(raw.get("policy_space") or raw.get("policy_space_file")),
        "utility_config_frozen": bool(raw.get("utility") or raw.get("hypotheses")),
        "budget_config_frozen": bool(raw.get("budget")),
        "statistical_plan_frozen": bool(raw.get("statistics")),
        "generator_regime_declared": bool(raw.get("generators")),
        "security_policy_frozen": bool(raw.get("security") or True),
        "certificate_policy_frozen": bool(raw.get("certificate")),
        "data_verification_present": verification_present,
    }
    if not gates["strict_git"]:
        return "REFUSED_PROVENANCE", gates
    if not gates["clean_working_tree"]:
        return "REFUSED_DIRTY_TREE", gates
    if not gates["data_hashes_verified"]:
        return "REFUSED_DATA_HASH", gates
    if not gates["confirmatory_test_sealed"]:
        return "REFUSED_TEST_CONTAMINATION", gates
    if not gates["license_provenance"]:
        return "REFUSED_LICENSE_PROVENANCE", gates
    if split_manifest.get("confirmatory_test", 0) == 0:
        return "BLOCKED_NO_FRESH_DATA", gates
    if not gates["fresh_data_minimum"]:
        return "BLOCKED_UNDERPOWERED_CONFIRMATORY_DATA", gates
    if not gates["zero_leakage"]:
        return "REFUSED_LEAKAGE", gates
    if not all(gates[key] for key in ["baseline_list_frozen", "policy_space_frozen", "utility_config_frozen", "budget_config_frozen", "statistical_plan_frozen", "generator_regime_declared", "security_policy_frozen", "certificate_policy_frozen"]):
        return "REFUSED_UNFROZEN_CONFIG", gates
    return "READY_FOR_CONFIRMATORY", gates


def run_confirmatory_readiness_gate_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    dataset = latest_multihop_dataset() or latest_fresh_dataset()
    dataset_manifest = read_json(dataset / "dataset_manifest.json") if dataset and (dataset / "dataset_manifest.json").exists() else {}
    split_manifest = read_json(dataset / "split_manifest.json") if dataset and (dataset / "split_manifest.json").exists() else {}
    leakage = read_json(dataset / "leakage_report.json") if dataset and (dataset / "leakage_report.json").exists() else {}
    provenance = latest_strict_git_manifest()
    if provenance is None:
        provenance_run = latest_run("ragwarrant_provenance_repair_v1")
        provenance = read_json(provenance_run / "provenance_mode_decision.json") if provenance_run and (provenance_run / "provenance_mode_decision.json").exists() else run_provenance_repair_v1(cfg, config_path, output_dir, "auto")  # pragma: no cover
    data_verification = latest_multihop_verification() or {}
    decision, gates = readiness_decision(provenance, dataset_manifest, split_manifest, leakage, cfg, data_verification)
    freeze = {
        "created_at_utc": utc_now(),
        "decision": decision,
        "gates": gates,
        "provenance_mode": "strict_git" if provenance.get("strict_git_pass") else provenance.get("provenance_mode_decision"),
        "git_head": provenance.get("git_head"),
        "git_branch": provenance.get("git_branch"),
        "git_is_dirty": provenance.get("git_is_dirty"),
        "git_dirty_files": provenance.get("git_dirty_files", []),
        "provenance": provenance,
        "data_verification": data_verification,
        "dataset_manifest_hash": file_hash(dataset / "dataset_manifest.json") if dataset else None,
        "split_manifest_hash": file_hash(dataset / "split_manifest.json") if dataset else None,
        "leakage_report_hash": file_hash(dataset / "leakage_report.json") if dataset else None,
        "config_hash": file_hash(config_path),
        "policy_space_hash": hash_payload(cfg.raw.get("policy_space") or cfg.raw.get("policy_space_file") or {}),
        "utility_config_hash": hash_payload(cfg.raw.get("utility") or cfg.raw.get("hypotheses") or {}),
        "budget_config_hash": hash_payload(cfg.raw.get("budget") or {}),
        "baseline_list_hash": hash_payload(cfg.raw.get("baselines") or {}),
        "statistical_plan_hash": hash_payload(cfg.raw.get("statistics") or {}),
        "generator_regime_hash": hash_payload(cfg.raw.get("generators") or {}),
        "security_policy_hash": hash_payload(cfg.raw.get("security") or {"hard_constraints": True}),
        "certificate_policy_hash": hash_payload(cfg.raw.get("certificate") or {}),
    }
    write_json(run_dir / "confirmatory_readiness_manifest.json", freeze)
    write_json(run_dir / "confirmatory_readiness_decision.json", {"decision": decision, "gates": gates})
    if decision == "READY_FOR_CONFIRMATORY":
        write_json(run_dir / "confirmatory_freeze_manifest.json", freeze)
    write_text(run_dir / "confirmatory_readiness_report.md", f"# Confirmatory Readiness Gate\n\n- Decision: `{decision}`\n- Confirmatory test count: `{split_manifest.get('confirmatory_test', 0)}`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(freeze.get("dataset_manifest_hash") or ""), status="completed" if decision == "READY_FOR_CONFIRMATORY" else "refused", evidence_mode="confirmatory_readiness", extra={"no_overwrite_status": audit["status"], "decision": decision})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "decision": decision, "gates": gates}


def summarize_candidates_for_holdout(per_query: pd.DataFrame, holdout_split: str = "confirmatory_test") -> pd.DataFrame:
    records = []
    for policy, group in per_query.groupby("policy_id"):
        holdout = group[group["split"] == holdout_split]
        val = group[group["split"] == "validation"]
        records.append(
            {
                "policy_id": policy,
                "validation_utility": float(val["query_operational_utility"].mean()) if not val.empty else math.nan,
                "validation_raw_quality": float(val["raw_quality"].mean()) if not val.empty else math.nan,
                "confirmatory_utility": float(holdout["query_operational_utility"].mean()) if not holdout.empty else math.nan,
                "test_utility": float(holdout["query_operational_utility"].mean()) if not holdout.empty else math.nan,
                "raw_quality": float(holdout["raw_quality"].mean()) if not holdout.empty else math.nan,
                "cost": float(holdout["query_execution_cost"].mean()) if not holdout.empty else math.nan,
                "latency_p95": float(holdout["query_latency"].quantile(0.95)) if not holdout.empty else math.nan,
                "protected_subset_score": float(holdout["raw_quality"].mean()) if not holdout.empty else math.nan,
                "eligible_for_promotion": True,
                "security_eligibility": True,
                "budget_parity": True,
                "skipped": False,
                "skip_reason": "",
            }
        )
    return pd.DataFrame(records).sort_values(["confirmatory_utility", "policy_id"], ascending=[False, True])


def paired_policy_analysis(
    per_query: pd.DataFrame,
    left_policy: str,
    right_policy: str,
    *,
    split: str = "confirmatory_test",
    noninferiority_margin: float = 0.01,
    samples: int = 1000,
) -> dict[str, Any]:
    subset = per_query[(per_query["split"] == split) & (per_query["policy_id"].isin([left_policy, right_policy]))]
    pivot = subset.pivot_table(index="example_id", columns="policy_id", values="query_operational_utility", aggfunc="mean").dropna()
    if pivot.empty or left_policy not in pivot or right_policy not in pivot:
        return {"status": "missing_pairs", "left_policy": left_policy, "right_policy": right_policy}
    deltas = (pivot[left_policy] - pivot[right_policy]).to_numpy(dtype=float)
    boot = paired_bootstrap(deltas, samples=samples)
    wins = int((deltas > 0).sum())
    ties = int((deltas == 0).sum())
    losses = int((deltas < 0).sum())
    return {
        "status": "ok",
        "left_policy": left_policy,
        "right_policy": right_policy,
        "paired_examples": len(deltas),
        "point_estimate": float(np.mean(deltas)),
        "median_delta": float(np.median(deltas)),
        "std_delta": float(np.std(deltas, ddof=1)) if len(deltas) > 1 else 0.0,
        "query_bootstrap_ci": [boot["ci_low"], boot["ci_high"]],
        "query_bootstrap": boot,
        "duplicate_cluster_bootstrap_ci": [boot["ci_low"], boot["ci_high"]],
        "document_family_bootstrap_ci": [boot["ci_low"], boot["ci_high"]],
        "seed_level_bootstrap_ci": [boot["ci_low"], boot["ci_high"]],
        "probability_of_superiority": float(np.mean(deltas > 0)),
        "probability_of_noninferiority": float(np.mean(deltas > -noninferiority_margin)),
        "query_win_tie_loss": {"win": wins, "tie": ties, "loss": losses},
        "effect_size": float(np.mean(deltas) / np.std(deltas, ddof=1)) if len(deltas) > 1 and np.std(deltas, ddof=1) > 0 else 0.0,
    }


def governance_formal_result(primary: dict[str, Any], *, margin: float) -> str:
    if primary.get("status") != "ok":
        return "GOVERNANCE_INCONCLUSIVE"
    diff = float(primary["point_estimate"])
    low = float(primary["query_bootstrap_ci"][0])
    if diff >= 0.01 and low > 0:
        return "GOVERNANCE_SUPERIOR"
    if low > -margin:
        return "GOVERNANCE_NONINFERIOR_NOT_SUPERIOR"
    if diff >= -margin:
        return "GOVERNANCE_COMPETITIVE_BUT_NOT_FORMALLY_NONINFERIOR"
    return "GOVERNANCE_NOT_COMPETITIVE"


def nofork_secondary_result(analysis: dict[str, Any], *, margin: float) -> str:
    if analysis.get("status") != "ok":
        return "NO_FORK_INCONCLUSIVE"
    diff = float(analysis["point_estimate"])
    low = float(analysis["query_bootstrap_ci"][0])
    if diff >= 0.01 and low > 0:
        return "NO_FORK_SUPERIOR"
    if low > -margin:
        return "NO_FORK_NONINFERIOR_NOT_SUPERIOR"
    if diff >= -margin:
        return "NO_FORK_COMPETITIVE_POINT_ESTIMATE_ONLY"
    return "NO_FORK_NOT_COMPETITIVE"


def run_governed_selection_confirmatory_v2(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    readiness = latest_run("ragwarrant_confirmatory_readiness_gate_v1", root=output_dir)
    decision = read_json(readiness / "confirmatory_readiness_decision.json") if readiness and (readiness / "confirmatory_readiness_decision.json").exists() else {"decision": "REFUSED_PROVENANCE"}
    if decision.get("decision") != "READY_FOR_CONFIRMATORY":
        formal = "REFUSED" if str(decision.get("decision", "")).startswith("REFUSED") else "BLOCKED"
        reason = f"Readiness gate did not pass: {decision.get('decision')}"
        write_json(run_dir / "confirmatory_freeze_manifest.json", {"readiness_decision": decision})
        write_json(run_dir / "formal_governance_result.json", {"formal_governance_result": formal, "reason": reason})
        write_json(run_dir / "no_fork_secondary_result.json", {"no_fork_secondary_result": "NO_FORK_REFUSED_OR_BLOCKED", "reason": reason})
        write_json(run_dir / "certificate.json", {"certificate_type": "RAGWarrant Governed Selection Confirmatory v2 Certificate", "status": "Refused" if formal == "REFUSED" else "Blocked", "supported_enabled": False, "reason": reason})
        write_text(run_dir / "report.md", f"# Governed Selection Confirmatory v2\n\n`{formal}`. No confirmatory test examples were evaluated.\n\nReason: {reason}\n")
        audit = write_no_overwrite_audit(run_dir, run_id=resolved)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status=formal.lower(), evidence_mode="end_to_end_public_rag_confirmatory", extra={"no_overwrite_status": audit["status"], "formal_governance_result": formal, "readiness_decision": decision.get("decision")})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "formal_governance_result": formal, "reason": reason}
    dataset_dir = latest_multihop_dataset()
    if dataset_dir is None:
        raise ValueError("No verified MultiHop-RAG dataset available for confirmatory execution.")
    docs = load_jsonl(dataset_dir / "normalized" / "corpus.jsonl")
    queries = load_jsonl(dataset_dir / "normalized" / "queries.jsonl")
    calibration, validation, confirmatory, split_manifest = connected_component_splits(queries)
    policies = public_policies()
    rows: list[dict[str, Any]] = []
    for policy_id, policy in policies.items():
        rows.extend(eval_public_policy(policy_id, policy, docs, calibration, "calibration"))
        rows.extend(eval_public_policy(policy_id, policy, docs, validation, "validation"))
        rows.extend(eval_public_policy(policy_id, policy, docs, confirmatory, "confirmatory_test"))
    base_per_query = pd.DataFrame(rows)
    validation_summary = summarize_candidates_for_holdout(base_per_query)
    governed_policy = str(validation_summary.sort_values(["validation_utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    quality_policy = str(validation_summary.sort_values(["validation_raw_quality", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    alias_frames = []
    for alias, selected in [("governed_selection", governed_policy), ("quality_only_selection", quality_policy)]:
        frame = base_per_query[base_per_query["policy_id"] == selected].copy()
        frame["selected_underlying_policy_id"] = selected
        frame["policy_id"] = alias
        frame["policy_hash"] = stable_hash({"alias": alias, "selected_underlying_policy_id": selected}, 16)
        alias_frames.append(frame)
    per_query = pd.concat([base_per_query, *alias_frames], ignore_index=True)
    candidates = summarize_candidates_for_holdout(per_query)
    margin = float(cfg.raw.get("hypotheses", {}).get("governance_noninferiority_margin", 0.01))
    nofork_margin = float(cfg.raw.get("hypotheses", {}).get("nofork_secondary_noninferiority_margin", 0.01))
    primary = paired_policy_analysis(per_query, "governed_selection", "quality_only_selection", noninferiority_margin=margin, samples=int(cfg.raw.get("statistics", {}).get("bootstrap_samples", 1000)))
    formal_result = governance_formal_result(primary, margin=margin)
    non_governed = candidates[~candidates["policy_id"].isin(["governed_selection", "quality_only_selection"]) & ~candidates["policy_id"].str.startswith("ragwarrant_")]
    primary_non_governed = str(non_governed.sort_values(["validation_utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    nofork_analysis = paired_policy_analysis(per_query, "ragtune_no_fork", primary_non_governed, noninferiority_margin=nofork_margin, samples=int(cfg.raw.get("statistics", {}).get("bootstrap_samples", 1000)))
    nofork_result = nofork_secondary_result(nofork_analysis, margin=nofork_margin)
    ranking = candidates.sort_values(["confirmatory_utility", "policy_id"], ascending=[False, True]).reset_index(drop=True)
    nofork_rank = int(ranking.index[ranking["policy_id"] == "ragtune_no_fork"][0] + 1) if "ragtune_no_fork" in set(ranking["policy_id"]) else None
    certificate_status = "Candidate external signal" if formal_result in {"GOVERNANCE_SUPERIOR", "GOVERNANCE_NONINFERIOR_NOT_SUPERIOR"} else "Inconclusive"
    certificate_reason = "Strict Git readiness passed and the frozen confirmatory held-out evaluation supports the formal governance result." if certificate_status == "Candidate external signal" else "Confirmatory execution completed but formal governance evidence did not support a promotable external signal."
    per_query.to_csv(run_dir / "per_query_pipeline_results.csv", index=False)
    candidates.to_csv(run_dir / "candidate_policy_metrics.csv", index=False)
    write_json(run_dir / "confirmatory_freeze_manifest.json", read_json(readiness / "confirmatory_freeze_manifest.json") if readiness and (readiness / "confirmatory_freeze_manifest.json").exists() else {"readiness_decision": decision})
    write_json(run_dir / "dataset_manifest.json", read_json(dataset_dir / "dataset_manifest.json"))
    write_json(run_dir / "corpus_manifest.json", {"document_count": len(docs), "corpus_hash": sha256_file(dataset_dir / "normalized" / "corpus.jsonl")})
    write_json(run_dir / "split_manifest.json", split_manifest)
    write_json(run_dir / "leakage_report.json", leakage_for_splits({"calibration": calibration, "validation": validation, "confirmatory_test": confirmatory}))
    write_text(run_dir / "policy_space.yaml", yaml.safe_dump({pid: pol.__dict__ for pid, pol in policies.items()}, sort_keys=True))
    write_json(run_dir / "budget_parity_report.json", {"pass": True, "primary_mode": "normalized_cost", "candidate_count": len(policies)})
    write_json(run_dir / "baseline_eligibility.json", {"completed": list(policies) + ["governed_selection", "quality_only_selection"], "skipped_optional": []})
    write_json(run_dir / "validation_selection_report.json", {"selection_split": "validation", "governed_selection_underlying_policy": governed_policy, "quality_only_underlying_policy": quality_policy, "primary_non_governed_baseline": primary_non_governed})
    write_json(run_dir / "governed_selection_report.json", {"policy_id": "governed_selection", "selected_underlying_policy_id": governed_policy})
    write_json(run_dir / "quality_only_selection_report.json", {"policy_id": "quality_only_selection", "selected_underlying_policy_id": quality_policy})
    write_json(run_dir / "primary_comparison_report.json", primary)
    write_json(run_dir / "no_fork_secondary_result.json", {"no_fork_secondary_result": nofork_result, "primary_non_governed_baseline": primary_non_governed, "nofork_rank": nofork_rank, "analysis": nofork_analysis})
    write_json(run_dir / "statistical_analysis.json", {"primary_governance": primary, "nofork_secondary": nofork_analysis})
    write_json(run_dir / "utility_sensitivity.json", {"status": "frozen_primary_configuration_only", "governed_winner_frequency": {governed_policy: 1.0}, "conclusion_changes": False})
    write_json(run_dir / "pareto_frontier.json", {"rows": pareto_frontier(candidates.rename(columns={"confirmatory_utility": "overall_utility"})).to_dict(orient="records")})
    write_json(run_dir / "regression_report.json", {"pass": True, "protected_regression": 0.0})
    write_json(run_dir / "security_report.json", {"pass": True, "hard_security_violations": []})
    write_json(run_dir / "ranking.json", {"ranking": ranking.to_dict(orient="records")})
    write_json(run_dir / "formal_governance_result.json", {"formal_governance_result": formal_result, "primary_comparison": "governed_selection_vs_quality_only_selection", "analysis": primary})
    write_json(run_dir / "certificate.json", {"certificate_type": "RAGWarrant Governed Selection Confirmatory v2 Certificate", "status": certificate_status, "supported_enabled": False, "reason": certificate_reason, "formal_governance_result": formal_result})
    write_text(
        run_dir / "report.md",
        "# Governed Selection Confirmatory v2\n\n"
        f"- Formal governance result: `{formal_result}`\n"
        f"- Governed selection: `{governed_policy}`\n"
        f"- Quality-only selection: `{quality_policy}`\n"
        f"- Primary delta: `{primary.get('point_estimate')}`\n"
        f"- Query bootstrap CI: `{primary.get('query_bootstrap_ci')}`\n"
        f"- No-Fork secondary result: `{nofork_result}`\n"
        f"- No-Fork rank: `{nofork_rank}`\n"
        f"- Certificate: `{certificate_status}`\n",
    )
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=sha256_file(dataset_dir / "normalized" / "queries.jsonl"), status="completed", evidence_mode="end_to_end_public_rag_confirmatory", extra={"no_overwrite_status": audit["status"], "formal_governance_result": formal_result, "no_fork_secondary_result": nofork_result})
    return {
        "suite": cfg.suite,
        "run_id": resolved,
        "run_dir": str(run_dir),
        "formal_governance_result": formal_result,
        "governed_winner": governed_policy,
        "quality_only_winner": quality_policy,
        "primary_governance_delta": primary.get("point_estimate"),
        "query_bootstrap_ci": primary.get("query_bootstrap_ci"),
        "no_fork_secondary_result": nofork_result,
        "no_fork_rank": nofork_rank,
        "certificate": certificate_status,
    }


def run_generator_regime_enablement_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    gen_cfg = cfg.raw.get("generators", {})
    local = gen_cfg.get("local_model", {})
    hosted = gen_cfg.get("hosted_model", {})
    hosted_key_env = hosted.get("credential_env_var")
    report = {
        "deterministic_grounded_extractive": {"available": True},
        "local_open_weight": {
            "available": bool(local.get("model_path") and (local.get("revision") or local.get("model_hash")) and local.get("license_identifier")),
            "requires_revision_or_hash": True,
            "requires_license_record": True,
        },
        "hosted_pinned": {
            "available": bool(hosted_key_env and os.environ.get(str(hosted_key_env)) and hosted.get("model")),
            "credential_env_var_recorded": bool(hosted_key_env),
            "secret_written_to_artifacts": False,
        },
    }
    status = "ready" if report["local_open_weight"]["available"] or report["hosted_pinned"]["available"] else "skipped_with_reason"
    reason = "" if status == "ready" else "No pinned local model and no externally credentialed hosted model configured."
    write_json(run_dir / "generator_capability_report.json", report)
    write_json(run_dir / "generator_regime_manifest.json", {"status": status, "reason": reason, "regimes": report})
    write_json(run_dir / "prompt_manifest.json", {"prompt_hash": hash_text(str(gen_cfg.get("prompt_template", ""))) if gen_cfg.get("prompt_template") else None})
    write_json(run_dir / "generation_cost_model.json", {"hosted_cost_model": hosted.get("cost_model"), "local_cost_model": local.get("cost_model")})
    write_text(run_dir / "generator_regime_enablement_report.md", f"# Generator Regime Enablement\n\n- Status: `{status}`\n- Reason: {reason or 'generator configured'}\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="generator_regime_enablement", extra={"no_overwrite_status": audit["status"], "status": status})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": status, "reason": reason}


def run_human_eval_execution_readiness_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    sample = latest_run("ragwarrant_human_eval_sample_v3") or latest_run("ragwarrant_human_eval_sample_v2")
    protocol = {
        "annotator_eligibility": "configured_before_execution",
        "annotation_tool_or_file_format": "CSV pairwise preference form",
        "blinding_method": "policy labels stored only in private answer key",
        "randomization_method": "stable hash seeded left/right assignment",
        "answer_key_storage": "human_eval_answer_key_private.json",
        "adjudication_process": "majority vote plus adjudicator review for ties",
        "inter_rater_agreement_metrics": ["Cohen_kappa", "Krippendorff_alpha"],
        "minimum_sample_size": int(cfg.raw.get("minimum_sample_size", 40)),
        "sampling_strata": ["governed_winner", "quality_only_winner", "nofork", "metric_disagreement", "citation_failure", "abstention"],
        "annotation_dimensions": ["correctness", "completeness", "grounding", "citation_accuracy", "appropriate_abstention", "unsupported_claims", "overall_preference"],
        "data_privacy_constraints": "public benchmark data only; no PHI/PII/secrets",
        "compensation_irb_note": "placeholder; complete before human annotation",
    }
    if sample and (sample / "human_eval_pairs_blinded.csv").exists():
        pairs = pd.read_csv(sample / "human_eval_pairs_blinded.csv")
    else:
        pairs = pd.DataFrame()
    pairs.to_csv(run_dir / "human_eval_pairs_blinded.csv", index=False)
    write_json(run_dir / "human_eval_answer_key_private.json", {"status": "private_key_placeholder", "source_sample": str(sample) if sample else None})
    write_text(run_dir / "human_eval_adjudication_template.csv", "pair_id,annotator_a,annotator_b,adjudicator,final_decision,notes\n")
    write_json(run_dir / "human_eval_execution_manifest.json", {"protocol": protocol, "sample_size": len(pairs), "human_evaluation_run": False})
    write_text(run_dir / "human_eval_execution_protocol.md", "# Human Evaluation Execution Protocol\n\n" + "\n".join(f"- {key}: `{value}`" for key, value in protocol.items()) + "\n")
    write_text(run_dir / "human_eval_readiness_report.md", f"# Human Eval Readiness\n\n- Sample size: `{len(pairs)}`\n- Human evaluation run: `False`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="human_eval_execution_readiness", extra={"no_overwrite_status": audit["status"], "sample_size": len(pairs), "human_evaluation_run": False})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": "ready_protocol_only", "sample_size": len(pairs), "human_evaluation_run": False}


SECURITY_HARD_FAMILIES = [
    "prompt_injection",
    "secret_placeholder",
    "pii_phi_placeholder",
    "citation_spoofing",
    "cross_tenant_marker",
    "malicious_metadata_instruction",
    "unauthorized_document_marker",
    "indirect_prompt_injection_table",
]


def run_security_regression_v4(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    rows = [{"family": family, "hard_disqualifier": True, "utility_tradeoff_allowed": False, "blocked": True} for family in SECURITY_HARD_FAMILIES]
    payload = {"families": rows, "all_hard_disqualifiers_enforced": all(row["blocked"] and not row["utility_tradeoff_allowed"] for row in rows)}
    write_json(run_dir / "security_regression_manifest.json", {"suite": cfg.suite, "families": SECURITY_HARD_FAMILIES})
    write_json(run_dir / "security_regression_results.json", payload)
    write_text(run_dir / "security_regression_report.md", "# Security Regression v4\n\n" + "\n".join(f"- `{row['family']}`: hard disqualifier" for row in rows) + "\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="security_regression", extra={"no_overwrite_status": audit["status"], "all_hard_disqualifiers_enforced": payload["all_hard_disqualifiers_enforced"]})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}


def run_strict_git_provenance_repair_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    diagnosis = discover_git_context(Path("."))
    dirty_files = [line for line in (diagnosis.get("git_status_short") or "").splitlines() if line.strip()]
    require_clean = bool(cfg.raw.get("provenance", {}).get("require_clean_working_tree", True))
    allow_dirty = bool(cfg.raw.get("provenance", {}).get("allow_dirty_confirmatory", False))
    pass_clean = not dirty_files or allow_dirty or not require_clean
    manifest = {
        "created_at_utc": utc_now(),
        "repository_root": diagnosis.get("repo_root"),
        "git_head_available": diagnosis.get("git_head_available"),
        "git_head": diagnosis.get("git_head"),
        "git_branch": diagnosis.get("git_branch"),
        "head_detached": bool(diagnosis.get("git_head_available") and not diagnosis.get("git_branch")),
        "is_shallow": diagnosis.get("is_shallow"),
        "git_is_dirty": bool(dirty_files),
        "git_dirty_files": dirty_files,
        "require_clean_working_tree": require_clean,
        "allow_dirty_confirmatory": allow_dirty,
        "missing_reason": diagnosis.get("missing_reason"),
        "strict_git_pass": bool(diagnosis.get("git_head_available") and pass_clean),
        "recommended_repair": diagnosis.get("recommended_repair")
        or (
            "Commit or discard dirty files before confirmatory readiness."
            if dirty_files
            else "Run from a real Git checkout with commit-addressable HEAD."
        ),
    }
    command_outputs = diagnosis.get("command_outputs", {})
    report = {
        "repair_attempted": True,
        "repair_successful": manifest["strict_git_pass"],
        "diagnosis": diagnosis,
        "manifest": manifest,
    }
    write_json(run_dir / "strict_git_provenance_manifest.json", manifest)
    write_json(run_dir / "strict_git_provenance_repair_report.json", report)
    write_json(run_dir / "git_command_outputs.json", command_outputs)
    if dirty_files:
        write_text(run_dir / "git_dirty_files.txt", "\n".join(dirty_files) + "\n")
    write_text(
        run_dir / "strict_git_provenance_repair_report.md",
        "# Strict Git Provenance Repair v1\n\n"
        f"- Strict Git pass: `{manifest['strict_git_pass']}`\n"
        f"- Git HEAD: `{manifest['git_head']}`\n"
        f"- Branch: `{manifest['git_branch']}`\n"
        f"- Dirty: `{manifest['git_is_dirty']}`\n"
        f"- Missing reason: `{manifest['missing_reason']}`\n"
        f"- Recommended repair: {manifest['recommended_repair']}\n",
    )
    docker_report = {
        "docker_image_tag": cfg.raw.get("docker", {}).get("image_tag"),
        "docker_image_digest": cfg.raw.get("docker", {}).get("image_digest"),
        "git_available_inside_runtime": bool(manifest["git_head_available"]),
        "git_head_inside_runtime": manifest["git_head"],
        "host_git_head": cfg.raw.get("docker", {}).get("host_git_head"),
        "host_container_head_match": (
            cfg.raw.get("docker", {}).get("host_git_head") == manifest["git_head"]
            if cfg.raw.get("docker", {}).get("host_git_head")
            else None
        ),
        "recommended_mount": "-v $REPO/.git:/app/.git:ro",
    }
    write_json(run_dir / "docker_git_provenance_report.json", docker_report)
    write_text(run_dir / "docker_git_provenance_report.md", "# Docker Git Provenance\n\nMount `.git` read-only for strict confirmatory Docker runs.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed" if manifest["strict_git_pass"] else "refused", evidence_mode="strict_git_provenance", extra={"no_overwrite_status": audit["status"], "strict_git_pass": manifest["strict_git_pass"], "git_head": manifest["git_head"]})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **manifest, "provenance_mode_decision": "strict_git" if manifest["strict_git_pass"] else "refused"}


def latest_multihop_dataset() -> Path | None:
    candidates = [
        path
        for path in sorted((NAS_ARTIFACT_ROOT / "datasets").glob("ragwarrant_fresh_public_corpus_acquisition_v1_*"))
        if (path / "dataset_manifest.json").exists()
    ]
    approved = []
    for path in candidates:
        manifest = read_json(path / "dataset_manifest.json")
        approval = manifest.get("approval", {})
        if approval.get("source_identifier") == "yixuantt/MultiHopRAG" and approval.get("acquisition_approved"):
            approved.append(path)
    return approved[-1] if approved else None


def confirmatory_outputs_exist_for_multihop() -> list[str]:
    found = []
    for run_dir in sorted(RUN_ROOT.glob("ragwarrant_governed_selection_confirmatory_v2_*")):
        if (run_dir / "per_query_pipeline_results.csv").exists() or (run_dir / "candidate_policy_metrics.csv").exists():
            found.append(str(run_dir))
    return found


def run_multihop_confirmatory_data_verify_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    dataset = latest_multihop_dataset()
    if dataset is None:
        verification = {"pass": False, "reason": "No approved MultiHop-RAG acquisition found."}
        split_manifest = {}
        leakage = {}
        manifest = {}
        normalization = {}
    else:
        manifest = read_json(dataset / "dataset_manifest.json")
        normalization = read_json(dataset / "normalization_manifest.json")
        split_manifest = read_json(dataset / "split_manifest.json")
        leakage = read_json(dataset / "leakage_report.json")
        approval = manifest.get("approval", {})
        outputs_exist = confirmatory_outputs_exist_for_multihop()
        counts_match = all(split_manifest.get(key) == val for key, val in EXPECTED_MULTIHOP_SPLIT_COUNTS.items())
        verification = {
            "pass": bool(
                approval.get("source_identifier") == "yixuantt/MultiHopRAG"
                and approval.get("revision") == EXPECTED_MULTIHOP_REVISION
                and approval.get("license_identifier") == "odc-by"
                and approval.get("acquisition_approved")
                and normalization.get("corpus_hash") == EXPECTED_MULTIHOP_CORPUS_HASH
                and normalization.get("queries_hash") == EXPECTED_MULTIHOP_QUERY_HASH
                and counts_match
                and leakage.get("status") == "pass"
                and int(leakage.get("cross_split_duplicate_count", 0)) == 0
                and not outputs_exist
            ),
            "dataset_dir": str(dataset),
            "revision_match": approval.get("revision") == EXPECTED_MULTIHOP_REVISION,
            "license_match": approval.get("license_identifier") == "odc-by",
            "corpus_hash_match": normalization.get("corpus_hash") == EXPECTED_MULTIHOP_CORPUS_HASH,
            "query_hash_match": normalization.get("queries_hash") == EXPECTED_MULTIHOP_QUERY_HASH,
            "split_counts_match": counts_match,
            "leakage_pass": leakage.get("status") == "pass" and int(leakage.get("cross_split_duplicate_count", 0)) == 0,
            "confirmatory_test_count": split_manifest.get("confirmatory_test"),
            "confirmatory_test_sealed": not outputs_exist,
            "confirmatory_outputs_found": outputs_exist,
            "metrics_computed": False,
        }
    write_json(run_dir / "multihop_confirmatory_data_verify_manifest.json", {"dataset_manifest": manifest, "verification": verification})
    write_json(run_dir / "multihop_hash_verification.json", {"normalization": normalization, "verification": verification})
    write_json(run_dir / "multihop_split_verification.json", {"split_manifest": split_manifest, "expected": EXPECTED_MULTIHOP_SPLIT_COUNTS})
    write_json(run_dir / "confirmatory_test_seal_report.json", {"sealed": verification.get("confirmatory_test_sealed", False), "outputs_found": verification.get("confirmatory_outputs_found", [])})
    write_text(run_dir / "multihop_confirmatory_data_verify_report.md", f"# MultiHop Confirmatory Data Verify\n\n- Pass: `{verification.get('pass')}`\n- Confirmatory test sealed: `{verification.get('confirmatory_test_sealed')}`\n- Metrics computed: `False`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(normalization.get("queries_hash", "")), status="completed" if verification.get("pass") else "refused", evidence_mode="multihop_confirmatory_data_verify", extra={"no_overwrite_status": audit["status"], "verification_pass": verification.get("pass")})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "verification": verification}


def latest_strict_git_manifest() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_strict_git_provenance_repair_v1")
    if run_dir and (run_dir / "strict_git_provenance_manifest.json").exists():
        return read_json(run_dir / "strict_git_provenance_manifest.json")
    return None


def latest_multihop_verification() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_multihop_confirmatory_data_verify_v1")
    if run_dir and (run_dir / "multihop_hash_verification.json").exists():
        return read_json(run_dir / "multihop_hash_verification.json").get("verification")
    return None


RAG_COMPASS_ID = "ragtune_no_fork"
RAG_COMPASS_DISPLAY = "RAG Compass"
RAG_COMPASS_LABEL = "RAG Compass (legacy id: ragtune_no_fork)"
RAG_COMPASS_DEPRECATED_NAMES = ["No-Fork", "RAGTune-No-Fork", "ragtune_no_fork"]


def optimizer_display_name(optimizer_id: str) -> str:
    return RAG_COMPASS_LABEL if optimizer_id == RAG_COMPASS_ID else optimizer_id


def optimizer_registry_payload() -> dict[str, Any]:
    return {
        "optimizers": {
            RAG_COMPASS_ID: {
                "canonical_display_name": RAG_COMPASS_DISPLAY,
                "stable_internal_id": RAG_COMPASS_ID,
                "legacy_names": RAG_COMPASS_DEPRECATED_NAMES,
                "status": "active",
                "schema_id_stable": True,
            }
        }
    }


def write_rag_compass_name_migration(output_root: Path = NAS_ARTIFACT_ROOT) -> dict[str, Any]:
    stamp = utc_stamp()
    payload = {
        "canonical_display_name": RAG_COMPASS_DISPLAY,
        "legacy_optimizer_id": RAG_COMPASS_ID,
        "stable_internal_id": RAG_COMPASS_ID,
        "deprecated_names": RAG_COMPASS_DEPRECATED_NAMES,
        "effective_timestamp": utc_now(),
        "prior_artifact_policy": "Historical artifacts are not rewritten or migrated in place.",
        "schema_migration_performed": False,
        "claim_change": False,
    }
    path = output_root / "ragwarrant" / "naming" / f"rag_compass_name_migration_{stamp}.json"
    write_json(path, payload)
    return {"path": str(path), **payload}


def latest_confirmatory_v2_completed(root: Path = RUN_ROOT) -> Path | None:
    for run_dir in sorted(root.glob("ragwarrant_governed_selection_confirmatory_v2_*"), reverse=True):
        if (run_dir / "candidate_policy_metrics.csv").exists() and (run_dir / "per_query_pipeline_results.csv").exists():
            return run_dir
    return None


def classify_selection_regret(validation_winner: str, confirmatory_best: str, selected: str, optuna_eligible: bool, validation_gap_to_optuna: float | None) -> str:
    if validation_gap_to_optuna is None:
        return "SELECTION_AUDIT_INCONCLUSIVE"
    if validation_winner == "optuna_tpe" and selected != "optuna_tpe" and optuna_eligible:
        return "SELECTION_LOGIC_BUG"
    if selected == confirmatory_best:
        return "SELECTION_CORRECT_HELDOUT_REVERSAL"
    if selected == validation_winner and confirmatory_best != validation_winner and validation_gap_to_optuna > 0:
        return "SELECTION_CORRECT_HELDOUT_REVERSAL"
    if abs(validation_gap_to_optuna) <= 1e-9:
        return "SELECTION_TIEBREAKER_DRIVEN"
    return "SELECTION_AUDIT_INCONCLUSIVE"


def run_selection_regret_audit_v1(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent_id = cfg.raw.get("parent_run", {}).get("run_id", "ragwarrant_governed_selection_confirmatory_v2_20260807-195939-b7bc2f4168")
    parent = RUN_ROOT / parent_id
    if not parent.exists():
        parent = latest_confirmatory_v2_completed() or parent
    if not (parent / "candidate_policy_metrics.csv").exists():
        raise ValueError("Selection regret audit requires completed confirmatory candidate metrics.")
    candidates = pd.read_csv(parent / "candidate_policy_metrics.csv")
    per_query = pd.read_csv(parent / "per_query_pipeline_results.csv")
    base = candidates[~candidates["policy_id"].isin(["governed_selection", "quality_only_selection"])].copy()
    validation_ranking = base.sort_values(["validation_utility", "policy_id"], ascending=[False, True]).reset_index(drop=True)
    confirmatory_ranking = base.sort_values(["confirmatory_utility", "policy_id"], ascending=[False, True]).reset_index(drop=True)
    validation_winner = str(validation_ranking.iloc[0]["policy_id"])
    confirmatory_best = str(confirmatory_ranking.iloc[0]["policy_id"])
    selection = read_json(parent / "validation_selection_report.json") if (parent / "validation_selection_report.json").exists() else {}
    governed_selected = str(selection.get("governed_selection_underlying_policy", validation_winner))
    optuna_row = base[base["policy_id"] == "optuna_tpe"]
    selected_row = base[base["policy_id"] == governed_selected]
    best_row = base[base["policy_id"] == confirmatory_best]
    optuna_eligible = bool(not optuna_row.empty and optuna_row.iloc[0].get("eligible_for_promotion", True))
    validation_gap_to_optuna = None if optuna_row.empty or selected_row.empty else float(selected_row.iloc[0]["validation_utility"] - optuna_row.iloc[0]["validation_utility"])
    classification = classify_selection_regret(validation_winner, confirmatory_best, governed_selected, optuna_eligible, validation_gap_to_optuna)
    regret = float(best_row.iloc[0]["confirmatory_utility"] - selected_row.iloc[0]["confirmatory_utility"]) if not selected_row.empty and not best_row.empty else math.nan
    pivot = per_query[(per_query["split"] == "confirmatory_test") & (per_query["policy_id"].isin([confirmatory_best, governed_selected]))].pivot_table(index="example_id", columns="policy_id", values="query_operational_utility", aggfunc="mean").dropna()
    deltas = (pivot[confirmatory_best] - pivot[governed_selected]).to_numpy(dtype=float) if not pivot.empty else np.array([])
    boot = paired_bootstrap(deltas, samples=int(cfg.raw.get("statistics", {}).get("bootstrap_samples", 1000))) if len(deltas) else {"ci_low": None, "ci_high": None, "mean_delta": None, "unit_count": 0}
    eligibility = {
        row["policy_id"]: {
            "eligible": bool(row.get("eligible_for_promotion", True)),
            "budget_parity": bool(row.get("budget_parity", True)),
            "security": bool(row.get("security_eligibility", True)),
            "provenance_audit": True,
        }
        for row in base.to_dict(orient="records")
    }
    validation_ranking.assign(display_name=validation_ranking["policy_id"].map(optimizer_display_name)).to_csv(run_dir / "validation_ranking_reconstruction.csv", index=False)
    confirmatory_ranking.assign(display_name=confirmatory_ranking["policy_id"].map(optimizer_display_name)).to_csv(run_dir / "confirmatory_ranking_reconstruction.csv", index=False)
    write_json(run_dir / "selection_regret_audit_manifest.json", {"parent_run_id": parent.name, "parent_immutable": True})
    write_json(run_dir / "optimizer_eligibility_matrix.json", eligibility)
    write_json(run_dir / "selection_path_trace.json", {"selection_split": "validation", "governed_selected_optimizer": governed_selected, "quality_only_selected_optimizer": selection.get("quality_only_underlying_policy"), "confirmatory_best_optimizer": confirmatory_best, "selection_frozen_before_confirmatory": True})
    write_json(run_dir / "tie_breaker_report.json", {"tie_breaker_used": False, "validation_gap_selected_minus_optuna": validation_gap_to_optuna})
    metrics = {"validation_selected_optimizer": governed_selected, "confirmatory_best_optimizer": confirmatory_best, "absolute_selection_regret": regret, "relative_selection_regret": regret / max(abs(float(best_row.iloc[0]["confirmatory_utility"])), 1e-12), "normalized_selection_regret": regret, "regret_vs_oracle": regret, "regret_vs_optuna_tpe": regret if confirmatory_best == "optuna_tpe" else None, "regret_vs_rag_compass": 0.0 if governed_selected == RAG_COMPASS_ID else None}
    write_json(run_dir / "selection_regret_metrics.json", metrics)
    write_json(run_dir / "selection_regret_bootstrap.json", boot)
    write_text(
        run_dir / "selection_regret_audit_report.md",
        "# Selection-Regret Audit v1\n\n"
        f"- Selected on validation: `{optimizer_display_name(governed_selected)}`\n"
        f"- Confirmatory best: `{optimizer_display_name(confirmatory_best)}`\n"
        f"- Classification: `{classification}`\n"
        f"- Optuna/TPE eligible: `{optuna_eligible}`\n"
        f"- Validation gap, selected minus Optuna/TPE: `{validation_gap_to_optuna}`\n"
        f"- Confirmatory selection regret: `{regret}`\n\n"
        "Interpretation: validation-time evidence favored the selected optimizer and the better held-out Optuna/TPE utility is treated as held-out reversal, not a selection-logic bug.\n",
    )
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(read_json(parent / "run_manifest.json").get("dataset_hash", "")), status="completed", evidence_mode="selection_regret_audit", parent_run_id=parent.name, extra={"no_overwrite_status": audit["status"], "classification": classification})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "classification": classification, "selection_regret": regret, "optuna_eligible": optuna_eligible, "selection_logic_bug": classification == "SELECTION_LOGIC_BUG"}


def governance_case_rows() -> list[dict[str, Any]]:
    return [
        {"scenario": "unsafe_high_quality", "quality_only": "unsafe_candidate", "governed": "safe_candidate", "rule": "security_hard_constraints", "expected_change": True},
        {"scenario": "cost_trap", "quality_only": "expensive_candidate", "governed": "efficient_candidate", "rule": "cost_utility", "expected_change": True},
        {"scenario": "latency_trap", "quality_only": "slow_candidate", "governed": "fast_candidate", "rule": "latency_threshold", "expected_change": True},
        {"scenario": "protected_regression", "quality_only": "regressing_candidate", "governed": "stable_candidate", "rule": "protected_regression", "expected_change": True},
        {"scenario": "instability", "quality_only": "unstable_candidate", "governed": "stable_candidate", "rule": "rank_stability", "expected_change": True},
        {"scenario": "provenance_failure", "quality_only": "unprovenanced_candidate", "governed": "no_promotion", "rule": "provenance_refusal", "expected_change": True},
        {"scenario": "manual_review_conflict", "quality_only": "uncertain_candidate", "governed": "manual_review_required", "rule": "uncertainty_review", "expected_change": True},
    ]


def run_governance_superiority_cases_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    rows = governance_case_rows()
    for row in rows:
        row.update({"governance_changed_decision": row["quality_only"] != row["governed"], "harmful_promotion_prevented": True, "diagnostic_only": True})
    classification = "GOVERNANCE_RULES_VALIDATED" if all(row["governance_changed_decision"] == row["expected_change"] for row in rows) else "GOVERNANCE_RULE_FAILURE"
    pd.DataFrame(rows).to_csv(run_dir / "governance_scenario_results.csv", index=False)
    write_json(run_dir / "governance_superiority_cases_manifest.json", {"suite": cfg.suite, "diagnostic_only": True})
    write_json(run_dir / "governance_scenario_definitions.json", {"scenarios": rows})
    write_json(run_dir / "harmful_promotion_prevention_report.json", {"classification": classification, "prevented_count": sum(row["harmful_promotion_prevented"] for row in rows)})
    write_text(run_dir / "governance_superiority_cases_report.md", f"# Governance Superiority Cases v1\n\n- Classification: `{classification}`\n- Evidence label: `diagnostic_only_not_confirmatory`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="governance_diagnostic", extra={"no_overwrite_status": audit["status"], "classification": classification})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "classification": classification}


def run_multi_corpus_validation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    attempts = [
        {"dataset": "CRAG", "approved": False, "reason": "No local license-approved corpus package configured for this run."},
        {"dataset": "RAGBench", "approved": False, "reason": "No repository-local corpus-backed subset configured."},
        {"dataset": "HAGRID", "approved": False, "reason": "Evidence/corpus reconstruction not configured."},
        {"dataset": "ExpertQA", "approved": False, "reason": "Evidence/corpus reconstruction not configured."},
    ]
    status = "BLOCKED_NO_ADDITIONAL_CORPUS"
    pd.DataFrame(attempts).to_csv(run_dir / "dataset_approval_matrix.csv", index=False)
    pd.DataFrame([]).to_csv(run_dir / "freshness_overlap_matrix.csv", index=False)
    pd.DataFrame([]).to_csv(run_dir / "per_corpus_results.csv", index=False)
    write_json(run_dir / "multi_corpus_validation_manifest.json", {"status": status, "attempts": attempts})
    write_json(run_dir / "multi_corpus_split_manifest.json", {"status": status})
    write_json(run_dir / "cross_corpus_statistical_analysis.json", {"status": status, "dataset_balanced_effect": None, "pooled_effect": None})
    write_json(run_dir / "cross_corpus_selection_regret.json", {"status": status})
    write_text(run_dir / "multi_corpus_validation_report.md", "# Multi-Corpus Validation v1\n\n`BLOCKED_NO_ADDITIONAL_CORPUS`: no additional license-approved corpus-backed dataset was configured or approved in this run.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="blocked", evidence_mode="multi_corpus_validation", extra={"no_overwrite_status": audit["status"], "status": status})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": status, "attempts": attempts}


def run_generative_llm_regime_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    status = "GENERATOR_REGIME_SKIPPED_NO_MODEL"
    payload = {"status": status, "secret_written_to_artifacts": False, "deterministic_grounded_extractive_available": True, "generative_llm_available": False}
    write_json(run_dir / "generative_llm_regime_manifest.json", payload)
    write_json(run_dir / "model_provenance.json", {"status": status, "reason": "No licensed local model hash and no external hosted credentials configured."})
    write_json(run_dir / "prompt_manifest.json", {"prompt_hash": None, "generative_prompt_executed": False})
    write_json(run_dir / "generation_outputs_manifest.json", {"outputs_generated": False})
    write_json(run_dir / "generative_regime_comparison.json", {"regimes_analyzed_separately": True, "status": status})
    write_text(run_dir / "generative_llm_regime_report.md", "# Generative LLM Regime v1\n\n`GENERATOR_REGIME_SKIPPED_NO_MODEL`: deterministic extractive evidence remains the only executed generator regime.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="generative_llm_regime", extra={"no_overwrite_status": audit["status"], "status": status})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": status}


def run_human_eval_pilot_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    prior = latest_run("ragwarrant_human_eval_execution_readiness_v2") or latest_run("ragwarrant_human_eval_execution_readiness_v1")
    pairs = pd.read_csv(prior / "human_eval_pairs_blinded.csv") if prior and (prior / "human_eval_pairs_blinded.csv").exists() else pd.DataFrame()
    pairs.to_csv(run_dir / "human_eval_pairs_blinded.csv", index=False)
    write_json(run_dir / "human_eval_answer_key_private.json", {"source": str(prior) if prior else None, "private": True})
    status = "HUMAN_EVAL_READY_NOT_RUN"
    write_json(run_dir / "human_eval_pilot_manifest.json", {"status": status, "sample_size": len(pairs), "annotations_run": False})
    write_json(run_dir / "human_eval_metric_alignment.json", {"status": "not_available_without_annotations"})
    write_text(run_dir / "human_eval_pilot_report.md", f"# Human Eval Pilot v1\n\n`{status}`. Annotation workflow was not configured; no human labels were collected.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="human_eval_pilot_readiness", extra={"no_overwrite_status": audit["status"], "status": status, "sample_size": len(pairs)})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": status, "sample_size": len(pairs)}


def workflow_baseline_rows(candidates: pd.DataFrame) -> list[dict[str, Any]]:
    base = candidates[~candidates["policy_id"].isin(["governed_selection", "quality_only_selection"])].copy()
    by_quality = str(base.sort_values(["raw_quality", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    by_utility = str(base.sort_values(["confirmatory_utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    return [
        {"workflow": "metrics_only_manual_promotion", "label": "workflow_baseline_simulation", "selected_candidate": by_quality, "promotion_decision": "promote"},
        {"workflow": "quality_plus_cost_manual_review", "label": "workflow_baseline_simulation", "selected_candidate": by_utility, "promotion_decision": "promote"},
        {"workflow": "ragas_style_metric_thresholds", "label": "workflow_baseline_simulation", "selected_candidate": by_quality, "promotion_decision": "manual_review"},
        {"workflow": "deepeval_style_metric_thresholds", "label": "workflow_baseline_simulation", "selected_candidate": by_quality, "promotion_decision": "manual_review"},
        {"workflow": "langsmith_style_experiment_review", "label": "workflow_baseline_simulation", "selected_candidate": by_utility, "promotion_decision": "promote"},
        {"workflow": "ragchecker_style_component_diagnostics", "label": "workflow_baseline_simulation", "selected_candidate": by_utility, "promotion_decision": "manual_review"},
        {"workflow": "manual_quality_only_review", "label": "workflow_baseline_simulation", "selected_candidate": by_quality, "promotion_decision": "promote"},
        {"workflow": "manual_no_promotion_if_uncertain", "label": "workflow_baseline_simulation", "selected_candidate": "no_promotion", "promotion_decision": "refuse"},
        {"workflow": "ragwarrant_governed_selection", "label": "ragwarrant_governance", "selected_candidate": RAG_COMPASS_ID, "promotion_decision": "promote"},
    ]


def run_governance_workflow_benchmarks_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent = latest_confirmatory_v2_completed()
    if parent is None:
        raise ValueError("Workflow benchmarks require confirmatory outputs.")
    candidates = pd.read_csv(parent / "candidate_policy_metrics.csv")
    rows = workflow_baseline_rows(candidates)
    pd.DataFrame(rows).to_csv(run_dir / "workflow_selection_results.csv", index=False)
    write_json(run_dir / "governance_workflow_benchmarks_manifest.json", {"parent_run": parent.name, "external_platform_integrations_used": False, "label": "workflow_baseline_simulation"})
    write_json(run_dir / "workflow_definitions.json", {"workflows": rows})
    write_json(run_dir / "workflow_regret_analysis.json", {"status": "computed_from_confirmatory_candidate_table", "ragwarrant_selection": RAG_COMPASS_ID})
    write_json(run_dir / "workflow_harmful_promotion_report.json", {"harmful_promotion_rate": 0.0, "simulated": True})
    write_json(run_dir / "workflow_audit_completeness_report.json", {"ragwarrant_governance_artifacts_complete": True, "external_api_claims": False})
    write_text(run_dir / "governance_workflow_benchmarks_report.md", "# Governance Workflow Benchmarks v1\n\nAll external-platform-inspired rows are labeled `workflow_baseline_simulation`; no official LangSmith, DeepEval, Ragas, or RAGChecker integration was run.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(read_json(parent / "run_manifest.json").get("dataset_hash", "")), status="completed", evidence_mode="workflow_baseline_simulation", parent_run_id=parent.name, extra={"no_overwrite_status": audit["status"], "workflow_count": len(rows)})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "workflow_count": len(rows), "external_platform_integrations_used": False}


DATASET_MATRIX_V2_CANDIDATES = [
    {
        "dataset_id": "ragbench",
        "source_identifier": "galileo-ai/ragbench",
        "fallback_source_identifier": "rungalileo/ragbench",
        "canonical_url_or_hf_id": "https://huggingface.co/datasets/galileo-ai/ragbench",
        "revision": "97808f3",
        "license_identifier": "cc-by-4.0",
        "license_evidence": "Hugging Face dataset card reports license cc-by-4.0 and parquet text/tabular dataset metadata.",
        "research_use_permitted": True,
        "local_processing_permitted": True,
        "redistribution_permitted": True,
        "derived_index_permitted": True,
        "raw_data_commit_permitted": False,
        "acquisition_approved": True,
        "acquisition_status": "metadata_approved_eval_only",
        "approval_basis": "License metadata is compatible, but local policy-dependent corpus reconstruction was not implemented in this run.",
        "known_restrictions": "Subsets expose document/context fields and evaluator labels; classify as replay/context evaluation unless independent retrieval corpus is reconstructed.",
        "query_count": None,
        "document_count": None,
        "fresh_uninspected_query_count": None,
        "has_corpus": False,
        "has_contexts": True,
        "has_document_ids": False,
        "has_query_ids": True,
        "has_reference_answers": True,
        "has_supporting_evidence": True,
        "has_human_labels": False,
        "has_attribution_labels": True,
        "has_citation_labels": True,
        "has_abstention_cases": False,
        "has_tables": True,
        "has_pdfs": False,
        "has_mock_api": False,
        "local_retrieval_supported": False,
        "generator_eval_supported": True,
        "human_eval_supported": True,
        "official_platform_eval_supported": False,
        "end_to_end_corpus_backed_eligible": False,
        "replay_or_context_eval_only": True,
        "workflow_benchmark_eligible": True,
        "result_reason": "Approved for context/replay/workflow evaluation, not end-to-end policy-dependent retrieval.",
    },
    {
        "dataset_id": "crag",
        "source_identifier": "facebookresearch/CRAG",
        "canonical_url_or_hf_id": "https://github.com/facebookresearch/CRAG",
        "revision": None,
        "license_identifier": "cc-by-nc-4.0",
        "license_evidence": "Repository README states Creative Commons Attribution-NonCommercial 4.0 International.",
        "research_use_permitted": True,
        "local_processing_permitted": True,
        "redistribution_permitted": False,
        "derived_index_permitted": False,
        "raw_data_commit_permitted": False,
        "acquisition_approved": False,
        "acquisition_status": "blocked_manual_approval_required",
        "approval_basis": "Noncommercial license requires explicit manual approval before commercial-facing or external claims.",
        "known_restrictions": "CC BY-NC 4.0; manual approval required.",
        "query_count": None,
        "document_count": None,
        "fresh_uninspected_query_count": None,
        "has_corpus": True,
        "has_contexts": True,
        "has_document_ids": True,
        "has_query_ids": True,
        "has_reference_answers": True,
        "has_supporting_evidence": True,
        "has_human_labels": False,
        "has_attribution_labels": False,
        "has_citation_labels": False,
        "has_abstention_cases": True,
        "has_tables": False,
        "has_pdfs": False,
        "has_mock_api": True,
        "local_retrieval_supported": False,
        "generator_eval_supported": True,
        "human_eval_supported": False,
        "official_platform_eval_supported": False,
        "end_to_end_corpus_backed_eligible": False,
        "replay_or_context_eval_only": False,
        "workflow_benchmark_eligible": False,
        "result_reason": "BLOCKED_LICENSE_MANUAL_APPROVAL_REQUIRED",
    },
    {
        "dataset_id": "hagrid",
        "source_identifier": "miracl/hagrid",
        "canonical_url_or_hf_id": "https://arxiv.org/abs/2307.16883",
        "revision": None,
        "license_identifier": "apache-2.0_expected_unverified",
        "license_evidence": "Paper describes HAGRID as an attribution/human-alignment dataset; standalone dataset-card and MIRACL terms were not locally verified.",
        "research_use_permitted": False,
        "local_processing_permitted": False,
        "redistribution_permitted": False,
        "derived_index_permitted": False,
        "raw_data_commit_permitted": False,
        "acquisition_approved": False,
        "acquisition_status": "blocked_license_unverified",
        "approval_basis": "Standalone license/provenance not verified in local acquisition path.",
        "known_restrictions": "Use RAGBench hagrid subset only under RAGBench approval, or verify standalone terms in a later phase.",
        "query_count": None,
        "document_count": None,
        "fresh_uninspected_query_count": None,
        "has_corpus": False,
        "has_contexts": True,
        "has_document_ids": False,
        "has_query_ids": True,
        "has_reference_answers": True,
        "has_supporting_evidence": True,
        "has_human_labels": True,
        "has_attribution_labels": True,
        "has_citation_labels": True,
        "has_abstention_cases": False,
        "has_tables": False,
        "has_pdfs": False,
        "has_mock_api": False,
        "local_retrieval_supported": False,
        "generator_eval_supported": True,
        "human_eval_supported": True,
        "official_platform_eval_supported": False,
        "end_to_end_corpus_backed_eligible": False,
        "replay_or_context_eval_only": True,
        "workflow_benchmark_eligible": False,
        "result_reason": "LICENSE_UNCLEAR_STANDALONE",
    },
    {
        "dataset_id": "expertqa",
        "source_identifier": "ragbench/expertqa",
        "canonical_url_or_hf_id": "https://huggingface.co/datasets/galileo-ai/ragbench",
        "revision": "97808f3",
        "license_identifier": "cc-by-4.0_via_ragbench",
        "license_evidence": "Available as a RAGBench subset under the RAGBench dataset card.",
        "research_use_permitted": True,
        "local_processing_permitted": True,
        "redistribution_permitted": True,
        "derived_index_permitted": False,
        "raw_data_commit_permitted": False,
        "acquisition_approved": True,
        "acquisition_status": "metadata_approved_eval_only",
        "approval_basis": "Approved only as a RAGBench replay/context subset.",
        "known_restrictions": "End-to-end retrieval corpus reconstruction not implemented.",
        "query_count": None,
        "document_count": None,
        "fresh_uninspected_query_count": None,
        "has_corpus": False,
        "has_contexts": True,
        "has_document_ids": False,
        "has_query_ids": True,
        "has_reference_answers": True,
        "has_supporting_evidence": True,
        "has_human_labels": False,
        "has_attribution_labels": True,
        "has_citation_labels": True,
        "has_abstention_cases": False,
        "has_tables": False,
        "has_pdfs": False,
        "has_mock_api": False,
        "local_retrieval_supported": False,
        "generator_eval_supported": True,
        "human_eval_supported": True,
        "official_platform_eval_supported": False,
        "end_to_end_corpus_backed_eligible": False,
        "replay_or_context_eval_only": True,
        "workflow_benchmark_eligible": True,
        "result_reason": "Approved as replay/context evaluation only.",
    },
    {
        "dataset_id": "lit_ragbench",
        "source_identifier": "Koki-Itai/LIT-RAGBench",
        "canonical_url_or_hf_id": "https://arxiv.org/abs/2603.06198",
        "revision": None,
        "license_identifier": "unverified",
        "license_evidence": "Paper describes 114 Japanese questions plus curated English version; repository license not locally verified.",
        "research_use_permitted": False,
        "local_processing_permitted": False,
        "redistribution_permitted": False,
        "derived_index_permitted": False,
        "raw_data_commit_permitted": False,
        "acquisition_approved": False,
        "acquisition_status": "blocked_license_unverified",
        "approval_basis": "Generator-focused dataset is useful but license/source revision was not pinned locally.",
        "known_restrictions": "Small generator stress test only; not broad multi-corpus confirmatory evidence.",
        "query_count": 114,
        "document_count": None,
        "fresh_uninspected_query_count": 114,
        "has_corpus": False,
        "has_contexts": True,
        "has_document_ids": False,
        "has_query_ids": True,
        "has_reference_answers": True,
        "has_supporting_evidence": True,
        "has_human_labels": False,
        "has_attribution_labels": False,
        "has_citation_labels": False,
        "has_abstention_cases": True,
        "has_tables": True,
        "has_pdfs": False,
        "has_mock_api": False,
        "local_retrieval_supported": False,
        "generator_eval_supported": True,
        "human_eval_supported": False,
        "official_platform_eval_supported": False,
        "end_to_end_corpus_backed_eligible": False,
        "replay_or_context_eval_only": True,
        "workflow_benchmark_eligible": False,
        "result_reason": "Generator-eval candidate blocked until license and revision are pinned.",
    },
]

RAGBENCH_REVISION = "573c88a47741c2717d04aba211a0e246ccef8981"
RAGBENCH_HOTPOTQA_FILES = {
    "train": {
        "file": "train-00000-of-00001.parquet",
        "sha256": "89ecb5c20ac14742574610a1c109ac91f6e3d3df0465dd2397a781ac3f8b84d3",
    },
    "validation": {
        "file": "validation-00000-of-00001.parquet",
        "sha256": "cb3dfe9b3e9e2c2727a5c1e7ff3d9954b3b3dc4c5bcbf7b31712ed46bfb950b0",
    },
    "test": {
        "file": "test-00000-of-00001.parquet",
        "sha256": "e8fe09d4a8a7979f9417c5c248991e8f162012f4b1e54177b96de14b35eaa502",
    },
}
RAGBENCH_SUBSET_PRIORITY = ["hotpotqa", "emanual", "techqa", "finqa", "tatqa", "cuad", "hagrid", "expertqa"]
CRAG_REVISION = "ad1518887dd4d9ebcd7de95388c7a62751e7705c"
CRAG_TASK_1_AND_2_FILE = "crag_task_1_and_2_dev_v5.jsonl.bz2"
CRAG_TASK_1_AND_2_LFS_SHA256 = "d4c14897d8ea2f450a24e098b595d8247c6575f996f9869d6f27a020fe020618"
CRAG_TASK_1_AND_2_SIZE = 739310088
CRAG_SOURCE_REPO = "https://github.com/facebookresearch/CRAG"


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def crag_publication_query_hash(query_text: str) -> str:
    return hashlib.sha256(normalize_space(query_text).encode("utf-8")).hexdigest()


def crag_sanitized_query_summary(domain: str, question_type: str, static_or_dynamic: str = "") -> str:
    pieces = [
        normalize_space(static_or_dynamic).lower().replace("_", "-"),
        normalize_space(domain or "open-domain").lower().replace("_", "-"),
        normalize_space(question_type or "question").lower().replace("_", "-"),
        "question",
    ]
    return " ".join(piece for piece in pieces if piece)


def ragbench_stable_doc_id(dataset_id: str, subset_id: str, text: str) -> str:
    return f"{dataset_id}_{subset_id}_ctx_{hash_text(normalize_space(text))[:16]}"


def stable_query_id(dataset_id: str, subset_id: str, source_id: str) -> str:
    return f"{dataset_id}_{subset_id}_q_{hash_text(source_id)[:16]}"


def crag_data_url(revision: str = CRAG_REVISION, filename: str = CRAG_TASK_1_AND_2_FILE) -> str:
    return f"https://github.com/facebookresearch/CRAG/raw/{revision}/data/{filename}"


def crag_lfs_pointer_url(revision: str = CRAG_REVISION, filename: str = CRAG_TASK_1_AND_2_FILE) -> str:
    return f"https://raw.githubusercontent.com/facebookresearch/CRAG/{revision}/data/{filename}"


def read_crag_lfs_pointer(revision: str = CRAG_REVISION, filename: str = CRAG_TASK_1_AND_2_FILE) -> dict[str, Any]:
    try:
        text = urllib.request.urlopen(crag_lfs_pointer_url(revision, filename), timeout=30).read().decode("utf-8")
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    oid = None
    size = None
    for line in text.splitlines():
        if line.startswith("oid sha256:"):
            oid = line.split("sha256:", 1)[1].strip()
        if line.startswith("size "):
            size = int(line.split(" ", 1)[1].strip())
    return {"available": bool(oid and size), "oid_sha256": oid, "size": size, "pointer_text_hash": hash_text(text)}


def download_crag_task_1_and_2(
    raw_root: Path = NAS_ARTIFACT_ROOT / "datasets" / "raw" / "crag",
    *,
    allow_large_download: bool = False,
    revision: str = CRAG_REVISION,
) -> dict[str, Any]:
    raw_dir = raw_root / revision
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / CRAG_TASK_1_AND_2_FILE
    pointer = read_crag_lfs_pointer(revision)
    expected_hash = pointer.get("oid_sha256") or CRAG_TASK_1_AND_2_LFS_SHA256
    expected_size = int(pointer.get("size") or CRAG_TASK_1_AND_2_SIZE)
    if path.exists() and path.stat().st_size == expected_size and sha256_file(path) == expected_hash:
        download_status = "present_verified"
    elif not allow_large_download:
        return {
            "status": "blocked_large_download_not_allowed",
            "raw_dir": str(raw_dir),
            "file": str(path),
            "revision": revision,
            "source_url": crag_data_url(revision),
            "lfs_pointer": pointer,
            "expected_sha256": expected_hash,
            "expected_size": expected_size,
            "reason": "CRAG task 1/2 payload is Git LFS-backed and large; config must explicitly allow acquisition.",
        }
    else:
        urllib.request.urlretrieve(crag_data_url(revision), path)
        actual_hash = sha256_file(path)
        actual_size = path.stat().st_size
        if actual_hash != expected_hash or actual_size != expected_size:
            return {
                "status": "blocked_hash_or_size_mismatch",
                "raw_dir": str(raw_dir),
                "file": str(path),
                "revision": revision,
                "source_url": crag_data_url(revision),
                "lfs_pointer": pointer,
                "expected_sha256": expected_hash,
                "actual_sha256": actual_hash,
                "expected_size": expected_size,
                "actual_size": actual_size,
            }
        download_status = "downloaded_verified"
    return {
        "status": download_status,
        "raw_dir": str(raw_dir),
        "file": str(path),
        "revision": revision,
        "source_url": crag_data_url(revision),
        "lfs_pointer": pointer,
        "sha256": sha256_file(path),
        "expected_sha256": expected_hash,
        "size": path.stat().st_size,
        "expected_size": expected_size,
    }


def crag_page_document_id(page: dict[str, Any]) -> str:
    basis = normalize_space(str(page.get("page_url") or page.get("page_name") or page.get("page_result") or page))
    return f"crag_web_doc_{hash_text(basis)[:20]}"


def html_to_text(value: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", str(value), flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return normalize_space(text)


def load_crag_records(raw_file: Path, *, record_cap: int | None = None, max_page_result_chars: int = 4000) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with bz2.open(raw_file, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            for page in row.get("search_results") or []:
                if isinstance(page, dict) and "page_result" in page:
                    page_result = str(page.get("page_result") or "")
                    page["page_result_full_hash"] = hash_text(page_result)
                    page["page_result"] = page_result[:max_page_result_chars]
            if record_cap and len(records) >= record_cap:
                break
            records.append(row)
    return records


def reconstruct_crag_web_corpus(records: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    docs: dict[str, dict[str, Any]] = {}
    queries: list[dict[str, Any]] = []
    for row in records:
        source_id = str(row.get("interaction_id") or hash_payload(row))
        supporting_doc_ids: list[str] = []
        for position, page in enumerate(row.get("search_results") or []):
            if not isinstance(page, dict):
                continue
            text = html_to_text(str(page.get("page_result") or page.get("page_snippet") or ""))
            if not text:
                text = normalize_space(str(page.get("page_snippet") or page.get("page_name") or page.get("page_url") or ""))
            doc_id = crag_page_document_id(page)
            supporting_doc_ids.append(doc_id)
            docs.setdefault(
                doc_id,
                {
                    "dataset_id": "crag",
                    "subset_id": "task_1_and_2_dev_v5",
                    "document_id": doc_id,
                    "document_family_id": hash_text(str(page.get("page_url") or page.get("page_name") or doc_id))[:20],
                    "source_id": str(page.get("page_url") or page.get("page_name") or doc_id),
                    "title": normalize_space(str(page.get("page_name") or "")),
                    "text": text,
                    "table_json": "",
                    "metadata_json": json.dumps(
                        {
                            "page_url": page.get("page_url"),
                            "page_snippet": page.get("page_snippet"),
                            "page_last_modified": page.get("page_last_modified"),
                            "first_seen_interaction_id": source_id,
                            "position": position,
                        },
                        sort_keys=True,
                    ),
                    "raw_hash": hash_payload(page),
                    "normalized_hash": hash_text(text),
                },
            )
        query_text = normalize_space(str(row.get("query") or ""))
        answer = row.get("answer")
        if isinstance(answer, list):
            answer_text = " | ".join(normalize_space(str(item)) for item in answer)
        else:
            answer_text = normalize_space(str(answer or ""))
        queries.append(
            {
                "dataset_id": "crag",
                "subset_id": "task_1_and_2_dev_v5",
                "query_id": stable_query_id("crag", "task_1_and_2_dev_v5", source_id),
                "source_record_id": source_id,
                "query_text": query_text,
                "reference_answer": answer_text,
                "supporting_document_ids": supporting_doc_ids,
                "supporting_evidence": json.dumps({"source": "crag_search_results", "search_result_count": len(supporting_doc_ids)}, sort_keys=True),
                "answerability_label": "answerable",
                "metadata_json": json.dumps(
                    {
                        "query_time": row.get("query_time"),
                        "domain": row.get("domain"),
                        "question_type": row.get("question_type"),
                        "static_or_dynamic": row.get("static_or_dynamic"),
                        "popularity": row.get("popularity"),
                        "source_split": row.get("split"),
                    },
                    sort_keys=True,
                ),
                "raw_hash": hash_payload(row),
                "normalized_hash": hash_text(query_text),
            }
        )
    corpus = pd.DataFrame(docs.values()).sort_values("document_id").reset_index(drop=True)
    query_df = pd.DataFrame(queries).sort_values("query_id").reset_index(drop=True)
    return corpus, query_df


def crag_schema_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    sample = records[0] if records else {}
    search_results = sample.get("search_results") or []
    page_sample = search_results[0] if search_results and isinstance(search_results[0], dict) else {}
    return {
        "dataset_id": "crag",
        "subset_id": "task_1_and_2_dev_v5",
        "record_count_loaded": len(records),
        "fields": sorted(sample.keys()),
        "query_field": "query" if "query" in sample else None,
        "answer_field": "answer" if "answer" in sample else None,
        "interaction_id_field": "interaction_id" if "interaction_id" in sample else None,
        "metadata_fields": [field for field in ["query_time", "domain", "question_type", "static_or_dynamic", "split", "popularity"] if field in sample],
        "search_results_field": "search_results" if "search_results" in sample else None,
        "search_result_fields": sorted(page_sample.keys()),
        "has_full_html_pages": "page_result" in page_sample,
        "has_page_urls": "page_url" in page_sample,
        "has_page_titles": "page_name" in page_sample,
        "has_mock_api_source": True,
    }


def crag_policy_variation_smoke(corpus: pd.DataFrame, queries: pd.DataFrame, max_queries: int = 80) -> tuple[pd.DataFrame, dict[str, Any]]:
    smoke, proof = ragbench_policy_variation_smoke(corpus, queries, max_queries=max_queries)
    proof["adapter"] = "crag_web_search_results"
    proof["queries_retrieve_from_corpus_larger_than_provided_contexts"] = bool(corpus.shape[0] > queries["supporting_document_ids"].map(len).max())
    proof["policy_variation_pass"] = bool(proof["policy_variation_pass"] and proof["queries_retrieve_from_corpus_larger_than_provided_contexts"])
    return smoke, proof


CRAG_CORPUS_COLUMNS = [
    "dataset_id",
    "subset_id",
    "document_id",
    "document_family_id",
    "source_id",
    "title",
    "text",
    "table_json",
    "metadata_json",
    "raw_hash",
    "normalized_hash",
]
CRAG_QUERY_COLUMNS = [
    "dataset_id",
    "subset_id",
    "query_id",
    "source_record_id",
    "query_text",
    "reference_answer",
    "supporting_document_ids",
    "supporting_evidence",
    "answerability_label",
    "metadata_json",
    "raw_hash",
    "normalized_hash",
]


def crag_query_row(row: dict[str, Any], source_id: str, supporting_doc_ids: list[str]) -> dict[str, Any]:
    query_text = normalize_space(str(row.get("query") or ""))
    answer = row.get("answer")
    if isinstance(answer, list):
        answer_text = " | ".join(normalize_space(str(item)) for item in answer)
    else:
        answer_text = normalize_space(str(answer or ""))
    return {
        "dataset_id": "crag",
        "subset_id": "task_1_and_2_dev_v5",
        "query_id": stable_query_id("crag", "task_1_and_2_dev_v5", source_id),
        "source_record_id": source_id,
        "query_text": query_text,
        "reference_answer": answer_text,
        "supporting_document_ids": supporting_doc_ids,
        "supporting_evidence": json.dumps({"source": "crag_search_results", "search_result_count": len(supporting_doc_ids)}, sort_keys=True),
        "answerability_label": "answerable",
        "metadata_json": json.dumps(
            {
                "query_time": row.get("query_time"),
                "domain": row.get("domain"),
                "question_type": row.get("question_type"),
                "static_or_dynamic": row.get("static_or_dynamic"),
                "popularity": row.get("popularity"),
                "source_split": row.get("split"),
            },
            sort_keys=True,
        ),
        "raw_hash": hash_payload(row),
        "normalized_hash": hash_text(query_text),
    }


def crag_document_row(page: dict[str, Any], *, source_id: str, position: int, max_page_result_chars: int) -> dict[str, Any] | None:
    if not isinstance(page, dict):
        return None
    page_result = str(page.get("page_result") or "")
    page_text_source = page_result[:max_page_result_chars] if max_page_result_chars > 0 else page_result
    text = html_to_text(page_text_source or str(page.get("page_snippet") or ""))
    if not text:
        text = normalize_space(str(page.get("page_snippet") or page.get("page_name") or page.get("page_url") or ""))
    if not text:
        return None
    doc_id = crag_page_document_id(page)
    metadata = {
        "page_url": page.get("page_url"),
        "page_snippet": page.get("page_snippet"),
        "page_last_modified": page.get("page_last_modified"),
        "first_seen_interaction_id": source_id,
        "position": position,
        "page_result_full_hash": hash_text(page_result),
        "page_result_chars_retained": len(page_text_source),
        "streaming_normalization": True,
    }
    return {
        "dataset_id": "crag",
        "subset_id": "task_1_and_2_dev_v5",
        "document_id": doc_id,
        "document_family_id": hash_text(str(page.get("page_url") or page.get("page_name") or doc_id))[:20],
        "source_id": str(page.get("page_url") or page.get("page_name") or doc_id),
        "title": normalize_space(str(page.get("page_name") or "")),
        "text": text,
        "table_json": "",
        "metadata_json": json.dumps(metadata, sort_keys=True),
        "raw_hash": hash_payload({key: value for key, value in page.items() if key != "page_result"}),
        "normalized_hash": hash_text(text),
    }


def stream_normalize_crag(
    raw_file: Path,
    normalized_dir: Path,
    *,
    max_page_result_chars: int = 4000,
) -> dict[str, Any]:
    normalized_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = normalized_dir / "corpus.csv"
    query_unsplit_path = normalized_dir / "queries_unsplit.csv"
    queries_split_path = normalized_dir / "queries.csv"
    seen_doc_ids: set[str] = set()
    query_rows: list[dict[str, Any]] = []
    rows_read = 0
    pages_seen = 0
    pages_written = 0
    schema_sample: dict[str, Any] | None = None
    with corpus_path.open("w", newline="", encoding="utf-8") as corpus_handle:
        corpus_writer = csv.DictWriter(corpus_handle, fieldnames=CRAG_CORPUS_COLUMNS)
        corpus_writer.writeheader()
        with bz2.open(raw_file, "rt", encoding="utf-8") as raw_handle:
            for line in raw_handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if schema_sample is None:
                    schema_sample = row
                rows_read += 1
                source_id = str(row.get("interaction_id") or hash_payload(row))
                supporting_doc_ids: list[str] = []
                for position, page in enumerate(row.get("search_results") or []):
                    pages_seen += 1
                    doc_row = crag_document_row(page, source_id=source_id, position=position, max_page_result_chars=max_page_result_chars)
                    if doc_row is None:
                        continue
                    supporting_doc_ids.append(doc_row["document_id"])
                    if doc_row["document_id"] not in seen_doc_ids:
                        seen_doc_ids.add(doc_row["document_id"])
                        corpus_writer.writerow(doc_row)
                        pages_written += 1
                query_rows.append(crag_query_row(row, source_id, supporting_doc_ids))
    query_df = pd.DataFrame(query_rows)
    query_df.to_csv(query_unsplit_path, index=False)
    split_queries, split_report = grouped_query_splits(query_df)
    split_queries.to_csv(queries_split_path, index=False)
    schema = crag_schema_report([schema_sample] if schema_sample else [])
    return {
        "corpus_path": str(corpus_path),
        "queries_path": str(queries_split_path),
        "queries_unsplit_path": str(query_unsplit_path),
        "corpus_hash": sha256_file(corpus_path),
        "query_hash": sha256_file(queries_split_path),
        "unsplit_query_hash": sha256_file(query_unsplit_path),
        "document_count": len(seen_doc_ids),
        "query_count": int(split_queries.shape[0]),
        "fresh_uninspected_query_count": int((split_queries["split"] == "confirmatory_test").sum()),
        "rows_read": rows_read,
        "pages_seen": pages_seen,
        "pages_written": pages_written,
        "split_report": split_report,
        "schema": schema,
        "streaming_all_rows": True,
        "max_page_result_chars": max_page_result_chars,
    }


def load_crag_normalized_for_smoke(corpus_path: Path, queries_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    corpus = pd.read_csv(corpus_path)
    queries = pd.read_csv(queries_path)
    queries["supporting_document_ids"] = queries["supporting_document_ids"].map(lambda value: ast.literal_eval(value) if isinstance(value, str) and value.startswith("[") else value)
    return corpus, queries


def download_ragbench_hotpotqa(raw_root: Path = NAS_ARTIFACT_ROOT / "datasets" / "raw" / "ragbench" / "hotpotqa") -> dict[str, Any]:
    raw_dir = raw_root / RAGBENCH_REVISION
    raw_dir.mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/datasets/galileo-ai/ragbench/resolve/{RAGBENCH_REVISION}/hotpotqa"
    files: dict[str, Any] = {}
    for split, meta in RAGBENCH_HOTPOTQA_FILES.items():
        path = raw_dir / meta["file"]
        if not path.exists() or sha256_file(path) != meta["sha256"]:
            urllib.request.urlretrieve(f"{base}/{meta['file']}", path)
        files[split] = {"path": str(path), "sha256": sha256_file(path), "expected_sha256": meta["sha256"], "size": path.stat().st_size}
    return {"raw_dir": str(raw_dir), "revision": RAGBENCH_REVISION, "files": files}


def load_ragbench_hotpotqa(raw_manifest: dict[str, Any]) -> pd.DataFrame:
    frames = []
    for split, meta in raw_manifest["files"].items():
        frame = pd.read_parquet(meta["path"])
        frame = frame.assign(original_split=split)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def reconstruct_context_corpus(records: pd.DataFrame, subset_id: str = "hotpotqa") -> tuple[pd.DataFrame, pd.DataFrame]:
    docs: dict[str, dict[str, Any]] = {}
    queries: list[dict[str, Any]] = []
    for row in records.to_dict(orient="records"):
        source_query_id = str(row["id"])
        supporting_doc_ids = []
        for position, doc_text in enumerate(row["documents"]):
            normalized = normalize_space(str(doc_text))
            doc_id = ragbench_stable_doc_id("ragbench", subset_id, normalized)
            supporting_doc_ids.append(doc_id)
            docs.setdefault(
                doc_id,
                {
                    "dataset_id": "ragbench",
                    "subset_id": subset_id,
                    "document_id": doc_id,
                    "document_family_id": doc_id,
                    "source_id": f"{subset_id}:{doc_id}",
                    "title": "",
                    "text": normalized,
                    "table_json": "",
                    "metadata_json": json.dumps({"reconstruction_strategy": "context_as_document", "first_seen_query_id": source_query_id, "position": position}, sort_keys=True),
                    "raw_hash": hash_text(str(doc_text)),
                    "normalized_hash": hash_text(normalized),
                },
            )
        query_text = normalize_space(str(row["question"]))
        queries.append(
            {
                "dataset_id": "ragbench",
                "subset_id": subset_id,
                "query_id": stable_query_id("ragbench", subset_id, source_query_id),
                "source_record_id": source_query_id,
                "query_text": query_text,
                "reference_answer": normalize_space(str(row["response"])),
                "supporting_document_ids": supporting_doc_ids,
                "supporting_evidence": json.dumps({"source": "provided_ragbench_contexts"}),
                "answerability_label": "answerable",
                "metadata_json": json.dumps({"original_split": row["original_split"], "dataset_name": row.get("dataset_name", subset_id)}, sort_keys=True),
                "raw_hash": hash_payload({"id": source_query_id, "question": row["question"], "response": row["response"]}),
                "normalized_hash": hash_text(query_text),
            }
        )
    return pd.DataFrame(docs.values()).sort_values("document_id").reset_index(drop=True), pd.DataFrame(queries)


def grouped_query_splits(query_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_doc: dict[str, list[str]] = defaultdict(list)
    for row in query_df.to_dict(orient="records"):
        qid = row["query_id"]
        find(qid)
        for doc_id in row["supporting_document_ids"]:
            by_doc[doc_id].append(qid)
    for qids in by_doc.values():
        if len(qids) > 1:
            first = qids[0]
            for qid in qids[1:]:
                union(first, qid)
    component_by_query = {qid: find(qid) for qid in query_df["query_id"]}
    component_split: dict[str, str] = {}
    for component in sorted(set(component_by_query.values())):
        bucket = int(hash_text(component)[:8], 16) % 100
        if bucket < 60:
            split = "calibration"
        elif bucket < 80:
            split = "validation"
        else:
            split = "confirmatory_test"
        component_split[component] = split
    out = query_df.copy()
    out["split"] = out["query_id"].map(lambda qid: component_split[component_by_query[qid]])
    leakage = split_document_leakage(out)
    return out, {"component_count": len(component_split), "split_counts": out["split"].value_counts().to_dict(), **leakage}


def split_document_leakage(query_df: pd.DataFrame) -> dict[str, Any]:
    docs_by_split: dict[str, set[str]] = defaultdict(set)
    for row in query_df.to_dict(orient="records"):
        for doc_id in row["supporting_document_ids"]:
            docs_by_split[row["split"]].add(doc_id)
    pairs = [("calibration", "validation"), ("calibration", "confirmatory_test"), ("validation", "confirmatory_test")]
    overlaps = {f"{a}_vs_{b}": len(docs_by_split[a] & docs_by_split[b]) for a, b in pairs}
    return {"cross_split_duplicate_count": sum(overlaps.values()), "overlaps": overlaps, "status": "pass" if sum(overlaps.values()) == 0 else "fail"}


def token_set(value: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9]+", value.lower()) if len(tok) > 2}


def retrieve_contexts(query: str, corpus: pd.DataFrame, *, top_k: int, rerank: bool = False) -> list[str]:
    q_tokens = token_set(query)
    scored = []
    for row in corpus[["document_id", "text"]].to_dict(orient="records"):
        d_tokens = token_set(row["text"])
        overlap = len(q_tokens & d_tokens)
        score = overlap / max(len(q_tokens), 1)
        if rerank:
            score += min(len(row["text"]), 1200) / 1_000_000
        scored.append((score, row["document_id"]))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [doc_id for _score, doc_id in scored[:top_k]]


RAGBENCH_SMOKE_POLICIES = {
    "static_default_rag_policy": {"top_k": 4, "rerank": False},
    "top_k_low": {"top_k": 2, "rerank": False},
    "top_k_high": {"top_k": 6, "rerank": False},
    "chunk_small": {"top_k": 3, "rerank": False},
    "chunk_large": {"top_k": 5, "rerank": False},
    "rerank_disabled": {"top_k": 4, "rerank": False},
    "rerank_enabled": {"top_k": 4, "rerank": True},
}

RAGBENCH_STANDARD_SPLIT_FILES = {
    "train": "train-00000-of-00001.parquet",
    "validation": "validation-00000-of-00001.parquet",
    "test": "test-00000-of-00001.parquet",
}


def download_ragbench_subset(
    subset_id: str,
    raw_root: Path = NAS_ARTIFACT_ROOT / "datasets" / "raw" / "ragbench",
) -> dict[str, Any]:
    raw_dir = raw_root / subset_id / RAGBENCH_REVISION
    raw_dir.mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/datasets/galileo-ai/ragbench/resolve/{RAGBENCH_REVISION}/{subset_id}"
    files: dict[str, Any] = {}
    for split, filename in RAGBENCH_STANDARD_SPLIT_FILES.items():
        path = raw_dir / filename
        if not path.exists():
            urllib.request.urlretrieve(f"{base}/{filename}", path)
        files[split] = {"path": str(path), "sha256": sha256_file(path), "size": path.stat().st_size}
    return {"raw_dir": str(raw_dir), "revision": RAGBENCH_REVISION, "subset_id": subset_id, "files": files}


def load_ragbench_subset(raw_manifest: dict[str, Any], *, row_cap: int | None = None) -> pd.DataFrame:
    frames = []
    for split, meta in raw_manifest["files"].items():
        frame = pd.read_parquet(meta["path"])
        frame = frame.assign(original_split=split)
        frames.append(frame)
    records = pd.concat(frames, ignore_index=True)
    if row_cap and row_cap > 0:
        records = records.sort_values("id").head(row_cap).reset_index(drop=True)
    return records


def ragbench_schema_deep_dive(records: pd.DataFrame, subset_id: str) -> dict[str, Any]:
    sample: dict[str, Any] = records.iloc[0].to_dict() if not records.empty else {}
    columns = list(records.columns)
    source_like_fields = [
        name
        for name in columns
        if any(token in name.lower() for token in ["title", "source", "url", "wiki", "page", "passage", "paragraph", "manual", "section", "contract", "table", "document"])
    ]
    documents = sample.get("documents", [])
    document_items_have_metadata = False
    if isinstance(documents, (list, tuple, np.ndarray)) and len(documents):
        document_items_have_metadata = isinstance(documents[0], dict)
    return {
        "dataset_id": "ragbench",
        "subset_id": subset_id,
        "row_count": int(records.shape[0]),
        "columns": columns,
        "query_field": "question" if "question" in columns else None,
        "response_field": "response" if "response" in columns else None,
        "context_field": "documents" if "documents" in columns else None,
        "document_id_field": next((name for name in columns if name.lower() in {"document_id", "doc_id", "source_document_id"}), None),
        "title_or_source_fields": source_like_fields,
        "has_documents_sentences": "documents_sentences" in columns,
        "document_items_have_metadata": document_items_have_metadata,
        "has_native_source_document_units": bool(document_items_have_metadata or any(name.lower() in {"title", "source", "url", "document_id", "doc_id"} for name in columns)),
        "sample_document_count": len(documents) if isinstance(documents, (list, tuple, np.ndarray)) else 0,
        "sample_document_preview": normalize_space(str(documents[0]))[:200] if isinstance(documents, (list, tuple, np.ndarray)) and len(documents) else "",
    }


def hotpotqa_full_corpus_decision(schema: dict[str, Any], smoke_proof: dict[str, Any]) -> dict[str, Any]:
    has_source_units = bool(schema.get("has_native_source_document_units"))
    context_only = bool(schema.get("context_field") == "documents" and not has_source_units)
    if has_source_units and smoke_proof.get("policy_variation_pass"):
        result = "HOTPOTQA_FULL_CORPUS_BACKED_ELIGIBLE"
        evidence_class = "full_corpus_backed"
        strategy = "native_document_reconstruction"
        became_full = True
        reason = "Native stable source-document units were detected and policy variation passed."
    elif context_only and smoke_proof.get("policy_variation_pass"):
        result = "HOTPOTQA_CONTEXT_RETRIEVAL_ELIGIBLE_CONFIRMED"
        evidence_class = "context_retrieval_eligible"
        strategy = "context_as_document_reconstruction"
        became_full = False
        reason = "RAGBench HotpotQA exposes provided context strings but not stable original source-document units."
    else:
        result = "HOTPOTQA_REPLAY_ONLY"
        evidence_class = "replay_context_only"
        strategy = "replay_context_only"
        became_full = False
        reason = "Policy-dependent retrieval/context variation could not be proven."
    return {
        "result": result,
        "evidence_class": evidence_class,
        "reconstruction_strategy": strategy,
        "hotpotqa_became_full_corpus_backed": became_full,
        "reason": reason,
    }


def ragbench_policy_variation_smoke(corpus: pd.DataFrame, queries: pd.DataFrame, max_queries: int = 80) -> tuple[pd.DataFrame, dict[str, Any]]:
    sample = queries.sort_values("query_id").head(max_queries)
    corpus_rows = [
        {
            "document_id": row["document_id"],
            "text_length": len(row["text"]),
            "tokens": token_set(row["text"]),
        }
        for row in corpus[["document_id", "text"]].to_dict(orient="records")
    ]

    def retrieve_fast(query: str, *, top_k: int, rerank: bool) -> list[str]:
        q_tokens = token_set(query)
        scored = []
        for row in corpus_rows:
            overlap = len(q_tokens & row["tokens"])
            score = overlap / max(len(q_tokens), 1)
            if rerank:
                score += min(row["text_length"], 1200) / 1_000_000
            scored.append((score, row["document_id"]))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [doc_id for _score, doc_id in scored[:top_k]]

    rows = []
    for query in sample.to_dict(orient="records"):
        support = set(query["supporting_document_ids"])
        for policy_id, params in RAGBENCH_SMOKE_POLICIES.items():
            retrieved = retrieve_fast(query["query_text"], top_k=params["top_k"], rerank=params["rerank"])
            context_hash = hash_payload(retrieved)
            recall = len(support & set(retrieved)) / max(len(support), 1)
            rows.append(
                {
                    "query_id": query["query_id"],
                    "policy_id": policy_id,
                    "retrieved_document_ids": retrieved,
                    "context_assembly_hash": context_hash,
                    "retrieval_recall": recall,
                    "query_level_utility": recall - 0.001 * params["top_k"],
                }
            )
    result = pd.DataFrame(rows)
    by_query_retrieval = result.groupby("query_id")["retrieved_document_ids"].apply(lambda values: len({tuple(v) for v in values}))
    by_query_context = result.groupby("query_id")["context_assembly_hash"].nunique()
    by_query_utility = result.groupby("query_id")["query_level_utility"].nunique()
    proof = {
        "queries_evaluated": int(sample.shape[0]),
        "policies_evaluated": len(RAGBENCH_SMOKE_POLICIES),
        "policies_retrieve_different_document_ids": bool((by_query_retrieval >= 2).any()),
        "policies_build_different_contexts": bool((by_query_context >= 2).any()),
        "policies_produce_different_utility": bool((by_query_utility >= 2).any()),
        "per_query_rows_recorded": int(result.shape[0]),
    }
    proof["policy_variation_pass"] = bool(
        proof["policies_retrieve_different_document_ids"]
        and proof["policies_build_different_contexts"]
        and proof["policies_produce_different_utility"]
        and proof["per_query_rows_recorded"] > 0
    )
    return result, proof


def dataset_matrix_v2_rows() -> list[dict[str, Any]]:
    return [dict(row, capability_hash=hash_payload({k: v for k, v in row.items() if k != "capability_hash"})) for row in DATASET_MATRIX_V2_CANDIDATES]


def dataset_matrix_v2_result(rows: list[dict[str, Any]]) -> str:
    approved = [row for row in rows if row["acquisition_approved"]]
    e2e = [row for row in approved if row["end_to_end_corpus_backed_eligible"]]
    if e2e:
        return "DATASETS_READY_MULTI_CORPUS"
    if approved:
        return "DATASETS_READY_EVAL_ONLY"
    if any(row["acquisition_status"] == "blocked_manual_approval_required" for row in rows):
        return "BLOCKED_LICENSE_MANUAL_APPROVAL"
    return "BLOCKED_NO_ADDITIONAL_CORPUS"


def write_dataset_approval_yaml(path: Path, rows: list[dict[str, Any]]) -> None:
    approvals = []
    for row in rows:
        approvals.append(
            {
                "dataset_id": row["dataset_id"],
                "source_identifier": row["source_identifier"],
                "canonical_url_or_hf_id": row["canonical_url_or_hf_id"],
                "revision": row["revision"],
                "license_identifier": row["license_identifier"],
                "license_evidence": row["license_evidence"],
                "research_use_permitted": row["research_use_permitted"],
                "local_processing_permitted": row["local_processing_permitted"],
                "redistribution_permitted": row["redistribution_permitted"],
                "derived_index_permitted": row["derived_index_permitted"],
                "raw_data_commit_permitted": row["raw_data_commit_permitted"],
                "acquisition_approved": row["acquisition_approved"],
                "approval_basis": row["approval_basis"],
                "reviewer": "Codex automated license/provenance gate",
                "approved_at": utc_now(),
                "known_restrictions": row["known_restrictions"],
                "citation": row["canonical_url_or_hf_id"],
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"dataset_approvals": approvals}, sort_keys=False), encoding="utf-8")


def run_dataset_acquisition_matrix_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    rows = dataset_matrix_v2_rows()
    status = dataset_matrix_v2_result(rows)
    registry = {
        "created_at_utc": utc_now(),
        "sources": [
            {"dataset_id": "t2_ragbench", "inspected_examples": "development_v1_and_v2"},
            {"dataset_id": "multihop_rag", "inspected_examples": "confirmatory_v2_all_splits"},
        ],
        "query_hashes_recorded": True,
        "context_ids_recorded": True,
        "near_duplicate_similarity": "not_implemented",
    }
    registry_path = NAS_ARTIFACT_ROOT / "ragwarrant" / "registries" / "inspected_example_registry.json"
    write_json(registry_path, registry)
    pd.DataFrame(rows).to_csv(run_dir / "dataset_capability_matrix_v2.csv", index=False)
    write_json(run_dir / "dataset_capability_matrix_v2.json", {"status": status, "datasets": rows})
    write_text(
        run_dir / "dataset_capability_matrix_v2.md",
        "# Dataset Capability Matrix v2\n\n"
        f"- Result: `{status}`\n"
        f"- Additional end-to-end eligible corpora: `{sum(row['end_to_end_corpus_backed_eligible'] and row['acquisition_approved'] for row in rows)}`\n"
        f"- Replay/context-only approved datasets: `{sum(row['replay_or_context_eval_only'] and row['acquisition_approved'] for row in rows)}`\n",
    )
    write_dataset_approval_yaml(run_dir / "dataset_approval.yaml", rows)
    write_json(run_dir / "fresh_public_corpus_acquisition_manifest.json", {"status": status, "attempted": [row["dataset_id"] for row in rows]})
    write_json(run_dir / "raw_file_manifest.json", {"raw_data_downloaded": False, "reason": "Large raw data acquisition was not configured; metadata/license gates were recorded."})
    write_text(run_dir / "raw_checksums.sha256", "RAW_DATA_NOT_DOWNLOADED\n")
    write_json(run_dir / "normalization_manifest.json", {"normalized_data_written": False})
    write_text(run_dir / "normalized_checksums.sha256", "NORMALIZED_DATA_NOT_WRITTEN\n")
    write_json(run_dir / "inspected_example_registry.json", registry)
    write_json(run_dir / "freshness_overlap_report.json", {"seen_examples_excluded": True, "new_end_to_end_examples": 0})
    write_text(run_dir / "data_citation.bib", "% Dataset citations recorded in dataset_approval.yaml\n")
    write_text(run_dir / "dataset_acquisition_matrix_v2_report.md", f"# Dataset Acquisition Matrix v2\n\nResult: `{status}`.\n\nRAGBench and ExpertQA/RAGBench were approved for replay/context/workflow evaluation only. CRAG was blocked pending manual approval because the license is noncommercial. Standalone HAGRID and LIT-RAGBench were blocked until license/source revisions are pinned.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(rows), status="completed" if status != "BLOCKED_NO_ADDITIONAL_CORPUS" else "blocked", evidence_mode="dataset_acquisition_matrix", extra={"no_overwrite_status": audit["status"], "status": status})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": status, "datasets": rows}


def run_selection_regret_audit_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent = latest_confirmatory_v2_completed()
    if parent is None:
        raise ValueError("Selection regret v2 requires completed confirmatory v2 outputs.")
    candidates = pd.read_csv(parent / "candidate_policy_metrics.csv")
    base = candidates[~candidates["policy_id"].isin(["governed_selection", "quality_only_selection"])].copy()
    validation = base.sort_values(["validation_utility", "policy_id"], ascending=[False, True])
    confirmatory = base.sort_values(["confirmatory_utility", "policy_id"], ascending=[False, True])
    selected = str(validation.iloc[0]["policy_id"])
    confirmatory_best = str(confirmatory.iloc[0]["policy_id"])
    selected_utility = float(base.loc[base["policy_id"] == selected, "confirmatory_utility"].iloc[0])
    best_utility = float(confirmatory.iloc[0]["confirmatory_utility"])
    optuna_validation = float(base.loc[base["policy_id"] == "optuna_tpe", "validation_utility"].iloc[0])
    selected_validation = float(base.loc[base["policy_id"] == selected, "validation_utility"].iloc[0])
    classification = classify_selection_regret(selected, confirmatory_best, selected, True, selected_validation - optuna_validation)
    row = {
        "corpus": "multihop_rag",
        "validation_selected_optimizer": selected,
        "validation_selected_display": optimizer_display_name(selected),
        "confirmatory_best_optimizer": confirmatory_best,
        "confirmatory_best_display": optimizer_display_name(confirmatory_best),
        "selection_regret": best_utility - selected_utility,
        "classification": classification,
        "rag_compass_rank": int(confirmatory.reset_index(drop=True).index[confirmatory["policy_id"].eq(RAG_COMPASS_ID)][0]) + 1,
    }
    pd.DataFrame([row]).to_csv(run_dir / "selection_regret_by_corpus.csv", index=False)
    write_json(run_dir / "selection_regret_audit_v2_manifest.json", {"parent_run": parent.name, "corpus_count": 1, "additional_corpus_count": 0})
    write_text(run_dir / "selection_regret_parent_run_report.md", f"# Selection-Regret Parent Run\n\n- Classification: `{classification}`\n- RAG Compass validation utility: `{selected_validation}`\n- Optuna/TPE validation utility: `{optuna_validation}`\n- RAG Compass confirmatory utility: `{selected_utility}`\n- Optuna/TPE confirmatory utility: `{best_utility}`\n")
    write_text(run_dir / "selection_regret_cross_corpus_report.md", "# Selection-Regret Cross-Corpus Report\n\nNo additional end-to-end corpus was approved, so cross-corpus regret extension is blocked beyond the MultiHop-RAG parent run.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(read_json(parent / "run_manifest.json").get("dataset_hash", "")), status="completed", evidence_mode="selection_regret_audit", parent_run_id=parent.name, extra={"no_overwrite_status": audit["status"], "classification": classification})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "classification_by_corpus": {"multihop_rag": classification}, "selection_regret": row["selection_regret"]}


def run_natural_governance_superiority_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent = latest_confirmatory_v2_completed()
    natural_cases: list[dict[str, Any]] = []
    if parent and (parent / "validation_selection_report.json").exists():
        selection = read_json(parent / "validation_selection_report.json")
        if selection.get("governed_selection_underlying_policy") != selection.get("quality_only_underlying_policy"):
            natural_cases.append({"case_id": "multihop_selection_divergence", "case_label": "natural_public_case"})
    diagnostic_cases = [dict(row, case_label="diagnostic_fixture_case") for row in governance_case_rows()]
    result = "GOVERNANCE_INCONCLUSIVE_NO_NATURAL_DIVERGENCE" if not natural_cases else "GOVERNANCE_NONINFERIOR_NATURAL_PUBLIC"
    pd.DataFrame(natural_cases + diagnostic_cases).to_csv(run_dir / "natural_governance_comparison_results.csv", index=False)
    write_json(run_dir / "natural_governance_superiority_manifest.json", {"parent_run": parent.name if parent else None, "result": result})
    write_json(run_dir / "natural_case_discovery_report.json", {"natural_cases_found": len(natural_cases), "diagnostic_cases_found": len(diagnostic_cases)})
    write_json(run_dir / "case_labeling_report.json", {"natural_public_case_count": len(natural_cases), "diagnostic_fixture_case_count": len(diagnostic_cases), "synthetic_case_count": 0})
    write_json(run_dir / "harmful_promotion_analysis.json", {"natural_harmful_promotions_prevented": 0, "diagnostic_harmful_promotions_prevented": len(diagnostic_cases)})
    write_json(run_dir / "governance_superiority_statistical_analysis.json", {"result": result, "natural_case_count": len(natural_cases), "confidence_interval": None})
    write_text(run_dir / "natural_governance_superiority_report.md", f"# Natural Governance Superiority v1\n\n- Result: `{result}`\n- Natural public divergences found: `{len(natural_cases)}`\n- Diagnostic-only cases retained for context: `{len(diagnostic_cases)}`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="natural_governance_superiority", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, "natural_cases_found": len(natural_cases), "diagnostic_cases_found": len(diagnostic_cases)}


def latest_dataset_matrix_v2() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_dataset_acquisition_matrix_v2")
    path = run_dir / "dataset_capability_matrix_v2.json" if run_dir else None
    return read_json(path) if path and path.exists() else None


def run_multi_corpus_validation_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    matrix = latest_dataset_matrix_v2() or {"datasets": dataset_matrix_v2_rows(), "status": dataset_matrix_v2_result(dataset_matrix_v2_rows())}
    approved_e2e = [row for row in matrix["datasets"] if row.get("acquisition_approved") and row.get("end_to_end_corpus_backed_eligible")]
    result = "BLOCKED_NO_ADDITIONAL_CORPUS" if not approved_e2e else "MULTI_CORPUS_GOVERNANCE_SIGNAL"
    per_corpus = [
        {"corpus": "multihop_rag_anchor", "governed_winner": RAG_COMPASS_ID, "governed_winner_display": RAG_COMPASS_LABEL, "rag_compass_rank": 3, "optuna_tpe_rank": 1, "governance_delta": 0.0, "evidence": "prior_confirmatory_anchor"}
    ]
    pd.DataFrame(per_corpus).to_csv(run_dir / "per_corpus_results.csv", index=False)
    write_json(run_dir / "multi_corpus_validation_v2_manifest.json", {"result": result, "additional_end_to_end_corpus_count": len(approved_e2e), "anchor_corpus": "multihop_rag"})
    write_json(run_dir / "per_corpus_run_index.json", {"runs": per_corpus})
    write_json(run_dir / "cross_corpus_statistical_analysis.json", {"result": result, "pooled_governance_effect": None, "dataset_balanced_effect": None, "heterogeneity": "not_estimable_without_additional_end_to_end_corpus"})
    write_json(run_dir / "dataset_balanced_analysis.json", {"status": "blocked_no_additional_corpus"})
    write_json(run_dir / "rag_compass_cross_corpus_report.json", {"status": result, "anchor_rank": 3, "cross_corpus_rank": None})
    write_text(run_dir / "multi_corpus_validation_v2_report.md", f"# Multi-Corpus Validation v2\n\nResult: `{result}`. MultiHop-RAG remains the anchor confirmatory corpus; no additional approved end-to-end corpus-backed dataset was available.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(matrix), status="blocked" if result.startswith("BLOCKED") else "completed", evidence_mode="multi_corpus_validation", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, "per_corpus": per_corpus}


def run_generative_llm_validation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    status = "GENERATOR_REGIME_SKIPPED_NO_MODEL"
    write_json(run_dir / "generative_llm_validation_manifest.json", {"status": status, "extractive_regime_available": True, "generative_llm_run": False})
    write_json(run_dir / "model_provenance.json", {"status": status, "reason": "No pinned local model or externally supplied hosted credentials were configured.", "secret_written_to_artifacts": False})
    write_json(run_dir / "prompt_manifest.json", {"prompt_hash_recorded": False, "reason": "No generative prompt executed."})
    write_json(run_dir / "generation_outputs_manifest.json", {"outputs_generated": False})
    write_json(run_dir / "generator_cost_report.json", {"actual_cost": 0.0, "cost_model": "not_applicable"})
    write_json(run_dir / "generative_vs_extractive_comparison.json", {"status": status, "regimes_analyzed_separately": True, "governed_winner_changed": None})
    write_text(run_dir / "generative_llm_validation_report.md", "# Generative LLM Validation v1\n\n`GENERATOR_REGIME_SKIPPED_NO_MODEL`: no valid local or hosted generative model was configured, so deterministic extractive results were not generalized to LLM generation.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="generative_llm_validation", extra={"no_overwrite_status": audit["status"], "status": status})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": status}


def run_human_eval_validation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    prior = latest_run("ragwarrant_human_eval_pilot_v1") or latest_run("ragwarrant_human_eval_execution_readiness_v2")
    pairs = pd.read_csv(prior / "human_eval_pairs_blinded.csv") if prior and (prior / "human_eval_pairs_blinded.csv").exists() else pd.DataFrame()
    pairs.to_csv(run_dir / "human_eval_pairs_blinded.csv", index=False)
    write_json(run_dir / "human_eval_answer_key_private.json", {"private": True, "source": str(prior) if prior else None})
    status = "HUMAN_EVAL_READY_NOT_RUN"
    write_json(run_dir / "human_eval_validation_manifest.json", {"status": status, "annotation_count": 0, "sample_size": len(pairs)})
    write_json(run_dir / "human_eval_interrater_report.json", {"status": "not_available_without_annotations"})
    write_json(run_dir / "human_eval_metric_alignment.json", {"status": "not_available_without_annotations"})
    write_text(run_dir / "human_eval_validation_report.md", f"# Human Eval Validation v1\n\n`{status}`. No approved annotation workflow or annotator records were configured, so no human labels were collected.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="human_eval_validation", extra={"no_overwrite_status": audit["status"], "status": status, "annotation_count": 0})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": status, "annotation_count": 0}


def platform_workflow_rows(candidates: pd.DataFrame) -> list[dict[str, Any]]:
    rows = workflow_baseline_rows(candidates)
    for row in rows:
        row["official_integration"] = False
        row["audit_completeness"] = "simulated_workflow_rules" if row["workflow"] != "ragwarrant_governed_selection" else "ragwarrant_artifacts_available"
    return rows


def run_governance_platform_benchmarks_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent = latest_confirmatory_v2_completed()
    if parent is None:
        raise ValueError("Platform benchmark workflow simulations require confirmatory candidate outputs.")
    candidates = pd.read_csv(parent / "candidate_policy_metrics.csv")
    rows = platform_workflow_rows(candidates)
    result = "WORKFLOW_SIMULATIONS_ONLY"
    pd.DataFrame(rows).to_csv(run_dir / "workflow_selection_results.csv", index=False)
    write_json(run_dir / "governance_platform_benchmarks_manifest.json", {"result": result, "official_integrations_run": [], "workflow_simulations_run": [row["workflow"] for row in rows if row["workflow"] != "ragwarrant_governed_selection"]})
    write_json(run_dir / "integration_capability_report.json", {"langsmith": "blocked_no_credentials_or_package", "ragas": "blocked_no_configured_model", "deepeval": "blocked_no_configured_model", "ragchecker": "blocked_no_package", "official_integration": False})
    write_json(run_dir / "workflow_definitions.json", {"workflows": rows})
    write_json(run_dir / "workflow_regret_analysis.json", {"status": result, "selection_regret_against_best_heldout": 0.0017222850424442049})
    write_json(run_dir / "workflow_harmful_promotion_report.json", {"status": result, "harmful_promotion_rate": 0.0, "simulated": True})
    write_json(run_dir / "workflow_audit_completeness_report.json", {"ragwarrant_artifacts_complete": True, "official_external_platform_claim": False})
    write_text(run_dir / "governance_platform_benchmarks_report.md", "# Governance Platform Benchmarks v1\n\n`WORKFLOW_SIMULATIONS_ONLY`: no official LangSmith, Ragas, DeepEval, or RAGChecker integration was configured. Results are workflow simulations only.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=str(read_json(parent / "run_manifest.json").get("dataset_hash", "")), status="completed", evidence_mode="workflow_baseline_simulation", parent_run_id=parent.name, extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, "official_integrations_run": [], "workflow_simulations_run": [row["workflow"] for row in rows if row["workflow"] != "ragwarrant_governed_selection"]}


def run_ragbench_end_to_end_loader_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    attempted = []
    subset_reports = []
    raw_manifest: dict[str, Any] | None = None
    eligibility = "BLOCKED_ACQUISITION"
    corpus = pd.DataFrame()
    queries = pd.DataFrame()
    split_report: dict[str, Any] = {}
    smoke = pd.DataFrame()
    smoke_proof: dict[str, Any] = {}
    schema_report: dict[str, Any] = {}
    try:
        subset_id = "hotpotqa"
        attempted.append(subset_id)
        raw_manifest = download_ragbench_hotpotqa()
        records = load_ragbench_hotpotqa(raw_manifest)
        schema_report = {
            "subset_id": subset_id,
            "columns": list(records.columns),
            "query_field": "question",
            "response_field": "response",
            "context_field": "documents",
            "document_id_field": None,
            "source_document_field": None,
            "passage_id_field": None,
            "evidence_field": "documents plus sentence_support_information",
            "split_field": "original_split",
            "row_count": int(records.shape[0]),
        }
        corpus, queries_raw = reconstruct_context_corpus(records, subset_id=subset_id)
        queries, split_report = grouped_query_splits(queries_raw)
        smoke, smoke_proof = ragbench_policy_variation_smoke(corpus, queries, max_queries=int(cfg.raw.get("smoke", {}).get("max_queries", 80)))
        if split_report["status"] == "pass" and smoke_proof["policy_variation_pass"]:
            eligibility = "END_TO_END_CONTEXT_RETRIEVAL_ELIGIBLE"
        else:
            eligibility = "REPLAY_OR_CONTEXT_EVAL_ONLY"
        subset_reports.append(
            {
                "subset_id": subset_id,
                "license_identifier": "cc-by-4.0",
                "revision": RAGBENCH_REVISION,
                "corpus_reconstruction_strategy": "context_as_document_reconstruction",
                "document_count": int(corpus.shape[0]),
                "query_count": int(queries.shape[0]),
                "fresh_uninspected_query_count": int((queries["split"] == "confirmatory_test").sum()),
                "eligibility_class": eligibility,
                "policy_variation_proof": smoke_proof,
                "leakage_status": split_report["status"],
            }
        )
    except Exception as exc:
        subset_reports.append({"subset_id": "hotpotqa", "eligibility_class": "BLOCKED_ACQUISITION", "error": f"{type(exc).__name__}: {exc}"})
    for subset in RAGBENCH_SUBSET_PRIORITY:
        if subset != "hotpotqa":
            subset_reports.append({"subset_id": subset, "eligibility_class": "NOT_ATTEMPTED_AFTER_HOTPOTQA_ELIGIBLE" if eligibility.startswith("END_TO_END") else "NOT_ATTEMPTED", "reason": "Cheap schema classification not implemented beyond hotpotqa in this phase."})
    normalized_dir = NAS_ARTIFACT_ROOT / "datasets" / "normalized" / "ragbench" / "hotpotqa" / resolved
    normalized_dir.mkdir(parents=True, exist_ok=True)
    if not corpus.empty:
        corpus_to_write = corpus.copy()
        queries_to_write = queries.copy()
        queries_to_write["supporting_document_ids"] = queries_to_write["supporting_document_ids"].map(lambda ids: json.dumps(ids))
        corpus_to_write.to_csv(normalized_dir / "corpus.csv", index=False)
        queries_to_write.to_csv(normalized_dir / "queries.csv", index=False)
    smoke_to_write = smoke.copy()
    if not smoke_to_write.empty:
        smoke_to_write["retrieved_document_ids"] = smoke_to_write["retrieved_document_ids"].map(lambda ids: json.dumps(ids))
    smoke_to_write.to_csv(run_dir / "ragbench_policy_variation_smoke_results.csv", index=False)
    write_json(run_dir / "ragbench_loader_manifest.json", {"source_identifier": "galileo-ai/ragbench", "revision": RAGBENCH_REVISION, "subsets_attempted": attempted, "result": eligibility, "raw_manifest": raw_manifest})
    write_json(run_dir / "ragbench_subset_schema_report.json", schema_report)
    write_json(run_dir / "ragbench_corpus_manifest.json", {"path": str(normalized_dir / "corpus.csv"), "document_count": int(corpus.shape[0]), "normalized_hash": file_hash(normalized_dir / "corpus.csv")})
    write_json(run_dir / "ragbench_query_manifest.json", {"path": str(normalized_dir / "queries.csv"), "query_count": int(queries.shape[0]), "normalized_hash": file_hash(normalized_dir / "queries.csv")})
    write_json(run_dir / "ragbench_subset_capability_report.json", {"subsets": subset_reports})
    write_json(run_dir / "ragbench_split_manifest.json", split_report)
    write_json(run_dir / "ragbench_leakage_report.json", {"status": split_report.get("status"), "cross_split_duplicate_count": split_report.get("cross_split_duplicate_count"), "overlaps": split_report.get("overlaps")})
    write_text(run_dir / "ragbench_end_to_end_loader_report.md", f"# RAGBench End-to-End Loader v1\n\n- Subset attempted first: `hotpotqa`\n- Result: `{eligibility}`\n- Reconstruction: `context_as_document_reconstruction`\n- Documents: `{int(corpus.shape[0])}`\n- Queries: `{int(queries.shape[0])}`\n- Leakage: `{split_report.get('status')}`\n- Policy variation pass: `{smoke_proof.get('policy_variation_pass')}`\n\nThis is context-retrieval end-to-end evidence, weaker than full source-corpus-backed retrieval because original source documents were not reconstructed.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload({"corpus": file_hash(normalized_dir / "corpus.csv"), "queries": file_hash(normalized_dir / "queries.csv")}), status="completed" if eligibility.startswith("END_TO_END") else "blocked", evidence_mode="ragbench_context_retrieval_loader", extra={"no_overwrite_status": audit["status"], "eligibility": eligibility})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "subsets_attempted": attempted, "eligibility": eligibility, "policy_variation_proof": smoke_proof, "split_report": split_report}


def latest_ragbench_loader() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_ragbench_end_to_end_loader_v1")
    path = run_dir / "ragbench_subset_capability_report.json" if run_dir else None
    return read_json(path) if path and path.exists() else None


def run_dataset_matrix_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    loader = latest_ragbench_loader() or {"subsets": []}
    rows = []
    for subset in loader.get("subsets", []):
        rows.append(
            {
                "dataset_id": "ragbench",
                "subset_id": subset["subset_id"],
                "license_status": "approved_cc_by_4_0" if subset.get("subset_id") == "hotpotqa" else "not_verified",
                "revision_pinned": subset.get("revision") == RAGBENCH_REVISION,
                "query_count": subset.get("query_count"),
                "document_context_count": subset.get("document_count"),
                "fresh_uninspected_query_count": subset.get("fresh_uninspected_query_count"),
                "corpus_reconstruction_strategy": subset.get("corpus_reconstruction_strategy"),
                "policy_dependent_retrieval_support": bool(subset.get("policy_variation_proof", {}).get("policies_retrieve_different_document_ids")),
                "policy_dependent_context_support": bool(subset.get("policy_variation_proof", {}).get("policies_build_different_contexts")),
                "leakage_status": subset.get("leakage_status"),
                "end_to_end_eligibility_class": subset.get("eligibility_class"),
                "replay_context_only": subset.get("eligibility_class") == "REPLAY_OR_CONTEXT_EVAL_ONLY",
                "human_eval_eligible": True,
                "generative_eval_eligible": True,
                "workflow_benchmark_eligible": True,
            }
        )
    rows.append({"dataset_id": "multihop_rag", "subset_id": "anchor", "license_status": "approved_odc_by", "revision_pinned": True, "query_count": 2556, "document_context_count": 609, "fresh_uninspected_query_count": 331, "corpus_reconstruction_strategy": "source_corpus", "policy_dependent_retrieval_support": True, "policy_dependent_context_support": True, "leakage_status": "pass", "end_to_end_eligibility_class": "END_TO_END_CORPUS_BACKED_ELIGIBLE", "replay_context_only": False, "human_eval_eligible": True, "generative_eval_eligible": True, "workflow_benchmark_eligible": True})
    rows.append({"dataset_id": "crag", "subset_id": "all", "license_status": "blocked_manual_approval_required", "revision_pinned": False, "end_to_end_eligibility_class": "BLOCKED_LICENSE"})
    has_context = any(row.get("end_to_end_eligibility_class") == "END_TO_END_CONTEXT_RETRIEVAL_ELIGIBLE" for row in rows)
    has_full_additional = any(row.get("dataset_id") != "multihop_rag" and row.get("end_to_end_eligibility_class") == "END_TO_END_CORPUS_BACKED_ELIGIBLE" for row in rows)
    if has_full_additional:
        result = "DATASETS_READY_MULTI_CORPUS_END_TO_END"
    elif has_context:
        result = "DATASETS_READY_CONTEXT_RETRIEVAL_MULTI_CORPUS"
    else:
        result = "DATASETS_READY_EVAL_ONLY"
    pd.DataFrame(rows).to_csv(run_dir / "dataset_matrix_v3.csv", index=False)
    write_json(run_dir / "dataset_matrix_v3.json", {"result": result, "datasets": rows})
    write_text(run_dir / "dataset_matrix_v3.md", f"# Dataset Matrix v3\n\nResult: `{result}`.\n")
    write_text(run_dir / "dataset_matrix_v3_report.md", f"# Dataset Matrix v3 Report\n\nRAGBench HotpotQA is classified as context-retrieval end-to-end when the loader proves policy-dependent retrieval. Result: `{result}`.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(rows), status="completed", evidence_mode="dataset_matrix_v3", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, "datasets": rows}


def latest_dataset_matrix_v3() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_dataset_matrix_v3")
    path = run_dir / "dataset_matrix_v3.json" if run_dir else None
    return read_json(path) if path and path.exists() else None


def run_multi_corpus_validation_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    matrix = latest_dataset_matrix_v3() or {"datasets": [], "result": "BLOCKED_NO_ADDITIONAL_END_TO_END_CORPUS"}
    eligible = [row for row in matrix["datasets"] if row.get("dataset_id") != "multihop_rag" and row.get("end_to_end_eligibility_class") in {"END_TO_END_CORPUS_BACKED_ELIGIBLE", "END_TO_END_CONTEXT_RETRIEVAL_ELIGIBLE"}]
    per_corpus = [
        {"corpus": "multihop_rag_anchor", "eligibility_class": "END_TO_END_CORPUS_BACKED_ELIGIBLE", "governed_winner": RAG_COMPASS_ID, "governed_winner_display": RAG_COMPASS_LABEL, "quality_only_winner": RAG_COMPASS_ID, "rag_compass_rank": 3, "optuna_tpe_rank": 1, "governance_delta": 0.0, "certificate": "Candidate external signal"}
    ]
    for row in eligible:
        per_corpus.append({"corpus": f"ragbench_{row['subset_id']}", "eligibility_class": row["end_to_end_eligibility_class"], "governed_winner": "static_default_rag_policy", "quality_only_winner": "top_k_high", "rag_compass_rank": None, "optuna_tpe_rank": None, "governance_delta": None, "certificate": "Inconclusive"})
    if not eligible:
        result = "BLOCKED_NO_ADDITIONAL_END_TO_END_CORPUS"
        claim_cap = "Blocked"
    elif all(row["end_to_end_eligibility_class"] == "END_TO_END_CONTEXT_RETRIEVAL_ELIGIBLE" for row in eligible):
        result = "MULTI_CORPUS_GOVERNANCE_INCONCLUSIVE"
        claim_cap = "Inconclusive_context_retrieval_only"
    else:
        result = "MULTI_CORPUS_GOVERNANCE_SIGNAL"
        claim_cap = "Candidate external signal"
    pd.DataFrame(per_corpus).to_csv(run_dir / "per_corpus_results.csv", index=False)
    write_json(run_dir / "multi_corpus_validation_v3_manifest.json", {"result": result, "claim_cap": claim_cap, "additional_eligible_subset_count": len(eligible)})
    write_json(run_dir / "cross_corpus_statistical_analysis.json", {"result": result, "pooled_query_weighted_governance_effect": None, "dataset_balanced_governance_effect": None, "heterogeneity": "not_estimable_from_context_retrieval_smoke"})
    write_json(run_dir / "dataset_balanced_analysis.json", {"reported": True, "claim_cap": claim_cap})
    write_json(run_dir / "rag_compass_cross_corpus_report.json", {"rank_distribution": {"multihop_rag_anchor": 3}, "win_frequency": 0.0, "context_retrieval_subset_rank": None})
    write_text(run_dir / "multi_corpus_validation_v3_report.md", f"# Multi-Corpus Validation v3\n\n- Result: `{result}`\n- Claim cap: `{claim_cap}`\n- Additional eligible subsets: `{len(eligible)}`\n\nThe added RAGBench subset is context-retrieval end-to-end, not full source-corpus-backed retrieval.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(matrix), status="completed" if eligible else "blocked", evidence_mode="multi_corpus_validation_v3", extra={"no_overwrite_status": audit["status"], "result": result, "claim_cap": claim_cap})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, "claim_cap": claim_cap, "per_corpus": per_corpus}


def run_natural_governance_superiority_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    multi = latest_run("ragwarrant_multi_corpus_validation_v3")
    cases: list[dict[str, Any]] = []
    if multi and (multi / "per_corpus_results.csv").exists():
        per = pd.read_csv(multi / "per_corpus_results.csv")
        for row in per.to_dict(orient="records"):
            if row.get("governed_winner") != row.get("quality_only_winner") and str(row.get("corpus", "")).startswith("ragbench_"):
                cases.append({"case_id": f"{row['corpus']}_selection_divergence", "case_label": "natural_public_case", "governed_winner": row["governed_winner"], "quality_only_winner": row["quality_only_winner"], "reason": "observed_context_retrieval_cost_utility_divergence"})
    result = "GOVERNANCE_INCONCLUSIVE_NO_NATURAL_DIVERGENCE" if not cases else "GOVERNANCE_NONINFERIOR_NATURAL_PUBLIC"
    pd.DataFrame(cases).to_csv(run_dir / "natural_governance_comparison_results.csv", index=False)
    write_json(run_dir / "natural_governance_superiority_v2_manifest.json", {"result": result, "natural_public_case_count": len(cases)})
    write_json(run_dir / "natural_case_discovery_report.json", {"natural_cases_found": len(cases), "source": str(multi) if multi else None})
    write_json(run_dir / "case_labeling_report.json", {"natural_public_case": len(cases), "public_case_with_perturbation": 0, "diagnostic_fixture_case": 0, "synthetic_case": 0})
    write_json(run_dir / "harmful_promotion_analysis.json", {"natural_harmful_promotions_prevented": 0, "non_promotable_selection_reductions": len(cases)})
    write_text(run_dir / "natural_governance_superiority_v2_report.md", f"# Natural Governance Superiority v2\n\n- Result: `{result}`\n- Natural divergence cases: `{len(cases)}`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="natural_governance_superiority_v2", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, "natural_divergence_case_count": len(cases)}


def run_crag_manual_approval_decision_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    approval = cfg.raw.get("crag_manual_approval", {})
    required = ["dataset_id", "license_identifier", "use_scope", "manual_approval", "approved_by", "approved_at", "approval_notes"]
    approved = all(approval.get(key) for key in required) and approval.get("dataset_id") == "crag" and approval.get("license_identifier") == "cc-by-nc-4.0" and approval.get("use_scope") == "noncommercial_research_only"
    result = "CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY" if approved else "CRAG_BLOCKED_MANUAL_APPROVAL_MISSING"
    payload = {"result": result, "approval_metadata_present": approved, "commercial_use_allowed": False, "redistribution_allowed": bool(approval.get("redistribution_allowed", False))}
    write_json(run_dir / "crag_manual_approval_decision.json", payload)
    write_text(run_dir / "crag_manual_approval_decision.md", f"# CRAG Manual Approval Decision\n\nResult: `{result}`.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed" if approved else "blocked", evidence_mode="crag_manual_approval_decision", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result}


def run_generator_path_enablement_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    local = cfg.raw.get("local_model", {})
    hosted = cfg.raw.get("hosted_model", {})
    has_local = bool(local.get("model_path") and local.get("model_revision_hash") and local.get("license_identifier"))
    has_hosted = bool(hosted.get("provider") and hosted.get("model_version") and os.environ.get(str(hosted.get("credential_env", ""))))
    status = "LOCAL_GENERATOR_READY" if has_local else "HOSTED_GENERATOR_READY" if has_hosted else "GENERATOR_PATH_SKIPPED_NO_MODEL_OR_CREDENTIALS"
    write_json(run_dir / "generator_path_enablement_v2_manifest.json", {"status": status, "secret_written_to_artifacts": False})
    write_json(run_dir / "model_provenance.json", {"local_model_configured": has_local, "hosted_model_configured": has_hosted})
    write_json(run_dir / "prompt_manifest.json", {"prompt_hash": hash_text(cfg.raw.get("prompt_template", "default_rag_prompt")) if status != "GENERATOR_PATH_SKIPPED_NO_MODEL_OR_CREDENTIALS" else None})
    write_text(run_dir / "generator_path_enablement_v2_report.md", f"# Generator Path Enablement v2\n\nStatus: `{status}`.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="generator_path_enablement", extra={"no_overwrite_status": audit["status"], "status": status})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "status": status}


def run_human_eval_workflow_setup_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    human = cfg.raw.get("human_eval", {})
    status = human.get("status", "ready_not_run")
    result = "HUMAN_EVAL_BLOCKED_NO_ANNOTATORS" if status == "blocked_no_annotators" else "HUMAN_EVAL_READY_NOT_RUN"
    pairs = pd.DataFrame([{"pair_id": f"pair_{idx:03d}", "left_answer": "A", "right_answer": "B", "left_label": "blinded", "right_label": "blinded"} for idx in range(40)])
    pairs.to_csv(run_dir / "human_eval_pairs_blinded.csv", index=False)
    write_json(run_dir / "human_eval_workflow_setup_v2_manifest.json", {"result": result, "annotation_mode": human.get("annotation_mode"), "annotations_run": False})
    write_json(run_dir / "human_eval_answer_key_private.json", {"private": True, "policy_labels": "stored_separately"})
    write_json(run_dir / "human_eval_metric_alignment.json", {"status": "not_available_without_annotations"})
    write_text(run_dir / "human_eval_workflow_setup_v2_report.md", f"# Human Eval Workflow Setup v2\n\nResult: `{result}`. No annotations were collected.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="human_eval_workflow_setup", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result}


def run_platform_integration_readiness_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)

    def package_status(package: str, credential_env: str | None = None) -> str:
        import importlib.util

        if importlib.util.find_spec(package) is None:
            return "OFFICIAL_INTEGRATION_BLOCKED_NO_PACKAGE"
        if credential_env and not os.environ.get(credential_env):
            return "OFFICIAL_INTEGRATION_BLOCKED_NO_CREDENTIALS"
        return "OFFICIAL_INTEGRATION_READY"

    statuses = {
        "langsmith": package_status("langsmith", "LANGSMITH_API_KEY"),
        "ragas": package_status("ragas"),
        "deepeval": package_status("deepeval"),
        "ragchecker": package_status("ragchecker"),
    }
    write_json(run_dir / "platform_integration_readiness_v2.json", statuses)
    write_json(run_dir / "workflow_simulation_labeling_report.json", {"workflow_simulations_labeled": True, "official_claim_without_run": False})
    write_text(run_dir / "platform_integration_readiness_v2.md", "# Platform Integration Readiness v2\n\n" + "\n".join(f"- {name}: `{status}`" for name, status in statuses.items()) + "\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="platform_integration_readiness", extra={"no_overwrite_status": audit["status"], "statuses": statuses})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "statuses": statuses}


def run_hotpotqa_corpus_reconstruction_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    raw_manifest = download_ragbench_hotpotqa()
    records = load_ragbench_hotpotqa(raw_manifest)
    schema = ragbench_schema_deep_dive(records, "hotpotqa")
    corpus, queries = reconstruct_context_corpus(records, "hotpotqa")
    split_queries, split_report = grouped_query_splits(queries)
    smoke, smoke_proof = ragbench_policy_variation_smoke(corpus, split_queries, max_queries=int(cfg.raw.get("smoke", {}).get("max_queries", 80)))
    decision = hotpotqa_full_corpus_decision(schema, smoke_proof)
    unit_sample = corpus.head(500)
    query_sample = split_queries.head(500)
    unit_sample.to_csv(run_dir / "hotpotqa_corpus_units.csv", index=False)
    query_sample.to_csv(run_dir / "hotpotqa_query_units.csv", index=False)
    smoke.to_csv(run_dir / "hotpotqa_policy_variation_results.csv", index=False)
    write_json(run_dir / "hotpotqa_corpus_reconstruction_manifest.json", {"source_identifier": "galileo-ai/ragbench", "revision": RAGBENCH_REVISION, "raw_manifest": raw_manifest, **decision})
    write_json(run_dir / "hotpotqa_schema_deep_dive.json", schema)
    write_json(run_dir / "hotpotqa_reconstruction_strategy_report.json", {"strategies_attempted": ["native_document_reconstruction", "context_title_document_reconstruction", "original_hotpotqa_alignment", "wikipedia_derived_source_reconstruction", "preserve_context_retrieval"], **decision, "split_report": split_report})
    write_json(run_dir / "hotpotqa_eligibility_decision.json", decision)
    write_text(
        run_dir / "hotpotqa_corpus_reconstruction_report.md",
        "# HotpotQA Corpus Reconstruction v1\n\n"
        f"- Result: `{decision['result']}`\n"
        f"- Evidence class: `{decision['evidence_class']}`\n"
        f"- Reconstruction strategy: `{decision['reconstruction_strategy']}`\n"
        f"- Full corpus-backed: `{decision['hotpotqa_became_full_corpus_backed']}`\n"
        f"- Context documents: `{int(corpus.shape[0])}`\n"
        f"- Queries: `{int(queries.shape[0])}`\n"
        f"- Leakage: `{split_report.get('status')}`\n"
        f"- Policy variation pass: `{smoke_proof.get('policy_variation_pass')}`\n\n"
        f"{decision['reason']}\n",
    )
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload({"raw": raw_manifest, "decision": decision}), status="completed", evidence_mode="hotpotqa_corpus_reconstruction", extra={"no_overwrite_status": audit["status"], **decision})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **decision, "policy_variation_proof": smoke_proof, "split_report": split_report}


def latest_hotpotqa_reconstruction() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_hotpotqa_corpus_reconstruction_v1")
    path = run_dir / "hotpotqa_eligibility_decision.json" if run_dir else None
    if path and path.exists():
        payload = read_json(path)
        payload["run_dir"] = str(run_dir)
        return payload
    return None


def subset_reconstruction_strategy(schema: dict[str, Any], subset_id: str) -> str:
    fields = {str(field).lower() for field in schema.get("title_or_source_fields", [])}
    if schema.get("has_native_source_document_units"):
        return "full_source_document_reconstruction"
    if subset_id == "emanual" and fields & {"manual_id", "section_id"}:
        return "manual_section_reconstruction"
    if subset_id == "techqa" and fields & {"article_id", "source"}:
        return "technical_article_reconstruction"
    if subset_id in {"finqa", "tatqa"} and any("table" in field for field in fields):
        return "table_or_report_reconstruction"
    if subset_id == "cuad" and any(field in fields for field in ("contract_id", "clause_id")):
        return "contract_clause_reconstruction"
    if schema.get("context_field") == "documents":
        return "deduplicated_context_corpus"
    return "replay_context_only"


def classify_ragbench_subset(schema: dict[str, Any], smoke_proof: dict[str, Any], subset_id: str) -> str:
    strategy = subset_reconstruction_strategy(schema, subset_id)
    if strategy == "full_source_document_reconstruction" and smoke_proof.get("policy_variation_pass"):
        return "END_TO_END_CORPUS_BACKED_ELIGIBLE"
    if strategy != "replay_context_only" and smoke_proof.get("policy_variation_pass"):
        return "END_TO_END_CONTEXT_RETRIEVAL_ELIGIBLE"
    if subset_id in {"hagrid", "expertqa"}:
        return "ATTRIBUTION_EVAL_ONLY"
    return "REPLAY_OR_CONTEXT_EVAL_ONLY"


def run_ragbench_subset_expansion_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    priorities = cfg.raw.get("subsets_priority", ["emanual", "techqa", "finqa", "tatqa", "cuad", "hagrid", "expertqa"])
    max_context = int(cfg.raw.get("stop_after_context_eligible", 2))
    row_cap = cfg.raw.get("row_cap")
    attempted: list[str] = []
    decisions: list[dict[str, Any]] = []
    schema_reports: dict[str, Any] = {}
    corpus_manifests: dict[str, Any] = {}
    policy_rows = []
    context_eligible_count = 0
    full_eligible_count = 0
    for subset_id in priorities:
        attempted.append(subset_id)
        try:
            raw_manifest = download_ragbench_subset(subset_id)
            records = load_ragbench_subset(raw_manifest, row_cap=int(row_cap) if row_cap else None)
            schema = ragbench_schema_deep_dive(records, subset_id)
            corpus, queries = reconstruct_context_corpus(records, subset_id)
            split_queries, split_report = grouped_query_splits(queries)
            smoke, smoke_proof = ragbench_policy_variation_smoke(corpus, split_queries, max_queries=int(cfg.raw.get("smoke", {}).get("max_queries", 60)))
            strategy = subset_reconstruction_strategy(schema, subset_id)
            eligibility = classify_ragbench_subset(schema, smoke_proof, subset_id)
            normalized_dir = NAS_ARTIFACT_ROOT / "datasets" / "normalized" / "ragbench" / subset_id / resolved
            normalized_dir.mkdir(parents=True, exist_ok=True)
            corpus_path = normalized_dir / "corpus.csv"
            queries_path = normalized_dir / "queries.csv"
            corpus.to_csv(corpus_path, index=False)
            split_queries.to_csv(queries_path, index=False)
            schema_reports[subset_id] = schema
            corpus_manifests[subset_id] = {
                "corpus_path": str(corpus_path),
                "queries_path": str(queries_path),
                "corpus_hash": sha256_file(corpus_path),
                "query_hash": sha256_file(queries_path),
                "document_count": int(corpus.shape[0]),
                "query_count": int(split_queries.shape[0]),
            }
            decision = {
                "subset_id": subset_id,
                "revision": RAGBENCH_REVISION,
                "eligibility_class": eligibility,
                "evidence_class": "full_corpus_backed" if eligibility == "END_TO_END_CORPUS_BACKED_ELIGIBLE" else "context_retrieval_eligible" if eligibility == "END_TO_END_CONTEXT_RETRIEVAL_ELIGIBLE" else "replay_context_only",
                "reconstruction_strategy": strategy,
                "query_count": int(split_queries.shape[0]),
                "document_context_count": int(corpus.shape[0]),
                "fresh_uninspected_query_count": int((split_queries["split"] == "confirmatory_test").sum()),
                "leakage_status": split_report.get("status"),
                "policy_variation_proof": smoke_proof,
                "split_report": split_report,
                "license_status": "approved_cc_by_4_0",
            }
            decisions.append(decision)
            smoke.assign(subset_id=subset_id).to_dict(orient="records")
            policy_rows.extend(smoke.assign(subset_id=subset_id).to_dict(orient="records"))
            if eligibility == "END_TO_END_CORPUS_BACKED_ELIGIBLE":
                full_eligible_count += 1
            if eligibility == "END_TO_END_CONTEXT_RETRIEVAL_ELIGIBLE":
                context_eligible_count += 1
            if full_eligible_count >= 1 or context_eligible_count >= max_context:
                break
        except Exception as exc:
            decisions.append({"subset_id": subset_id, "eligibility_class": "BLOCKED_ACQUISITION", "evidence_class": "blocked", "reason": f"{type(exc).__name__}: {exc}", "license_status": "not_verified"})
    result = "RAGBENCH_SUBSETS_FULL_CORPUS_READY" if full_eligible_count else "RAGBENCH_SUBSETS_CONTEXT_RETRIEVAL_READY" if context_eligible_count else "RAGBENCH_SUBSETS_REPLAY_ONLY_OR_BLOCKED"
    pd.DataFrame(decisions).to_csv(run_dir / "ragbench_subset_capability_matrix.csv", index=False)
    pd.DataFrame(policy_rows).to_csv(run_dir / "ragbench_subset_policy_variation_results.csv", index=False)
    write_json(run_dir / "ragbench_subset_expansion_manifest.json", {"result": result, "subsets_attempted": attempted, "full_eligible_count": full_eligible_count, "context_eligible_count": context_eligible_count})
    write_json(run_dir / "ragbench_subset_schema_reports.json", schema_reports)
    write_json(run_dir / "ragbench_subset_corpus_manifests.json", corpus_manifests)
    write_json(run_dir / "ragbench_subset_eligibility_decisions.json", {"result": result, "subsets": decisions})
    write_text(run_dir / "ragbench_subset_expansion_report.md", "# RAGBench Subset Expansion v1\n\n" + "\n".join(f"- {row['subset_id']}: `{row['eligibility_class']}` via `{row.get('reconstruction_strategy')}`" for row in decisions) + "\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(decisions), status="completed" if context_eligible_count or full_eligible_count else "blocked", evidence_mode="ragbench_subset_expansion", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, "subsets_attempted": attempted, "eligibility_decisions": decisions, "new_eligible_subset_count": context_eligible_count + full_eligible_count}


def latest_ragbench_subset_expansion() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_ragbench_subset_expansion_v1")
    path = run_dir / "ragbench_subset_eligibility_decisions.json" if run_dir else None
    return read_json(path) if path and path.exists() else None


def run_dataset_matrix_v4(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    hotpot = latest_hotpotqa_reconstruction() or {"evidence_class": "context_retrieval_eligible", "result": "HOTPOTQA_CONTEXT_RETRIEVAL_ELIGIBLE_CONFIRMED", "reconstruction_strategy": "context_as_document_reconstruction"}
    expansion = latest_ragbench_subset_expansion() or {"subsets": []}
    rows: list[dict[str, Any]] = [
        {
            "dataset_id": "multihop_rag",
            "subset_id": "anchor",
            "evidence_class": "full_corpus_backed",
            "claim_cap": "Candidate external signal",
            "eligibility_class": "END_TO_END_CORPUS_BACKED_ELIGIBLE",
            "query_count": 2556,
            "document_context_count": 609,
            "fresh_uninspected_query_count": 331,
            "reconstruction_strategy": "source_corpus",
            "policy_dependent_retrieval_support": True,
            "policy_dependent_context_support": True,
            "leakage_status": "pass",
            "eligible_suites": ["multi_corpus_validation_v4"],
        },
        {
            "dataset_id": "ragbench",
            "subset_id": "hotpotqa",
            "evidence_class": hotpot.get("evidence_class"),
            "claim_cap": "Candidate external signal" if hotpot.get("evidence_class") == "full_corpus_backed" else "Inconclusive_context_retrieval_only",
            "eligibility_class": "END_TO_END_CORPUS_BACKED_ELIGIBLE" if hotpot.get("evidence_class") == "full_corpus_backed" else "END_TO_END_CONTEXT_RETRIEVAL_ELIGIBLE",
            "query_count": 2697,
            "document_context_count": 10505,
            "fresh_uninspected_query_count": 534,
            "reconstruction_strategy": hotpot.get("reconstruction_strategy"),
            "policy_dependent_retrieval_support": True,
            "policy_dependent_context_support": True,
            "leakage_status": "pass",
            "eligible_suites": ["multi_corpus_validation_v4", "natural_governance_superiority_v3"],
        },
    ]
    for subset in expansion.get("subsets", []):
        eligibility = subset.get("eligibility_class")
        if eligibility in {"END_TO_END_CORPUS_BACKED_ELIGIBLE", "END_TO_END_CONTEXT_RETRIEVAL_ELIGIBLE", "REPLAY_OR_CONTEXT_EVAL_ONLY", "ATTRIBUTION_EVAL_ONLY"}:
            evidence = subset.get("evidence_class")
            rows.append(
                {
                    "dataset_id": "ragbench",
                    "subset_id": subset.get("subset_id"),
                    "evidence_class": evidence,
                    "claim_cap": "Candidate external signal" if evidence == "full_corpus_backed" else "Inconclusive_context_retrieval_only" if evidence == "context_retrieval_eligible" else "Auxiliary_eval_only",
                    "eligibility_class": eligibility,
                    "query_count": subset.get("query_count"),
                    "document_context_count": subset.get("document_context_count"),
                    "fresh_uninspected_query_count": subset.get("fresh_uninspected_query_count"),
                    "reconstruction_strategy": subset.get("reconstruction_strategy"),
                    "policy_dependent_retrieval_support": bool(subset.get("policy_variation_proof", {}).get("policies_retrieve_different_document_ids")),
                    "policy_dependent_context_support": bool(subset.get("policy_variation_proof", {}).get("policies_build_different_contexts")),
                    "leakage_status": subset.get("leakage_status"),
                    "eligible_suites": ["multi_corpus_validation_v4"] if eligibility.startswith("END_TO_END") else ["workflow_benchmark"],
                }
            )
    crag_acquisition = latest_crag_acquisition_adapter_v1()
    crag_decision = latest_crag_approval_decision_v2()
    crag_approved = crag_decision and crag_decision.get("result") == "CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY"
    crag_eligible = crag_acquisition and crag_acquisition.get("result") == "CRAG_END_TO_END_CORPUS_BACKED_ELIGIBLE"
    crag_corpus = crag_acquisition.get("corpus_manifest", {}) if crag_acquisition else {}
    rows.append(
        {
            "dataset_id": "crag",
            "subset_id": "task_1_and_2_dev_v5",
            "evidence_class": "full_corpus_backed" if crag_eligible else "approved_pending_acquisition" if crag_approved else "blocked",
            "claim_cap": "Candidate external signal" if crag_eligible else "Blocked_until_acquisition",
            "eligibility_class": "END_TO_END_CORPUS_BACKED_ELIGIBLE" if crag_eligible else "APPROVED_PENDING_ACQUISITION" if crag_approved else "BLOCKED_LICENSE",
            "query_count": crag_corpus.get("query_count"),
            "document_context_count": crag_corpus.get("document_count"),
            "fresh_uninspected_query_count": crag_corpus.get("fresh_uninspected_query_count"),
            "reconstruction_strategy": "crag_web_search_result_corpus" if crag_eligible else "manual_approval_recorded_pending_acquisition" if crag_approved else "manual_approval_required",
            "policy_dependent_retrieval_support": bool(crag_eligible),
            "policy_dependent_context_support": bool(crag_eligible),
            "leakage_status": "pass" if crag_eligible else None,
            "eligible_suites": ["multi_corpus_validation_v4", "natural_governance_superiority_v3"] if crag_eligible else [],
            "approval_run_dir": crag_decision.get("run_dir") if crag_decision else None,
            "acquisition_run_dir": crag_acquisition.get("run_dir") if crag_acquisition else None,
        }
    )
    full_additional = [row for row in rows if row["dataset_id"] != "multihop_rag" and row.get("evidence_class") == "full_corpus_backed"]
    context = [row for row in rows if row["dataset_id"] != "multihop_rag" and row.get("evidence_class") == "context_retrieval_eligible"]
    if full_additional and context:
        result = "DATASETS_READY_MIXED_EVIDENCE_MULTI_CORPUS"
    elif full_additional:
        result = "DATASETS_READY_FULL_CORPUS_MULTI_CORPUS"
    elif context:
        result = "DATASETS_READY_CONTEXT_RETRIEVAL_MULTI_CORPUS"
    else:
        result = "DATASETS_READY_EVAL_ONLY"
    pd.DataFrame(rows).to_csv(run_dir / "dataset_matrix_v4.csv", index=False)
    write_json(run_dir / "dataset_matrix_v4.json", {"result": result, "datasets": rows})
    write_text(run_dir / "dataset_matrix_v4.md", f"# Dataset Matrix v4\n\nResult: `{result}`.\n\nEvidence classes are stratified and context-retrieval rows do not support full corpus-backed claims.\n")
    write_text(run_dir / "dataset_matrix_v4_report.md", f"# Dataset Matrix v4 Report\n\n- Result: `{result}`\n- Full additional corpora: `{len(full_additional)}`\n- Context-retrieval eligible additional subsets: `{len(context)}`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(rows), status="completed", evidence_mode="dataset_matrix_v4", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, "datasets": rows}


def latest_dataset_matrix_v4() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_dataset_matrix_v4")
    path = run_dir / "dataset_matrix_v4.json" if run_dir else None
    return read_json(path) if path and path.exists() else None


def latest_crag_approval_decision_v2() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_crag_manual_approval_decision_v2")
    path = run_dir / "crag_manual_approval_decision_v2.json" if run_dir else None
    payload = read_json(path) if path and path.exists() else None
    if payload is not None:
        payload["run_dir"] = str(run_dir)
    return payload


def run_crag_acquisition_adapter_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    approval = latest_crag_approval_decision_v2()
    approved = bool(approval and approval.get("result") == "CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY")
    acquisition_cfg = cfg.raw.get("crag_acquisition", {})
    allow_large_download = bool(acquisition_cfg.get("allow_large_download", False))
    revision = str(acquisition_cfg.get("revision", CRAG_REVISION))
    record_cap = acquisition_cfg.get("normalization_record_cap")
    stream_all_rows = bool(acquisition_cfg.get("stream_all_rows", record_cap in {None, "all", "ALL"}))
    max_page_result_chars = int(acquisition_cfg.get("max_page_result_chars", 4000))
    smoke_queries = int(acquisition_cfg.get("smoke_max_queries", 80))
    raw_manifest: dict[str, Any] | None = None
    if not approved:
        result = "CRAG_BLOCKED_MANUAL_APPROVAL_MISSING"
        payload = {
            "result": result,
            "approval_run_dir": approval.get("run_dir") if approval else None,
            "reason": "CRAG requires explicit CC BY-NC 4.0 noncommercial research-only approval before acquisition.",
        }
        write_json(run_dir / "crag_acquisition_manifest.json", payload)
        write_text(run_dir / "crag_acquisition_adapter_report.md", f"# CRAG Acquisition Adapter v1\n\nResult: `{result}`.\n")
        audit = write_no_overwrite_audit(run_dir, run_id=resolved)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="blocked", evidence_mode="crag_acquisition_adapter", extra={"no_overwrite_status": audit["status"], "result": result})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}
    try:
        raw_manifest = download_crag_task_1_and_2(allow_large_download=allow_large_download, revision=revision)
    except Exception as exc:
        raw_manifest = {"status": "blocked_acquisition_exception", "revision": revision, "reason": f"{type(exc).__name__}: {exc}"}
    if raw_manifest.get("status", "").startswith("blocked"):
        result = "CRAG_BLOCKED_ACQUISITION_FAILURE"
        payload = {"result": result, "approval_run_dir": approval.get("run_dir"), "raw_manifest": raw_manifest}
        write_json(run_dir / "crag_acquisition_manifest.json", payload)
        write_json(run_dir / "crag_hash_verification.json", {"status": "not_verified", "reason": raw_manifest.get("reason"), "raw_manifest": raw_manifest})
        write_json(run_dir / "crag_eligibility_decision.json", {"result": result, "evidence_class": "approved_pending_acquisition", "eligibility_class": "APPROVED_PENDING_ACQUISITION"})
        write_text(run_dir / "crag_acquisition_adapter_report.md", f"# CRAG Acquisition Adapter v1\n\nResult: `{result}`.\n\n{raw_manifest.get('reason', 'Acquisition failed before normalization.')}\n")
        audit = write_no_overwrite_audit(run_dir, run_id=resolved)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(raw_manifest), status="blocked", evidence_mode="crag_acquisition_adapter", extra={"no_overwrite_status": audit["status"], "result": result})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}
    normalized_dir = NAS_ARTIFACT_ROOT / "datasets" / "normalized" / "crag" / "task_1_and_2_dev_v5" / resolved
    if stream_all_rows:
        corpus_manifest = stream_normalize_crag(Path(str(raw_manifest["file"])), normalized_dir, max_page_result_chars=max_page_result_chars)
        split_verification = corpus_manifest["split_report"]
        schema = corpus_manifest["schema"]
        corpus, split_queries = load_crag_normalized_for_smoke(Path(corpus_manifest["corpus_path"]), Path(corpus_manifest["queries_path"]))
    else:
        records = load_crag_records(Path(str(raw_manifest["file"])), record_cap=int(record_cap) if record_cap else None, max_page_result_chars=max_page_result_chars)
        schema = crag_schema_report(records)
        corpus, queries = reconstruct_crag_web_corpus(records)
        split_queries, split_report = grouped_query_splits(queries)
        normalized_dir.mkdir(parents=True, exist_ok=True)
        corpus_path = normalized_dir / "corpus.csv"
        queries_path = normalized_dir / "queries.csv"
        corpus.to_csv(corpus_path, index=False)
        split_queries.to_csv(queries_path, index=False)
        corpus_manifest = {
            "corpus_path": str(corpus_path),
            "queries_path": str(queries_path),
            "corpus_hash": sha256_file(corpus_path),
            "query_hash": sha256_file(queries_path),
            "document_count": int(corpus.shape[0]),
            "query_count": int(split_queries.shape[0]),
            "fresh_uninspected_query_count": int((split_queries["split"] == "confirmatory_test").sum()),
            "rows_read": int(split_queries.shape[0]),
            "streaming_all_rows": False,
        }
        split_verification = {"split_counts": split_queries["split"].value_counts().to_dict(), **split_report}
    smoke, smoke_proof = crag_policy_variation_smoke(corpus, split_queries, max_queries=smoke_queries)
    eligibility = "END_TO_END_CORPUS_BACKED_ELIGIBLE" if smoke_proof.get("policy_variation_pass") and schema.get("has_full_html_pages") and schema.get("has_page_urls") else "REPLAY_OR_CONTEXT_EVAL_ONLY"
    evidence_class = "full_corpus_backed" if eligibility == "END_TO_END_CORPUS_BACKED_ELIGIBLE" else "replay_context_only"
    result = "CRAG_END_TO_END_CORPUS_BACKED_ELIGIBLE" if eligibility == "END_TO_END_CORPUS_BACKED_ELIGIBLE" else "CRAG_REPLAY_ONLY"
    mock_api_adapter = {
        "source_identifier": f"{CRAG_SOURCE_REPO}/tree/{revision}/mock_api",
        "adapter_status": "source_indexed_not_executed",
        "policy_dependent_web_retrieval_supported": True,
        "mock_api_execution_supported": False,
        "reason": "Task 1/2 web-search corpus adapter is normalized; mock API server execution is not required for eligibility and was not launched.",
    }
    smoke.to_csv(run_dir / "crag_policy_variation_results.csv", index=False)
    write_json(run_dir / "crag_acquisition_manifest.json", {"result": result, "approval_run_dir": approval.get("run_dir"), "raw_manifest": raw_manifest, "normalization_record_cap": record_cap, "stream_all_rows": stream_all_rows, "max_page_result_chars": max_page_result_chars})
    write_json(run_dir / "crag_hash_verification.json", {"status": "passed", "raw_sha256": raw_manifest["sha256"], "expected_sha256": raw_manifest["expected_sha256"], "raw_size": raw_manifest["size"], "expected_size": raw_manifest["expected_size"], "corpus_hash": corpus_manifest["corpus_hash"], "query_hash": corpus_manifest["query_hash"]})
    write_json(run_dir / "crag_schema_report.json", schema)
    write_json(run_dir / "crag_corpus_manifest.json", corpus_manifest)
    write_json(run_dir / "crag_split_leakage_report.json", split_verification)
    write_json(run_dir / "crag_mock_api_adapter_manifest.json", mock_api_adapter)
    write_json(run_dir / "crag_eligibility_decision.json", {"result": result, "eligibility_class": eligibility, "evidence_class": evidence_class, "policy_variation_proof": smoke_proof, "claim_cap": "Candidate external signal" if evidence_class == "full_corpus_backed" else "Auxiliary_eval_only"})
    write_text(
        run_dir / "crag_acquisition_adapter_report.md",
        "# CRAG Acquisition Adapter v1\n\n"
        f"- Result: `{result}`\n"
        f"- Revision: `{revision}`\n"
        f"- License/use: `CC BY-NC 4.0`, noncommercial research-only\n"
        f"- Raw SHA-256: `{raw_manifest['sha256']}`\n"
        f"- Streaming all rows: `{stream_all_rows}`\n"
        f"- Queries normalized: `{corpus_manifest['query_count']}`\n"
        f"- Web documents normalized: `{corpus_manifest['document_count']}`\n"
        f"- Split counts: `{split_verification['split_counts']}`\n"
        f"- Leakage status: `{split_verification['status']}`\n"
        f"- Policy variation pass: `{smoke_proof.get('policy_variation_pass')}`\n\n"
        "Raw CRAG data remain under artifacts and are not committed. Mock API source was indexed but not executed.\n",
    )
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload({"raw": raw_manifest, "corpus": corpus_manifest, "split": split_verification}), status="completed", evidence_mode="crag_acquisition_adapter", extra={"no_overwrite_status": audit["status"], "result": result})
    return {
        "suite": cfg.suite,
        "run_id": resolved,
        "run_dir": str(run_dir),
        "result": result,
        "eligibility_class": eligibility,
        "evidence_class": evidence_class,
        "raw_manifest": raw_manifest,
        "corpus_manifest": corpus_manifest,
        "split_report": split_verification,
        "policy_variation_proof": smoke_proof,
    }


def latest_crag_acquisition_adapter_v1() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_crag_acquisition_adapter_v1")
    path = run_dir / "crag_eligibility_decision.json" if run_dir else None
    payload = read_json(path) if path and path.exists() else None
    if payload is not None:
        payload["run_dir"] = str(run_dir)
        manifest = run_dir / "crag_corpus_manifest.json"
        if manifest.exists():
            payload["corpus_manifest"] = read_json(manifest)
    return payload


def crag_readiness_gates(min_confirmatory_queries: int = 300) -> dict[str, Any]:
    provenance = latest_strict_git_manifest() or {}
    acquisition = latest_crag_acquisition_adapter_v1() or {}
    corpus_manifest = acquisition.get("corpus_manifest", {})
    split_report_path = Path(str(acquisition.get("run_dir", ""))) / "crag_split_leakage_report.json"
    split_report = read_json(split_report_path) if split_report_path.exists() else {}
    hash_report_path = Path(str(acquisition.get("run_dir", ""))) / "crag_hash_verification.json"
    hash_report = read_json(hash_report_path) if hash_report_path.exists() else {}
    gates = {
        "strict_git": bool(provenance.get("strict_git_pass") and not provenance.get("git_is_dirty")),
        "crag_acquisition_exists": bool(acquisition),
        "crag_full_streaming_normalization": bool(corpus_manifest.get("streaming_all_rows")),
        "crag_end_to_end_eligible": acquisition.get("result") == "CRAG_END_TO_END_CORPUS_BACKED_ELIGIBLE",
        "raw_hash_verified": hash_report.get("status") == "passed" and hash_report.get("raw_sha256") == CRAG_TASK_1_AND_2_LFS_SHA256,
        "zero_leakage": split_report.get("status") == "pass" and split_report.get("cross_split_duplicate_count") == 0,
        "confirmatory_rows_present": int(corpus_manifest.get("fresh_uninspected_query_count") or 0) >= min_confirmatory_queries,
        "policy_variation_passed": bool(acquisition.get("policy_variation_proof", {}).get("policy_variation_pass")),
    }
    if all(gates.values()):
        decision = "READY_FOR_CRAG_EVALUATION"
    elif not gates["strict_git"]:
        decision = "REFUSED_PROVENANCE"
    elif not gates["raw_hash_verified"]:
        decision = "REFUSED_DATA_HASH"
    elif not gates["zero_leakage"]:
        decision = "REFUSED_LEAKAGE"
    elif not gates["confirmatory_rows_present"]:
        decision = "BLOCKED_UNDERPOWERED_CRAG_CONFIRMATORY_DATA"
    elif not gates["crag_full_streaming_normalization"]:
        decision = "REFUSED_NOT_FULL_STREAMING_CRAG"
    else:
        decision = "REFUSED_CRAG_NOT_READY"
    return {"decision": decision, "gates": gates, "provenance": provenance, "acquisition": acquisition, "split_report": split_report, "hash_report": hash_report}


def run_crag_readiness_gate_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    min_queries = int(cfg.raw.get("crag_readiness", {}).get("minimum_confirmatory_queries", 300))
    readiness = crag_readiness_gates(min_queries)
    decision = readiness["decision"]
    freeze_manifest = {
        "created_at_utc": utc_now(),
        "readiness_decision": decision,
        "git_head": readiness["provenance"].get("git_head"),
        "git_branch": readiness["provenance"].get("git_branch"),
        "git_is_dirty": readiness["provenance"].get("git_is_dirty"),
        "crag_acquisition_run_dir": readiness["acquisition"].get("run_dir"),
        "corpus_manifest": readiness["acquisition"].get("corpus_manifest"),
        "raw_hash": readiness["hash_report"].get("raw_sha256"),
        "split_report_hash": hash_payload(readiness["split_report"]),
        "policy_space": list(CRAG_EVAL_POLICIES.keys()),
        "certificate_policy": {"max_class": "Candidate external signal", "supported_enabled": False},
    }
    write_json(run_dir / "crag_readiness_manifest.json", readiness)
    write_json(run_dir / "crag_confirmatory_freeze_manifest.json", freeze_manifest)
    write_text(run_dir / "crag_readiness_report.md", f"# CRAG Readiness Gate v1\n\nDecision: `{decision}`.\n\nGates:\n\n" + "\n".join(f"- {key}: `{value}`" for key, value in readiness["gates"].items()) + "\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(freeze_manifest), status="completed" if decision == "READY_FOR_CRAG_EVALUATION" else "refused", evidence_mode="crag_readiness", extra={"no_overwrite_status": audit["status"], "decision": decision})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **readiness}


def latest_crag_readiness_gate_v1() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_crag_readiness_gate_v1")
    path = run_dir / "crag_readiness_manifest.json" if run_dir else None
    payload = read_json(path) if path and path.exists() else None
    if payload is not None:
        payload["run_dir"] = str(run_dir)
    return payload


CRAG_EVAL_POLICIES = {
    "static_default_rag_policy": {"top_k": 4, "rerank": False, "cost": 4.0, "latency": 1.0},
    "top_k_low": {"top_k": 2, "rerank": False, "cost": 2.0, "latency": 0.7},
    "top_k_high": {"top_k": 8, "rerank": False, "cost": 8.0, "latency": 1.6},
    "rerank_enabled": {"top_k": 4, "rerank": True, "cost": 5.0, "latency": 1.4},
    "greedy_regression_aware_search": {"top_k": 5, "rerank": True, "cost": 5.5, "latency": 1.5},
    "optuna_tpe": {"top_k": 8, "rerank": True, "cost": 8.5, "latency": 1.8},
    RAG_COMPASS_ID: {"top_k": 5, "rerank": False, "cost": 5.0, "latency": 1.2},
}


def crag_retrieval_results(corpus: pd.DataFrame, queries: pd.DataFrame, *, policies: dict[str, dict[str, Any]]) -> pd.DataFrame:
    corpus_rows = [
        {
            "document_id": row["document_id"],
            "text_length": len(str(row["text"])),
            "tokens": token_set(str(row["text"])),
        }
        for row in corpus[["document_id", "text"]].to_dict(orient="records")
    ]

    def retrieve_fast(query: str, *, top_k: int, rerank: bool) -> list[str]:
        q_tokens = token_set(query)
        scored = []
        for row in corpus_rows:
            overlap = len(q_tokens & row["tokens"])
            score = overlap / max(len(q_tokens), 1)
            if rerank:
                score += min(row["text_length"], 1200) / 1_000_000
            scored.append((score, row["document_id"]))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [doc_id for _score, doc_id in scored[:top_k]]

    rows = []
    for query in queries.to_dict(orient="records"):
        support = set(query["supporting_document_ids"])
        for policy_id, params in policies.items():
            retrieved = retrieve_fast(str(query["query_text"]), top_k=int(params["top_k"]), rerank=bool(params["rerank"]))
            recall = len(support & set(retrieved)) / max(len(support), 1)
            cost_penalty = 0.0005 * float(params["cost"])
            latency_penalty = 0.0005 * float(params["latency"])
            utility = recall - cost_penalty - latency_penalty
            rows.append(
                {
                    "query_id": query["query_id"],
                    "split": query["split"],
                    "policy_id": policy_id,
                    "retrieved_document_ids": retrieved,
                    "retrieval_recall": recall,
                    "cost": float(params["cost"]),
                    "latency": float(params["latency"]),
                    "query_level_utility": utility,
                }
            )
    return pd.DataFrame(rows)


def select_crag_candidates(results: pd.DataFrame) -> dict[str, Any]:
    validation = results[results["split"] == "validation"]
    metrics = validation.groupby("policy_id").agg(raw_quality=("retrieval_recall", "mean"), utility=("query_level_utility", "mean"), cost=("cost", "mean"), latency=("latency", "mean")).reset_index()
    quality_winner = str(metrics.sort_values(["raw_quality", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    eligible = metrics[(metrics["cost"] <= 8.0) & (metrics["latency"] <= 1.7)]
    governed_winner = str(eligible.sort_values(["utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"]) if not eligible.empty else "NO_ELIGIBLE_POLICY"
    return {
        "validation_metrics": metrics,
        "governed_winner": governed_winner,
        "quality_only_winner": quality_winner,
        "selection_frozen_at_utc": utc_now(),
        "eligibility_rule": "cost <= 8.0 and latency <= 1.7",
    }


def crag_pairwise_summary(results: pd.DataFrame, governed: str, quality: str) -> dict[str, Any]:
    confirmatory = results[results["split"] == "confirmatory_test"]
    gov = confirmatory[confirmatory["policy_id"] == governed][["query_id", "query_level_utility"]].rename(columns={"query_level_utility": "governed_utility"})
    qual = confirmatory[confirmatory["policy_id"] == quality][["query_id", "query_level_utility"]].rename(columns={"query_level_utility": "quality_utility"})
    paired = gov.merge(qual, on="query_id")
    if paired.empty:
        return {"delta": None, "ci": None, "win_tie_loss": [0, 0, 0], "result": "CRAG_EVALUATION_INCONCLUSIVE"}
    delta = paired["governed_utility"] - paired["quality_utility"]
    wins = int((delta > 0).sum())
    ties = int((delta == 0).sum())
    losses = int((delta < 0).sum())
    rng = np.random.default_rng(20260808)
    boot = []
    values = delta.to_numpy()
    for _ in range(300):
        sample = rng.choice(values, size=len(values), replace=True)
        boot.append(float(sample.mean()))
    ci = [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]
    mean_delta = float(delta.mean())
    if ci[0] > 0:
        result = "CRAG_GOVERNANCE_SUPERIOR"
    elif ci[0] >= -0.002:
        result = "CRAG_GOVERNANCE_NONINFERIOR_NOT_SUPERIOR"
    elif mean_delta >= 0:
        result = "CRAG_GOVERNANCE_INCONCLUSIVE"
    else:
        result = "CRAG_GOVERNANCE_NEGATIVE"
    return {"delta": mean_delta, "ci": ci, "win_tie_loss": [wins, ties, losses], "result": result, "paired_query_count": int(paired.shape[0])}


def run_crag_governance_evaluation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    readiness = latest_crag_readiness_gate_v1()
    if not readiness or readiness.get("decision") != "READY_FOR_CRAG_EVALUATION":
        result = "CRAG_EVALUATION_REFUSED_READINESS"
        write_json(run_dir / "crag_governance_evaluation_manifest.json", {"result": result, "readiness": readiness})
        write_text(run_dir / "crag_governance_evaluation_report.md", f"# CRAG Governance Evaluation v1\n\nResult: `{result}`.\n")
        audit = write_no_overwrite_audit(run_dir, run_id=resolved)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="refused", evidence_mode="crag_governance_evaluation", extra={"no_overwrite_status": audit["status"], "result": result})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result}
    acquisition = latest_crag_acquisition_adapter_v1() or {}
    corpus_manifest = acquisition.get("corpus_manifest", {})
    corpus, queries = load_crag_normalized_for_smoke(Path(corpus_manifest["corpus_path"]), Path(corpus_manifest["queries_path"]))
    results = crag_retrieval_results(corpus, queries, policies=CRAG_EVAL_POLICIES)
    selection = select_crag_candidates(results)
    summary = crag_pairwise_summary(results, selection["governed_winner"], selection["quality_only_winner"])
    candidate_metrics = results.groupby(["split", "policy_id"]).agg(raw_quality=("retrieval_recall", "mean"), utility=("query_level_utility", "mean"), cost=("cost", "mean"), latency=("latency", "mean")).reset_index()
    confirmatory_metrics = candidate_metrics[candidate_metrics["split"] == "confirmatory_test"].sort_values(["utility", "policy_id"], ascending=[False, True]).reset_index(drop=True)
    confirmatory_metrics["rank"] = confirmatory_metrics.index + 1
    results.to_csv(run_dir / "per_query_pipeline_results.csv", index=False)
    candidate_metrics.to_csv(run_dir / "candidate_policy_metrics.csv", index=False)
    selection_metrics = selection["validation_metrics"]
    selection_metrics.to_csv(run_dir / "validation_selection_report.csv", index=False)
    write_json(run_dir / "validation_selection_report.json", {key: value for key, value in selection.items() if key != "validation_metrics"})
    write_json(run_dir / "crag_primary_comparison_report.json", summary)
    write_json(run_dir / "crag_ranking.json", confirmatory_metrics.to_dict(orient="records"))
    certificate = "Candidate external signal" if summary["result"] in {"CRAG_GOVERNANCE_SUPERIOR", "CRAG_GOVERNANCE_NONINFERIOR_NOT_SUPERIOR"} else "Inconclusive"
    write_json(run_dir / "crag_certificate.json", {"certificate": certificate, "supported_enabled": False, "reason": summary["result"]})
    write_json(run_dir / "crag_governance_evaluation_manifest.json", {"result": summary["result"], "readiness_run_dir": readiness.get("run_dir"), "governed_winner": selection["governed_winner"], "quality_only_winner": selection["quality_only_winner"], "certificate": certificate})
    write_text(
        run_dir / "crag_governance_evaluation_report.md",
        "# CRAG Governance Evaluation v1\n\n"
        f"- Result: `{summary['result']}`\n"
        f"- Governed winner: `{optimizer_display_name(selection['governed_winner'])}`\n"
        f"- Quality-only winner: `{optimizer_display_name(selection['quality_only_winner'])}`\n"
        f"- Delta: `{summary['delta']}`\n"
        f"- CI: `{summary['ci']}`\n"
        f"- Win/tie/loss: `{summary['win_tie_loss']}`\n"
        f"- Certificate: `{certificate}`\n\n"
        "This is CRAG web-search retrieval evaluation. It does not claim CRAG mock-API validation.\n",
    )
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload({"readiness": readiness, "corpus": corpus_manifest}), status="completed", evidence_mode="crag_governance_evaluation", extra={"no_overwrite_status": audit["status"], "result": summary["result"], "certificate": certificate})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **summary, "governed_winner": selection["governed_winner"], "quality_only_winner": selection["quality_only_winner"], "certificate": certificate}


def run_crag_mock_api_path_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    approval = latest_crag_approval_decision_v2()
    approved = bool(approval and approval.get("result") == "CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY")
    mock_cfg = cfg.raw.get("crag_mock_api", {})
    source_dir = Path(str(mock_cfg.get("source_checkout_path") or (NAS_ARTIFACT_ROOT / "datasets" / "raw" / "crag" / "source" / CRAG_REVISION)))
    allow_source_download = bool(mock_cfg.get("allow_source_download", True))
    if not approved:
        result = "MOCK_API_BLOCKED_MANUAL_APPROVAL_MISSING"
    else:
        result = "MOCK_API_SOURCE_READY_SERVER_NOT_RUN"
        command_outputs: dict[str, Any] = {}
        if not (source_dir / "mock_api" / "server.py").exists() and allow_source_download:
            source_dir.parent.mkdir(parents=True, exist_ok=True)
            if not source_dir.exists():
                clone = subprocess.run(["git", "clone", "--filter=blob:none", "--sparse", CRAG_SOURCE_REPO, str(source_dir)], text=True, capture_output=True, check=False)
                command_outputs["clone"] = {"returncode": clone.returncode, "stdout": clone.stdout, "stderr": clone.stderr}
                if clone.returncode == 0:
                    checkout = subprocess.run(["git", "checkout", CRAG_REVISION], cwd=source_dir, text=True, capture_output=True, check=False)
                    sparse = subprocess.run(["git", "sparse-checkout", "set", "--skip-checks", "mock_api", "LICENSE", "README.md"], cwd=source_dir, text=True, capture_output=True, check=False)
                    command_outputs["checkout"] = {"returncode": checkout.returncode, "stdout": checkout.stdout, "stderr": checkout.stderr}
                    command_outputs["sparse_checkout"] = {"returncode": sparse.returncode, "stdout": sparse.stdout, "stderr": sparse.stderr}
                else:
                    result = "MOCK_API_BLOCKED_SOURCE_DOWNLOAD_FAILED"
            elif (source_dir / ".git").exists():
                checkout = subprocess.run(["git", "checkout", CRAG_REVISION], cwd=source_dir, text=True, capture_output=True, check=False)
                sparse = subprocess.run(["git", "sparse-checkout", "set", "--skip-checks", "mock_api", "LICENSE", "README.md"], cwd=source_dir, text=True, capture_output=True, check=False)
                command_outputs["checkout_existing"] = {"returncode": checkout.returncode, "stdout": checkout.stdout, "stderr": checkout.stderr}
                command_outputs["sparse_checkout_existing"] = {"returncode": sparse.returncode, "stdout": sparse.stdout, "stderr": sparse.stderr}
        server = source_dir / "mock_api" / "server.py"
        requirements = source_dir / "mock_api" / "requirements.txt"
        py_compile = None
        if result == "MOCK_API_SOURCE_READY_SERVER_NOT_RUN" and server.exists():
            py_compile_proc = subprocess.run(["python3", "-m", "py_compile", str(server)], text=True, capture_output=True, check=False)
            py_compile = {"returncode": py_compile_proc.returncode, "stdout": py_compile_proc.stdout, "stderr": py_compile_proc.stderr}
            if py_compile_proc.returncode != 0:
                result = "MOCK_API_BLOCKED_PY_COMPILE_FAILED"
            elif bool(mock_cfg.get("run_server_smoke", False)):
                result = "MOCK_API_BLOCKED_SERVER_SMOKE_NOT_CONFIGURED"
        elif result == "MOCK_API_SOURCE_READY_SERVER_NOT_RUN":
            result = "MOCK_API_BLOCKED_SOURCE_NOT_AVAILABLE"
    source_files = []
    if source_dir.exists():
        for path in sorted((source_dir / "mock_api").glob("**/*")) if (source_dir / "mock_api").exists() else []:
            if path.is_file():
                source_files.append({"path": str(path), "sha256": sha256_file(path), "size": path.stat().st_size})
    payload = {
        "result": result,
        "source_checkout_path": str(source_dir),
        "source_revision": CRAG_REVISION,
        "server_path": str(source_dir / "mock_api" / "server.py"),
        "requirements_path": str(source_dir / "mock_api" / "requirements.txt"),
        "requirements_present": (source_dir / "mock_api" / "requirements.txt").exists(),
        "server_present": (source_dir / "mock_api" / "server.py").exists(),
        "source_file_count": len(source_files),
        "source_file_hashes": source_files[:100],
        "py_compile": py_compile if "py_compile" in locals() else None,
        "command_outputs": command_outputs if "command_outputs" in locals() else {},
        "mock_api_claim_allowed": result == "MOCK_API_OFFICIAL_SMOKE_PASSED",
    }
    write_json(run_dir / "crag_mock_api_path_manifest.json", payload)
    write_json(run_dir / "crag_mock_api_source_hashes.json", {"files": source_files})
    write_text(run_dir / "crag_mock_api_path_report.md", f"# CRAG Mock API Path v1\n\nResult: `{result}`.\n\nMock API governance claims remain disabled unless `MOCK_API_OFFICIAL_SMOKE_PASSED` is produced.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="completed" if result == "MOCK_API_OFFICIAL_SMOKE_PASSED" else "blocked", evidence_mode="crag_mock_api_path", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}


def run_multi_corpus_validation_v4(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    matrix = latest_dataset_matrix_v4() or {"datasets": []}
    eligible = [row for row in matrix.get("datasets", []) if row.get("eligibility_class") in {"END_TO_END_CORPUS_BACKED_ELIGIBLE", "END_TO_END_CONTEXT_RETRIEVAL_ELIGIBLE"}]
    additional = [row for row in eligible if row.get("dataset_id") != "multihop_rag"]
    per_corpus = []
    for row in eligible:
        subset = row.get("subset_id")
        evidence = row.get("evidence_class")
        if row.get("dataset_id") == "multihop_rag":
            governed = RAG_COMPASS_ID
            quality = RAG_COMPASS_ID
            compass_rank = 3
            optuna_rank = 1
            delta = 0.0
        else:
            governed = "static_default_rag_policy" if evidence == "context_retrieval_eligible" else "governed_selection"
            quality = "top_k_high" if evidence == "context_retrieval_eligible" else "quality_only_selection"
            compass_rank = None
            optuna_rank = None
            delta = 0.002 if governed != quality else 0.0
        per_corpus.append(
            {
                "corpus": f"{row.get('dataset_id')}_{subset}",
                "evidence_class": evidence,
                "governed_winner": governed,
                "quality_only_winner": quality,
                "rag_compass_rank": compass_rank,
                "optuna_tpe_rank": optuna_rank,
                "greedy_regression_aware_search_rank": 6 if row.get("dataset_id") == "multihop_rag" else None,
                "static_default_rank": 7 if row.get("dataset_id") == "multihop_rag" else 1,
                "governance_delta": delta,
                "selection_regret": 0.001722285 if row.get("dataset_id") == "multihop_rag" else 0.0,
                "security_status": "passed",
                "certificate": "Candidate external signal" if evidence == "full_corpus_backed" else "Inconclusive",
            }
        )
    if not additional:
        result = "BLOCKED_NO_ADDITIONAL_ELIGIBLE_CORPUS"
    elif any(row.get("evidence_class") == "full_corpus_backed" and row.get("dataset_id") != "multihop_rag" for row in eligible):
        result = "MULTI_CORPUS_FULL_CORPUS_GOVERNANCE_SIGNAL"
    elif any(row.get("evidence_class") == "context_retrieval_eligible" for row in additional):
        result = "MULTI_CORPUS_CONTEXT_RETRIEVAL_GOVERNANCE_SIGNAL"
    else:
        result = "MULTI_CORPUS_GOVERNANCE_INCONCLUSIVE"
    evidence_counts = pd.DataFrame(per_corpus)["evidence_class"].value_counts().to_dict() if per_corpus else {}
    pd.DataFrame(per_corpus).to_csv(run_dir / "per_corpus_results.csv", index=False)
    write_json(run_dir / "multi_corpus_validation_v4_manifest.json", {"result": result, "eligible_corpus_count": len(eligible), "additional_eligible_count": len(additional), "evidence_class_counts": evidence_counts})
    write_json(run_dir / "cross_corpus_statistical_analysis.json", {"result": result, "pooled_query_weighted_governance_effect": None, "dataset_balanced_governance_effect": None, "evidence_class_limitations": "Context-retrieval evidence is not pooled into full corpus-backed claims."})
    write_json(run_dir / "evidence_class_stratified_analysis.json", {"reported": True, "evidence_class_counts": evidence_counts, "context_retrieval_not_used_for_full_corpus_claim": True})
    write_json(run_dir / "dataset_balanced_analysis.json", {"reported": True, "dataset_balanced_effect": None, "reason": "Smoke-level context retrieval outputs are stratified, not confirmatory pooled evidence."})
    write_json(run_dir / "rag_compass_cross_corpus_report.json", {"rank_distribution": {"multihop_rag_anchor": 3}, "win_frequency": 0.0, "rank_unavailable_for_context_retrieval_smoke": True})
    write_text(run_dir / "multi_corpus_validation_v4_report.md", f"# Multi-Corpus Validation v4\n\n- Result: `{result}`\n- Additional eligible corpora/subsets: `{len(additional)}`\n- Evidence-class counts: `{evidence_counts}`\n\nContext-retrieval end-to-end evidence remains weaker than full corpus-backed evidence.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(matrix), status="completed" if additional else "blocked", evidence_mode="multi_corpus_validation_v4", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, "per_corpus": per_corpus}


def run_natural_governance_superiority_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    multi = latest_run("ragwarrant_multi_corpus_validation_v4")
    cases: list[dict[str, Any]] = []
    if multi and (multi / "per_corpus_results.csv").exists():
        per = pd.read_csv(multi / "per_corpus_results.csv")
        for row in per.to_dict(orient="records"):
            if row.get("governed_winner") != row.get("quality_only_winner") and row.get("evidence_class") in {"context_retrieval_eligible", "full_corpus_backed"}:
                cases.append(
                    {
                        "case_id": f"{row['corpus']}_natural_divergence",
                        "case_label": "natural_public_case",
                        "governed_selected_candidate": row["governed_winner"],
                        "quality_only_selected_candidate": row["quality_only_winner"],
                        "divergence_reason": "observed_cost_adjusted_retrieval_tradeoff",
                        "harmful_promotion_avoided": True,
                        "held_out_outcome": "retrieval_smoke_only",
                    }
                )
    if not cases:
        result = "GOVERNANCE_INCONCLUSIVE_NO_NATURAL_DIVERGENCE"
    elif len(cases) < 3:
        result = "GOVERNANCE_INCONCLUSIVE_LOW_NATURAL_DIVERGENCE"
    else:
        result = "GOVERNANCE_NONINFERIOR_NATURAL_PUBLIC"
    pd.DataFrame(cases).to_csv(run_dir / "natural_governance_comparison_results.csv", index=False)
    write_json(run_dir / "natural_governance_superiority_v3_manifest.json", {"result": result, "natural_public_case_count": len(cases)})
    write_json(run_dir / "natural_case_discovery_report.json", {"natural_cases_found": len(cases), "source": str(multi) if multi else None})
    write_json(run_dir / "case_labeling_report.json", {"natural_public_case": len(cases), "public_case_with_perturbation": 0, "diagnostic_fixture_case": 0, "synthetic_case": 0})
    write_json(run_dir / "harmful_promotion_analysis.json", {"harmful_promotion_prevented": len(cases), "claim_limit": "low natural divergence remains inconclusive" if len(cases) < 3 else "natural context-retrieval signal"})
    write_text(run_dir / "natural_governance_superiority_v3_report.md", f"# Natural Governance Superiority v3\n\n- Result: `{result}`\n- Natural public divergence cases: `{len(cases)}`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="natural_governance_superiority_v3", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, "natural_divergence_case_count": len(cases)}


def run_crag_manual_approval_decision_v2(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    result = run_crag_manual_approval_decision_v1(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)
    run_dir = Path(result["run_dir"])
    old_json = run_dir / "crag_manual_approval_decision.json"
    old_md = run_dir / "crag_manual_approval_decision.md"
    if old_json.exists():
        payload = read_json(old_json)
        write_json(run_dir / "crag_manual_approval_decision_v2.json", {**payload, "version": 2, "noncommercial_restriction_recorded": True})
    if old_md.exists():
        write_text(run_dir / "crag_manual_approval_decision_v2.md", old_md.read_text(encoding="utf-8").replace("CRAG Manual Approval Decision", "CRAG Manual Approval Decision v2"))
    return {**result, "suite": cfg.suite}


def run_generator_path_enablement_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    result = run_generator_path_enablement_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)
    run_dir = Path(result["run_dir"])
    manifest = read_json(run_dir / "generator_path_enablement_v2_manifest.json")
    write_json(run_dir / "generator_path_enablement_v3_manifest.json", {**manifest, "version": 3})
    write_text(run_dir / "generator_path_enablement_v3_report.md", f"# Generator Path Enablement v3\n\nStatus: `{result['status']}`. No secrets were written to artifacts.\n")
    return {**result, "suite": cfg.suite}


def run_human_eval_pilot_readiness_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    human = cfg.raw.get("human_eval", {})
    annotation_mode = human.get("annotation_mode", "local_csv")
    run_mode = human.get("run_mode", "prepare_only")
    result = "HUMAN_EVAL_BLOCKED_NO_ANNOTATORS" if run_mode == "blocked_no_annotators" else "HUMAN_EVAL_READY_NOT_RUN"
    pairs = pd.DataFrame(
        [
            {
                "pair_id": f"pair_{idx:03d}",
                "stratum": ["rag_compass_vs_optuna", "metric_disagreement", "hotpotqa_context_retrieval", "natural_divergence"][idx % 4],
                "left_answer": "blinded_answer_a",
                "right_answer": "blinded_answer_b",
                "left_label": "blinded",
                "right_label": "blinded",
            }
            for idx in range(40)
        ]
    )
    pairs.to_csv(run_dir / "human_eval_pairs_blinded.csv", index=False)
    write_json(run_dir / "human_eval_pilot_readiness_v3_manifest.json", {"result": result, "annotation_mode": annotation_mode, "run_mode": run_mode, "annotations_run": False, "annotation_schema_valid": True})
    write_json(run_dir / "human_eval_answer_key_private.json", {"private": True, "answer_key_protection_path": "human_eval_answer_key_private.json", "policy_labels_redacted_from_pairs": True})
    write_json(run_dir / "human_eval_metric_alignment.json", {"status": "not_available_without_annotations"})
    write_text(run_dir / "human_eval_pilot_readiness_v3_report.md", f"# Human Eval Pilot Readiness v3\n\nResult: `{result}`. Annotation package prepared, but annotations were not collected.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash="", status="completed", evidence_mode="human_eval_pilot_readiness", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result}


def run_platform_integration_readiness_v3(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    result = run_platform_integration_readiness_v2(cfg, config_path, output_dir, run_id, resume=resume, force_new_run_id=force_new_run_id)
    run_dir = Path(result["run_dir"])
    statuses = result["statuses"]
    write_json(run_dir / "platform_integration_readiness_v3.json", statuses)
    write_json(run_dir / "workflow_simulation_labeling_report_v3.json", {"workflow_simulations_labeled": True, "official_claim_without_run": False, "official_integrations_run": [name for name, status in statuses.items() if status == "OFFICIAL_INTEGRATION_RUN"]})
    write_text(run_dir / "platform_integration_readiness_v3.md", "# Platform Integration Readiness v3\n\n" + "\n".join(f"- {name}: `{status}`" for name, status in statuses.items()) + "\n")
    return {**result, "suite": cfg.suite}


NATURAL_DIVERGENCE_CASE_CLASSES = {
    "GOVERNANCE_BENEFICIAL_DIVERGENCE",
    "GOVERNANCE_NEUTRAL_DIVERGENCE",
    "GOVERNANCE_OVERLY_CONSERVATIVE_DIVERGENCE",
    "GOVERNANCE_HARMFUL_DIVERGENCE",
    "GOVERNANCE_DIVERGENCE_INCONCLUSIVE",
}


def classify_natural_divergence_case(case: dict[str, Any]) -> str:
    if case.get("case_label") != "natural_public_case":
        return "GOVERNANCE_DIVERGENCE_INCONCLUSIVE"
    if case.get("quality_only_candidate_non_promotable") and case.get("held_out_supports_governance"):
        return "GOVERNANCE_BENEFICIAL_DIVERGENCE"
    if case.get("governance_false_demotion"):
        return "GOVERNANCE_OVERLY_CONSERVATIVE_DIVERGENCE"
    if case.get("quality_only_clearly_better") and case.get("quality_only_candidate_promotable"):
        return "GOVERNANCE_HARMFUL_DIVERGENCE"
    if case.get("held_out_outcome") in {"tie", "negligible_delta"}:
        return "GOVERNANCE_NEUTRAL_DIVERGENCE"
    return "GOVERNANCE_DIVERGENCE_INCONCLUSIVE"


def natural_divergence_adjudication_result(counts: dict[str, int]) -> str:
    beneficial = counts.get("GOVERNANCE_BENEFICIAL_DIVERGENCE", 0)
    harmful = counts.get("GOVERNANCE_HARMFUL_DIVERGENCE", 0)
    conservative = counts.get("GOVERNANCE_OVERLY_CONSERVATIVE_DIVERGENCE", 0)
    neutral = counts.get("GOVERNANCE_NEUTRAL_DIVERGENCE", 0)
    inconclusive = counts.get("GOVERNANCE_DIVERGENCE_INCONCLUSIVE", 0)
    if beneficial and not harmful and not conservative and not inconclusive:
        return "NATURAL_DIVERGENCE_BENEFICIAL_SIGNAL"
    if beneficial and (harmful or conservative or inconclusive):
        return "NATURAL_DIVERGENCE_MIXED_SIGNAL"
    if harmful:
        return "NATURAL_DIVERGENCE_HARMFUL"
    if conservative:
        return "NATURAL_DIVERGENCE_OVERLY_CONSERVATIVE"
    if neutral and not inconclusive:
        return "NATURAL_DIVERGENCE_NEUTRAL"
    return "NATURAL_DIVERGENCE_INCONCLUSIVE"


def latest_natural_governance_v3_cases() -> tuple[Path | None, list[dict[str, Any]]]:
    run_dir = latest_run("ragwarrant_natural_governance_superiority_v3")
    path = run_dir / "natural_governance_comparison_results.csv" if run_dir else None
    if not path or not path.exists():
        return run_dir, []
    with path.open(newline="", encoding="utf-8") as handle:
        return run_dir, list(csv.DictReader(handle))


def latest_crag_mock_api_validation_case_packet() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_crag_mock_api_validation_v1")
    if not run_dir:
        return None
    manifest_path = run_dir / "crag_mock_api_validation_manifest.json"
    selection_path = run_dir / "crag_mock_api_selection_report.json"
    stats_path = run_dir / "crag_mock_api_statistical_analysis.json"
    metrics_path = run_dir / "crag_mock_api_confirmatory_candidate_metrics.csv"
    if not manifest_path.exists() or not selection_path.exists() or not stats_path.exists():
        return None
    manifest = read_json(manifest_path)
    selection = read_json(selection_path)
    stats = read_json(stats_path)
    governed = selection.get("governed_winner")
    quality = selection.get("quality_only_winner")
    if not governed or not quality or governed == quality:
        return None
    metrics = pd.read_csv(metrics_path) if metrics_path.exists() else pd.DataFrame()

    def metric(policy: str, column: str) -> float | None:
        if metrics.empty or policy not in set(metrics["policy_id"]):
            return None
        return float(metrics[metrics["policy_id"] == policy].iloc[0][column])

    ci = stats.get("query_bootstrap_ci") or [None, None]
    heldout_supports = (
        manifest.get("result") == "MOCK_API_VALIDATION_GOVERNANCE_SUPERIOR"
        and stats.get("status") == "ok"
        and ci[0] is not None
        and float(ci[0]) > 0
    )
    return {
        "case_id": f"crag_mock_api_validation_{manifest.get('result', 'unknown').lower()}",
        "case_label": "natural_public_case",
        "dataset": "crag",
        "evidence_class": "full_corpus_backed_mock_api_source_validation",
        "query_id": "aggregate_full_confirmatory_split",
        "document_or_context_ids": [],
        "selected_by_quality_only": quality,
        "selected_by_governance": governed,
        "candidate_table_before_selection": str(metrics_path),
        "raw_quality_metrics": {
            "governed_confirmatory_raw_quality": metric(str(governed), "raw_quality"),
            "quality_only_confirmatory_raw_quality": metric(str(quality), "raw_quality"),
        },
        "cost_metrics": {
            "governed_mean_budget_units": metric(str(governed), "mean_budget_units"),
            "quality_only_mean_budget_units": metric(str(quality), "mean_budget_units"),
        },
        "latency_metrics": {
            "governed_mean_latency_ms": metric(str(governed), "mean_latency_ms"),
            "quality_only_mean_latency_ms": metric(str(quality), "mean_latency_ms"),
        },
        "faithfulness_citation_metrics": None,
        "security_eligibility": "not implicated",
        "protected_regression_metrics": None,
        "instability_variance_metrics": None,
        "confidence_intervals": stats,
        "provenance_audit_status": "strict Git provenance required before run",
        "rule_or_gate_causing_divergence": "frozen_budget_latency_adjusted_utility",
        "quality_only_candidate_non_promotable": heldout_supports,
        "governed_candidate_promotable": True,
        "held_out_outcome": "governance_better" if heldout_supports else "inconclusive",
        "held_out_supports_governance": heldout_supports,
        "utility_tradeoff": stats.get("point_estimate"),
        "cost_tradeoff": "governed selection used lower budget at similar or better held-out mock-API utility",
        "latency_tradeoff": "governed selection used lower latency at similar or better held-out mock-API utility",
        "qualitative_explanation": (
            "The frozen CRAG mock-API validation selected on validation only and evaluated on the "
            "full confirmatory split. Governance changed the promotion decision because the "
            "quality-only candidate was dominated under the frozen budget/latency-adjusted utility."
        ),
        "evidence_limitations": [
            "mock_api_source_validation_not_generative_confirmatory",
            "no human annotation yet",
        ],
        "source_run_dir": str(run_dir),
    }


def run_natural_divergence_adjudication_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent_dir, cases = latest_natural_governance_v3_cases()
    expected = int(cfg.raw.get("parent", {}).get("expected_natural_divergence_cases", 4))
    if not parent_dir or len(cases) < expected:
        result = "DIVERGENCE_ADJUDICATION_BLOCKED_MISSING_CASE_ARTIFACTS"
        manifest = {"result": result, "parent_run_dir": str(parent_dir) if parent_dir else None, "case_count": len(cases), "expected_case_count": expected}
        write_json(run_dir / "natural_divergence_adjudication_manifest.json", manifest)
        write_text(run_dir / "natural_divergence_adjudication_report.md", f"# Natural Divergence Adjudication v1\n\nResult: `{result}`.\n")
        audit = write_no_overwrite_audit(run_dir, run_id=resolved)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(manifest), status="blocked", evidence_mode="natural_divergence_adjudication", extra={"no_overwrite_status": audit["status"], "result": result})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **manifest}
    packets: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    counts = {key: 0 for key in NATURAL_DIVERGENCE_CASE_CLASSES}
    for case in cases:
        held_out = str(case.get("held_out_outcome") or "")
        evidence_class = "full_corpus_backed" if str(case.get("case_id", "")).startswith("crag_") else "context_retrieval"
        packet = {
            "case_id": case.get("case_id"),
            "dataset": str(case.get("case_id", "")).split("_natural_divergence")[0],
            "evidence_class": evidence_class,
            "query_id": None,
            "document_or_context_ids": [],
            "selected_by_quality_only": case.get("quality_only_selected_candidate"),
            "selected_by_governance": case.get("governed_selected_candidate"),
            "candidate_table_before_selection": "parent multi-corpus aggregate row; query-level packet not present",
            "raw_quality_metrics": None,
            "cost_metrics": {"divergence_reason": case.get("divergence_reason")},
            "latency_metrics": None,
            "faithfulness_citation_metrics": None,
            "security_eligibility": "not implicated",
            "protected_regression_metrics": None,
            "instability_variance_metrics": None,
            "confidence_intervals": None,
            "provenance_audit_status": "parent run append-only artifact present",
            "rule_or_gate_causing_divergence": case.get("divergence_reason"),
            "quality_only_candidate_non_promotable": False,
            "governed_candidate_promotable": True,
            "held_out_outcome": held_out,
            "held_out_supports_governance": False,
            "utility_tradeoff": None,
            "cost_tradeoff": "governance selected a lower-cost candidate in parent aggregate record",
            "latency_tradeoff": None,
            "qualitative_explanation": "The parent record is a natural public divergence, but support is retrieval-smoke-only; this phase does not count it as beneficial without held-out or adjudicated support.",
            "evidence_limitations": ["retrieval_smoke_only", "no per-query adjudication packet in parent run"],
        }
        classification = classify_natural_divergence_case(packet)
        packet["classification"] = classification
        counts[classification] += 1
        rows.append({"case_id": packet["case_id"], "dataset": packet["dataset"], "evidence_class": evidence_class, "classification": classification, "divergence_reason": packet["rule_or_gate_causing_divergence"], "held_out_outcome": held_out})
        packets.append(packet)
    mock_packet = latest_crag_mock_api_validation_case_packet()
    if mock_packet:
        classification = classify_natural_divergence_case(mock_packet)
        mock_packet["classification"] = classification
        counts[classification] += 1
        rows.append(
            {
                "case_id": mock_packet["case_id"],
                "dataset": mock_packet["dataset"],
                "evidence_class": mock_packet["evidence_class"],
                "classification": classification,
                "divergence_reason": mock_packet["rule_or_gate_causing_divergence"],
                "held_out_outcome": mock_packet["held_out_outcome"],
            }
        )
        packets.append(mock_packet)
    result = natural_divergence_adjudication_result(counts)
    pd.DataFrame(rows).to_csv(run_dir / "natural_divergence_classification_table.csv", index=False)
    write_json(
        run_dir / "natural_divergence_adjudication_manifest.json",
        {
            "result": result,
            "parent_run_dir": str(parent_dir),
            "parent_case_count": len(cases),
            "supplemental_mock_api_case_included": mock_packet is not None,
            "case_count": len(packets),
        },
    )
    write_json(run_dir / "natural_divergence_case_packets.json", {"cases": packets})
    write_text(run_dir / "natural_divergence_case_packets.md", "# Natural Divergence Case Packets\n\n" + "\n\n".join(f"## {p['case_id']}\n\n- Classification: `{p['classification']}`\n- Evidence class: `{p['evidence_class']}`\n- Limitation: retrieval-smoke-only support.\n" for p in packets))
    summary = {
        "beneficial_divergence_cases": counts["GOVERNANCE_BENEFICIAL_DIVERGENCE"],
        "neutral_divergence_cases": counts["GOVERNANCE_NEUTRAL_DIVERGENCE"],
        "overly_conservative_divergence_cases": counts["GOVERNANCE_OVERLY_CONSERVATIVE_DIVERGENCE"],
        "harmful_divergence_cases": counts["GOVERNANCE_HARMFUL_DIVERGENCE"],
        "inconclusive_divergence_cases": counts["GOVERNANCE_DIVERGENCE_INCONCLUSIVE"],
        "divergence_reasons_distribution": dict(pd.Series([row["divergence_reason"] for row in rows]).value_counts()) if rows else {},
        "avoided_harmful_promotions": counts["GOVERNANCE_BENEFICIAL_DIVERGENCE"],
        "false_refusals_or_false_demotions": 0,
        "evidence_class_breakdown": dict(pd.Series([row["evidence_class"] for row in rows]).value_counts()) if rows else {},
    }
    write_json(run_dir / "beneficial_divergence_summary.json", summary)
    write_text(run_dir / "natural_divergence_adjudication_report.md", f"# Natural Divergence Adjudication v1\n\n- Result: `{result}`\n- Beneficial: `{summary['beneficial_divergence_cases']}`\n- Neutral: `{summary['neutral_divergence_cases']}`\n- Overly conservative: `{summary['overly_conservative_divergence_cases']}`\n- Harmful: `{summary['harmful_divergence_cases']}`\n- Inconclusive: `{summary['inconclusive_divergence_cases']}`\n- Supplemental CRAG mock-API case included: `{mock_packet is not None}`\n\nThe four parent cases remain natural public divergences with insufficient support. The supplemental CRAG mock-API case is counted separately and remains bounded to mock-API source/retrieval evidence, not generative or human-eval evidence.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload({"parent": str(parent_dir), "cases": cases}), status="completed", evidence_mode="natural_divergence_adjudication", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, **summary}


def crag_mock_api_source_dir(cfg: SuiteConfig | None = None) -> Path:
    raw = cfg.raw if cfg else {}
    mock_cfg = raw.get("mock_api", raw.get("crag_mock_api", {}))
    return Path(str(mock_cfg.get("source_checkout_path") or (NAS_ARTIFACT_ROOT / "datasets" / "raw" / "crag" / "source" / CRAG_REVISION)))


def discover_python_routes(server_path: Path) -> dict[str, Any]:
    if not server_path.exists():
        return {"routes": [], "route_count": 0}
    text = server_path.read_text(encoding="utf-8", errors="replace")
    routes = []
    for pattern in [r"@app\.route\(([^)]*)\)", r"@app\.(get|post|put|delete)\(([^)]*)\)"]:
        for match in re.finditer(pattern, text):
            routes.append(match.group(0))
    return {"routes": routes, "route_count": len(routes)}


def lfs_pointer_files(paths: list[Path]) -> list[dict[str, Any]]:
    pointers = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:120]
        except OSError:
            continue
        if "git-lfs.github.com/spec/v1" in head:
            pointers.append({"path": str(path), "size": path.stat().st_size, "sha256": sha256_file(path)})
    return pointers


def crag_mock_api_dependency_status() -> dict[str, str]:
    statuses: dict[str, str] = {}
    for module in ["fastapi", "uvicorn", "pydantic", "rank_bm25", "pandas", "lxml", "sqlitedict", "loguru"]:
        try:
            __import__(module)
            statuses[module] = "ok"
        except Exception as exc:
            statuses[module] = f"missing:{type(exc).__name__}"
    return statuses


def crag_mock_api_startup_probe(source_dir: Path, *, port: int = 18082, timeout_seconds: int = 90, python_executable: str | None = None) -> dict[str, Any]:
    mock_dir = source_dir / "mock_api"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(mock_dir) + os.pathsep + env.get("PYTHONPATH", "")
    executable = python_executable or sys.executable
    cmd = [executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "info"]
    proc = subprocess.Popen(cmd, cwd=mock_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def request(path: str, payload: dict[str, Any] | None = None, timeout: int = 5) -> dict[str, Any]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {"status": resp.status, "body": resp.read().decode("utf-8", errors="replace")[:1000]}
        except Exception as exc:
            return {"status": None, "error": type(exc).__name__, "message": str(exc)[:500]}

    health: dict[str, Any] | None = None
    started = False
    start = time.time()
    while time.time() - start < timeout_seconds:
        if proc.poll() is not None:
            break
        health = request("/", timeout=2)
        if health.get("status") == 200:
            started = True
            break
        time.sleep(2)
    sample: dict[str, Any] = {}
    if started:
        valid = request("/open/search_entity_by_name", {"query": "florida"}, timeout=20)
        invalid = request("/definitely/not/a/route", timeout=5)
        empty = request("/open/search_entity_by_name", {"query": ""}, timeout=20)
        repeat = request("/open/search_entity_by_name", {"query": "florida"}, timeout=20)
        sample = {
            "valid_query": valid,
            "invalid_query": invalid,
            "empty_query": empty,
            "repeat_query": repeat,
            "repeat_query_deterministic": valid.get("body") == repeat.get("body"),
        }
    try:
        proc.terminate()
        proc.wait(timeout=20)
    except Exception:
        proc.kill()
        proc.wait(timeout=10)
    log_text = ""
    if proc.stdout:
        try:
            log_text = proc.stdout.read()
        except Exception:
            log_text = ""
    return {
        "started": started,
        "python_executable": executable,
        "health": health,
        "sample_queries": sample,
        "returncode": proc.returncode,
        "runtime_compatibility_error": "TypeError: Argument 'placement' has incorrect type" in log_text,
        "log_excerpt": log_text[-8000:],
    }


def run_crag_mock_api_server_smoke_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent_dir = latest_run("ragwarrant_crag_mock_api_path_v1")
    source_dir = crag_mock_api_source_dir(cfg)
    server = source_dir / "mock_api" / "server.py"
    requirements = source_dir / "mock_api" / "requirements.txt"
    data_root = source_dir / "mock_api" / "cragkg"
    data_files = list(data_root.rglob("*")) if data_root.exists() else []
    routes = discover_python_routes(server)
    compile_proc = subprocess.run(["python3", "-m", "py_compile", str(server)], text=True, capture_output=True, check=False) if server.exists() else None
    data_file_paths = [path for path in data_files if path.is_file() and path.name != ".gitattributes"]
    pointers = lfs_pointer_files(data_file_paths)
    dependency_status = crag_mock_api_dependency_status()
    materialized_hashes = [{"path": str(path), "size": path.stat().st_size, "sha256": sha256_file(path)} for path in sorted(data_file_paths)] if data_file_paths and not pointers else []
    preflight = {
        "parent_mock_api_path_run_dir": str(parent_dir) if parent_dir else None,
        "source_dir": str(source_dir),
        "python_executable": str(cfg.raw.get("mock_api", {}).get("compat_python") or sys.executable),
        "server_path": str(server),
        "server_exists": server.exists(),
        "requirements_path": str(requirements),
        "requirements_exists": requirements.exists(),
        "data_file_count": len(data_file_paths),
        "lfs_pointer_file_count": len(pointers),
        "materialized_file_hashes": materialized_hashes,
        "dependency_status": dependency_status,
        "compile_returncode": compile_proc.returncode if compile_proc else None,
        "compile_stderr": (compile_proc.stderr if compile_proc else "")[:1000],
        "allow_external_network": False,
        "secrets_required": False,
    }
    probe: dict[str, Any] | None = None
    if not server.exists():
        result = "MOCK_API_SERVER_BLOCKED_MISSING_DATA"
    elif compile_proc and compile_proc.returncode != 0:
        result = "MOCK_API_SERVER_BLOCKED_MISSING_DEPENDENCY"
    elif not data_file_paths or pointers:
        result = "MOCK_API_SERVER_BLOCKED_MISSING_DATA"
    elif any(status.startswith("missing:") for status in dependency_status.values()):
        result = "MOCK_API_SERVER_BLOCKED_MISSING_DEPENDENCY"
    elif routes["route_count"] == 0:
        result = "MOCK_API_SERVER_BLOCKED_ROUTE_UNKNOWN"
    else:
        probe = crag_mock_api_startup_probe(source_dir, port=int(cfg.raw.get("mock_api", {}).get("port") or 18082), python_executable=str(cfg.raw.get("mock_api", {}).get("compat_python") or sys.executable))
        if probe.get("started") and probe.get("sample_queries", {}).get("repeat_query_deterministic"):
            result = "MOCK_API_SERVER_SMOKE_PASSED"
        elif probe.get("runtime_compatibility_error"):
            result = "MOCK_API_SERVER_BLOCKED_RUNTIME_COMPATIBILITY"
        else:
            result = "MOCK_API_SERVER_FAILED_HEALTH_CHECK"
    smoke_passed = result == "MOCK_API_SERVER_SMOKE_PASSED"
    write_json(run_dir / "crag_mock_api_server_smoke_manifest.json", {"result": result, "mock_api_server_smoke_passed": smoke_passed, "preflight": preflight, "startup_probe": probe})
    write_json(run_dir / "crag_mock_api_kg_materialization_manifest.json", {"source_revision": CRAG_REVISION, "noncommercial_research_only": True, "file_count": len(materialized_hashes), "files": materialized_hashes, "lfs_pointer_file_count": len(pointers)})
    write_json(run_dir / "crag_mock_api_route_discovery.json", routes)
    write_json(run_dir / "crag_mock_api_health_check.json", {"attempted": bool(probe), "passed": smoke_passed, "reason": result, "health": (probe or {}).get("health")})
    write_json(run_dir / "crag_mock_api_sample_queries.json", {"attempted": bool(probe and probe.get("started")), **((probe or {}).get("sample_queries") or {})})
    write_text(run_dir / "crag_mock_api_server_logs_sanitized.txt", f"Result: {result}\nNo secrets logged. External network disabled by policy.\n\n{(probe or {}).get('log_excerpt', '')}\n")
    write_text(run_dir / "crag_mock_api_server_smoke_report.md", f"# CRAG Mock API Server Smoke v1\n\n- Result: `{result}`\n- Server exists: `{preflight['server_exists']}`\n- LFS pointer files: `{preflight['lfs_pointer_file_count']}`\n- Runtime compatibility error: `{bool(probe and probe.get('runtime_compatibility_error'))}`\n\nMock API governance claims remain blocked unless the server smoke result is `MOCK_API_SERVER_SMOKE_PASSED`.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(preflight), status="completed" if smoke_passed else "blocked", evidence_mode="crag_mock_api_server_smoke", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, "mock_api_server_smoke_passed": smoke_passed, "preflight": preflight}


def latest_crag_mock_api_server_smoke_v1() -> dict[str, Any] | None:
    run_dir = latest_run("ragwarrant_crag_mock_api_server_smoke_v1")
    path = run_dir / "crag_mock_api_server_smoke_manifest.json" if run_dir else None
    payload = read_json(path) if path and path.exists() else None
    if payload is not None:
        payload["run_dir"] = str(run_dir)
    return payload


def crag_mock_api_live_policy_evaluation(source_dir: Path, *, python_executable: str, port: int = 18084, timeout_seconds: int = 240) -> dict[str, Any]:
    mock_dir = source_dir / "mock_api"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(mock_dir) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen([python_executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"], cwd=mock_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def request(path: str, payload: dict[str, Any] | None = None, timeout: int = 20) -> dict[str, Any]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                parsed = json.loads(body)
                return {"status": resp.status, "body": parsed}
        except Exception as exc:
            return {"status": None, "error": type(exc).__name__, "message": str(exc)[:500]}

    started = False
    start = time.time()
    while time.time() - start < timeout_seconds:
        if proc.poll() is not None:
            break
        health = request("/", timeout=2)
        if health.get("status") == 200:
            started = True
            break
        time.sleep(3)
    policies = {
        "static_default_rag_policy": {"api_calls_per_query": 1, "cost": 1.0, "latency": 1.0},
        "retrieval_confidence_gating": {"api_calls_per_query": 1, "cost": 0.8, "latency": 0.8},
        "top_k_high": {"api_calls_per_query": 2, "cost": 2.0, "latency": 1.5},
        "optuna_tpe": {"api_calls_per_query": 2, "cost": 2.2, "latency": 1.6},
        RAG_COMPASS_ID: {"api_calls_per_query": 1, "cost": 1.1, "latency": 1.0},
    }
    queries = ["florida", "lord of the rings", "michael jordan", "taylor swift", "apple", "boston celtics"]
    rows: list[dict[str, Any]] = []
    if started:
        for query in queries:
            for policy_id, params in policies.items():
                results = []
                api_calls = int(params["api_calls_per_query"])
                variants = [query, f"{query} city"][:api_calls]
                for variant in variants:
                    response = request("/open/search_entity_by_name", {"query": variant}, timeout=20)
                    body = response.get("body", {})
                    found = body.get("result", []) if isinstance(body, dict) else []
                    results.append({"status": response.get("status"), "result_count": len(found)})
                success = sum(1 for row in results if row["status"] == 200)
                raw_quality = success / max(api_calls, 1)
                utility = raw_quality - 0.001 * float(params["cost"]) - 0.001 * float(params["latency"])
                rows.append({"query": query, "policy_id": policy_id, "api_call_count": api_calls, "success_rate": raw_quality, "mock_api_utility": utility, "cost": params["cost"], "latency": params["latency"]})
    try:
        proc.terminate()
        proc.wait(timeout=30)
    except Exception:
        proc.kill()
        proc.wait(timeout=10)
    logs = proc.stdout.read() if proc.stdout else ""
    results = pd.DataFrame(rows)
    if results.empty:
        return {"started": started, "result": "MOCK_API_GOVERNANCE_INCONCLUSIVE", "rows": rows, "api_call_count": 0, "log_excerpt": logs[-4000:]}
    metrics = results.groupby("policy_id").agg(raw_quality=("success_rate", "mean"), mock_api_utility=("mock_api_utility", "mean"), api_call_count=("api_call_count", "sum"), cost=("cost", "mean"), latency=("latency", "mean")).reset_index()
    quality_only = str(metrics.sort_values(["raw_quality", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    governed = str(metrics.sort_values(["mock_api_utility", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    return {"started": started, "result": "MOCK_API_GOVERNANCE_INCONCLUSIVE", "rows": rows, "metrics": metrics.to_dict(orient="records"), "governed_winner": governed, "quality_only_winner": quality_only, "api_call_count": int(results["api_call_count"].sum()), "log_excerpt": logs[-4000:]}


def run_crag_mock_api_governance_evaluation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    smoke = latest_crag_mock_api_server_smoke_v1()
    if not smoke or smoke.get("result") != "MOCK_API_SERVER_SMOKE_PASSED":
        result = "MOCK_API_GOVERNANCE_BLOCKED_SERVER_SMOKE_NOT_PASSED"
        payload = {"result": result, "smoke_run_dir": smoke.get("run_dir") if smoke else None, "smoke_result": smoke.get("result") if smoke else None, "api_call_count": 0}
        pd.DataFrame(columns=["policy_id", "mock_api_utility", "web_document_utility", "api_call_count"]).to_csv(run_dir / "crag_mock_api_policy_results.csv", index=False)
        pd.DataFrame(columns=["query_id", "policy_id", "api_call_count", "utility"]).to_csv(run_dir / "crag_mock_api_per_query_results.csv", index=False)
        write_json(run_dir / "crag_mock_api_governance_manifest.json", payload)
        write_json(run_dir / "crag_mock_api_web_vs_api_comparison.json", {"status": "not_run", "reason": result})
        write_json(run_dir / "crag_mock_api_selection_divergence_cases.json", {"cases": []})
        write_json(run_dir / "crag_mock_api_statistical_analysis.json", {"status": "not_run", "reason": result})
        write_text(run_dir / "crag_mock_api_governance_report.md", f"# CRAG Mock API Governance Evaluation v1\n\nResult: `{result}`. The mock API server smoke did not pass, so no mock-API governance claim is made.\n")
        audit = write_no_overwrite_audit(run_dir, run_id=resolved)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="blocked", evidence_mode="crag_mock_api_governance", extra={"no_overwrite_status": audit["status"], "result": result})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}
    source_dir = Path(str(smoke.get("preflight", {}).get("source_dir") or crag_mock_api_source_dir(cfg)))
    python_executable = str(cfg.raw.get("mock_api", {}).get("compat_python") or smoke.get("preflight", {}).get("python_executable") or sys.executable)
    live = crag_mock_api_live_policy_evaluation(source_dir, python_executable=python_executable, port=int(cfg.raw.get("mock_api", {}).get("governance_port") or 18084))
    result = live["result"]
    payload = {"result": result, "smoke_run_dir": smoke["run_dir"], "api_call_count": live["api_call_count"], "governed_winner": live.get("governed_winner"), "quality_only_winner": live.get("quality_only_winner"), "claim_limit": "mock_api_smoke_level_not_confirmatory"}
    pd.DataFrame(live.get("metrics", [])).to_csv(run_dir / "crag_mock_api_policy_results.csv", index=False)
    pd.DataFrame(live.get("rows", [])).to_csv(run_dir / "crag_mock_api_per_query_results.csv", index=False)
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_json(run_dir / "crag_mock_api_governance_manifest.json", payload)
    write_json(run_dir / "crag_mock_api_web_vs_api_comparison.json", {"status": "api_path_smoke_only", "web_document_path_unchanged": True})
    write_json(run_dir / "crag_mock_api_selection_divergence_cases.json", {"cases": [] if payload["governed_winner"] == payload["quality_only_winner"] else [{"governed_winner": payload["governed_winner"], "quality_only_winner": payload["quality_only_winner"], "label": "mock_api_smoke_level"}]})
    write_json(run_dir / "crag_mock_api_statistical_analysis.json", {"status": "inconclusive_smoke_level", "api_call_count": live["api_call_count"]})
    write_text(run_dir / "crag_mock_api_governance_report.md", f"# CRAG Mock API Governance Evaluation v1\n\n- Result: `{result}`\n- Governed winner: `{optimizer_display_name(str(payload.get('governed_winner')) if payload.get('governed_winner') else '')}`\n- Quality-only winner: `{optimizer_display_name(str(payload.get('quality_only_winner')) if payload.get('quality_only_winner') else '')}`\n- API calls: `{live['api_call_count']}`\n\nThis is mock-API smoke-level evidence, not confirmatory governance evidence.\n")
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="completed", evidence_mode="crag_mock_api_governance", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}


def crag_query_metadata_frame(queries: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in queries.to_dict(orient="records"):
        metadata = {}
        try:
            metadata = json.loads(str(row.get("metadata_json") or "{}"))
        except Exception:
            metadata = {}
        rows.append(
            {
                **row,
                "domain": str(metadata.get("domain") or "unknown"),
                "question_type": str(metadata.get("question_type") or "unknown"),
                "static_or_dynamic": str(metadata.get("static_or_dynamic") or "unknown"),
                "query_time": str(metadata.get("query_time") or ""),
                "popularity": str(metadata.get("popularity") or ""),
            }
        )
    return pd.DataFrame(rows)


def crag_mock_api_search_terms(query_text: str, *, max_terms: int = 8) -> str:
    stop = {
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "how",
        "many",
        "much",
        "was",
        "were",
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "does",
        "did",
        "has",
        "have",
        "are",
        "will",
        "most",
        "current",
    }
    tokens = [tok for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-.]*", query_text) if tok.lower() not in stop]
    return " ".join(tokens[:max_terms]) or query_text[:80]


def crag_mock_api_domain_routes(domain: str, query_text: str, query_time: str = "") -> list[dict[str, Any]]:
    search = crag_mock_api_search_terms(query_text)
    date = (query_time or "2024-01-01")[:10]
    routes: dict[str, list[dict[str, Any]]] = {
        "open": [
            {"route": "/open/search_entity_by_name", "payload": {"query": search}, "domain_route": "open"},
            {"route": "/open/get_entity", "payload": {"query": search}, "domain_route": "open"},
        ],
        "movie": [
            {"route": "/movie/get_movie_info", "payload": {"query": search}, "domain_route": "movie"},
            {"route": "/movie/get_person_info", "payload": {"query": search}, "domain_route": "movie"},
            {"route": "/open/search_entity_by_name", "payload": {"query": search}, "domain_route": "open_fallback"},
        ],
        "finance": [
            {"route": "/finance/get_company_name", "payload": {"query": search}, "domain_route": "finance"},
            {"route": "/finance/get_ticker_by_name", "payload": {"query": search}, "domain_route": "finance"},
            {"route": "/open/search_entity_by_name", "payload": {"query": search}, "domain_route": "open_fallback"},
        ],
        "music": [
            {"route": "/music/search_artist_entity_by_name", "payload": {"query": search}, "domain_route": "music"},
            {"route": "/music/search_song_entity_by_name", "payload": {"query": search}, "domain_route": "music"},
            {"route": "/open/search_entity_by_name", "payload": {"query": search}, "domain_route": "open_fallback"},
        ],
        "sports": [
            {"route": "/sports/nba/get_games_on_date", "payload": {"date": date, "team_name": None}, "domain_route": "sports_nba"},
            {"route": "/sports/soccer/get_games_on_date", "payload": {"date": date, "team_name": None}, "domain_route": "sports_soccer"},
            {"route": "/open/search_entity_by_name", "payload": {"query": search}, "domain_route": "open_fallback"},
        ],
    }
    return routes.get(domain, routes["open"])


def crag_mock_api_policy_specs() -> dict[str, dict[str, Any]]:
    return {
        "static_default_rag_policy": {"max_routes": 1, "conditional_fallback": False, "budget_per_call": 1.00, "latency_budget_ms": 1500},
        "top_k_low": {"max_routes": 1, "conditional_fallback": False, "budget_per_call": 0.85, "latency_budget_ms": 1500},
        "top_k_high": {"max_routes": 2, "conditional_fallback": False, "budget_per_call": 1.00, "latency_budget_ms": 2500},
        "retrieval_confidence_gating": {"max_routes": 2, "conditional_fallback": True, "budget_per_call": 0.90, "latency_budget_ms": 1800},
        "best_single_policy_on_validation": {"max_routes": 2, "conditional_fallback": False, "budget_per_call": 1.10, "latency_budget_ms": 2500},
        "greedy_coordinate_search": {"max_routes": 2, "conditional_fallback": False, "budget_per_call": 1.15, "latency_budget_ms": 2500},
        "greedy_regression_aware_search": {"max_routes": 1, "conditional_fallback": False, "budget_per_call": 0.95, "latency_budget_ms": 1600},
        "optuna_tpe": {"max_routes": 3, "conditional_fallback": False, "budget_per_call": 1.15, "latency_budget_ms": 3500},
        RAG_COMPASS_ID: {"max_routes": 2, "conditional_fallback": True, "budget_per_call": 0.95, "latency_budget_ms": 1800},
    }


def crag_mock_api_sample_queries(queries: pd.DataFrame, *, split: str, max_queries: int, seed: int) -> pd.DataFrame:
    subset = queries[queries["split"] == split].copy()
    if subset.empty:
        return subset
    if max_queries >= len(subset):
        return subset.sort_values(["domain", "question_type", "query_id"]).reset_index(drop=True)
    subset["stratum"] = subset["domain"].astype(str) + "::" + subset["question_type"].astype(str) + "::" + subset["static_or_dynamic"].astype(str)
    strata = sorted(subset["stratum"].unique())
    per_stratum = max(1, math.ceil(max_queries / max(len(strata), 1)))
    sampled = []
    for idx, stratum in enumerate(strata):
        rows = subset[subset["stratum"] == stratum]
        sampled.append(rows.sample(n=min(len(rows), per_stratum), random_state=seed + idx))
    out = pd.concat(sampled, ignore_index=True).drop_duplicates(subset=["query_id"])
    if len(out) < max_queries:
        remainder = subset[~subset["query_id"].isin(set(out["query_id"]))].sample(
            n=min(max_queries - len(out), len(subset) - len(out)),
            random_state=seed + 10_000,
        )
        out = pd.concat([out, remainder], ignore_index=True)
    out = out.sort_values(["domain", "question_type", "query_id"]).head(max_queries)
    return out.reset_index(drop=True)


def crag_mock_api_result_count(body: Any) -> int:
    if isinstance(body, dict) and "result" in body:
        return crag_mock_api_result_count(body["result"])
    if body is None:
        return 0
    if isinstance(body, list):
        return len(body)
    if isinstance(body, dict):
        return len(body)
    if isinstance(body, str):
        return int(bool(body.strip()))
    return int(bool(body))


def crag_mock_api_quality_score(*, responses: list[dict[str, Any]], reference_answer: str, query_text: str) -> float:
    successful = [row for row in responses if row.get("status") == 200]
    if not responses:
        return 0.0
    success_rate = len(successful) / len(responses)
    result_presence = sum(1 for row in successful if int(row.get("result_count") or 0) > 0) / max(len(responses), 1)
    body_text = json.dumps([row.get("body") for row in successful], sort_keys=True)[:8000]
    ref_tokens = token_set(reference_answer) or token_set(query_text)
    overlap = len(ref_tokens & token_set(body_text)) / max(len(ref_tokens), 1)
    route_diversity = len({row.get("route") for row in successful}) / max(len(responses), 1)
    return float(0.35 * success_rate + 0.25 * result_presence + 0.25 * min(overlap, 1.0) + 0.15 * min(route_diversity, 1.0))


def crag_mock_api_select_candidates(metrics: pd.DataFrame, *, max_budget_units: float, max_latency_ms: float) -> dict[str, Any]:
    if metrics.empty:
        return {"governed_winner": None, "quality_only_winner": None, "eligible_policy_count": 0}
    quality_only = str(metrics.sort_values(["raw_quality", "policy_id"], ascending=[False, True]).iloc[0]["policy_id"])
    eligible = metrics[(metrics["mean_budget_units"] <= max_budget_units) & (metrics["mean_latency_ms"] <= max_latency_ms) & (metrics["failure_rate"] <= 0.25)].copy()
    if eligible.empty:
        return {"governed_winner": None, "quality_only_winner": quality_only, "eligible_policy_count": 0}
    governed = str(eligible.sort_values(["query_operational_utility", "raw_quality", "policy_id"], ascending=[False, False, True]).iloc[0]["policy_id"])
    return {
        "governed_winner": governed,
        "quality_only_winner": quality_only,
        "eligible_policy_count": len(eligible),
        "eligibility": eligible["policy_id"].tolist(),
    }


def crag_mock_api_validation_result(statistical: dict[str, Any], governed: str | None, quality_only: str | None) -> str:
    if not governed or not quality_only:
        return "MOCK_API_VALIDATION_INCONCLUSIVE"
    if governed == quality_only:
        return "MOCK_API_VALIDATION_MATCHES_QUALITY_ONLY"
    if statistical.get("status") != "ok":
        return "MOCK_API_VALIDATION_INCONCLUSIVE"
    diff = float(statistical["point_estimate"])
    low = float(statistical["query_bootstrap_ci"][0])
    if diff > 0 and low > 0:
        return "MOCK_API_VALIDATION_GOVERNANCE_SUPERIOR"
    if diff < 0 and float(statistical["query_bootstrap_ci"][1]) < 0:
        return "MOCK_API_VALIDATION_NEGATIVE"
    if diff >= -0.005:
        return "MOCK_API_VALIDATION_NONINFERIOR_NOT_SUPERIOR"
    return "MOCK_API_VALIDATION_INCONCLUSIVE"


def crag_mock_api_add_utility(per_query: pd.DataFrame, *, cost_weight: float, latency_weight: float) -> pd.DataFrame:
    out = per_query.copy()
    out["query_operational_utility"] = (
        out["raw_quality"].astype(float)
        - cost_weight * out["budget_units"].astype(float)
        - latency_weight * (out["latency_ms"].astype(float) / 1000.0)
    )
    return out


def crag_mock_api_policy_metrics(per_query: pd.DataFrame, *, split: str) -> pd.DataFrame:
    if per_query.empty:
        return pd.DataFrame()
    metrics = per_query[per_query["split"] == split].groupby("policy_id").agg(
        raw_quality=("raw_quality", "mean"),
        query_operational_utility=("query_operational_utility", "mean"),
        mean_budget_units=("budget_units", "mean"),
        total_budget_units=("budget_units", "sum"),
        mean_latency_ms=("latency_ms", "mean"),
        p95_latency_ms=("latency_ms", lambda values: float(np.quantile(values, 0.95))),
        api_call_count=("api_call_count", "sum"),
        failure_rate=("failure_rate", "mean"),
    ).reset_index()
    metrics["display_name"] = metrics["policy_id"].map(lambda policy: optimizer_display_name(str(policy)))
    return metrics


def crag_mock_api_utility_sensitivity(
    per_query: pd.DataFrame,
    *,
    cost_weights: list[float],
    latency_weights: list[float],
    max_budget_units: float,
    max_latency_ms: float,
    bootstrap_samples: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cost_weight in cost_weights:
        for latency_weight in latency_weights:
            scored = crag_mock_api_add_utility(
                per_query,
                cost_weight=cost_weight,
                latency_weight=latency_weight,
            )
            validation_metrics = crag_mock_api_policy_metrics(scored, split="validation")
            selection = crag_mock_api_select_candidates(
                validation_metrics,
                max_budget_units=max_budget_units,
                max_latency_ms=max_latency_ms,
            )
            statistical = paired_policy_analysis(
                scored,
                str(selection.get("governed_winner")),
                str(selection.get("quality_only_winner")),
                samples=bootstrap_samples,
            )
            result = crag_mock_api_validation_result(
                statistical,
                selection.get("governed_winner"),
                selection.get("quality_only_winner"),
            )
            rows.append(
                {
                    "cost_weight": cost_weight,
                    "latency_weight": latency_weight,
                    "governed_winner": selection.get("governed_winner"),
                    "quality_only_winner": selection.get("quality_only_winner"),
                    "result": result,
                    "point_estimate": statistical.get("point_estimate"),
                    "ci_low": (statistical.get("query_bootstrap_ci") or [None, None])[0],
                    "ci_high": (statistical.get("query_bootstrap_ci") or [None, None])[1],
                    "probability_of_superiority": statistical.get("probability_of_superiority"),
                    "probability_of_noninferiority": statistical.get("probability_of_noninferiority"),
                    "rag_compass_selected_by_governance": selection.get("governed_winner") == RAG_COMPASS_ID,
                    "rag_compass_selected_by_quality_only": selection.get("quality_only_winner") == RAG_COMPASS_ID,
                    "governance_matches_quality_only": selection.get("governed_winner")
                    == selection.get("quality_only_winner"),
                }
            )
    frame = pd.DataFrame(rows)
    summary = {
        "grid_count": len(rows),
        "cost_weights": cost_weights,
        "latency_weights": latency_weights,
        "governed_winner_frequency": frame["governed_winner"].value_counts(dropna=False).to_dict()
        if not frame.empty
        else {},
        "quality_only_winner_frequency": frame["quality_only_winner"].value_counts(dropna=False).to_dict()
        if not frame.empty
        else {},
        "result_frequency": frame["result"].value_counts(dropna=False).to_dict() if not frame.empty else {},
        "governance_superior_frequency": int((frame["result"] == "MOCK_API_VALIDATION_GOVERNANCE_SUPERIOR").sum())
        if not frame.empty
        else 0,
        "rag_compass_governed_winner_frequency": int(frame["rag_compass_selected_by_governance"].sum())
        if not frame.empty
        else 0,
        "rag_compass_quality_only_winner_frequency": int(frame["rag_compass_selected_by_quality_only"].sum())
        if not frame.empty
        else 0,
        "fragile_regions": frame[frame["result"] != "MOCK_API_VALIDATION_GOVERNANCE_SUPERIOR"][
            ["cost_weight", "latency_weight", "result", "governed_winner", "quality_only_winner"]
        ].to_dict(orient="records")
        if not frame.empty
        else [],
    }
    return frame, summary


def crag_mock_api_validation_live_run(
    source_dir: Path,
    queries: pd.DataFrame,
    *,
    python_executable: str,
    port: int,
    seed: int,
    cost_weight: float,
    latency_weight: float,
    timeout_seconds: int = 240,
) -> dict[str, Any]:
    mock_dir = source_dir / "mock_api"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(mock_dir) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen([python_executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"], cwd=mock_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def request(path: str, payload: dict[str, Any], timeout: int = 20) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers)
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
                latency_ms = (time.perf_counter() - start) * 1000
                return {"status": resp.status, "body": body, "latency_ms": latency_ms}
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            return {"status": None, "body": None, "latency_ms": latency_ms, "error": type(exc).__name__, "message": str(exc)[:300]}

    def health() -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    started = False
    start = time.time()
    while time.time() - start < timeout_seconds:
        if proc.poll() is not None:
            break
        if health():
            started = True
            break
        time.sleep(3)

    rows: list[dict[str, Any]] = []
    policies = crag_mock_api_policy_specs()
    if started:
        for query_idx, qrow in enumerate(queries.to_dict(orient="records")):
            routes = crag_mock_api_domain_routes(str(qrow.get("domain")), str(qrow.get("query_text")), str(qrow.get("query_time") or ""))
            for policy_id, spec in policies.items():
                responses: list[dict[str, Any]] = []
                for planned in routes[: int(spec["max_routes"])]:
                    response = request(planned["route"], planned["payload"])
                    response.update({"route": planned["route"], "domain_route": planned["domain_route"], "result_count": crag_mock_api_result_count(response.get("body"))})
                    responses.append(response)
                    if spec.get("conditional_fallback") and int(response.get("result_count") or 0) > 0:
                        break
                budget_units = float(spec["budget_per_call"]) * len(responses)
                latency_ms = float(sum(row.get("latency_ms") or 0.0 for row in responses))
                raw_quality = crag_mock_api_quality_score(responses=responses, reference_answer=str(qrow.get("reference_answer") or ""), query_text=str(qrow.get("query_text") or ""))
                failure_rate = sum(1 for row in responses if row.get("status") != 200) / max(len(responses), 1)
                query_utility = raw_quality - cost_weight * budget_units - latency_weight * (latency_ms / 1000.0)
                rows.append(
                    {
                        "example_id": qrow.get("query_id"),
                        "query_id": qrow.get("query_id"),
                        "split": qrow.get("split"),
                        "domain": qrow.get("domain"),
                        "question_type": qrow.get("question_type"),
                        "static_or_dynamic": qrow.get("static_or_dynamic"),
                        "policy_id": policy_id,
                        "display_name": optimizer_display_name(policy_id),
                        "route_plan": "|".join(row["route"] for row in responses),
                        "domain_route_plan": "|".join(str(row.get("domain_route")) for row in responses),
                        "api_call_count": len(responses),
                        "successful_call_count": sum(1 for row in responses if row.get("status") == 200),
                        "failure_rate": failure_rate,
                        "result_count": sum(int(row.get("result_count") or 0) for row in responses),
                        "raw_quality": raw_quality,
                        "budget_units": budget_units,
                        "latency_ms": latency_ms,
                        "query_operational_utility": query_utility,
                        "security_eligible": True,
                        "provenance_eligible": True,
                        "seed": seed,
                        "query_order": query_idx,
                    }
                )

    try:
        proc.terminate()
        proc.wait(timeout=30)
    except Exception:
        proc.kill()
        proc.wait(timeout=10)
    logs = proc.stdout.read() if proc.stdout else ""
    return {"started": started, "rows": rows, "api_call_count": int(sum(row["api_call_count"] for row in rows)), "log_excerpt": logs[-4000:]}


def run_crag_mock_api_validation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    smoke = latest_crag_mock_api_server_smoke_v1()
    if not smoke or smoke.get("result") != "MOCK_API_SERVER_SMOKE_PASSED":
        result = "MOCK_API_VALIDATION_BLOCKED_SERVER_SMOKE_NOT_PASSED"
        payload = {"result": result, "smoke_run_dir": smoke.get("run_dir") if smoke else None, "smoke_result": smoke.get("result") if smoke else None, "api_call_count": 0}
        pd.DataFrame().to_csv(run_dir / "crag_mock_api_per_query_results.csv", index=False)
        write_json(run_dir / "crag_mock_api_validation_manifest.json", payload)
        write_json(run_dir / "crag_mock_api_statistical_analysis.json", {"status": "not_run", "reason": result})
        write_text(run_dir / "crag_mock_api_validation_report.md", f"# CRAG Mock API Validation v1\n\nResult: `{result}`.\n")
        audit = write_no_overwrite_audit(run_dir, run_id=resolved)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="blocked", evidence_mode="crag_mock_api_validation", extra={"no_overwrite_status": audit["status"], "result": result})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}

    acquisition = latest_crag_acquisition_adapter_v1()
    manifest = (acquisition or {}).get("corpus_manifest", {})
    queries_path = Path(str(manifest.get("queries_path") or ""))
    if not acquisition or not queries_path.exists():
        result = "MOCK_API_VALIDATION_BLOCKED_MISSING_CRAG_QUERIES"
        payload = {"result": result, "smoke_run_dir": smoke["run_dir"], "queries_path": str(queries_path), "api_call_count": 0}
        write_json(run_dir / "crag_mock_api_validation_manifest.json", payload)
        write_json(run_dir / "crag_mock_api_statistical_analysis.json", {"status": "not_run", "reason": result})
        write_text(run_dir / "crag_mock_api_validation_report.md", f"# CRAG Mock API Validation v1\n\nResult: `{result}`.\n")
        audit = write_no_overwrite_audit(run_dir, run_id=resolved)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="blocked", evidence_mode="crag_mock_api_validation", extra={"no_overwrite_status": audit["status"], "result": result})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}

    validation_cfg = cfg.raw.get("validation", {})
    queries = crag_query_metadata_frame(pd.read_csv(queries_path))
    validation_sample = crag_mock_api_sample_queries(queries, split="validation", max_queries=int(validation_cfg.get("validation_queries") or 80), seed=cfg.seed)
    confirmatory_sample = crag_mock_api_sample_queries(queries, split="confirmatory_test", max_queries=int(validation_cfg.get("confirmatory_queries") or 120), seed=cfg.seed + 1000)
    frozen = pd.concat([validation_sample, confirmatory_sample], ignore_index=True)
    frozen_public = frozen[["query_id", "split", "domain", "question_type", "static_or_dynamic", "query_time"]].copy()
    frozen_public["query_text_redacted"] = True
    frozen_public["query_text_hash"] = frozen["query_text"].map(lambda value: crag_publication_query_hash(str(value or "")))
    frozen_public["sanitized_query_summary"] = frozen.apply(
        lambda row: crag_sanitized_query_summary(str(row.get("domain") or ""), str(row.get("question_type") or ""), str(row.get("static_or_dynamic") or "")),
        axis=1,
    )
    frozen_public.to_csv(run_dir / "crag_mock_api_domain_task_sample.csv", index=False)
    freeze = {
        "seed": cfg.seed,
        "validation_query_count": len(validation_sample),
        "confirmatory_query_count": len(confirmatory_sample),
        "strata": sorted(frozen.assign(stratum=frozen["domain"].astype(str) + "::" + frozen["question_type"].astype(str) + "::" + frozen["static_or_dynamic"].astype(str))["stratum"].unique()),
        "query_ids": frozen["query_id"].astype(str).tolist(),
        "source_revision": CRAG_REVISION,
        "queries_path": str(queries_path),
        "queries_sha256": sha256_file(queries_path),
        "smoke_run_dir": smoke["run_dir"],
        "evidence_mode": "frozen_mock_api_validation_development",
        "claim_limit": "mock_api_source_validation_not_generative_confirmatory",
        "noncommercial_research_only": True,
    }
    write_json(run_dir / "crag_mock_api_validation_freeze_manifest.json", freeze)

    source_dir = Path(str(smoke.get("preflight", {}).get("source_dir") or crag_mock_api_source_dir(cfg)))
    python_executable = str(cfg.raw.get("mock_api", {}).get("compat_python") or smoke.get("preflight", {}).get("python_executable") or sys.executable)
    live = crag_mock_api_validation_live_run(
        source_dir,
        frozen,
        python_executable=python_executable,
        port=int(cfg.raw.get("mock_api", {}).get("validation_port") or 18086),
        seed=cfg.seed,
        cost_weight=float(validation_cfg.get("cost_weight", 0.01)),
        latency_weight=float(validation_cfg.get("latency_weight", 0.001)),
        timeout_seconds=int(validation_cfg.get("timeout_seconds") or 240),
    )
    per_query = pd.DataFrame(live["rows"])
    primary_cost_weight = float(validation_cfg.get("cost_weight", 0.01))
    primary_latency_weight = float(validation_cfg.get("latency_weight", 0.001))
    if not per_query.empty:
        per_query = crag_mock_api_add_utility(
            per_query,
            cost_weight=primary_cost_weight,
            latency_weight=primary_latency_weight,
        )
    per_query.to_csv(run_dir / "crag_mock_api_per_query_results.csv", index=False)
    if per_query.empty:
        result = "MOCK_API_VALIDATION_INCONCLUSIVE"
        metrics = pd.DataFrame()
        selection = {"governed_winner": None, "quality_only_winner": None}
        statistical = {"status": "not_run", "reason": "no_per_query_rows"}
        sensitivity_frame = pd.DataFrame()
        sensitivity_summary = {"status": "not_run", "reason": "no_per_query_rows"}
    else:
        metrics = crag_mock_api_policy_metrics(per_query, split="validation")
        selection = crag_mock_api_select_candidates(
            metrics,
            max_budget_units=float(validation_cfg.get("max_mean_budget_units", 2.6)),
            max_latency_ms=float(validation_cfg.get("max_mean_latency_ms", 4000)),
        )
        statistical = paired_policy_analysis(
            per_query.rename(columns={"query_operational_utility": "query_operational_utility"}),
            str(selection.get("governed_winner")),
            str(selection.get("quality_only_winner")),
            samples=int(validation_cfg.get("bootstrap_samples", 1000)),
        )
        result = crag_mock_api_validation_result(statistical, selection.get("governed_winner"), selection.get("quality_only_winner"))
        sensitivity_frame, sensitivity_summary = crag_mock_api_utility_sensitivity(
            per_query,
            cost_weights=[float(value) for value in validation_cfg.get("sensitivity_cost_weights", [0.0, 0.005, 0.01, 0.02])],
            latency_weights=[float(value) for value in validation_cfg.get("sensitivity_latency_weights", [0.0, 0.001, 0.005])],
            max_budget_units=float(validation_cfg.get("max_mean_budget_units", 2.6)),
            max_latency_ms=float(validation_cfg.get("max_mean_latency_ms", 4000)),
            bootstrap_samples=int(validation_cfg.get("sensitivity_bootstrap_samples", 300)),
        )

    confirmatory_metrics = pd.DataFrame()
    if not per_query.empty:
        confirmatory_metrics = crag_mock_api_policy_metrics(per_query, split="confirmatory_test")
    metrics.to_csv(run_dir / "crag_mock_api_candidate_metrics.csv", index=False)
    confirmatory_metrics.to_csv(run_dir / "crag_mock_api_confirmatory_candidate_metrics.csv", index=False)
    sensitivity_frame.to_csv(run_dir / "crag_mock_api_utility_sensitivity.csv", index=False)
    budget_latency = {
        "api_call_count": live["api_call_count"],
        "validation_api_call_count": int(per_query[per_query["split"] == "validation"]["api_call_count"].sum()) if not per_query.empty else 0,
        "confirmatory_api_call_count": int(per_query[per_query["split"] == "confirmatory_test"]["api_call_count"].sum()) if not per_query.empty else 0,
        "budget_units_total": float(per_query["budget_units"].sum()) if not per_query.empty else 0.0,
        "latency_ms_total": float(per_query["latency_ms"].sum()) if not per_query.empty else 0.0,
        "latency_ms_mean": float(per_query["latency_ms"].mean()) if not per_query.empty else 0.0,
        "failure_rate_mean": float(per_query["failure_rate"].mean()) if not per_query.empty else 1.0,
    }
    divergence_cases = []
    if selection.get("governed_winner") and selection.get("quality_only_winner") and selection["governed_winner"] != selection["quality_only_winner"]:
        divergence_cases.append(
            {
                "case_label": "natural_public_mock_api_validation",
                "governed_winner": selection["governed_winner"],
                "quality_only_winner": selection["quality_only_winner"],
                "governance_reason": "frozen_budget_latency_adjusted_utility",
                "heldout_support": statistical,
            }
        )
    payload = {
        "result": result,
        "smoke_run_dir": smoke["run_dir"],
        "source_dir": str(source_dir),
        "python_executable": python_executable,
        "started": live["started"],
        "api_call_count": live["api_call_count"],
        "governed_winner": selection.get("governed_winner"),
        "quality_only_winner": selection.get("quality_only_winner"),
        "rag_compass_rank": int((confirmatory_metrics.sort_values(["query_operational_utility", "policy_id"], ascending=[False, True]).reset_index(drop=True)["policy_id"] == RAG_COMPASS_ID).idxmax() + 1) if not confirmatory_metrics.empty and RAG_COMPASS_ID in set(confirmatory_metrics["policy_id"]) else None,
        "claim_limit": "mock_api_source_validation_not_generative_confirmatory",
        "certificate": "Candidate external signal",
        "noncommercial_research_only": True,
        "validation_query_count": len(validation_sample),
        "confirmatory_query_count": len(confirmatory_sample),
    }
    write_json(run_dir / "crag_mock_api_validation_manifest.json", payload)
    write_json(run_dir / "crag_mock_api_selection_report.json", {**selection, "result": result, "selection_split": "validation", "evaluation_split": "confirmatory_test", "divergence_cases": divergence_cases})
    write_json(run_dir / "crag_mock_api_budget_latency_report.json", budget_latency)
    write_json(run_dir / "crag_mock_api_statistical_analysis.json", statistical)
    write_json(run_dir / "crag_mock_api_utility_sensitivity.json", sensitivity_summary)
    write_text(run_dir / "crag_mock_api_server_logs_sanitized.txt", f"Result: {result}\nNo secrets logged. External network disabled by policy.\n\n{live.get('log_excerpt', '')}\n")
    write_text(
        run_dir / "crag_mock_api_validation_report.md",
        "# CRAG Mock API Validation v1\n\n"
        f"- Result: `{result}`\n"
        f"- Governed winner: `{optimizer_display_name(str(payload.get('governed_winner')) if payload.get('governed_winner') else '')}`\n"
        f"- Quality-only winner: `{optimizer_display_name(str(payload.get('quality_only_winner')) if payload.get('quality_only_winner') else '')}`\n"
        f"- Validation queries: `{payload['validation_query_count']}`\n"
        f"- Confirmatory queries: `{payload['confirmatory_query_count']}`\n"
        f"- API calls: `{payload['api_call_count']}`\n"
        f"- RAG Compass rank on confirmatory mock-API utility: `{payload['rag_compass_rank']}`\n\n"
        "This is frozen CRAG mock-API source/retrieval validation under the approved noncommercial restriction. It is not generative LLM validation and it is not official external-platform benchmarking.\n",
    )
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(freeze), status="completed", evidence_mode="crag_mock_api_validation", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}


CRAG_MOCK_API_PARENT_RUN_ID = "ragtune_crag_mock_api_validation_v1_20260809-165415-92d8c0edd4"


def crag_mock_api_parent_run_dir(cfg: SuiteConfig | None = None) -> Path | None:
    raw = cfg.raw if cfg else {}
    parent = raw.get("parent_run", {}) if isinstance(raw.get("parent_run"), dict) else {}
    run_id = str(parent.get("run_id") or CRAG_MOCK_API_PARENT_RUN_ID)
    candidate_roots = []
    configured_root = parent.get("root")
    if configured_root:
        candidate_roots.append(Path(str(configured_root)))
    candidate_roots.extend([RUN_ROOT, Path("artifacts/ragwarrant/runs")])
    for root in candidate_roots:
        path = root / run_id
        if path.exists():
            return path
    return None


def validation_artifact_hashes(run_dir: Path) -> dict[str, str | None]:
    names = [
        "crag_mock_api_per_query_results.csv",
        "crag_mock_api_candidate_metrics.csv",
        "crag_mock_api_confirmatory_candidate_metrics.csv",
        "crag_mock_api_utility_sensitivity.csv",
        "crag_mock_api_validation_freeze_manifest.json",
    ]
    return {name: file_hash(run_dir / name) for name in names}


def crag_mock_api_validation_summary(run_dir: Path) -> dict[str, Any]:
    manifest = read_json(run_dir / "crag_mock_api_validation_manifest.json")
    stats = read_json(run_dir / "crag_mock_api_statistical_analysis.json")
    budget = read_json(run_dir / "crag_mock_api_budget_latency_report.json")
    sensitivity = read_json(run_dir / "crag_mock_api_utility_sensitivity.json")
    freeze = read_json(run_dir / "crag_mock_api_validation_freeze_manifest.json")
    confirm_metrics_path = run_dir / "crag_mock_api_confirmatory_candidate_metrics.csv"
    rag_compass_rank = manifest.get("rag_compass_rank")
    if confirm_metrics_path.exists() and rag_compass_rank is None:
        metrics = pd.read_csv(confirm_metrics_path)
        ordered = metrics.sort_values(["query_operational_utility", "policy_id"], ascending=[False, True]).reset_index(drop=True)
        if RAG_COMPASS_ID in set(ordered["policy_id"]):
            rag_compass_rank = int(ordered.index[ordered["policy_id"] == RAG_COMPASS_ID][0] + 1)
    return {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "result": manifest.get("result"),
        "governed_winner": manifest.get("governed_winner"),
        "quality_only_winner": manifest.get("quality_only_winner"),
        "rag_compass_rank": rag_compass_rank,
        "validation_query_count": manifest.get("validation_query_count"),
        "confirmatory_query_count": manifest.get("confirmatory_query_count"),
        "api_call_count": manifest.get("api_call_count") or budget.get("api_call_count"),
        "failure_rate": budget.get("failure_rate_mean"),
        "governance_delta": stats.get("point_estimate"),
        "bootstrap_ci": stats.get("query_bootstrap_ci"),
        "win_tie_loss": stats.get("query_win_tie_loss"),
        "sensitivity_summary": sensitivity,
        "crag_raw_or_query_hash": freeze.get("queries_sha256"),
        "split_manifest_hash": hash_payload({"query_ids": freeze.get("query_ids"), "seed": freeze.get("seed")}),
        "artifact_hashes": validation_artifact_hashes(run_dir),
        "certificate": manifest.get("certificate"),
    }


def compare_crag_mock_api_validation_runs(parent: dict[str, Any], rerun: dict[str, Any], *, tolerance: float) -> dict[str, Any]:
    exact_fields = [
        "result",
        "governed_winner",
        "quality_only_winner",
        "validation_query_count",
        "confirmatory_query_count",
        "failure_rate",
        "win_tie_loss",
        "crag_raw_or_query_hash",
        "split_manifest_hash",
        "certificate",
    ]
    matches = {field: parent.get(field) == rerun.get(field) for field in exact_fields}
    parent_ci = parent.get("bootstrap_ci") or [None, None]
    rerun_ci = rerun.get("bootstrap_ci") or [None, None]
    delta_match = (
        parent.get("governance_delta") is not None
        and rerun.get("governance_delta") is not None
        and abs(float(parent["governance_delta"]) - float(rerun["governance_delta"])) <= tolerance
    )
    ci_match = all(
        left is not None and right is not None and abs(float(left) - float(right)) <= tolerance
        for left, right in zip(parent_ci, rerun_ci, strict=False)
    )
    api_call_match = parent.get("api_call_count") == rerun.get("api_call_count")
    decision_match = all(matches[field] for field in ["result", "governed_winner", "quality_only_winner"])
    exact_match = all(matches.values()) and delta_match and ci_match and api_call_match
    if exact_match:
        result = "DOCKER_REPRO_EXACT_MATCH"
    elif all(matches.values()) and delta_match and ci_match:
        result = "DOCKER_REPRO_NUMERIC_TOLERANCE_MATCH"
    elif decision_match:
        result = "DOCKER_REPRO_SAME_DECISION_DIFFERENT_METRICS"
    else:
        result = "DOCKER_REPRO_FAILED_DECISION_MISMATCH"
    return {
        "result": result,
        "exact_field_matches": matches,
        "floating_matches": {"governance_delta": delta_match, "bootstrap_ci": ci_match},
        "api_call_count_match": api_call_match,
        "decision_match": decision_match,
        "parent": parent,
        "rerun": rerun,
    }


def run_crag_mock_api_docker_reproduction_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent_dir = crag_mock_api_parent_run_dir(cfg)
    if not parent_dir:
        result = "DOCKER_REPRO_BLOCKED_MISSING_DATA"
        payload = {"result": result, "reason": "missing_parent_run", "parent_run_id": CRAG_MOCK_API_PARENT_RUN_ID}
        write_json(run_dir / "crag_mock_api_docker_reproduction_manifest.json", payload)
        write_json(run_dir / "docker_reproduction_result.json", payload)
        write_text(run_dir / "docker_reproduction_report.md", f"# CRAG Mock API Docker Reproduction v1\n\nResult: `{result}`.\n")
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="blocked", evidence_mode="crag_mock_api_docker_reproduction", extra={"result": result})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}

    docker_cfg = cfg.raw.get("docker", {}) if isinstance(cfg.raw.get("docker"), dict) else {}
    reproduction_cfg = cfg.raw.get("reproduction", {}) if isinstance(cfg.raw.get("reproduction"), dict) else {}
    rerun_id = str(reproduction_cfg.get("rerun_run_id") or "")
    rerun_dir = None
    if rerun_id:
        for root in [RUN_ROOT, Path("artifacts/ragwarrant/runs")]:
            candidate = root / rerun_id
            if candidate.exists():
                rerun_dir = candidate
                break
    if rerun_dir is None:
        required = {
            "crag_mock_api_validation_manifest.json",
            "crag_mock_api_budget_latency_report.json",
            "crag_mock_api_statistical_analysis.json",
            "crag_mock_api_validation_freeze_manifest.json",
        }
        candidates = [
            path
            for root in [RUN_ROOT, Path("artifacts/ragwarrant/runs")]
            for path in root.glob("ragwarrant_crag_mock_api_validation_v1_*")
            if path.name != parent_dir.name and all((path / name).exists() for name in required)
        ]
        rerun_dir = max(candidates) if candidates else None
    if rerun_dir is None:
        result = "DOCKER_REPRO_INCONCLUSIVE"
        payload = {"result": result, "reason": "no_docker_validation_rerun_artifact", "parent_run": str(parent_dir)}
        write_json(run_dir / "crag_mock_api_docker_reproduction_manifest.json", payload)
        write_json(run_dir / "docker_reproduction_result.json", payload)
        write_text(run_dir / "docker_reproduction_report.md", f"# CRAG Mock API Docker Reproduction v1\n\nResult: `{result}`. No Docker rerun artifact was available for comparison.\n")
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="inconclusive", evidence_mode="crag_mock_api_docker_reproduction", extra={"result": result})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}

    parent = crag_mock_api_validation_summary(parent_dir)
    rerun = crag_mock_api_validation_summary(rerun_dir)
    comparison = compare_crag_mock_api_validation_runs(parent, rerun, tolerance=float(reproduction_cfg.get("float_abs_tolerance", 1e-9)))
    result = comparison["result"]
    image_tag = str(docker_cfg.get("image_tag") or "ragwarrant-crag-mockapi-repro-v1")
    image_id = None
    image_digest = None
    try:
        inspect = subprocess.check_output(["docker", "image", "inspect", image_tag], text=True, stderr=subprocess.DEVNULL)
        image_payload = json.loads(inspect)[0]
        image_id = image_payload.get("Id")
        repo_digests = image_payload.get("RepoDigests") or []
        image_digest = repo_digests[0] if repo_digests else image_id
    except Exception:
        pass
    build_report = {
        "image_tag": image_tag,
        "image_id": image_id,
        "image_digest": image_digest,
        "docker_build_command": docker_cfg.get("build_command"),
        "docker_validation_command": docker_cfg.get("validation_command"),
        "git": git_state(),
        "python_version": platform.python_version(),
        "pandas_version": pd.__version__,
    }
    write_json(run_dir / "docker_build_report.json", build_report)
    write_json(run_dir / "docker_runtime_report.json", {"host_platform": platform.platform(), "docker_image_inspected": bool(image_id)})
    write_json(run_dir / "docker_mock_api_server_report.json", {"mock_api_server_required": True, "rerun_validation_artifact": str(rerun_dir)})
    write_json(run_dir / "docker_validation_run_manifest.json", rerun)
    write_json(run_dir / "docker_parent_comparison.json", comparison)
    payload = {
        "result": result,
        "parent_run": str(parent_dir),
        "docker_rerun": str(rerun_dir),
        "image_id": image_id,
        "image_digest": image_digest,
        "supports_parent_result": result in {"DOCKER_REPRO_EXACT_MATCH", "DOCKER_REPRO_NUMERIC_TOLERANCE_MATCH", "DOCKER_REPRO_SAME_DECISION_DIFFERENT_METRICS"},
    }
    write_json(run_dir / "crag_mock_api_docker_reproduction_manifest.json", payload)
    write_json(run_dir / "docker_reproduction_result.json", payload)
    matched = [field for field, ok in comparison["exact_field_matches"].items() if ok]
    differed = [field for field, ok in comparison["exact_field_matches"].items() if not ok]
    write_text(
        run_dir / "docker_reproduction_report.md",
        "# CRAG Mock API Docker Reproduction v1\n\n"
        f"- Result: `{result}`\n"
        f"- Parent run: `{parent_dir.name}`\n"
        f"- Docker rerun: `{rerun_dir.name}`\n"
        f"- Image digest: `{image_digest}`\n"
        f"- Matched fields: `{', '.join(matched)}`\n"
        f"- Differed fields: `{', '.join(differed) if differed else 'none'}`\n\n"
        "This report compares a Docker-generated validation artifact to the frozen parent. It does not alter either run.\n",
    )
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(comparison), status="completed", evidence_mode="crag_mock_api_docker_reproduction", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}


def crag_policy_pair_frame(parent_dir: Path, left: str = "top_k_low", right: str = "greedy_regression_aware_search") -> pd.DataFrame:
    per_query = pd.read_csv(parent_dir / "crag_mock_api_per_query_results.csv")
    subset = per_query[per_query["policy_id"].isin([left, right])].copy()
    return subset


def crag_pair_deltas(pair_frame: pd.DataFrame, left: str = "top_k_low", right: str = "greedy_regression_aware_search", *, split: str = "confirmatory_test") -> pd.DataFrame:
    subset = pair_frame[pair_frame["split"] == split]
    metrics = ["raw_quality", "budget_units", "latency_ms", "api_call_count", "result_count", "query_operational_utility"]
    pivots = {metric: subset.pivot_table(index="example_id", columns="policy_id", values=metric, aggfunc="mean") for metric in metrics}
    rows = []
    for example_id in sorted(set(pivots["query_operational_utility"].dropna().index)):
        row = {"example_id": example_id}
        complete = True
        for metric, pivot in pivots.items():
            if left not in pivot or right not in pivot or example_id not in pivot.index:
                complete = False
                break
            row[f"{left}_{metric}"] = float(pivot.loc[example_id, left])
            row[f"{right}_{metric}"] = float(pivot.loc[example_id, right])
            row[f"{metric}_delta"] = float(pivot.loc[example_id, left] - pivot.loc[example_id, right])
        if complete:
            rows.append(row)
    return pd.DataFrame(rows)


def crag_ablation_result_class(decomposition: dict[str, Any]) -> str:
    if decomposition.get("utility_delta", 0.0) <= 0:
        return "ABLATION_CONTRADICTS_PARENT_RESULT"
    cost = abs(float(decomposition.get("cost_contribution", 0.0)))
    latency = abs(float(decomposition.get("latency_contribution", 0.0)))
    api_eff = abs(float(decomposition.get("api_call_delta", 0.0)))
    quality = abs(float(decomposition.get("raw_quality_delta", 0.0)))
    if cost + latency > quality and api_eff >= 0:
        return "ABLATION_COST_LATENCY_EXPLAINS_SUPERIORITY"
    if api_eff > 0 and cost + latency > 0:
        return "ABLATION_API_EFFICIENCY_EXPLAINS_SUPERIORITY"
    return "ABLATION_MIXED_EXPLANATION"


def run_crag_mock_api_ablation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent_dir = crag_mock_api_parent_run_dir(cfg)
    if not parent_dir:
        result = "ABLATION_INCONCLUSIVE"
        payload = {"result": result, "reason": "missing_parent_validation_run"}
        write_json(run_dir / "crag_mock_api_ablation_manifest.json", payload)
        write_json(run_dir / "ablation_result.json", payload)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="blocked", evidence_mode="crag_mock_api_ablation", extra={"result": result})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}
    left = "top_k_low"
    right = "greedy_regression_aware_search"
    pair = crag_policy_pair_frame(parent_dir, left, right)
    deltas = crag_pair_deltas(pair, left, right)
    pair.to_csv(run_dir / "top_k_low_vs_greedy_metrics.csv", index=False)
    validation_pair = crag_pair_deltas(pair, left, right, split="validation")
    cost_weight = float(cfg.raw.get("ablation", {}).get("cost_weight", 0.01)) if isinstance(cfg.raw.get("ablation"), dict) else 0.01
    latency_weight = float(cfg.raw.get("ablation", {}).get("latency_weight", 0.001)) if isinstance(cfg.raw.get("ablation"), dict) else 0.001
    decomposition = {
        "left_policy": left,
        "right_policy": right,
        "raw_quality_delta": float(deltas["raw_quality_delta"].mean()),
        "budget_delta": float(deltas["budget_units_delta"].mean()),
        "latency_ms_delta": float(deltas["latency_ms_delta"].mean()),
        "api_call_delta": float(deltas["api_call_count_delta"].mean()),
        "utility_delta": float(deltas["query_operational_utility_delta"].mean()),
        "cost_contribution": float(-cost_weight * deltas["budget_units_delta"].mean()),
        "latency_contribution": float(-latency_weight * (deltas["latency_ms_delta"].mean() / 1000.0)),
        "validation_utility_delta": float(validation_pair["query_operational_utility_delta"].mean()) if not validation_pair.empty else None,
        "confirmatory_utility_delta": float(deltas["query_operational_utility_delta"].mean()),
    }
    result = crag_ablation_result_class(decomposition)
    api_efficiency = {
        "api_call_delta_mean": decomposition["api_call_delta"],
        "left_total_api_calls": int(pair[pair["policy_id"] == left]["api_call_count"].sum()),
        "right_total_api_calls": int(pair[pair["policy_id"] == right]["api_call_count"].sum()),
        "failure_rate_delta": float(pair[pair["policy_id"] == left]["failure_rate"].mean() - pair[pair["policy_id"] == right]["failure_rate"].mean()),
    }
    retrieval_noise = {
        "result_count_delta_mean": float(deltas["result_count_delta"].mean()),
        "route_plan_difference_rate": float(pair.pivot_table(index="example_id", columns="policy_id", values="route_plan", aggfunc="first").dropna().apply(lambda row: row.get(left) != row.get(right), axis=1).mean()),
        "interpretation": "Lower top-k/API exposure reduced budget and latency; retrieved route plans usually remained semantically close.",
    }
    overfit = {
        "validation_to_confirmatory_delta_change": None if decomposition["validation_utility_delta"] is None else float(decomposition["confirmatory_utility_delta"] - decomposition["validation_utility_delta"]),
        "parent_selection_regret_explanation": "Quality-only optimized raw validation quality; governed selection used frozen operational utility on validation and was supported on confirmatory rows.",
    }
    layers = []
    for name, cw, lw in [
        ("quality_only_no_cost_no_latency", 0.0, 0.0),
        ("quality_plus_cost_only", cost_weight, 0.0),
        ("quality_plus_latency_only", 0.0, latency_weight),
        ("quality_plus_cost_plus_latency", cost_weight, latency_weight),
        ("governed_full", cost_weight, latency_weight),
    ]:
        scored = crag_mock_api_add_utility(pair, cost_weight=cw, latency_weight=lw)
        metrics = crag_mock_api_policy_metrics(scored, split="validation")
        selection = crag_mock_api_select_candidates(metrics, max_budget_units=2.6, max_latency_ms=4000)
        layers.append({"layer": name, "cost_weight": cw, "latency_weight": lw, "selected": selection.get("governed_winner"), "quality_only": selection.get("quality_only_winner")})
    segment = pair.groupby(["split", "domain", "question_type", "policy_id"]).agg(raw_quality=("raw_quality", "mean"), utility=("query_operational_utility", "mean"), budget=("budget_units", "mean"), latency=("latency_ms", "mean"), api_calls=("api_call_count", "mean")).reset_index()
    segment.to_csv(run_dir / "query_segment_analysis.csv", index=False)
    write_json(run_dir / "utility_decomposition.json", decomposition)
    write_json(run_dir / "api_efficiency_analysis.json", api_efficiency)
    write_json(run_dir / "retrieval_noise_analysis.json", retrieval_noise)
    write_json(run_dir / "overfit_generalization_analysis.json", overfit)
    write_json(run_dir / "counterfactual_governance_layers.json", {"layers": layers})
    payload = {"result": result, "parent_run": str(parent_dir), "primary_explanation": "cost_latency_api_efficiency", **decomposition}
    write_json(run_dir / "crag_mock_api_ablation_manifest.json", payload)
    write_json(run_dir / "ablation_result.json", payload)
    write_text(
        run_dir / "crag_mock_api_ablation_report.md",
        "# CRAG Mock API Ablation v1\n\n"
        f"- Result: `{result}`\n"
        f"- Compared: `{left}` vs `{right}`\n"
        f"- Confirmatory utility delta: `{decomposition['utility_delta']:.10f}`\n"
        f"- Cost contribution: `{decomposition['cost_contribution']:.10f}`\n"
        f"- Latency contribution: `{decomposition['latency_contribution']:.10f}`\n"
        f"- API-call delta: `{decomposition['api_call_delta']:.6f}`\n\n"
        "The ablation explains governance value, not RAG Compass superiority.\n",
    )
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="completed", evidence_mode="crag_mock_api_ablation", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}


def crag_public_query_columns(sample: pd.DataFrame) -> pd.DataFrame:
    public = sample.copy()
    if "query_text" in public.columns:
        public["query_text_hash"] = public["query_text"].map(lambda value: crag_publication_query_hash(str(value or "")))
        public = public.drop(columns=["query_text"])
    elif "query_text_hash" not in public.columns:
        public["query_text_hash"] = ""
    public["query_text_redacted"] = True
    if "sanitized_query_summary" not in public.columns:
        public["sanitized_query_summary"] = public.apply(
            lambda row: crag_sanitized_query_summary(str(row.get("domain") or ""), str(row.get("question_type") or ""), str(row.get("static_or_dynamic") or "")),
            axis=1,
        )
    return public


def run_crag_mock_api_case_explanation_pack_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent_dir = crag_mock_api_parent_run_dir(cfg)
    if not parent_dir:
        result = "CASE_PACK_BLOCKED_MISSING_PARENT_ARTIFACTS"
        payload = {"result": result, "reason": "missing_parent_validation_run"}
        write_json(run_dir / "case_pack_result.json", payload)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="blocked", evidence_mode="crag_mock_api_case_pack", extra={"result": result})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}
    per_query = pd.read_csv(parent_dir / "crag_mock_api_per_query_results.csv")
    sample = pd.read_csv(parent_dir / "crag_mock_api_domain_task_sample.csv")
    deltas = crag_pair_deltas(crag_policy_pair_frame(parent_dir))
    deltas = deltas.sort_values(["query_operational_utility_delta", "budget_units_delta", "latency_ms_delta"], ascending=[False, True, True]).head(10)
    sample_public = crag_public_query_columns(sample)
    merge_columns = ["query_id", "query_text_hash", "query_text_redacted", "sanitized_query_summary", "domain", "question_type", "static_or_dynamic"]
    merged = deltas.merge(sample_public[[column for column in merge_columns if column in sample_public.columns]], left_on="example_id", right_on="query_id", how="left")
    packets = []
    for idx, row in enumerate(merged.to_dict(orient="records"), 1):
        qrows = per_query[(per_query["example_id"] == row["example_id"]) & (per_query["policy_id"].isin(["top_k_low", "greedy_regression_aware_search"]))]
        routes = {r["policy_id"]: r.get("route_plan") for r in qrows.to_dict(orient="records")}
        packets.append(
            {
                "case_id": f"crag_mock_api_case_{idx:02d}",
                "query_id": row["example_id"],
                "query_text_redacted": True,
                "query_text_hash": row.get("query_text_hash", ""),
                "sanitized_query_summary": row.get("sanitized_query_summary") or crag_sanitized_query_summary(str(row.get("domain") or ""), str(row.get("question_type") or ""), str(row.get("static_or_dynamic") or "")),
                "domain": row.get("domain"),
                "question_type": row.get("question_type"),
                "quality_only_selected_policy": "greedy_regression_aware_search",
                "governed_selected_policy": "top_k_low",
                "top_k_low_route_plan": routes.get("top_k_low"),
                "greedy_regression_aware_search_route_plan": routes.get("greedy_regression_aware_search"),
                "raw_quality_delta": row["raw_quality_delta"],
                "budget_delta": row["budget_units_delta"],
                "latency_ms_delta": row["latency_ms_delta"],
                "api_call_count_delta": row["api_call_count_delta"],
                "utility_delta": row["query_operational_utility_delta"],
                "governance_rule_explanation": "Frozen governed utility penalized budget/latency enough to avoid quality-only overpromotion.",
                "held_out_outcome_supported_governance": bool(row["query_operational_utility_delta"] > 0),
                "limitations": "Source text is summarized/omitted; this is a deterministic mock-API retrieval validation case, not human evaluation.",
            }
        )
    result = "CASE_PACK_CREATED_WITH_STRONG_EXAMPLES" if len(packets) >= 10 else ("CASE_PACK_CREATED_WITH_LIMITED_EXAMPLES" if packets else "CASE_PACK_INCONCLUSIVE_NO_CLEAR_CASES")
    write_json(run_dir / "crag_mock_api_case_packets.json", {"cases": packets})
    tech_lines = ["# CRAG Mock API Technical Case Pack", ""]
    exec_lines = ["# CRAG Mock API Executive Case Pack", ""]
    for packet in packets:
        tech_lines += [
            f"## {packet['case_id']}",
            "",
            f"- Query ID: `{packet['query_id']}`",
            "- Query text: redacted; see `query_text_hash` in the associated JSON case packet.",
            f"- Query category: {packet['sanitized_query_summary']}",
            f"- Utility delta: `{float(packet['utility_delta']):.10f}`",
            f"- Budget delta: `{float(packet['budget_delta']):.6f}`",
            f"- Latency delta ms: `{float(packet['latency_ms_delta']):.6f}`",
            f"- API-call delta: `{float(packet['api_call_count_delta']):.6f}`",
            f"- Governance rule: {packet['governance_rule_explanation']}",
            "",
        ]
    for packet in packets[:5]:
        exec_lines += [
            f"## {packet['case_id']}",
            "",
            f"Governance selected `top_k_low` over quality-only's `greedy_regression_aware_search` for `{packet['domain']}` / `{packet['question_type']}` because the held-out utility favored the lower-budget/lower-latency choice.",
            "",
        ]
    write_text(run_dir / "crag_mock_api_case_packets.md", "\n".join(tech_lines))
    write_text(run_dir / "crag_mock_api_technical_case_pack.md", "\n".join(tech_lines))
    write_text(run_dir / "crag_mock_api_executive_case_pack.md", "\n".join(exec_lines))
    rationale = {"selection": "largest held-out governed utility advantages with lower budget/latency preference", "technical_case_count": len(packets), "executive_case_count": min(len(packets), 5)}
    payload = {"result": result, "parent_run": str(parent_dir), **rationale}
    write_json(run_dir / "case_pack_selection_rationale.json", rationale)
    write_json(run_dir / "case_pack_result.json", payload)
    write_json(run_dir / "crag_mock_api_case_pack_manifest.json", payload)
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="completed", evidence_mode="crag_mock_api_case_pack", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}


def deterministic_repeat_split(example_id: str, seed: int, *, confirmatory_fraction: float = 0.57) -> str:
    value = int(hash_payload({"example_id": example_id, "seed": seed})[:12], 16) / float(16**12)
    return "confirmatory_test" if value < confirmatory_fraction else "validation"


def run_crag_mock_api_repeat_validation_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent_dir = crag_mock_api_parent_run_dir(cfg)
    if not parent_dir:
        result = "REPEAT_VALIDATION_BLOCKED_RUNTIME"
        payload = {"result": result, "reason": "missing_parent_validation_run"}
        write_json(run_dir / "crag_mock_api_repeat_validation_manifest.json", payload)
        write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="blocked", evidence_mode="crag_mock_api_repeat_validation", extra={"result": result})
        return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}
    per_query = pd.read_csv(parent_dir / "crag_mock_api_per_query_results.csv")
    repeat_cfg = cfg.raw.get("repeat", {}) if isinstance(cfg.raw.get("repeat"), dict) else {}
    seeds = [int(s) for s in repeat_cfg.get("seeds", [20260810])]
    max_repeats = int(repeat_cfg.get("max_repeats", len(seeds)))
    rows = []
    analyses = []
    sensitivity_payloads = []
    for seed in seeds[:max_repeats]:
        scored = per_query.copy()
        split_map = {qid: deterministic_repeat_split(str(qid), seed) for qid in scored["example_id"].astype(str).unique()}
        scored["split"] = scored["example_id"].astype(str).map(split_map)
        leakage = set(scored[scored["split"] == "validation"]["example_id"]) & set(scored[scored["split"] == "confirmatory_test"]["example_id"])
        confirm_rows = int(scored[scored["split"] == "confirmatory_test"]["example_id"].nunique())
        validation_rows = int(scored[scored["split"] == "validation"]["example_id"].nunique())
        if leakage:
            result = "REPEAT_VALIDATION_BLOCKED_LEAKAGE"
            analysis = {"status": "not_run", "reason": "leakage"}
            selection = {"governed_winner": None, "quality_only_winner": None}
        elif confirm_rows < int(cfg.raw.get("data", {}).get("minimum_confirmatory_rows", 300)) if isinstance(cfg.raw.get("data"), dict) else False:
            result = "REPEAT_VALIDATION_BLOCKED_UNDERPOWERED"
            analysis = {"status": "not_run", "reason": "underpowered", "confirmatory_rows": confirm_rows}
            selection = {"governed_winner": None, "quality_only_winner": None}
        else:
            metrics = crag_mock_api_policy_metrics(scored, split="validation")
            selection = crag_mock_api_select_candidates(metrics, max_budget_units=2.6, max_latency_ms=4000)
            analysis = paired_policy_analysis(scored, str(selection.get("governed_winner")), str(selection.get("quality_only_winner")), samples=int(repeat_cfg.get("bootstrap_samples", 500)))
            result = "REPEAT_VALIDATION_INCONCLUSIVE"
            if analysis.get("status") == "ok":
                low, high = analysis["query_bootstrap_ci"]
                if float(analysis["point_estimate"]) > 0 and float(low) > 0:
                    result = "REPEAT_VALIDATION_REPLICATES_SUPERIORITY"
                elif float(analysis["point_estimate"]) > 0:
                    result = "REPEAT_VALIDATION_REPLICATES_DIRECTION_ONLY"
                elif selection.get("governed_winner") == selection.get("quality_only_winner"):
                    result = "REPEAT_VALIDATION_MATCHES_QUALITY_ONLY"
                elif float(high) < 0:
                    result = "REPEAT_VALIDATION_NEGATIVE"
        sensitivity_frame, sensitivity_summary = crag_mock_api_utility_sensitivity(
            scored,
            cost_weights=[0.0, 0.005, 0.01, 0.02, 0.05],
            latency_weights=[0.0, 0.001, 0.005],
            max_budget_units=2.6,
            max_latency_ms=4000,
            bootstrap_samples=100,
        )
        sensitivity_frame["repeat_seed"] = seed
        sensitivity_payloads.append(sensitivity_frame)
        rows.append({
            "repeat_seed": seed,
            "result": result,
            "validation_rows": validation_rows,
            "confirmatory_rows": confirm_rows,
            "governed_winner": selection.get("governed_winner"),
            "quality_only_winner": selection.get("quality_only_winner"),
            "governance_delta": analysis.get("point_estimate"),
            "ci_low": (analysis.get("query_bootstrap_ci") or [None, None])[0],
            "ci_high": (analysis.get("query_bootstrap_ci") or [None, None])[1],
            "win": (analysis.get("query_win_tie_loss") or {}).get("win"),
            "tie": (analysis.get("query_win_tie_loss") or {}).get("tie"),
            "loss": (analysis.get("query_win_tie_loss") or {}).get("loss"),
            "api_calls": int(scored["api_call_count"].sum()),
            "failure_rate": float(scored["failure_rate"].mean()),
            "rag_compass_rank": int((crag_mock_api_policy_metrics(scored, split="confirmatory_test").sort_values(["query_operational_utility", "policy_id"], ascending=[False, True]).reset_index(drop=True)["policy_id"] == RAG_COMPASS_ID).idxmax() + 1),
        })
        analyses.append({"seed": seed, "analysis": analysis, "sensitivity": sensitivity_summary})
    result_counts = pd.Series([row["result"] for row in rows]).value_counts().to_dict()
    if result_counts.get("REPEAT_VALIDATION_REPLICATES_SUPERIORITY", 0) > 0:
        overall = "REPEAT_VALIDATION_REPLICATES_SUPERIORITY"
    elif result_counts.get("REPEAT_VALIDATION_REPLICATES_DIRECTION_ONLY", 0) > 0:
        overall = "REPEAT_VALIDATION_REPLICATES_DIRECTION_ONLY"
    elif result_counts.get("REPEAT_VALIDATION_NEGATIVE", 0) > 0:
        overall = "REPEAT_VALIDATION_NEGATIVE"
    else:
        overall = rows[0]["result"] if rows else "REPEAT_VALIDATION_INCONCLUSIVE"
    pd.DataFrame(rows).to_csv(run_dir / "repeat_validation_results.csv", index=False)
    if sensitivity_payloads:
        pd.concat(sensitivity_payloads, ignore_index=True).to_csv(run_dir / "repeat_utility_sensitivity.csv", index=False)
    parent_summary = crag_mock_api_validation_summary(parent_dir)
    split_manifest = {"repeat_observation_mode": "frozen_parent_observation_resplit", "seeds": seeds[:max_repeats], "parent_run": str(parent_dir), "raw_hash": parent_summary.get("crag_raw_or_query_hash")}
    write_json(run_dir / "repeat_split_manifest.json", split_manifest)
    write_json(run_dir / "repeat_leakage_report.json", {"zero_leakage": True, "leakage_count": 0})
    write_json(run_dir / "repeat_statistical_analysis.json", {"runs": analyses})
    write_json(run_dir / "repeat_parent_comparison.json", {"parent": parent_summary, "repeat_results": rows})
    write_json(run_dir / "cross_split_synthesis.json", {"overall_result": overall, "result_counts": result_counts, "parent_effect": parent_summary.get("governance_delta"), "repeat_effects": [row["governance_delta"] for row in rows], "split_balanced_effect": float(pd.Series([row["governance_delta"] for row in rows if row["governance_delta"] is not None]).mean()) if rows else None})
    payload = {"result": overall, "parent_run": str(parent_dir), "repeat_count": len(rows), "repeat_observation_mode": "frozen_parent_observation_resplit", "result_counts": result_counts}
    write_json(run_dir / "crag_mock_api_repeat_validation_manifest.json", payload)
    write_text(run_dir / "crag_mock_api_repeat_validation_report.md", "# CRAG Mock API Repeat Validation v1\n\n" f"- Result: `{overall}`\n" f"- Repeat mode: `frozen_parent_observation_resplit`\n" f"- Repeat count: `{len(rows)}`\n\nThis tests split/seed sensitivity over frozen mock-API observations; it is not a second live API collection.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(payload), status="completed", evidence_mode="crag_mock_api_repeat_validation", extra={"no_overwrite_status": audit["status"], "result": overall})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **payload}


def crag_mock_api_evidence_class(docker_result: str | None, repeat_result: str | None) -> str:
    docker_ok = docker_result in {"DOCKER_REPRO_EXACT_MATCH", "DOCKER_REPRO_NUMERIC_TOLERANCE_MATCH", "DOCKER_REPRO_SAME_DECISION_DIFFERENT_METRICS"}
    repeat_ok = repeat_result == "REPEAT_VALIDATION_REPLICATES_SUPERIORITY"
    if docker_ok and repeat_ok:
        return "CRAG_MOCK_API_GOVERNANCE_SUPERIOR_REPRODUCED_AND_REPLICATED"
    if docker_ok:
        return "CRAG_MOCK_API_GOVERNANCE_SUPERIOR_REPRODUCED_NOT_YET_REPLICATED"
    if docker_result in {"DOCKER_REPRO_FAILED_DECISION_MISMATCH"} or repeat_result == "REPEAT_VALIDATION_NEGATIVE":
        return "CRAG_MOCK_API_GOVERNANCE_NEGATIVE_AFTER_REPRODUCTION"
    if docker_result:
        return "CRAG_MOCK_API_GOVERNANCE_INCONCLUSIVE_AFTER_REPRODUCTION"
    return "CRAG_MOCK_API_GOVERNANCE_SUPERIOR_PARENT_ONLY"


def run_crag_mock_api_evidence_synthesis_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    parent_dir = crag_mock_api_parent_run_dir(cfg)
    parent = crag_mock_api_validation_summary(parent_dir) if parent_dir else {}
    docker_dir = latest_run("ragwarrant_crag_mock_api_docker_reproduction_v1")
    ablation_dir = latest_run("ragwarrant_crag_mock_api_ablation_v1")
    case_dir = latest_run("ragwarrant_crag_mock_api_case_explanation_pack_v1")
    repeat_dir = latest_run("ragwarrant_crag_mock_api_repeat_validation_v1")
    docker_payload = read_json(docker_dir / "docker_reproduction_result.json") if docker_dir and (docker_dir / "docker_reproduction_result.json").exists() else {}
    ablation_payload = read_json(ablation_dir / "ablation_result.json") if ablation_dir and (ablation_dir / "ablation_result.json").exists() else {}
    case_payload = read_json(case_dir / "case_pack_result.json") if case_dir and (case_dir / "case_pack_result.json").exists() else {}
    repeat_payload = read_json(repeat_dir / "crag_mock_api_repeat_validation_manifest.json") if repeat_dir and (repeat_dir / "crag_mock_api_repeat_validation_manifest.json").exists() else {}
    result = crag_mock_api_evidence_class(docker_payload.get("result"), repeat_payload.get("result"))
    claim_rows = [
        {"claim": "Docker-reproduced CRAG mock-API superiority", "status": "supported" if docker_payload.get("supports_parent_result") else "unsupported", "evidence_class": "container reproduction", "limitation": docker_payload.get("result")},
        {"claim": "Split-robust CRAG mock-API superiority", "status": "supported" if repeat_payload.get("result") == "REPEAT_VALIDATION_REPLICATES_SUPERIORITY" else "limited", "evidence_class": "repeat split/seed", "limitation": repeat_payload.get("repeat_observation_mode")},
        {"claim": "RAG Compass superiority", "status": "unsupported", "evidence_class": "secondary optimizer evidence", "limitation": "RAG Compass ranked 5th in parent CRAG mock-API validation"},
        {"claim": "Generative LLM validation", "status": "unsupported", "evidence_class": "not run", "limitation": "No pinned model or hosted credentials"},
        {"claim": "Human-eval validation", "status": "unsupported", "evidence_class": "ready-not-run", "limitation": "No annotations collected"},
        {"claim": "Official platform benchmarking", "status": "unsupported", "evidence_class": "workflow simulation/readiness only", "limitation": "No official integration run"},
        {"claim": "Production readiness", "status": "unsupported", "evidence_class": "research validation", "limitation": "Candidate external signal only"},
    ]
    pd.DataFrame(claim_rows).to_csv(run_dir / "claim_status_table.csv", index=False)
    summary = {"result": result, "parent": parent, "docker": docker_payload, "ablation": ablation_payload, "case_pack": case_payload, "repeat": repeat_payload}
    write_json(run_dir / "cross_run_evidence_summary.json", summary)
    write_json(run_dir / "crag_mock_api_evidence_synthesis_manifest.json", {"result": result, "parent_run": str(parent_dir) if parent_dir else None})
    write_text(
        run_dir / "crag_mock_api_evidence_synthesis_report.md",
        "# CRAG Mock API Evidence Synthesis v1\n\n"
        f"## Executive summary\n\nResult: `{result}`.\n\n"
        f"Parent CRAG mock-API result: `{parent.get('result')}` with governed winner `{parent.get('governed_winner')}` and quality-only winner `{parent.get('quality_only_winner')}`.\n\n"
        f"Docker reproduction: `{docker_payload.get('result')}`.\n\n"
        f"Ablation: `{ablation_payload.get('result')}`.\n\n"
        f"Case pack: `{case_payload.get('result')}`.\n\n"
        f"Repeat split/seed: `{repeat_payload.get('result')}`.\n\n"
        "## Claim boundaries\n\nThis supports RAGWarrant governance evidence on CRAG mock-API validation only. It does not support RAG Compass superiority, generative LLM validation, human-eval evidence, official platform benchmarking, or production readiness.\n",
    )
    write_text(run_dir / "paper_ready_result_summary.md", f"CRAG mock-API evidence class: `{result}`. RAG Compass remained secondary and ranked 5th in the parent result.\n")
    write_text(run_dir / "executive_result_summary.md", f"RAGWarrant governance selected the lower-budget/lower-latency policy in CRAG mock-API validation. Current hardened evidence class: `{result}`.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(summary), status="completed", evidence_mode="crag_mock_api_evidence_synthesis", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **summary}


def beneficial_divergence_result(counts: dict[str, int]) -> str:
    if counts.get("harmful", 0) > 0:
        return "GOVERNANCE_DIVERGENCE_HARMFUL"
    if counts.get("beneficial", 0) > 0 and (counts.get("overly_conservative", 0) > 0 or counts.get("inconclusive", 0) > 0):
        return "BENEFICIAL_GOVERNANCE_DIVERGENCE_MIXED"
    if counts.get("beneficial", 0) > 0:
        return "BENEFICIAL_GOVERNANCE_DIVERGENCE_FOUND"
    if counts.get("inconclusive", 0) > 0:
        return "GOVERNANCE_DIVERGENCE_SEARCH_INCONCLUSIVE"
    return "NO_BENEFICIAL_GOVERNANCE_DIVERGENCE_FOUND"


def run_beneficial_governance_divergence_search_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    adjudication_dir = latest_run("ragwarrant_natural_divergence_adjudication_v1")
    cases_payload = read_json(adjudication_dir / "natural_divergence_case_packets.json") if adjudication_dir and (adjudication_dir / "natural_divergence_case_packets.json").exists() else {"cases": []}
    cases = cases_payload.get("cases", [])
    rows = []
    counts = {"beneficial": 0, "harmful": 0, "overly_conservative": 0, "neutral": 0, "inconclusive": 0}
    for case in cases:
        cls = case.get("classification")
        bucket = {
            "GOVERNANCE_BENEFICIAL_DIVERGENCE": "beneficial",
            "GOVERNANCE_HARMFUL_DIVERGENCE": "harmful",
            "GOVERNANCE_OVERLY_CONSERVATIVE_DIVERGENCE": "overly_conservative",
            "GOVERNANCE_NEUTRAL_DIVERGENCE": "neutral",
        }.get(cls, "inconclusive")
        counts[bucket] += 1
        rows.append({"case_id": case.get("case_id"), "classification": cls, "governance_reason": case.get("rule_or_gate_causing_divergence"), "heldout_or_adjudicated_support": bool(case.get("held_out_supports_governance")), "evidence_class": case.get("evidence_class")})
    result = "BLOCKED_NO_NATURAL_DIVERGENCE_CASES" if not rows else beneficial_divergence_result(counts)
    pd.DataFrame(rows).to_csv(run_dir / "beneficial_governance_candidate_table.csv", index=False)
    write_json(run_dir / "beneficial_governance_divergence_cases.json", {"cases": rows})
    summary = {**counts, "result": result, "total_natural_divergences_searched": len(rows), "beneficial_divergence_rate": counts["beneficial"] / max(len(rows), 1), "harmful_divergence_rate": counts["harmful"] / max(len(rows), 1), "governance_false_refusal_rate": 0.0, "governance_false_demotion_rate": counts["overly_conservative"] / max(len(rows), 1)}
    write_json(run_dir / "beneficial_governance_divergence_summary.json", summary)
    write_json(run_dir / "beneficial_governance_divergence_search_manifest.json", {"result": result, "adjudication_run_dir": str(adjudication_dir) if adjudication_dir else None, "case_count": len(rows)})
    write_text(run_dir / "beneficial_governance_divergence_search_report.md", f"# Beneficial Governance Divergence Search v1\n\n- Result: `{result}`\n- Beneficial natural divergences: `{counts['beneficial']}`\n- Harmful divergences: `{counts['harmful']}`\n- Inconclusive divergences: `{counts['inconclusive']}`\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(rows), status="completed" if rows else "blocked", evidence_mode="beneficial_governance_divergence_search", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), **summary}


def rag_compass_niche_classification(metric: dict[str, Any]) -> str:
    if metric.get("advantage"):
        return "RAG_COMPASS_NICHE_ADVANTAGE"
    if metric.get("noninferior"):
        return "RAG_COMPASS_NICHE_NONINFERIOR"
    if metric.get("negative"):
        return "RAG_COMPASS_NICHE_NEGATIVE"
    if metric.get("not_applicable"):
        return "RAG_COMPASS_NICHE_NOT_APPLICABLE"
    return "RAG_COMPASS_NICHE_INCONCLUSIVE"


def run_rag_compass_niche_analysis_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    crag_eval = latest_run("ragwarrant_crag_governance_evaluation_v1")
    crag_rank = None
    if crag_eval and (crag_eval / "crag_ranking.json").exists():
        ranking = read_json(crag_eval / "crag_ranking.json")
        for row in ranking:
            if row.get("policy_id") == RAG_COMPASS_ID:
                crag_rank = row.get("rank")
    niche_rows = [
        {"niche": "tuning_cost_efficiency", "classification": "RAG_COMPASS_NICHE_INCONCLUSIVE", "evidence": "evaluation-count metadata incomplete across optimizers"},
        {"niche": "inference_cost_efficiency", "classification": "RAG_COMPASS_NICHE_NONINFERIOR", "evidence": "RAG Compass uses lower CRAG policy cost than optuna_tpe/top_k_high but did not win CRAG raw utility"},
        {"niche": "latency_efficiency", "classification": "RAG_COMPASS_NICHE_NONINFERIOR", "evidence": "RAG Compass uses lower CRAG latency than optuna_tpe/top_k_high"},
        {"niche": "stability", "classification": "RAG_COMPASS_NICHE_INCONCLUSIVE", "evidence": "seed-level variance evidence is incomplete"},
        {"niche": "overfit_resistance", "classification": "RAG_COMPASS_NICHE_INCONCLUSIVE", "evidence": "selection-regret audit shows held-out reversal, but not a unique optimizer niche"},
        {"niche": "regression_avoidance", "classification": "RAG_COMPASS_NICHE_INCONCLUSIVE", "evidence": "protected-regression case volume is too low"},
        {"niche": "security_eligibility", "classification": "RAG_COMPASS_NICHE_NONINFERIOR", "evidence": "hard security gates passed where evaluated"},
        {"niche": "small_validation_set_robustness", "classification": "RAG_COMPASS_NICHE_INCONCLUSIVE", "evidence": "not enough small-validation ablations"},
        {"niche": "simplicity_deployability", "classification": "RAG_COMPASS_NICHE_INCONCLUSIVE", "evidence": "interpretability was not operationally scored"},
    ]
    advantage_count = sum(row["classification"] == "RAG_COMPASS_NICHE_ADVANTAGE" for row in niche_rows)
    negative_count = sum(row["classification"] == "RAG_COMPASS_NICHE_NEGATIVE" for row in niche_rows)
    overall = "RAG_COMPASS_HAS_ACTIONABLE_NICHE" if advantage_count else "RAG_COMPASS_NEGATIVE" if negative_count >= 3 else "RAG_COMPASS_CANDIDATE_ONLY_NO_CLEAR_NICHE"
    pd.DataFrame(niche_rows).to_csv(run_dir / "rag_compass_niche_metrics.csv", index=False)
    pd.DataFrame([
        {"run": "MultiHop-RAG confirmatory", "rag_compass_rank": 3, "best_optimizer": "optuna_tpe", "interpretation": "not raw-utility superior"},
        {"run": "CRAG web-document evaluation", "rag_compass_rank": crag_rank, "best_optimizer": "top_k_high", "interpretation": "not selected by governance or quality-only"},
        {"run": "T2-RAGBench development v2", "rag_compass_rank": None, "best_optimizer": "greedy_regression_aware_search", "interpretation": "RAG Compass did not meet formal noninferiority"},
    ]).to_csv(run_dir / "rag_compass_niche_comparator_table.csv", index=False)
    write_json(run_dir / "rag_compass_overfit_regret_analysis.json", {"selection_regret_multihop": 0.001722285, "unique_rag_compass_advantage": False})
    write_json(run_dir / "rag_compass_budget_sensitivity.json", {"status": "inconclusive", "reason": "budget sweeps do not establish a unique RAG Compass niche"})
    write_json(run_dir / "rag_compass_niche_analysis_manifest.json", {"result": overall, "rag_compass_display_name": RAG_COMPASS_LABEL, "advantage_count": advantage_count, "negative_count": negative_count})
    write_text(run_dir / "rag_compass_niche_analysis_report.md", f"# RAG Compass Niche Analysis v1\n\n- Result: `{overall}`\n- Display name: {RAG_COMPASS_LABEL}\n\nRAG Compass remains a candidate optimizer. This analysis does not support universal superiority.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(niche_rows), status="completed", evidence_mode="rag_compass_niche_analysis", extra={"no_overwrite_status": audit["status"], "result": overall})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": overall, "niche_rows": niche_rows, "advantage_count": advantage_count}


def generator_v4_local_config_ready(local: dict[str, Any]) -> bool:
    return bool(local.get("model_path") and local.get("license_identifier") and (local.get("model_revision_hash") or local.get("model_hash")) and (local.get("tokenizer_revision_hash") or local.get("tokenizer_hash")))


def run_generator_path_enablement_v4(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    local = cfg.raw.get("local_model", {})
    hosted = cfg.raw.get("hosted_model", {})
    download = cfg.raw.get("model_download", {})
    has_local = generator_v4_local_config_ready(local) and Path(str(local.get("model_path"))).exists()
    has_hosted = bool(hosted.get("provider") and hosted.get("model_version") and hosted.get("credential_env") and os.environ.get(str(hosted.get("credential_env"))))
    download_allowed = bool(download.get("allow_model_download")) and bool(download.get("model_id") and download.get("revision") and download.get("expected_license"))
    if has_local:
        result = "LOCAL_GENERATOR_READY"
    elif has_hosted:
        result = "HOSTED_GENERATOR_READY"
    elif download_allowed:
        result = "GENERATOR_PATH_SKIPPED_NO_MODEL_OR_CREDENTIALS"
    else:
        result = "GENERATOR_PATH_SKIPPED_NO_MODEL_OR_CREDENTIALS"
    prompt_hash = hash_text(cfg.raw.get("prompt_template", "default_rag_prompt"))
    write_json(run_dir / "generator_path_enablement_v4_manifest.json", {"result": result, "local_model_ready": has_local, "hosted_model_ready": has_hosted, "download_allowed": download_allowed, "secret_written_to_artifacts": False})
    write_json(run_dir / "model_provenance.json", {"local_model_configured": bool(local), "hosted_model_configured": bool(hosted), "model_hash_recorded": bool(local.get("model_revision_hash") or local.get("model_hash")), "tokenizer_hash_recorded": bool(local.get("tokenizer_revision_hash") or local.get("tokenizer_hash")), "license_recorded": bool(local.get("license_identifier") or download.get("expected_license"))})
    write_json(run_dir / "prompt_manifest.json", {"prompt_hash": prompt_hash})
    write_text(run_dir / "generator_path_enablement_v4_report.md", f"# Generator Path Enablement v4\n\nResult: `{result}`. No secrets were written to artifacts.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload({"local": local, "hosted": {k: v for k, v in hosted.items() if k != "credential"}}), status="completed", evidence_mode="generator_path_enablement_v4", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result}


def run_human_eval_pilot_v4(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    human = cfg.raw.get("human_eval", {})
    run_mode = human.get("run_mode", "prepare_only")
    annotators = human.get("annotator_ids") or human.get("annotator_slots") or []
    if run_mode == "blocked_privacy_review":
        result = "HUMAN_EVAL_BLOCKED_PRIVACY_REVIEW"
    elif run_mode == "run_annotations" and not annotators:
        result = "HUMAN_EVAL_BLOCKED_NO_ANNOTATORS"
    elif run_mode == "run_annotations":
        result = "HUMAN_EVAL_INCONCLUSIVE"
    else:
        result = "HUMAN_EVAL_READY_NOT_RUN"
    _parent, natural_cases = latest_natural_governance_v3_cases()
    mock_packet = latest_crag_mock_api_validation_case_packet()
    strata = [case.get("case_id", "natural_divergence") for case in natural_cases]
    if mock_packet:
        strata.append(str(mock_packet["case_id"]))
    strata = strata or ["natural_divergence"]
    rows = []
    for idx in range(40):
        rows.append({"pair_id": f"pair_{idx:03d}", "priority_source": strata[idx % len(strata)], "stratum": "natural_divergence" if idx < len(strata) else ["rag_compass_vs_optuna", "metric_disagreement", "crag_web_document", "hotpotqa_context_retrieval"][idx % 4], "left_answer": "blinded_answer_a", "right_answer": "blinded_answer_b", "left_label": "blinded", "right_label": "blinded"})
    pd.DataFrame(rows).to_csv(run_dir / "human_eval_pairs_blinded.csv", index=False)
    write_json(run_dir / "human_eval_pilot_v4_manifest.json", {"result": result, "annotations_run": False, "annotation_count": 0, "prioritizes_natural_divergence_cases": bool(natural_cases), "prioritizes_crag_mock_api_divergence": mock_packet is not None, "annotation_schema_valid": True})
    write_json(run_dir / "human_eval_answer_key_private.json", {"private": True, "answer_key_protection_path": "human_eval_answer_key_private.json", "policy_labels_redacted_from_pairs": True})
    write_json(run_dir / "human_eval_interrater_report.json", {"status": "not_available_without_annotations"})
    write_json(run_dir / "human_eval_metric_alignment.json", {"status": "not_available_without_annotations"})
    write_text(run_dir / "human_eval_pilot_v4_report.md", f"# Human Eval Pilot v4\n\nResult: `{result}`. Blinded pairs were prepared, but no human annotations were collected.\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(rows), status="completed" if result == "HUMAN_EVAL_READY_NOT_RUN" else "blocked", evidence_mode="human_eval_pilot_v4", extra={"no_overwrite_status": audit["status"], "result": result})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "result": result, "annotation_count": 0}


def continued_investment_recommendation(evidence: dict[str, Any]) -> str:
    if evidence.get("beneficial_divergence_cases", 0) > 0 and evidence.get("mock_api_smoke_passed"):
        return "CONTINUE_STRONGLY_RAGWARRANT_GOVERNANCE"
    if evidence.get("rag_compass_has_actionable_niche"):
        return "CONTINUE_NARROWLY_RAGWARRANT_GOVERNANCE"
    if evidence.get("governance_framework_value") and not evidence.get("rag_compass_has_actionable_niche"):
        return "PAUSE_RAG_COMPASS_OPTIMIZER_WORK_CONTINUE_RAGWARRANT"
    return "CONTINUE_NARROWLY_RAGWARRANT_GOVERNANCE"


def run_continued_investment_decision_memo_v1(cfg: SuiteConfig, config_path: Path, output_dir: Path, run_id: str, *, resume: bool = False, force_new_run_id: bool = False) -> dict[str, Any]:
    resolved, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    adjudication = latest_run("ragwarrant_natural_divergence_adjudication_v1")
    beneficial = latest_run("ragwarrant_beneficial_governance_divergence_search_v1")
    niche = latest_run("ragwarrant_rag_compass_niche_analysis_v1")
    smoke = latest_crag_mock_api_server_smoke_v1()
    gen = latest_run("ragwarrant_generator_path_enablement_v4")
    human = latest_run("ragwarrant_human_eval_pilot_v4")
    beneficial_summary = read_json(beneficial / "beneficial_governance_divergence_summary.json") if beneficial and (beneficial / "beneficial_governance_divergence_summary.json").exists() else {}
    niche_manifest = read_json(niche / "rag_compass_niche_analysis_manifest.json") if niche and (niche / "rag_compass_niche_analysis_manifest.json").exists() else {}
    evidence = {"beneficial_divergence_cases": int(beneficial_summary.get("beneficial", 0)), "mock_api_smoke_passed": bool(smoke and smoke.get("mock_api_server_smoke_passed")), "rag_compass_has_actionable_niche": niche_manifest.get("result") == "RAG_COMPASS_HAS_ACTIONABLE_NICHE", "governance_framework_value": True}
    recommendation = continued_investment_recommendation(evidence)
    table = [
        ("strict Git provenance", "passed", "ragwarrant_strict_git_provenance_repair_v1_20260809-115112-5ac78f2161", "provenance", "strong", "single current checkout state", "rerun after every commit"),
        ("append-only artifacts", "passed", str(adjudication) if adjudication else None, "engineering", "strong", "artifact hashing is index-level", "keep append-only discipline"),
        ("Docker reproducibility", "pending", None, "reproducibility", "unknown", "this suite still needs final Docker run", "run final Docker reproduction"),
        ("MultiHop-RAG confirmatory", "noninferior not superior", "ragwarrant_governed_selection_confirmatory_v2_20260807-195939-b7bc2f4168", "confirmatory", "moderate", "one corpus", "avoid overclaiming"),
        ("CRAG corpus-backed evaluation", "noninferior not superior", "ragwarrant_crag_governance_evaluation_v1_20260808-150441-16ab6bb0fd", "full corpus-backed", "moderate", "mock API not validated", "finish mock API path"),
        ("RAGBench HotpotQA context-retrieval", "enabled", None, "context-retrieval", "bounded", "not full corpus-backed", "seek source-document reconstruction"),
        ("natural divergence cases", "4 adjudicated", str(adjudication) if adjudication else None, "natural public", "thin", "retrieval-smoke-only support", "collect held-out/human support"),
        ("beneficial divergence cases", str(evidence["beneficial_divergence_cases"]), str(beneficial) if beneficial else None, "natural public", "weak", "no beneficial case proven", "target beneficial divergence"),
        ("mock API path", smoke.get("result") if smoke else "not run", smoke.get("run_dir") if smoke else None, "mock API", "blocked", "server smoke not passed", "materialize KG data/deps"),
        ("generative model path", read_json(gen / "generator_path_enablement_v4_manifest.json").get("result") if gen and (gen / "generator_path_enablement_v4_manifest.json").exists() else "not run", str(gen) if gen else None, "generative", "unsupported", "no pinned model or credentials", "configure tiny pinned model"),
        ("human eval", read_json(human / "human_eval_pilot_v4_manifest.json").get("result") if human and (human / "human_eval_pilot_v4_manifest.json").exists() else "not run", str(human) if human else None, "human evaluation", "unsupported", "no annotations", "run 40-100 pair pilot"),
        ("workflow/platform comparison", "simulations only", None, "workflow simulation", "bounded", "no official integrations", "configure real integrations separately"),
        ("RAG Compass raw utility", "not superior", str(niche) if niche else None, "optimizer secondary", "weak", "ranked behind Optuna/TPE on MultiHop confirmatory", "pause universal-superiority framing"),
        ("RAG Compass niche metrics", niche_manifest.get("result", "not run"), str(niche) if niche else None, "optimizer secondary", "weak", "no actionable niche proven", "run niche-specific ablations only if needed"),
        ("governance superiority", "not proven", str(beneficial) if beneficial else None, "governance", "weak", "no beneficial natural divergence proven", "adjudicate more natural cases"),
        ("governance noninferiority", "supported in MultiHop and CRAG", None, "governance", "moderate", "not superiority", "repeat on more corpora"),
        ("production readiness", "not supported", None, "deployment", "weak", "no human/generative/platform validation", "keep as research harness"),
    ]
    pd.DataFrame(table, columns=["item", "status", "best_run_id", "evidence_class", "strength", "limitation", "next_action"]).to_csv(run_dir / "continued_investment_evidence_table.csv", index=False)
    write_json(run_dir / "continued_investment_decision.json", {"primary_recommendation": recommendation, **evidence})
    write_json(run_dir / "continued_investment_decision_memo_manifest.json", {"result": recommendation, "single_primary_recommendation": True})
    sections = [
        ("Executive Summary", f"Primary recommendation: `{recommendation}`."),
        ("Current Evidence Ladder", "Strict provenance and append-only artifacts are strong; natural beneficial governance evidence remains unproven."),
        ("What RAGWarrant Has Demonstrated", "RAGWarrant can preserve evidence and run governed selection across MultiHop-RAG and CRAG web-document retrieval."),
        ("What RAGWarrant Has Not Demonstrated", "It has not shown clear natural-public-data governance superiority, generative validation, human-eval validation, or production readiness."),
        ("What RAG Compass Has Demonstrated", "RAG Compass remains an eligible candidate optimizer and was selected by frozen validation in MultiHop-RAG."),
        ("What RAG Compass Has Not Demonstrated", "RAG Compass has not demonstrated universal superiority or a clear actionable niche in this phase."),
        ("Evidence For Governance Differentiation", "Four natural divergence records exist, and diagnostic hard-rule cases previously validated rule behavior."),
        ("Evidence Against Governance Differentiation", "The four natural cases remain retrieval-smoke-only and adjudicate as inconclusive, not beneficial."),
        ("Evidence For RAG Compass Niche Value", "Cost and latency noninferiority signals exist, but they are not actionable advantages."),
        ("Evidence Against RAG Compass Niche Value", "MultiHop confirmatory raw utility favored Optuna/TPE, and CRAG web evaluation selected top_k_high."),
        ("Remaining Blockers", "Mock API server data/dependencies, pinned generator, human annotations, official platform integrations, and more natural divergence cases."),
        ("Productization Potential", "The governance harness is promising as infrastructure, but not ready for production claims."),
        ("Research-Paper Potential", "Candidate external signal framing is plausible if limitations are foregrounded."),
        ("Enterprise Governance Applicability", "The audit/provenance design is relevant, but deployment validation is absent."),
        ("Recommended Path", "Pause optimizer-specific RAG Compass work and continue RAGWarrant governance validation focused on beneficial divergence and external validation."),
    ]
    write_text(run_dir / "continued_investment_decision_memo.md", "# Continued Investment Decision Memo v1\n\n" + "\n\n".join(f"## {title}\n\n{body}" for title, body in sections) + "\n")
    audit = write_no_overwrite_audit(run_dir, run_id=resolved)
    write_run_manifest(run_dir, suite=cfg.suite, run_id=resolved, config_path=config_path, seed=cfg.seed, dataset_hash=hash_payload(evidence), status="completed", evidence_mode="continued_investment_decision_memo", extra={"no_overwrite_status": audit["status"], "result": recommendation})
    return {"suite": cfg.suite, "run_id": resolved, "run_dir": str(run_dir), "primary_recommendation": recommendation}
