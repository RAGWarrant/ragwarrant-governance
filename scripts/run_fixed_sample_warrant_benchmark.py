# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from ragwarrant.research.focus2_benchmark import run_focus2_benchmark
from ragwarrant.research.focus2_reporting import write_focus2_outputs
from ragwarrant.research.simulator import load_config


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FOCUS1_CONFIG = (
    REPOSITORY_ROOT / "configs/research/false_promotion_benchmark_v1.yaml"
)
DEFAULT_FOCUS2_CONFIG = (
    REPOSITORY_ROOT / "configs/research/fixed_sample_multi_risk_warrant_v1.yaml"
)


def _focus2_config(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("Focus 2 config must contain a mapping at the root")
    return loaded


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the research-only fixed-sample warrant benchmark."
    )
    parser.add_argument("--focus1-config", type=Path, default=DEFAULT_FOCUS1_CONFIG)
    parser.add_argument("--focus2-config", type=Path, default=DEFAULT_FOCUS2_CONFIG)
    parser.add_argument("--profile", choices=("CI", "LOCAL"), default="CI")
    parser.add_argument("--master-seed", type=int)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output or (
        REPOSITORY_ROOT
        / ".local_data/fixed_sample_warrant"
        / f"{args.profile.lower()}_v2"
    )
    result = run_focus2_benchmark(
        load_config(args.focus1_config),
        _focus2_config(args.focus2_config),
        profile=args.profile,
        master_seed=args.master_seed,
    )
    outputs = write_focus2_outputs(result, output)
    summary = {
        "status": "complete",
        "profile": args.profile,
        "evidence_role": "developmental",
        "seed_schedule_version": result["manifest"]["seed_schedule_version"],
        "scenario_count": len(result["scenario_summary_rows"]),
        "method_summary_row_count": len(result["method_summary_rows"]),
        "full_profile_used": False,
        "output_files": [path.name for path in outputs],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
