#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.docker_static_validation import validate_docker_static


def main() -> int:
    parser = argparse.ArgumentParser(description="Run static Docker validation without a container daemon")
    parser.add_argument("--output-root", default="artifacts/docker_hardening")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = validate_docker_static(ROOT, output_root=ROOT / args.output_root)
    print(json.dumps({"result_class": result["result_class"]}, sort_keys=True))
    return 0 if result["result_class"] == "DOCKER_STATIC_VALIDATION_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
