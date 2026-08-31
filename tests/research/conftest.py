"""Clean-checkout portability hooks for optional local research dependencies."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_PINNED_DRAND_CLIENT = (
    REPOSITORY_ROOT
    / ".github"
    / "drand-verifier"
    / "node_modules"
    / "drand-client"
    / "package.json"
)
_OPTIONAL_DRAND_CLIENT_TESTS = {
    "test_raw_master_seed_is_not_exposed_in_public_provenance",
    "test_self_asserted_verified_flags_cannot_replace_bls_verification",
    "test_protocol_slice_does_not_modify_historical_evidence",
}
_FOCUS1_WORKSPACE_TEST_MODULES = {
    "test_focus2_benchmark_integration.py",
    "test_focus2_v2_benchmark_integration.py",
}
_FOCUS1_FREEZE_DIGEST = (
    "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
)
_PORTABLE_FREEZE_DIRECTORY: tempfile.TemporaryDirectory[str] | None = None
_ORIGINAL_FREEZE_MANIFEST_PATH: Path | None = None
_ORIGINAL_FOCUS2_REPOSITORY_ROOT: Path | None = None


def _install_portable_focus1_freeze(items: list[pytest.Item]) -> None:
    """Bind Focus 2 tests to checkpoint-authoritative manifest bytes."""

    global _ORIGINAL_FREEZE_MANIFEST_PATH, _ORIGINAL_FOCUS2_REPOSITORY_ROOT
    global _PORTABLE_FREEZE_DIRECTORY
    from ragwarrant.research.packaging_portability_amendment import (
        HISTORICAL_FOCUS1_AUTHORITY_VERIFIED,
        IMMUTABLE_OWNER_REVIEW_COMMIT,
        _git_blob,
        verify_historical_focus1_authority,
    )

    authority = verify_historical_focus1_authority(REPOSITORY_ROOT)
    if authority["status"] != HISTORICAL_FOCUS1_AUTHORITY_VERIFIED:
        raise pytest.UsageError("Historical Focus 1 authority did not verify")
    fixture = authority["manifest"]
    _PORTABLE_FREEZE_DIRECTORY = tempfile.TemporaryDirectory(
        prefix="ragwarrant-portable-focus1-freeze-"
    )
    frozen_root = Path(_PORTABLE_FREEZE_DIRECTORY.name)
    for relative_path in fixture["input_hashes"]:
        destination = frozen_root.joinpath(*relative_path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            _git_blob(REPOSITORY_ROOT, IMMUTABLE_OWNER_REVIEW_COMMIT, relative_path)
        )
    manifest_path = frozen_root / "freeze_manifest.json"
    manifest_path.write_text(
        json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    from ragwarrant.research import focus2_benchmark
    _ORIGINAL_FREEZE_MANIFEST_PATH = focus2_benchmark.FREEZE_MANIFEST_PATH
    _ORIGINAL_FOCUS2_REPOSITORY_ROOT = focus2_benchmark.REPOSITORY_ROOT
    focus2_benchmark.FREEZE_MANIFEST_PATH = manifest_path
    focus2_benchmark.REPOSITORY_ROOT = frozen_root
    for item in items:
        if Path(str(item.path)).name == "test_focus2_benchmark_integration.py":
            item.module.FREEZE_MANIFEST = manifest_path


def pytest_sessionfinish() -> None:
    """Remove the generated operating-system temporary fixture."""

    global _ORIGINAL_FREEZE_MANIFEST_PATH, _ORIGINAL_FOCUS2_REPOSITORY_ROOT
    global _PORTABLE_FREEZE_DIRECTORY
    if _ORIGINAL_FREEZE_MANIFEST_PATH is not None:
        from ragwarrant.research import focus2_benchmark

        focus2_benchmark.FREEZE_MANIFEST_PATH = _ORIGINAL_FREEZE_MANIFEST_PATH
        _ORIGINAL_FREEZE_MANIFEST_PATH = None
    if _ORIGINAL_FOCUS2_REPOSITORY_ROOT is not None:
        from ragwarrant.research import focus2_benchmark

        focus2_benchmark.REPOSITORY_ROOT = _ORIGINAL_FOCUS2_REPOSITORY_ROOT
        _ORIGINAL_FOCUS2_REPOSITORY_ROOT = None
    if _PORTABLE_FREEZE_DIRECTORY is not None:
        _PORTABLE_FREEZE_DIRECTORY.cleanup()
        _PORTABLE_FREEZE_DIRECTORY = None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Gate only tests whose accepted contracts require ignored local inputs."""

    if any(
        Path(str(item.path)).name in _FOCUS1_WORKSPACE_TEST_MODULES for item in items
    ):
        _install_portable_focus1_freeze(items)
    drand_unavailable = pytest.mark.skip(
        reason=(
            "optional pinned drand-client dependency is absent in this clean "
            "checkout; only local BLS-verifier integration is skipped"
        )
    )
    for item in items:
        if (
            not _PINNED_DRAND_CLIENT.is_file()
            and Path(str(item.path)).name == "test_public_beacon_entropy.py"
            and item.name in _OPTIONAL_DRAND_CLIENT_TESTS
        ):
            item.add_marker(drand_unavailable)
