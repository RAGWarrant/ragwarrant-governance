# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

from ragwarrant.external_evaluators.deepeval_adapter import normalize_deepeval_export
from ragwarrant.external_evaluators.ragas_adapter import normalize_ragas_export
from ragwarrant.external_evaluators.schema import FIELDNAMES, summarize_metrics
from ragwarrant.generative_validation_common import mean, write_csv, write_json, write_md


def run_external_evaluator_adapter_demo(root: Path, *, output_root: Path) -> dict[str, object]:
    ragas_rows = [
        {"example_id": "ex_001", "query_hash": "hash_001", "policy_id": "quality_policy", "answer_correctness": 0.88, "faithfulness": 0.86, "context_precision": 0.76},
        {"example_id": "ex_001", "query_hash": "hash_001", "policy_id": "cheap_policy", "answer_correctness": 0.80, "faithfulness": 0.72, "context_precision": 0.82},
    ]
    deepeval_rows = [
        {"example_id": "ex_002", "query_hash": "hash_002", "policy_id": "quality_policy", "answer_relevancy_score": 0.84, "faithfulness_score": 0.88, "toxicity_score": 0.02},
        {"example_id": "ex_002", "query_hash": "hash_002", "policy_id": "cheap_policy", "answer_relevancy_score": 0.81, "faithfulness_score": 0.73, "toxicity_score": 0.02},
    ]
    metrics = normalize_ragas_export(ragas_rows) + normalize_deepeval_export(deepeval_rows)
    rows = [metric.as_row() for metric in metrics]
    summary = summarize_metrics(metrics)
    policy_scores: dict[str, list[float]] = {}
    for metric in metrics:
        policy_scores.setdefault(metric.policy_id, []).append(metric.normalized_value() * metric.metric_weight)
    means = {policy: mean(values) for policy, values in policy_scores.items()}
    winner = max(means, key=means.get)
    result = {
        "suite": "ragwarrant_external_evaluator_adapters_v1",
        "result_class": "EXTERNAL_EVALUATOR_ADAPTER_PROMOTION_DECISION_GENERATED",
        "supported_inputs": ["generic_jsonl", "generic_csv", "ragas_like_export", "deepeval_like_export"],
        "normalized_schema": FIELDNAMES,
        "metric_count": len(metrics),
        "promotion_decision_generated": True,
        "selected_policy": winner,
        "raw_traces_used": False,
        "raw_questions_committed": False,
        "raw_contexts_committed": False,
        "tool_replacement_claimed": False,
    }
    write_csv(output_root / "normalized_external_metrics.csv", FIELDNAMES, rows)
    write_csv(output_root / "external_metric_summary.csv", ["policy_id", "metric_group", "mean_weighted_normalized_score", "metric_count"], summary)
    write_json(output_root / "external_evaluator_manifest.json", result)
    write_json(output_root / "promotion_decision_from_external_metrics.json", result)
    write_md(
        output_root / "external_evaluator_demo_report.md",
        """
# External Evaluator Adapter Demo

RAGWarrant does not replace Ragas, DeepEval, TruLens, LangSmith, Phoenix, or platform evaluators. It can consume their exported metrics as inputs to a promotion-control decision.

The demo uses synthetic sanitized evaluator rows and writes only normalized metrics, hashes, and aggregate decisions.
""",
    )
    return result
