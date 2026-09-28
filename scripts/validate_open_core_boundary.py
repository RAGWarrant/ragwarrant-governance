#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "LICENSE",
    "NOTICE",
    "TRADEMARKS.md",
    "GOVERNANCE.md",
    "COMMERCIAL.md",
    "SUPPORT.md",
    "CONTRIBUTING.md",
    "CLA.md",
    "docs/licensing/THIRD_PARTY_DATA_BOUNDARIES.md",
    "docs/product/OPEN_CORE_ARCHITECTURE.md",
    "docs/product/RELEASE_CHANNELS.md",
)
ENTERPRISE_URL = "RAGWarrant/" + "ragwarrant-enterprise"
ENTERPRISE_URL_ALLOWED_PREFIXES = (
    "COMMERCIAL.md",
    "deployment_review/open_core_foundation/",
    "docs/product/",
)
COMMERCIAL_DOCS = (
    "COMMERCIAL.md",
    "SUPPORT.md",
    "README.md",
)
PROHIBITED_COMMERCIAL_CLAIM_TERMS = (
    "CRAG-derived performance",
    "CRAG proves",
    "CRAG validated enterprise",
    "CRAG production",
)


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line.strip()]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []

    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            failures.append(f"missing required file: {rel}")

    license_text = read("LICENSE") if (ROOT / "LICENSE").exists() else ""
    if "Apache License" not in license_text or "https://www.apache.org/licenses/LICENSE-2.0" not in license_text:
        failures.append("LICENSE is not recognized as Apache-2.0 text")

    if "RAGWarrant" + "®" in "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in tracked_files() if path.suffix in {".md", ".txt", ".toml", ".py", ".yml", ".yaml"}
    ):
        failures.append("registration symbol appears without verified registration")

    for rel in ("src/ragwarrant_enterprise", "ragwarrant-enterprise", "enterprise"):
        if (ROOT / rel).exists():
            failures.append(f"enterprise implementation path is committed publicly: {rel}")

    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if ENTERPRISE_URL in text and not rel.startswith(ENTERPRISE_URL_ALLOWED_PREFIXES):
            failures.append(f"enterprise repository URL outside allowed docs: {rel}")
        if "SPDX-License-Identifier: " + "Proprietary" in text:
            failures.append(f"proprietary SPDX marker in public core: {rel}")

    for rel in COMMERCIAL_DOCS:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in PROHIBITED_COMMERCIAL_CLAIM_TERMS:
            if marker in text:
                failures.append(f"commercial CRAG claim marker `{marker}` in {rel}")

    report = {
        "result_class": "OPEN_CORE_BOUNDARY_PASSED" if not failures else "OPEN_CORE_BOUNDARY_FAILED",
        "failures": failures,
        "enterprise_repository_creation": "BLOCKED_PENDING_RIGHTS_CONFIRMATION",
        "ownership_gate": "OWNERSHIP_GATE_BLOCKED_PENDING_HUMAN_IP_REVIEW",
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
