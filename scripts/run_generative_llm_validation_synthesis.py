#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.generative_validation_synthesis import synthesize_generative_validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/ragwarrant_generative_llm_validation_synthesis_v1.yaml")
    parser.add_argument("--output-root", default="results/generative_llm_validation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = synthesize_generative_validation(ROOT, output_root=ROOT / args.output_root)
    print(f"generative LLM validation synthesis: {payload['result_class']}")


if __name__ == "__main__":
    main()
