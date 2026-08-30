from __future__ import annotations

import argparse
import json
from pathlib import Path

from ragwarrant.research.seed_schedule import build_seed_schedule_manifest
from ragwarrant.research.simulator import load_config


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPOSITORY_ROOT / "configs/research/false_promotion_benchmark_v1.yaml"
DEFAULT_OUTPUT = REPOSITORY_ROOT / ".local_data/research_review"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enumerate and verify seed-schedule v2 without generating evidence."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _report(manifest: dict[str, object]) -> str:
    counts = manifest["configured_trial_counts"]
    overlaps = manifest["overlap_counts"]
    return "\n".join(
        [
            "# Seed Schedule V2 Static Review",
            "",
            f"- Amendment: `{manifest['amendment_id']}`",
            f"- Seed schedule version: `{manifest['seed_schedule_version']}`",
            f"- Identity format: `{manifest['canonical_identity_format']}`",
            f"- Scenario count: {manifest['scenario_count']}",
            f"- Sample-size cells: {manifest['sample_size_cell_count']}",
            f"- CI identities: {counts['CI']}",  # type: ignore[index]
            f"- LOCAL identities: {counts['LOCAL']}",  # type: ignore[index]
            f"- FULL identities: {counts['FULL']}",  # type: ignore[index]
            f"- CI/LOCAL overlap: {overlaps['CI_LOCAL']}",  # type: ignore[index]
            f"- CI/FULL overlap: {overlaps['CI_FULL']}",  # type: ignore[index]
            f"- LOCAL/FULL overlap: {overlaps['LOCAL_FULL']}",  # type: ignore[index]
            f"- Duplicate seed fingerprints: {manifest['duplicate_seed_count']}",
            f"- FULL entropy protocol: `{manifest['full_entropy_protocol']}`",
            f"- FULL status: `{manifest['full_confirmation_status']}`",
            "- FULL target round selected: false",
            "- FULL evidence generated: false",
            "- FULL results inspected: false",
            "",
            "Identity enumeration and pre-reveal namespace fingerprinting did not call evidence generation or retrieve beacon data. Under Quicknet's threshold-security assumptions, benchmark operators cannot derive the FULL master seed until the sealed future public round is published.",
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    manifest = build_seed_schedule_manifest(config)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "SEED_SCHEDULE_V2_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "SEED_SCHEDULE_V2_REPORT.md").write_text(
        _report(manifest), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "seed_schedule_version": manifest["seed_schedule_version"],
                "full_evidence_generated": False,
                "duplicate_seed_count": manifest["duplicate_seed_count"],
                "overlap_counts": manifest["overlap_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
