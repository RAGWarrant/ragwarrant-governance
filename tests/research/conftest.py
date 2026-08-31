"""PR A clean-checkout hooks for scientific-scope integration tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FOCUS1_DIGEST = "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
TARGET_MODULES = {
    "test_focus2_benchmark_integration.py",
    "test_focus2_v2_benchmark_integration.py",
}
_TEMPORARY: tempfile.TemporaryDirectory[str] | None = None
_ORIGINALS: dict[str, object] = {}


def _install_scientific_scope(items: list[pytest.Item]) -> None:
    global _TEMPORARY
    from ragwarrant.research.review_scope_authority import (
        DEFAULT_RECORD,
        VERIFIED,
        load_record,
        verify_review_scope,
    )

    verified = verify_review_scope(ROOT)
    if verified["status"] != VERIFIED:
        raise pytest.UsageError("PR A scientific review scope did not verify")
    record = load_record(ROOT / DEFAULT_RECORD)
    manifest = {
        "scope_id": verified["scope_id"],
        "benchmark_freeze_digest": FOCUS1_DIGEST,
        "input_hashes": record["scientific_sha256"],
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

    def verify_scientific_manifest(candidate, repository_root) -> str:
        current = verify_review_scope(repository_root)
        if current["status"] != VERIFIED or candidate != manifest:
            raise ValueError("PR A scientific review scope changed")
        return FOCUS1_DIGEST

    def verify_scientific_v1_reference() -> None:
        current = verify_review_scope(ROOT)
        if current["status"] != VERIFIED:
            raise ValueError("PR A scientific V1 reference changed")

    focus2_benchmark.verify_benchmark_freeze_manifest = verify_scientific_manifest
    focus2_v2_benchmark._verify_v1_baseline = verify_scientific_v1_reference
    for item in items:
        if Path(str(item.path)).name == "test_focus2_benchmark_integration.py":
            item.module.FREEZE_MANIFEST = manifest_path


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if any(Path(str(item.path)).name in TARGET_MODULES for item in items):
        _install_scientific_scope(items)


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
