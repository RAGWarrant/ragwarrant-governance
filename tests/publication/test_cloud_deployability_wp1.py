# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_uses_multistage_digest_pinned_runtime() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "AS builder" in text
    assert "AS runtime" in text
    assert "python:3.11-slim@sha256:a630a63cdb314e2d138a2fca3e375e319e8568346ffafac5b980f888630ac4f1" in text
    assert "HEALTHCHECK" not in text
    assert "pip install --require-hashes -r requirements-runtime.lock" in text
    assert "pip install --no-deps /tmp/wheelhouse/*.whl" in text


def test_runtime_image_does_not_copy_publication_or_test_trees() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    forbidden = [
        "COPY tests",
        "COPY paper",
        "COPY docs",
        "COPY results",
        "COPY artifacts",
        "COPY deployment_review",
    ]
    for needle in forbidden:
        assert needle not in text


def test_runtime_locks_are_hashed_and_split_from_dev_dependencies() -> None:
    runtime = (ROOT / "requirements-runtime.lock").read_text(encoding="utf-8")
    dev = (ROOT / "requirements-dev.lock").read_text(encoding="utf-8")
    assert "--hash=sha256:" in runtime
    assert "--hash=sha256:" in dev
    assert "pytest==" not in runtime
    assert "pytest==" in dev


def test_runtime_inspection_script_reports_forbidden_paths() -> None:
    script = (ROOT / "scripts/inspect_runtime_image.py").read_text(encoding="utf-8")
    for path in ["/app/tests", "/app/paper", "/app/docs", "/app/results", "/app/artifacts", "/app/deployment_review"]:
        assert path in script


def test_container_supply_chain_documents_digest_and_healthcheck_boundary() -> None:
    text = (ROOT / "docs/container_supply_chain.md").read_text(encoding="utf-8")
    assert "sha256:a630a63cdb314e2d138a2fca3e375e319e8568346ffafac5b980f888630ac4f1" in text
    assert "no Docker" in text
    assert "HEALTHCHECK" in text
