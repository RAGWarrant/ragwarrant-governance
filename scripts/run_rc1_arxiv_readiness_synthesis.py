#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
from pathlib import Path

from ragwarrant.rc1_maturity import run_rc1_arxiv_readiness_synthesis


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/ragwarrant_rc1_arxiv_readiness_synthesis_v1.yaml")
    parser.add_argument("--output-root", default="results/rc1_arxiv_readiness")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print("RC1 arXiv readiness synthesis dry run")
        return 0
    result = run_rc1_arxiv_readiness_synthesis(ROOT, output_root=ROOT / args.output_root)
    print(result["result_class"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
