#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.fresh_live_behavioral_governance import write_crag_acquisition_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/ragwarrant_fresh_live_crag_mock_api_behavioral_governance_v1.yaml")
    parser.add_argument("--output-root", default="artifacts/fresh_live_crag_behavioral_governance")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = write_crag_acquisition_report(ROOT, dry_run=args.dry_run)
    print(f"fresh live CRAG behavioral governance: {payload['result_class']}")


if __name__ == "__main__":
    main()
