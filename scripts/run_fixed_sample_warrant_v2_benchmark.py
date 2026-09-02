from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ragwarrant.research.focus2_v2_benchmark import (
    FROZEN_FOCUS1_CONFIG_PATH,
    FROZEN_V2_CONFIG_PATH,
    load_v2_config,
    run_focus2_v2_benchmark,
)
from ragwarrant.research.focus2_v2_reporting import write_focus2_v2_outputs
from ragwarrant.research.simulator import load_config

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the developmental Focus 2 v2 power ablation."
    )
    parser.add_argument("--profile", choices=("CI", "LOCAL"), default="CI")
    parser.add_argument("--focus1-config", type=Path, default=FROZEN_FOCUS1_CONFIG_PATH)
    parser.add_argument("--v2-config", type=Path, default=FROZEN_V2_CONFIG_PATH)
    parser.add_argument("--master-seed", type=int)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output or (
        REPOSITORY_ROOT
        / ".local_data"
        / "fixed_sample_warrant_v2"
        / f"{args.profile.lower()}_v2"
    )
    result = run_focus2_v2_benchmark(
        load_config(args.focus1_config),
        load_v2_config(args.v2_config),
        profile=args.profile,
        master_seed=args.master_seed,
    )
    written = write_focus2_v2_outputs(result, output)
    print(
        json.dumps(
            {
                "status": "focus2_v2_developmental_benchmark_complete",
                "profile": args.profile,
                "evidence_trial_count": result["manifest"]["trial_count_total"],
                "scenario_method_cell_count": result["manifest"][
                    "scenario_method_summary_count"
                ],
                "output_root": str(output),
                "output_file_count": len(written),
                "full_profile_used": False,
                "target_drand_round_selected": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
