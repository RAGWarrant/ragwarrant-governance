#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from ragwarrant.rc1_maturity import prepare_release_candidate


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/ragwarrant_release_candidate_v1.yaml")
    parser.add_argument("--version", default="v0.1.0-rc1")
    parser.add_argument("--output-root", default="artifacts/release_candidate/v0.1.0-rc1")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print(f"release candidate dry run: {args.version}")
        return 0
    result = prepare_release_candidate(ROOT, output_root=ROOT / args.output_root, version=args.version)
    print(result["result_class"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
