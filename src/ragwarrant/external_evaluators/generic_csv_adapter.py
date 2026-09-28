# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
from pathlib import Path

from ragwarrant.external_evaluators.schema import ExternalMetric, normalize_group


def load_csv_metrics(path: Path) -> list[ExternalMetric]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [
        ExternalMetric(
            example_id=str(row["example_id"]),
            query_hash=str(row["query_hash"]),
            policy_id=str(row["policy_id"]),
            dataset_id=str(row.get("dataset_id", "external")),
            evaluator_name=str(row.get("evaluator_name", "generic_csv")),
            metric_name=str(row["metric_name"]),
            metric_value=float(row["metric_value"]),
            metric_direction=str(row.get("metric_direction", "maximize")),
            metric_weight=float(row.get("metric_weight", 1.0)),
            metric_group=normalize_group(str(row.get("metric_group", "custom"))),
            split=str(row.get("split", "validation")),
            source_artifact_hash=str(row.get("source_artifact_hash", "")),
        )
        for row in rows
    ]
