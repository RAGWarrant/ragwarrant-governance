#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
from pathlib import Path

from ragwarrant.rc1_maturity import run_crag_evaluator_mapping_v2


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/ragwarrant_crag_evaluator_mapping_diagnostic_v2.yaml")
    parser.add_argument("--output-root", default="artifacts/crag_evaluator_mapping_v2")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print("CRAG evaluator mapping v2 dry run")
        return 0
    result = run_crag_evaluator_mapping_v2(ROOT, output_root=ROOT / args.output_root)
    print(result["result_class"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
