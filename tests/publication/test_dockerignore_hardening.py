# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _dockerignore() -> str:
    return (ROOT / ".dockerignore").read_text(encoding="utf-8")


def test_dockerignore_exists() -> None:
    assert (ROOT / ".dockerignore").exists()


def test_dockerignore_excludes_local_data() -> None:
    assert ".local_data" in _dockerignore()


def test_dockerignore_excludes_env_files() -> None:
    text = _dockerignore()
    assert ".env" in text
    assert ".env.*" in text


def test_dockerignore_excludes_secret_key_files() -> None:
    text = _dockerignore()
    assert "*.pem" in text
    assert "*.key" in text
    assert "*.p12" in text
    assert "*.pfx" in text


def test_dockerignore_excludes_large_model_files() -> None:
    text = _dockerignore()
    for pattern in ["*.safetensors", "*.onnx", "*.ckpt", "*.arrow"]:
        assert pattern in text


def test_dockerignore_does_not_exclude_required_configs() -> None:
    text = _dockerignore()
    assert "\nconfigs\n" not in text
    assert "\nsrc\n" not in text
    assert "\nscripts\n" not in text
