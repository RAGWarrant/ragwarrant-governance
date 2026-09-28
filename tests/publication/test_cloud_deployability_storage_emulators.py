# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_storage_emulator_marker_registered() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "storage_emulator" in text


def test_storage_emulator_extras_are_optional_not_runtime() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    runtime_lock = (ROOT / "requirements-runtime.lock").read_text(encoding="utf-8")
    assert "storage-emulators" in pyproject
    for package in ("boto3", "azure-storage-blob", "google-cloud-storage"):
        assert package in pyproject
        assert package not in runtime_lock


def test_storage_emulator_runner_uses_pinned_images_and_cleanup() -> None:
    text = (ROOT / "scripts" / "run_storage_emulator_tests.sh").read_text(encoding="utf-8")
    assert "localstack/localstack@sha256:" in text
    assert "fc9a03f14f4668f5d874eadb77e5da5461ce735e2ce86b77b0056606c0677dba" in text
    assert "mcr.microsoft.com/azure-storage/azurite@sha256:" in text
    assert "fsouza/fake-gcs-server@sha256:" in text
    assert "--platform \"$EMULATOR_PLATFORM\"" in text
    assert "RAGWARRANT_STORAGE_EMULATOR_PLATFORM:-linux/amd64" in text
    assert ":latest" not in text
    assert "trap cleanup EXIT INT TERM" in text
    assert "pytest -q -m storage_emulator" in text


def test_storage_staging_wrapper_preserves_exit_code() -> None:
    text = (ROOT / "scripts" / "run_storage_staging_job.py").read_text(encoding="utf-8")
    assert "return result.returncode" in text
    assert "build_storage_sink" in text


def test_storage_workflow_invokes_shared_runner() -> None:
    text = (ROOT / ".github" / "workflows" / "storage-staging-validation.yml").read_text(encoding="utf-8")
    assert "scripts/run_storage_emulator_tests.sh" in text
    assert "storage_emulator_validation_report.json" in text
    assert "requirements-storage-emulators.lock" in text
    assert "--require-hashes" in text
