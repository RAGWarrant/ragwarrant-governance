#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.selector_ablation_matrix import run_selector_ablation_matrix


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/ragwarrant_selector_ablation_matrix_v1.yaml")
    parser.add_argument("--output-root", default="artifacts/selector_ablation_matrix")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run_selector_ablation_matrix(ROOT, output_root=ROOT / args.output_root)
    print(f"selector ablation matrix: {result['result_class']}")


if __name__ == "__main__":
    main()
