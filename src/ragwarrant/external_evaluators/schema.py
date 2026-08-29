from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


METRIC_GROUPS = {
    "answer_correctness",
    "faithfulness",
    "groundedness",
    "context_precision",
    "context_recall",
    "context_relevance",
    "answer_relevance",
    "hallucination_risk",
    "toxicity_or_safety",
    "abstention_correctness",
    "custom",
}


@dataclass(frozen=True)
class ExternalMetric:
    example_id: str
    query_hash: str
    policy_id: str
    dataset_id: str
    evaluator_name: str
    metric_name: str
    metric_value: float
    metric_direction: str
    metric_weight: float
    metric_group: str
    split: str
    source_artifact_hash: str

    def normalized_value(self) -> float:
        return self.metric_value if self.metric_direction == "maximize" else 1.0 - self.metric_value

    def as_row(self) -> dict[str, object]:
        return asdict(self)


FIELDNAMES = [
    "example_id",
    "query_hash",
    "policy_id",
    "dataset_id",
    "evaluator_name",
    "metric_name",
    "metric_value",
    "metric_direction",
    "metric_weight",
    "metric_group",
    "split",
    "source_artifact_hash",
]


def normalize_group(group: str) -> str:
    cleaned = group.strip().lower()
    return cleaned if cleaned in METRIC_GROUPS else "custom"


def summarize_metrics(metrics: Iterable[ExternalMetric]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[ExternalMetric]] = {}
    for metric in metrics:
        grouped.setdefault((metric.policy_id, metric.metric_group), []).append(metric)
    rows: list[dict[str, object]] = []
    for (policy_id, group), values in sorted(grouped.items()):
        weighted = sum(metric.normalized_value() * metric.metric_weight for metric in values)
        weight = sum(metric.metric_weight for metric in values) or 1.0
        rows.append(
            {
                "policy_id": policy_id,
                "metric_group": group,
                "mean_weighted_normalized_score": round(weighted / weight, 6),
                "metric_count": len(values),
            }
        )
    return rows
