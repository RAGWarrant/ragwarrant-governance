# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _selectors() -> set[str]:
    with (ROOT / "artifacts/selector_ablation_matrix/selector_ablation_results.csv").open(newline="", encoding="utf-8") as handle:
        return {row["selector"] for row in csv.DictReader(handle)}


def test_selector_ablation_manifest_exists() -> None:
    assert (ROOT / "artifacts/selector_ablation_matrix/selector_ablation_manifest.json").exists()


def test_selector_ablation_results_exist() -> None:
    assert (ROOT / "artifacts/selector_ablation_matrix/selector_ablation_results.csv").exists()


def test_selector_ablation_includes_quality_only() -> None:
    assert "quality_only" in _selectors()


def test_selector_ablation_includes_cost_only() -> None:
    assert "cost_only" in _selectors()


def test_selector_ablation_includes_latency_only() -> None:
    assert "latency_only" in _selectors()


def test_selector_ablation_includes_governed_selector() -> None:
    assert "governed_noninferiority_selector" in _selectors()


def test_selector_ablation_marks_missing_inputs_unavailable() -> None:
    manifest = json.loads((ROOT / "artifacts/selector_ablation_matrix/selector_ablation_manifest.json").read_text(encoding="utf-8"))
    assert manifest["missing_inputs_marked_unavailable"] is True


def test_selector_ablation_no_universal_superiority_claim() -> None:
    manifest = json.loads((ROOT / "artifacts/selector_ablation_matrix/selector_ablation_manifest.json").read_text(encoding="utf-8"))
    assert manifest["universal_superiority_claimed"] is False
