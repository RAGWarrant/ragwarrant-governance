#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.public_mini_reproduction import run_public_mini_reproduction


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/ragwarrant_public_mini_reproduction_v1.yaml")
    parser.add_argument("--output-root", default="artifacts/public_mini_reproduction")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run_public_mini_reproduction(ROOT, output_root=ROOT / args.output_root)
    print(f"public mini reproduction: {result['result_class']}")


if __name__ == "__main__":
    main()
