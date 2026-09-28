#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.crag_evaluator_mapping import run_crag_evaluator_mapping


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/ragwarrant_crag_generated_answer_evaluator_mapping_v1.yaml")
    parser.add_argument("--output-root", default="artifacts/generative_llm_validation/crag_evaluator_mapping")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run_crag_evaluator_mapping(ROOT, output_root=ROOT / args.output_root)
    print(f"CRAG evaluator mapping: {result['mapping_result_class']}")


if __name__ == "__main__":
    main()
