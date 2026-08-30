#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.fresh_live_behavioral_governance import write_hotpotqa_acquisition_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["huggingface", "official_github"], default="huggingface")
    parser.add_argument("--config", default="distractor")
    parser.add_argument("--output-root", default=".local_data/hotpotqa")
    parser.add_argument("--max-examples", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = write_hotpotqa_acquisition_report(ROOT, dry_run=args.dry_run)
    print(payload["result_class"])
    if payload["result_class"] == "HOTPOTQA_BLOCKED_DATASET_UNAVAILABLE":
        print("Install `datasets` or place approved HotpotQA raw files under .local_data/hotpotqa; do not commit raw data.")


if __name__ == "__main__":
    main()
