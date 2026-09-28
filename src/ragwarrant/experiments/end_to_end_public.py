# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ragwarrant.artifacts import (
    copy_input_config,
    prepare_run_dir,
    write_no_overwrite_audit,
    write_policy_space,
    write_run_manifest,
)
from ragwarrant.config import SuiteConfig
from ragwarrant.end_to_end import RAGPolicy, chunk_documents, mini_corpus, run_pipeline
from ragwarrant.metrics import apply_utilities, rank_policies
from ragwarrant.utils.files import write_json, write_text
from ragwarrant.utils.hashing import stable_hash


def _policies() -> dict[str, RAGPolicy]:
    return {
        "static_default_rag_policy": RAGPolicy(top_k=2, citation_required=False),
        "best_single_policy_on_validation": RAGPolicy(top_k=4, citation_required=True),
        "uniform_random_search": RAGPolicy(top_k=3, chunk_size=48, citation_required=False),
        "greedy_regression_aware_search": RAGPolicy(top_k=5, reranker_enabled=True, citation_required=True),
        "ragwarrant_no_fork": RAGPolicy(top_k=5, reranker_enabled=True, citation_required=True, abstention_threshold=0.6),
    }


def run(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    evidence_mode = str(cfg.raw.get("evidence_mode", "end_to_end_smoke"))
    if evidence_mode == "end_to_end_public_rag" and not bool(cfg.raw.get("dataset_capability", {}).get("end_to_end_eligible")):
        raise ValueError("end_to_end_public_rag evidence mode requires an eligible public corpus-backed dataset")
    resolved_run_id, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    corpus = mini_corpus()
    policy_space = cfg.policy_space or {
        "chunk_size": [48, 80],
        "top_k": [2, 3, 4, 5],
        "reranker_enabled": [False, True],
        "citation_required": [False, True],
        "abstention_threshold": [0.4, 0.6],
    }
    write_policy_space(run_dir, policy_space)
    write_json(
        run_dir / "dataset_capability_report.json",
        {
            "has_corpus": True,
            "has_queries": True,
            "has_reference_answers": False,
            "has_supporting_documents": True,
            "redistribution_permitted": True,
            "end_to_end_eligible": evidence_mode == "end_to_end_public_rag",
            "evidence_mode": evidence_mode,
        },
    )
    write_json(
        run_dir / "corpus_manifest.json",
        {"corpus_id": "ragwarrant_mini_corpus_v1", "document_count": len(corpus), "corpus_hash": stable_hash(corpus, 16)},
    )
    static_chunks = chunk_documents(corpus, RAGPolicy())
    write_json(run_dir / "index_manifest.json", {"index_type": "deterministic_sparse", "chunk_count": len(static_chunks)})
    rows = []
    retrieval_rows = []
    generation_rows = []
    for policy_id, policy in _policies().items():
        metrics = run_pipeline(policy)
        rows.append(
            {
                "policy_id": policy_id,
                "baseline_name": policy_id,
                "raw_quality": metrics["raw_quality"],
                "cost": metrics["cost"],
                "latency_p50": metrics["latency_p50"],
                "latency_p95": metrics["latency_p95"],
                "latency_p99": metrics["latency_p99"],
                "protected_subset_score": metrics["protected_subset_score"],
                "regression_delta": 0.0,
                "skipped": False,
                "skip_reason": "",
                "seed": cfg.seed,
                "queries_evaluated": metrics["queries_evaluated"],
            }
        )
        retrieval_rows.append({"policy_id": policy_id, "top_k": policy.top_k, "reranker_enabled": policy.reranker_enabled})
        generation_rows.append(
            {
                "policy_id": policy_id,
                "faithfulness_proxy": metrics["faithfulness_proxy"],
                "citation_support_proxy": metrics["citation_support_proxy"],
                "abstention_accuracy_proxy": metrics["abstention_accuracy_proxy"],
            }
        )
    frame = pd.DataFrame(rows)
    scored = apply_utilities(
        frame,
        lambda_cost=float(cfg.objectives.get("cost_weight", 0.25)),
        lambda_latency=float(cfg.objectives.get("latency_weight", 0.10)),
        regression_threshold=float(cfg.objectives.get("protected_regression_threshold", -0.03)),
    )
    ranking = rank_policies(scored)
    ranking.to_csv(run_dir / "candidate_policy_metrics.csv", index=False)
    write_json(run_dir / "ranking.json", {"ranking": ranking.to_dict(orient="records")})
    write_json(run_dir / "winning_policy.json", ranking.iloc[0].to_dict())
    write_json(run_dir / "retrieval_metrics.json", {"rows": retrieval_rows})
    write_json(run_dir / "generation_metrics.json", {"rows": generation_rows})
    write_json(run_dir / "latency_report.json", {"rows": ranking[["policy_id", "latency_p50", "latency_p95", "latency_p99"]].to_dict(orient="records")})
    write_json(run_dir / "cost_report.json", {"rows": ranking[["policy_id", "cost"]].to_dict(orient="records")})
    write_text(run_dir / "pipeline_policy_space.yaml", (run_dir / "policy_space.yaml").read_text(encoding="utf-8"))
    certificate = {
        "certificate_type": "RAGWarrant End-to-End Public RAG Certificate",
        "status": "Inconclusive",
        "supported_enabled": False,
        "evidence_mode": evidence_mode,
        "winner": str(ranking.iloc[0]["policy_id"]),
        "reason": "local corpus-backed smoke run is not benchmark evidence",
    }
    write_json(run_dir / "certificate.json", certificate)
    aggregate = {
        "winner": str(ranking.iloc[0]["policy_id"]),
        "candidate_count": len(ranking),
        "evidence_mode": evidence_mode,
    }
    write_json(run_dir / "aggregate_metrics.json", aggregate)
    audit = write_no_overwrite_audit(run_dir, run_id=resolved_run_id)
    write_run_manifest(
        run_dir,
        suite=cfg.suite,
        run_id=resolved_run_id,
        config_path=config_path,
        seed=cfg.seed,
        dataset_hash=stable_hash(corpus, 16),
        status="completed",
        evidence_mode=evidence_mode,
        extra={"no_overwrite_status": audit["status"], "model_identifiers": ["deterministic_fake"]},
    )
    write_text(
        run_dir / "report.md",
        f"# {cfg.suite}\n\n"
        f"- Run ID: `{resolved_run_id}`\n"
        f"- Evidence mode: `{evidence_mode}`\n"
        f"- Winner: `{aggregate['winner']}`\n"
        "- Certificate: `Inconclusive`\n\n"
        "This run executes a local corpus, chunker, sparse retriever, context builder, deterministic generator, evaluator, cost recorder, and latency recorder. "
        "It is a smoke test and should not be cited as public end-to-end benchmark evidence.\n",
    )
    return {"suite": cfg.suite, "run_id": resolved_run_id, "run_dir": str(run_dir), "certificate": certificate, "winner": aggregate["winner"]}
