# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
tables = ROOT / "results" / "tables"
tables.mkdir(parents=True, exist_ok=True)
for name in ["run_index.csv", "claim_status/claim_status_table.csv"]:
    src = ROOT / "results" / name
    if src.exists():
        shutil.copy2(src, tables / src.name)
print("tables refreshed")
