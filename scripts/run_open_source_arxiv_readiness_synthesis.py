#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.open_source_arxiv_readiness_synthesis import run_open_source_arxiv_readiness_synthesis


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/ragwarrant_open_source_arxiv_readiness_synthesis_v1.yaml")
    parser.add_argument("--output-root", default="results/open_source_arxiv_readiness")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run_open_source_arxiv_readiness_synthesis(ROOT, output_root=ROOT / args.output_root)
    print(f"open-source/arXiv readiness synthesis: {result['result_class']}")


if __name__ == "__main__":
    main()
