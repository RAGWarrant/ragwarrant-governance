#!/usr/bin/env python3
"""Verify the explicit Focus 1 lineage or detached checkpoint authority."""

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
    module_name = "_ragwarrant_focus1_authority"
    spec = importlib.util.spec_from_file_location(module_name, IMPLEMENTATION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Focus 1 authority verifier cannot be loaded.")
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
        help="Canonical Git workspace containing the explicit authority record.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        implementation = _load_implementation()
        payload = implementation.verify_focus1_authority(args.repository_root)
        payload["ok"] = True
    except Exception as exc:
        status = getattr(exc, "status", "FOCUS1_AUTHORITY_MODE_INVALID")
        details = getattr(exc, "details", {})
        payload = {
            "status": status,
            "ok": False,
            "message": str(exc),
            "details": details,
        }
    payload["operation"] = "verify_focus1_authority"
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
