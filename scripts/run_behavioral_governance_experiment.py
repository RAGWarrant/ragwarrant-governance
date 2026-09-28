#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.behavioral_governance import run_experiment


def main() -> None:
    stats = run_experiment(ROOT)
    print(f"behavioral governance experiment completed: {stats['primary_result_class']}")
    print(f"governed winner: {stats['governed_winner']}")
    print(f"quality-only winner: {stats['quality_only_winner']}")


if __name__ == "__main__":
    main()
