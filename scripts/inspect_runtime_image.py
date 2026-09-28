#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


FORBIDDEN_PATHS = [
    "/app/tests",
    "/app/paper",
    "/app/docs",
    "/app/results",
    "/app/artifacts",
    "/app/deployment_review",
]


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def inspect_image(image: str) -> dict[str, object]:
    inspect = run(["docker", "image", "inspect", image])
    if inspect.returncode != 0:
        raise SystemExit(inspect.stderr.strip() or inspect.stdout.strip())
    payload = json.loads(inspect.stdout)[0]
    config = payload.get("Config", {})
    path_probe = run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/sh",
            image,
            "-c",
            "for p in "
            + " ".join(FORBIDDEN_PATHS)
            + "; do [ -e \"$p\" ] && echo \"$p\"; done; echo __TOP__; find /app -maxdepth 2 -type d -print | sort",
        ]
    )
    if path_probe.returncode != 0:
        raise SystemExit(path_probe.stderr.strip() or path_probe.stdout.strip())
    before, _, after = path_probe.stdout.partition("__TOP__\n")
    forbidden = [line.strip() for line in before.splitlines() if line.strip()]
    top_paths = [line.strip() for line in after.splitlines() if line.strip()]
    labels = config.get("Labels") or {}
    return {
        "image_reference": image,
        "image_id": payload.get("Id", ""),
        "image_size_bytes": payload.get("Size", 0),
        "user": config.get("User", ""),
        "entrypoint": config.get("Entrypoint", []),
        "cmd": config.get("Cmd", []),
        "included_top_level_paths": top_paths,
        "forbidden_path_findings": forbidden,
        "base_image_digest": "sha256:a630a63cdb314e2d138a2fca3e375e319e8568346ffafac5b980f888630ac4f1",
        "lockfile_identifier": Path("requirements-runtime.lock").name,
        "source_label": labels.get("org.opencontainers.image.source", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the minimized RAGWarrant runtime image.")
    parser.add_argument("image")
    parser.add_argument("--json-out")
    args = parser.parse_args()
    result = inspect_image(args.image)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text, end="")
    return 1 if result["forbidden_path_findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
