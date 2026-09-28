# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.external_evaluators.deepeval_adapter import normalize_deepeval_export
from ragwarrant.external_evaluators.generic_csv_adapter import load_csv_metrics
from ragwarrant.external_evaluators.generic_jsonl_adapter import load_jsonl_metrics
from ragwarrant.external_evaluators.ragas_adapter import normalize_ragas_export
from ragwarrant.external_evaluators.schema import FIELDNAMES


ROOT = Path(__file__).resolve().parents[2]


def test_external_evaluator_schema_exists() -> None:
    assert "metric_group" in FIELDNAMES


def test_generic_jsonl_adapter_normalizes_metrics(tmp_path: Path) -> None:
    path = tmp_path / "metrics.jsonl"
    path.write_text('{"example_id":"e","query_hash":"h","policy_id":"p","metric_name":"m","metric_value":0.7}\n', encoding="utf-8")
    assert load_jsonl_metrics(path)[0].metric_value == 0.7


def test_generic_csv_adapter_normalizes_metrics(tmp_path: Path) -> None:
    path = tmp_path / "metrics.csv"
    path.write_text("example_id,query_hash,policy_id,metric_name,metric_value\ne,h,p,m,0.8\n", encoding="utf-8")
    assert load_csv_metrics(path)[0].metric_value == 0.8


def test_ragas_adapter_accepts_ragas_like_export() -> None:
    rows = normalize_ragas_export([{"example_id": "e", "query_hash": "h", "policy_id": "p", "answer_correctness": 0.9}])
    assert rows[0].evaluator_name == "ragas"


def test_deepeval_adapter_accepts_deepeval_like_export() -> None:
    rows = normalize_deepeval_export([{"example_id": "e", "query_hash": "h", "policy_id": "p", "faithfulness_score": 0.9}])
    assert rows[0].evaluator_name == "deepeval"


def test_external_metrics_generate_promotion_decision() -> None:
    result = json.loads((ROOT / "artifacts/external_evaluator_adapters/promotion_decision_from_external_metrics.json").read_text(encoding="utf-8"))
    assert result["promotion_decision_generated"] is True


def test_external_evaluator_demo_artifacts_exist() -> None:
    assert (ROOT / "artifacts/external_evaluator_adapters/normalized_external_metrics.csv").exists()


def test_external_adapter_does_not_claim_tool_replacement() -> None:
    text = (ROOT / "docs/external_evaluator_adapters.md").read_text(encoding="utf-8")
    assert "does not replace" in text
