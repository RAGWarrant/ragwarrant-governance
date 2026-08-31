#!/usr/bin/env python3
"""Verify or initialize the confirmation-provenance amendment.

The default operation is read-only verification.  The two explicit write
operations can only register the preserved original materialization or create
new amendment artifacts; neither imports or invokes confirmation simulation,
FULL execution, a beacon, or drand.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPOSITORY_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ragwarrant.research.confirmation_provenance_amendment import (  # noqa: E402
    CONFIRMATION_DUPLICATE_MATERIALIZATION,
    CONFIRMATION_PROVENANCE_INCOMPLETE,
    ORIGINAL_PROTOCOL_ID,
    VerificationResult,
    guard_original_protocol_materialization,
    register_existing_materialization,
    verify_confirmation_provenance,
    write_new_amendment_artifacts,
)


AMENDMENT_IMPLEMENTATION_PATH = (
    "src/ragwarrant/research/confirmation_provenance_amendment.py"
)
CANONICAL_ORIGINAL_OUTPUT_ROOT = (
    ".local_data/research_review/joint_power_confirmation_v1"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument(
        "--register-existing",
        action="store_true",
        help=(
            "Atomically register the exact preserved original materialization. "
            "This performs no simulation and never rewrites original outputs."
        ),
    )
    operations.add_argument(
        "--create-amendment-artifacts",
        action="store_true",
        help=(
            "Exclusively create new provenance and corrected-diagnostic artifacts. "
            "Existing files are never overwritten."
        ),
    )
    operations.add_argument(
        "--check-materialization-request",
        action="store_true",
        help=(
            "Prove that a future request using the original protocol ID is "
            "refused before any generator could run."
        ),
    )
    parser.add_argument(
        "--output-root",
        default=CANONICAL_ORIGINAL_OUTPUT_ROOT,
        help=(
            "Repository-relative output root for --check-materialization-request. "
            "Aliases and alternate roots fail closed."
        ),
    )
    return parser.parse_args(argv)


def _emit(result: VerificationResult, *, operation: str) -> None:
    payload = result.as_dict()
    payload["operation"] = operation
    payload["repository_root"] = REPOSITORY_ROOT.as_posix()
    print(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.register_existing:
        operation = "register_existing"
        result = register_existing_materialization(REPOSITORY_ROOT)
        _emit(result, operation=operation)
        return 0 if result.ok else 1

    if args.create_amendment_artifacts:
        operation = "create_amendment_artifacts"
        result = write_new_amendment_artifacts(
            REPOSITORY_ROOT,
            amendment_implementation_path=AMENDMENT_IMPLEMENTATION_PATH,
        )
        _emit(result, operation=operation)
        return 0 if result.ok else 1

    if args.check_materialization_request:
        operation = "check_materialization_request"
        result = guard_original_protocol_materialization(
            REPOSITORY_ROOT,
            protocol_id=ORIGINAL_PROTOCOL_ID,
            requested_output_root=args.output_root,
        )
        _emit(result, operation=operation)
        correctly_refused = (
            result.status == CONFIRMATION_DUPLICATE_MATERIALIZATION
            and result.details.get("generator_called") is False
        )
        return 0 if correctly_refused else 1

    operation = "verify"
    result = verify_confirmation_provenance(REPOSITORY_ROOT)
    _emit(result, operation=operation)
    return 0 if result.ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        payload = {
            "status": CONFIRMATION_PROVENANCE_INCOMPLETE,
            "ok": False,
            "message": "Confirmation provenance verification was interrupted.",
            "details": {},
            "operation": "interrupted",
            "repository_root": REPOSITORY_ROOT.as_posix(),
        }
        print(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
        )
        raise SystemExit(130)
