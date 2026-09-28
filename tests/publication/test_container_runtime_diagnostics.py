# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.container_runtime import CONTAINER_RUNTIME_RESULT_CLASSES


ROOT = Path(__file__).resolve().parents[2]


def test_container_runtime_diagnostic_script_exists() -> None:
    assert (ROOT / "scripts/diagnose_container_runtime.py").exists()


def test_container_runtime_result_classes_defined() -> None:
    assert "CONTAINER_RUNTIME_CLI_PRESENT_DAEMON_UNAVAILABLE" in CONTAINER_RUNTIME_RESULT_CLASSES
    assert "CONTAINER_RUNTIME_UNAVAILABLE" in CONTAINER_RUNTIME_RESULT_CLASSES


def test_container_runtime_diagnostics_do_not_export_private_paths() -> None:
    payload = json.loads((ROOT / "artifacts/docker_hardening/container_runtime_diagnostics.json").read_text(encoding="utf-8"))
    text = json.dumps(payload)
    assert "/Users/" not in text
    assert "Documents/New project" not in text
    assert payload["private_paths_exported"] is False


def test_container_runtime_diagnostics_do_not_export_secrets() -> None:
    payload = json.loads((ROOT / "artifacts/docker_hardening/container_runtime_diagnostics.json").read_text(encoding="utf-8"))
    text = json.dumps(payload)
    assert "OPENAI_API_KEY" not in text
    assert "Bearer " not in text
    assert payload["secrets_exported"] is False
