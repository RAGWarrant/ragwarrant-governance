# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.container_security_scans import SECURITY_SCAN_RESULT_CLASSES


ROOT = Path(__file__).resolve().parents[2]


def test_optional_security_scans_have_skip_or_result() -> None:
    payload = json.loads((ROOT / "artifacts/docker_hardening/container_security_scan_manifest.json").read_text(encoding="utf-8"))
    assert payload["result_class"] in SECURITY_SCAN_RESULT_CLASSES
    assert payload["secrets_exported"] is False
    assert payload["private_paths_exported"] is False


def test_optional_security_scans_include_docker_scout_detection() -> None:
    payload = json.loads((ROOT / "artifacts/docker_hardening/container_security_scan_manifest.json").read_text(encoding="utf-8"))
    assert "docker_scout" in payload["tools_checked"]
