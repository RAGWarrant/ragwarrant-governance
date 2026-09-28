# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from ragwarrant.external_evaluators.schema import ExternalMetric


RAGAS_GROUP_MAP = {
    "answer_correctness": "answer_correctness",
    "faithfulness": "faithfulness",
    "context_precision": "context_precision",
    "context_recall": "context_recall",
    "answer_relevancy": "answer_relevance",
}


def normalize_ragas_export(rows: list[dict[str, object]]) -> list[ExternalMetric]:
    metrics: list[ExternalMetric] = []
    for row in rows:
        for key, group in RAGAS_GROUP_MAP.items():
            if key not in row:
                continue
            metrics.append(
                ExternalMetric(
                    example_id=str(row["example_id"]),
                    query_hash=str(row["query_hash"]),
                    policy_id=str(row["policy_id"]),
                    dataset_id=str(row.get("dataset_id", "ragas_export")),
                    evaluator_name="ragas",
                    metric_name=key,
                    metric_value=float(row[key]),
                    metric_direction="maximize",
                    metric_weight=1.0,
                    metric_group=group,
                    split=str(row.get("split", "validation")),
                    source_artifact_hash=str(row.get("source_artifact_hash", "")),
                )
            )
    return metrics
