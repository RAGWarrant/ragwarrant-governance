#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.crag_generative_validation import run_crag_generative_validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/ragwarrant_crag_generative_llm_validation_v1.yaml")
    parser.add_argument("--output-root", default="artifacts/generative_llm_validation/crag")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = run_crag_generative_validation(ROOT, output_root=ROOT / args.output_root, dry_run=args.dry_run)
    print(f"CRAG generative LLM validation: {payload['result_class']}")


if __name__ == "__main__":
    main()
