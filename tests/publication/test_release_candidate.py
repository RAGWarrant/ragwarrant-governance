from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.rc1_maturity import RELEASE_CANDIDATE_RESULT_CLASSES


ROOT = Path(__file__).resolve().parents[2]


def test_release_candidate_manifest_exists() -> None:
    assert (ROOT / "artifacts/release_candidate/v0.1.0-rc1/release_candidate_manifest.json").exists()


def test_release_notes_exist() -> None:
    assert (ROOT / "docs/release_notes_v0.1.0-rc1.md").exists()


def test_release_candidate_has_checksums() -> None:
    assert (ROOT / "artifacts/release_candidate/v0.1.0-rc1/release_checksums.sha256").read_text(encoding="utf-8").strip()


def test_release_candidate_result_class_allowed() -> None:
    payload = json.loads((ROOT / "artifacts/release_candidate/v0.1.0-rc1/release_candidate_manifest.json").read_text(encoding="utf-8"))
    assert payload["result_class"] in RELEASE_CANDIDATE_RESULT_CLASSES


def test_release_candidate_does_not_include_raw_data() -> None:
    payload = json.loads((ROOT / "artifacts/release_candidate/v0.1.0-rc1/release_candidate_manifest.json").read_text(encoding="utf-8"))
    assert payload["raw_data_included"] is False
