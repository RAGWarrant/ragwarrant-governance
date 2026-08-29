#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.container_security_scans import run_optional_container_security_scans


def main() -> int:
    parser = argparse.ArgumentParser(description="Record optional container security scanner availability")
    parser.add_argument("--output-root", default="artifacts/docker_hardening")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run_optional_container_security_scans(ROOT, output_root=ROOT / args.output_root)
    print(json.dumps({"result_class": result["result_class"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
