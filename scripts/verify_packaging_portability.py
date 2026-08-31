#!/usr/bin/env python3
"""Verify the research packaging-portability amendment without writing files."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_PATH = (
    REPOSITORY_ROOT
    / "src"
    / "ragwarrant"
    / "research"
    / "packaging_portability_amendment.py"
)


def _load_implementation() -> ModuleType:
    """Load the standalone verifier without importing the research package."""

    module_name = "_ragwarrant_packaging_portability_amendment"
    spec = importlib.util.spec_from_file_location(module_name, IMPLEMENTATION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Packaging-portability verifier cannot be loaded.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="Repository workspace containing the tracked amendment record.",
    )
    parser.add_argument(
        "--record-path",
        default=None,
        help="Canonical repository-relative amendment record path.",
    )
    parser.add_argument(
        "--workspace-materialization-root",
        type=Path,
        help=(
            "Optional absolute path to the ignored original confirmation output root. "
            "When omitted, only clean-checkout-portable tracked inputs are verified."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        implementation = _load_implementation()
        record_path = args.record_path or implementation.DEFAULT_RECORD_PATH
        result = implementation.verify_packaging_portability(
            args.repository_root,
            record_path=record_path,
            workspace_materialization_root=args.workspace_materialization_root,
        )
        payload = result.as_dict()
    except Exception as exc:
        payload = {
            "status": "PACKAGING_PORTABILITY_INCOMPLETE",
            "ok": False,
            "message": f"Packaging-portability verification failed to initialize: {exc}",
            "details": {},
        }
    payload["operation"] = "verify_packaging_portability"
    print(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
