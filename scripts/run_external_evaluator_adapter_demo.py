#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.external_evaluator_adapter_demo import run_external_evaluator_adapter_demo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/ragwarrant_external_evaluator_adapter_demo_v1.yaml")
    parser.add_argument("--output-root", default="artifacts/external_evaluator_adapters")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run_external_evaluator_adapter_demo(ROOT, output_root=ROOT / args.output_root)
    print(f"external evaluator adapter demo: {result['result_class']}")


if __name__ == "__main__":
    main()
