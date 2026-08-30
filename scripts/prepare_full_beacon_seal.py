from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ragwarrant.research.public_beacon import (
    build_seal_manifest,
    verify_benchmark_freeze_manifest,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare one future-round FULL seal without retrieving beacon data."
    )
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--subject-commit", required=True)
    parser.add_argument("--workflow-start-unix", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.freeze_manifest.read_text(encoding="utf-8"))
    if manifest.get("full_confirmation_ready") is not True:
        raise SystemExit("freeze manifest is not authorized for FULL confirmation")
    if manifest.get("focus2_implementation_status") != "FROZEN_FOR_FULL_CONFIRMATION":
        raise SystemExit("Focus 2 implementation is not frozen for confirmation")
    if manifest.get("full_profile_executed") is not False:
        raise SystemExit("freeze manifest indicates that FULL was already executed")
    head = _git("rev-parse", "HEAD")
    if head != args.subject_commit:
        raise SystemExit("checked-out commit differs from the requested subject commit")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("tracked working tree must be clean before sealing")
    freeze_digest = verify_benchmark_freeze_manifest(manifest, REPOSITORY_ROOT)
    seal = build_seal_manifest(
        subject_commit=args.subject_commit,
        benchmark_freeze_digest=freeze_digest,
        workflow_start_timestamp=args.workflow_start_unix,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(seal, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        json.dumps(
            {
                "status": "seal_prepared_pending_publication",
                "subject_commit": args.subject_commit,
                "target_round": seal["drand"]["target_round"],
                "full_executed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
