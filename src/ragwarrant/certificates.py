# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

import pandas as pd


def issue_certificate(
    ranking: pd.DataFrame,
    *,
    suite: str,
    fixture: bool,
    statistical_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if ranking.empty:
        status = "Data unavailable"
        winner = None
        reason = "no candidate metrics were produced"
    else:
        winner = str(ranking.iloc[0]["policy_id"])
        winner_row = ranking.iloc[0]
        if fixture:
            status = "Inconclusive"
            reason = "fixture/smoke data cannot support benchmark claims"
        elif bool(winner_row.get("regression_flags", False)):
            status = "Refused"
            reason = "protected-example regression gate blocked promotion"
        elif winner == "ragwarrant_no_fork":
            status = "Candidate signal"
            reason = "RAGWarrant-No-Fork won under declared utility without protected regression"
        else:
            status = "Inconclusive"
            reason = "winner is not RAGWarrant-No-Fork or evidence is incomplete"
    return {
        "certificate_type": "RAGWarrant Validation Certificate",
        "suite": suite,
        "status": status,
        "winner": winner,
        "reason": reason,
        "statistical_analysis": statistical_analysis or {},
        "claim_boundary": [
            "No hardware evidence.",
            "No quantum advantage claim.",
            "No hallucination elimination claim.",
            "Fixture tests are not benchmark evidence.",
        ],
    }
