#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.container_smoke_tests import run_container_smoke_tests


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Docker/container smoke tests when a runtime is available")
    parser.add_argument("--config", default="configs/experiments/ragwarrant_container_smoke_tests_v1.yaml")
    parser.add_argument("--output-root", default="artifacts/docker_hardening")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run_container_smoke_tests(ROOT, output_root=ROOT / args.output_root)
    print(json.dumps({"result_class": result["result_class"]}, sort_keys=True))
    return 0 if not result["result_class"].startswith("CONTAINER_RUNTIME_VALIDATION_FAILED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
