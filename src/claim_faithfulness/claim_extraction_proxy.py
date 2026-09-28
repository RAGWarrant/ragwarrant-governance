# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pandas as pd


def build_claim_proxy(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    answer = frame.get("generated_answer", pd.Series([""] * len(frame), index=frame.index)).astype(str)
    rows = []
    for idx, text in answer.items():
        sentences = [part.strip() for part in text.replace("?", ".").replace("!", ".").split(".") if part.strip()]
        if not sentences:
            sentences = [text[:120]]
        for claim_idx, sentence in enumerate(sentences[:4]):
            base = frame.loc[idx]
            retrieval = float(base.get("retrieval_confidence", 0.5))
            uncertainty = float(base.get("uncertainty", 0.5))
            hallucination = float(base.get("hallucination_labels_optional", 0.5))
            risk = min(1.0, 0.45 * hallucination + 0.35 * uncertainty + 0.20 * (1.0 - retrieval))
            rows.append(
                {
                    "example_id": str(base.get("example_id", idx)),
                    "claim_id": f"{base.get('example_id', idx)}::claim-{claim_idx}",
                    "claim_text": sentence,
                    "unsupported_claim_risk": risk,
                    "citation_support_proxy": retrieval * (1.0 - hallucination),
                    "high_risk_claim": risk >= 0.55,
                }
            )
    return pd.DataFrame(rows)

