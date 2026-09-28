# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNBOOKS = [
    ROOT / "deploy" / "aws" / "RUNBOOK.md",
    ROOT / "deploy" / "azure" / "RUNBOOK.md",
    ROOT / "deploy" / "gcp" / "RUNBOOK.md",
]


def test_zero_to_first_run_runbooks_exist_with_required_sections() -> None:
    required = [
        "## Prerequisites",
        "## Preflight",
        "## Deploy",
        "## Run",
        "## Expected Outputs",
        "## Troubleshooting",
        "## Rollback",
        "## Claim Boundaries",
    ]
    for path in RUNBOOKS:
        text = path.read_text(encoding="utf-8")
        for heading in required:
            assert heading in text, f"{path} missing {heading}"
        assert "deploy/load-image-reference.sh" in text
        assert "deploy/IMAGE_DIGEST" in text


def test_runbooks_do_not_claim_platform_validation_or_production_readiness() -> None:
    forbidden = [
        "production ready",
        "production validated",
        "platform certified",
        "establishes RAG Compass superiority",
    ]
    for path in RUNBOOKS:
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text
        assert "does not establish production readiness" in text
