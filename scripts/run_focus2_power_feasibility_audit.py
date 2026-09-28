# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate the bounded local Focus 2 feasibility audit without FULL evidence."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from ragwarrant.research.focus2_power_diagnostics import (
    FOCUS1_CONFIG_PATH,
    build_power_feasibility_rows,
    build_v1_preservation_manifest,
    load_overlay_config,
    render_feasibility_report,
)
from ragwarrant.research.simulator import load_config


DEFAULT_OUTPUT_DIR = Path(".local_data/research_review")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--profile",
        choices=("CI", "LOCAL", "FULL"),
        help="Optional guard only; CI and LOCAL are always audited together.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.profile == "FULL":
        raise SystemExit("FULL is prohibited in the Focus 2 power audit")
    config = load_config(FOCUS1_CONFIG_PATH)
    overlay = load_overlay_config()
    preservation = build_v1_preservation_manifest()
    rows = build_power_feasibility_rows(config, overlay)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "FOCUS2_POWER_FEASIBILITY_AUDIT.csv"
    report_path = args.output_dir / "FOCUS2_POWER_FEASIBILITY_AUDIT.md"
    manifest_path = args.output_dir / "FOCUS2_V1_PRESERVATION_MANIFEST.json"
    if not rows:
        raise SystemExit("power feasibility audit produced no rows")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report_path.write_text(
        render_feasibility_report(rows, preservation), encoding="utf-8"
    )
    manifest_path.write_text(
        json.dumps(preservation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} gate rows to {csv_path}")
    print(f"wrote {report_path}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
