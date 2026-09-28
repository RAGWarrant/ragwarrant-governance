#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
from pathlib import Path

from ragwarrant.rc1_maturity import build_paper_assets


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default="paper/tables")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    build_paper_assets(ROOT, output_root=ROOT / args.output_root)
    print("PAPER_ASSETS_BUILT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
