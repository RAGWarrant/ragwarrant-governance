"""Non-authoritative clean-checkout adapters for research integration tests."""

from __future__ import annotations

import json
import hashlib
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FOCUS1_DIGEST = "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
V1_SOURCE_SHA256 = "87e88342354346d0dceb29f45946e846b68f6b1fbaa42a946d5a53822ef4e8ad"
TEST_FREEZE_INPUTS = (
    "configs/research/false_promotion_benchmark_v1.yaml",
    "src/ragwarrant/research/benchmark.py",
    "src/ragwarrant/research/methods.py",
    "src/ragwarrant/research/simulator.py",
    "src/ragwarrant/research/types.py",
)
TARGET_MODULES = {
    "test_focus2_benchmark_integration.py",
    "test_focus2_v2_benchmark_integration.py",
}
_TEMPORARY: tempfile.TemporaryDirectory[str] | None = None
_ORIGINALS: dict[str, object] = {}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _install_test_freeze_adapter(items: list[pytest.Item]) -> None:
    """Supply ignored freeze inputs for tests without making an authority claim."""

    global _TEMPORARY
    input_hashes = {path: _sha256(ROOT / path) for path in TEST_FREEZE_INPUTS}
    manifest = {
        "test_fixture_only": True,
        "benchmark_freeze_digest": FOCUS1_DIGEST,
        "input_hashes": input_hashes,
    }
    _TEMPORARY = tempfile.TemporaryDirectory(prefix="ragwarrant-pr-a-scope-")
    manifest_path = Path(_TEMPORARY.name) / "scope_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    from ragwarrant.research import focus2_benchmark, focus2_v2_benchmark

    _ORIGINALS.update(
        manifest_path=focus2_benchmark.FREEZE_MANIFEST_PATH,
        manifest_verifier=focus2_benchmark.verify_benchmark_freeze_manifest,
        v1_verifier=focus2_v2_benchmark._verify_v1_baseline,
    )
    focus2_benchmark.FREEZE_MANIFEST_PATH = manifest_path

    def verify_test_manifest(candidate, repository_root) -> str:
        root = Path(repository_root)
        current = {path: _sha256(root / path) for path in TEST_FREEZE_INPUTS}
        if candidate != manifest or current != input_hashes:
            raise ValueError("test-only freeze inputs changed during execution")
        return FOCUS1_DIGEST

    def verify_test_v1_reference() -> None:
        source = ROOT / "src/ragwarrant/research/fixed_sample_warrant.py"
        if _sha256(source) != V1_SOURCE_SHA256:
            raise ValueError("test-only V1 source reference changed")

    focus2_benchmark.verify_benchmark_freeze_manifest = verify_test_manifest
    focus2_v2_benchmark._verify_v1_baseline = verify_test_v1_reference
    for item in items:
        if Path(str(item.path)).name == "test_focus2_benchmark_integration.py":
            item.module.FREEZE_MANIFEST = manifest_path


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if any(Path(str(item.path)).name in TARGET_MODULES for item in items):
        _install_test_freeze_adapter(items)


def pytest_sessionfinish() -> None:
    global _TEMPORARY
    if not _ORIGINALS:
        return
    from ragwarrant.research import focus2_benchmark, focus2_v2_benchmark

    focus2_benchmark.FREEZE_MANIFEST_PATH = _ORIGINALS["manifest_path"]
    focus2_benchmark.verify_benchmark_freeze_manifest = _ORIGINALS[
        "manifest_verifier"
    ]
    focus2_v2_benchmark._verify_v1_baseline = _ORIGINALS["v1_verifier"]
    _ORIGINALS.clear()
    if _TEMPORARY is not None:
        _TEMPORARY.cleanup()
        _TEMPORARY = None
