# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.promotion_decision import build_promotion_decision, write_promotion_decision


ROOT = Path(__file__).resolve().parents[2]


def test_promotion_decision_schema_has_required_decisions() -> None:
    schema = json.loads((ROOT / "schemas/promotion_decision.schema.json").read_text(encoding="utf-8"))
    enum = schema["properties"]["decision"]["enum"]
    assert {"PROMOTE", "BLOCK", "REJECT", "INCONCLUSIVE", "ERROR"}.issubset(set(enum))


def test_promotion_decision_contains_claim_boundaries(tmp_path: Path) -> None:
    decision = build_promotion_decision(
        run_id="test_run",
        suite="test_suite",
        result_class="BLOCK_PUBLICATION_HYGIENE",
        decision_reason="test decision",
    )
    out = tmp_path / "promotion_decision.json"
    write_promotion_decision(out, decision)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["decision"] == "BLOCK"
    assert payload["claim_boundaries"]["rag_compass_superiority_claimed"] is False
    assert payload["claim_boundaries"]["official_platform_benchmarking_claimed"] is False
