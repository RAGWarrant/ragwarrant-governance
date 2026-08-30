from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ragwarrant.research.public_beacon import build_execution_closure


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a public FULL closure independent of scientific direction."
    )
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--execution-manifest", type=Path)
    parser.add_argument("--benchmark-output", type=Path)
    parser.add_argument("--workflow-conclusion", required=True)
    parser.add_argument("--workflow-run-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seal = json.loads(args.seal.read_text(encoding="utf-8"))
    execution = None
    if args.execution_manifest and args.execution_manifest.is_file():
        execution = json.loads(args.execution_manifest.read_text(encoding="utf-8"))
    output_hashes_verified = False
    if execution is not None and args.benchmark_output and args.benchmark_output.is_dir():
        expected = execution.get("output_hashes")
        if isinstance(expected, dict) and expected:
            actual = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in args.benchmark_output.iterdir()
                if path.is_file() and path.name != "full_execution_manifest.json"
            }
            output_hashes_verified = actual == expected
    closure = build_execution_closure(
        seal,
        execution,
        workflow_conclusion=args.workflow_conclusion,
        workflow_run_url=args.workflow_run_url,
        output_hashes_verified=output_hashes_verified,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(closure, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
