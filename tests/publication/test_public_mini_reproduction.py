# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_public_mini_reproduction_config_exists() -> None:
    assert (ROOT / "configs/experiments/ragwarrant_public_mini_reproduction_v1.yaml").exists()


def test_public_mini_reproduction_script_exists() -> None:
    assert (ROOT / "scripts/run_public_mini_reproduction.py").exists()


def test_public_mini_reproduction_outputs_machine_readable_result_class() -> None:
    manifest = json.loads((ROOT / "artifacts/public_mini_reproduction/mini_reproduction_manifest.json").read_text(encoding="utf-8"))
    assert manifest["result_class"] in {
        "PUBLIC_MINI_REPRODUCTION_PASSED",
        "PUBLIC_MINI_REPRODUCTION_GOVERNANCE_PROMOTES_SAFE_POLICY",
        "PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED",
        "PUBLIC_MINI_REPRODUCTION_INCONCLUSIVE",
        "PUBLIC_MINI_REPRODUCTION_BLOCKED",
    }


def test_public_mini_reproduction_uses_no_raw_external_data() -> None:
    manifest = json.loads((ROOT / "artifacts/public_mini_reproduction/mini_reproduction_manifest.json").read_text(encoding="utf-8"))
    assert manifest["requires_crag_raw_data"] is False
    assert manifest["requires_hotpotqa_raw_data"] is False
    assert manifest["raw_external_data_used"] is False


def test_public_mini_reproduction_make_target_exists() -> None:
    assert "reproduce-public-mini" in (ROOT / "Makefile").read_text(encoding="utf-8")


def test_public_mini_reproduction_claim_update_exists() -> None:
    assert (ROOT / "results/public_mini_reproduction/claim_update.json").exists()
