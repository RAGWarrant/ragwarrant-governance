#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from ragwarrant.rc1_maturity import verify_run


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-root", default="artifacts/verify_run_demo")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print("verify-run dry run")
        return 0
    result = verify_run(ROOT, run_dir=ROOT / args.run_dir, output_root=ROOT / args.output_root)
    print(result["result_class"])
    return 0 if result["result_class"] == "VERIFY_RUN_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
