#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from ragwarrant.storage import build_storage_sink


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stage_outputs(mode: str, output_root: Path) -> list[dict[str, str]]:
    sink = build_storage_sink(mode=mode, output_root=output_root)
    staged: list[dict[str, str]] = []
    for path in sorted(output_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(output_root).as_posix()
        if relative == "storage_staging_report.json":
            continue
        stored = sink.put_file(path, relative)
        staged.append({"local_path": relative, "uri": stored.uri})
    return staged


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a command and stage sanitized artifacts through an object-storage sink.")
    parser.add_argument("--mode", required=True, choices=["s3", "azure_blob", "gcs"])
    parser.add_argument("--output-root", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise SystemExit("missing wrapped command")
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["RAGWARRANT_OUTPUT_DIR"] = str(output_root)
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, check=False)
    staged = stage_outputs(args.mode, output_root)
    report = {
        "mode": args.mode,
        "wrapped_exit_code": result.returncode,
        "staged_artifact_count": len(staged),
        "staged_artifacts": staged,
        "raw_payloads_exported": False,
        "secrets_exported": False,
        "private_paths_exported": False,
    }
    write_json(output_root / "storage_staging_report.json", report)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
