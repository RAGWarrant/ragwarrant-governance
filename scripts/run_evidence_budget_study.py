# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate the pre-confirmatory RAGWarrant evidence-budget study."""

from __future__ import annotations

import argparse
from pathlib import Path

from ragwarrant.research.evidence_budget_planner import (
    load_planner_config,
    plan_evidence_budget,
    render_study_report,
    render_subgroup_plan,
    study_rows,
    write_study_csv,
)


DEFAULT_CONFIG = Path("configs/research/evidence_budget_planner_v1.yaml")
DEFAULT_OUTPUT_DIR = Path(".local_data/research_review")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--execute-full",
        action="store_true",
        help="Guarded prohibited option retained to fail closed.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.execute_full:
        raise SystemExit("FULL evidence generation is prohibited in this planner")
    config = load_planner_config(args.config)
    plan = plan_evidence_budget(config)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = study_rows(config, plan)
    write_study_csv(args.output_dir / "EVIDENCE_BUDGET_STUDY.csv", rows)
    (args.output_dir / "EVIDENCE_BUDGET_STUDY.md").write_text(
        render_study_report(config, plan), encoding="utf-8"
    )
    (args.output_dir / "SUBGROUP_EVIDENCE_PLAN.md").write_text(
        render_subgroup_plan(config, plan), encoding="utf-8"
    )
    print(f"wrote {len(rows)} analytical planning rows")
    print("confirmatory evidence generated: false")
    print("FULL executed: false")
    print("drand round selected: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
