#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.aim_hardware_characterization import run_aim_hardware_characterization


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/ragwarrant_aim_hardware_characterization_v1.yaml")
    parser.add_argument("--output-root", default="artifacts/aim_hardware_characterization")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run_aim_hardware_characterization(ROOT, output_root=ROOT / args.output_root)
    print(f"AIM hardware characterization: {result['result_class']}")


if __name__ == "__main__":
    main()
