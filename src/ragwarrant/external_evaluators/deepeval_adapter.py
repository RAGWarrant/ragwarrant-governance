from __future__ import annotations

from ragwarrant.external_evaluators.schema import ExternalMetric


DEEPEVAL_GROUP_MAP = {
    "answer_relevancy_score": "answer_relevance",
    "faithfulness_score": "faithfulness",
    "contextual_precision_score": "context_precision",
    "contextual_recall_score": "context_recall",
    "toxicity_score": "toxicity_or_safety",
}


def normalize_deepeval_export(rows: list[dict[str, object]]) -> list[ExternalMetric]:
    metrics: list[ExternalMetric] = []
    for row in rows:
        for key, group in DEEPEVAL_GROUP_MAP.items():
            if key not in row:
                continue
            direction = "minimize" if key == "toxicity_score" else "maximize"
            metrics.append(
                ExternalMetric(
                    example_id=str(row["example_id"]),
                    query_hash=str(row["query_hash"]),
                    policy_id=str(row["policy_id"]),
                    dataset_id=str(row.get("dataset_id", "deepeval_export")),
                    evaluator_name="deepeval",
                    metric_name=key,
                    metric_value=float(row[key]),
                    metric_direction=direction,
                    metric_weight=1.0,
                    metric_group=group,
                    split=str(row.get("split", "validation")),
                    source_artifact_hash=str(row.get("source_artifact_hash", "")),
                )
            )
    return metrics
