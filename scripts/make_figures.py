# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
figures = ROOT / "results" / "figures"
figures.mkdir(parents=True, exist_ok=True)
(figures / "README.md").write_text(
    "# Figures\n\nNo generated figures are required for the publication bundle yet.\n",
    encoding="utf-8",
)
print("figure placeholder refreshed")
