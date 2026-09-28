#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COPYRIGHT = "Copyright 2026 RAGWarrant contributors"
SPDX = "SPDX-License-Identifier: Apache-2.0"
PROPRIETARY_MARKERS = (
    "SPDX-License-Identifier: " + "Proprietary",
    "Proprietary " + "and confidential",
)
SOURCE_SUFFIXES = {".py", ".sh", ".ps1", ".tf"}
SOURCE_NAMES = {"Dockerfile"}
SOURCE_PREFIXES = (
    "Dockerfile",
    "src/",
    "scripts/",
    "tests/",
    "deploy/",
)
EXCLUDED_PREFIXES = ("scripts/__pycache__/",)


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line.strip()]


def is_source(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return False
    if not any(rel.startswith(prefix) for prefix in SOURCE_PREFIXES):
        return False
    return path.suffix in SOURCE_SUFFIXES or path.name in SOURCE_NAMES


def main() -> int:
    missing: list[str] = []
    proprietary: list[str] = []
    checked: list[str] = []

    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if any(marker in text for marker in PROPRIETARY_MARKERS):
            proprietary.append(rel)

        if not is_source(path):
            continue

        checked.append(rel)
        head = "\n".join(text.splitlines()[:12])
        if COPYRIGHT not in head or SPDX not in head:
            missing.append(rel)

    report = {
        "result_class": "LICENSE_HEADERS_PASSED" if not missing and not proprietary else "LICENSE_HEADERS_FAILED",
        "checked_source_files": len(checked),
        "missing_headers": missing,
        "proprietary_markers": proprietary,
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if report["result_class"] == "LICENSE_HEADERS_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
