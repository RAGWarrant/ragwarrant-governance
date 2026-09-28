# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_docker_static_validation_artifact_exists() -> None:
    assert (ROOT / "artifacts/docker_hardening/docker_static_validation.json").exists()


def test_docker_static_validation_passes() -> None:
    payload = json.loads((ROOT / "artifacts/docker_hardening/docker_static_validation.json").read_text(encoding="utf-8"))
    assert payload["result_class"] == "DOCKER_STATIC_VALIDATION_PASSED"
    assert payload["failures"] == []
