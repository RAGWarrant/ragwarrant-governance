# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_json(script: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, script],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def test_license_headers_pass() -> None:
    report = run_json("scripts/validate_license_headers.py")
    assert report["result_class"] == "LICENSE_HEADERS_PASSED"
    assert report["missing_headers"] == []
    assert report["proprietary_markers"] == []


def test_open_core_boundary_passes() -> None:
    report = run_json("scripts/validate_open_core_boundary.py")
    assert report["result_class"] == "OPEN_CORE_BOUNDARY_PASSED"
    assert report["failures"] == []
    assert report["ownership_gate"] == "OWNERSHIP_GATE_BLOCKED_PENDING_HUMAN_IP_REVIEW"
    assert report["enterprise_repository_creation"] == "BLOCKED_PENDING_RIGHTS_CONFIRMATION"
