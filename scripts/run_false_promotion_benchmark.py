from __future__ import annotations

import argparse
import json
from pathlib import Path

from ragwarrant.research.benchmark import run_benchmark
from ragwarrant.research.reporting import write_benchmark_outputs
from ragwarrant.research.simulator import load_config


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPOSITORY_ROOT / "configs/research/false_promotion_benchmark_v1.yaml"
DEFAULT_OUTPUT = REPOSITORY_ROOT / ".local_data/false_promotion_benchmark_ci_v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the research-only known-truth false-promotion benchmark."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--profile", choices=("CI", "LOCAL", "FULL"), default="CI")
    parser.add_argument("--master-seed", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.profile == "FULL":
        raise SystemExit(
            "FULL is disabled in the development runner; use the autonomous sealed "
            "public-beacon workflow after Focus 2 is frozen"
        )
    config = load_config(args.config)
    result = run_benchmark(
        config,
        profile=args.profile,
        master_seed=args.master_seed,
    )
    outputs = write_benchmark_outputs(result, args.output)
    summary = {
        "status": "complete",
        "profile": args.profile,
        "seed_schedule_version": result["manifest"]["seed_schedule_version"],
        "evidence_role": result["manifest"]["evidence_role"],
        "scenario_count": len(result["scenario_summary_rows"]),
        "method_summary_row_count": len(result["method_summary_rows"]),
        "output_files": [path.name for path in outputs],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
