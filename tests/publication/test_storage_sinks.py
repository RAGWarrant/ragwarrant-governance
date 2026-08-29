from __future__ import annotations

from pathlib import Path

import pytest

from ragwarrant.storage.base import StorageUnavailable
from ragwarrant.storage.factory import build_storage_sink


def test_local_storage_sink_writes_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"ok": true}\n', encoding="utf-8")
    sink = build_storage_sink("local", tmp_path / "out")
    stored = sink.put_file(source, "nested/artifact.json")
    assert stored.uri == "file://nested/artifact.json"
    assert (tmp_path / "out/nested/artifact.json").exists()


def test_storage_factory_defaults_to_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("RAGWARRANT_STORAGE_MODE", raising=False)
    sink = build_storage_sink(output_root=tmp_path)
    assert sink.mode == "local"


def test_azure_blob_sink_blocks_without_dependency_or_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAGWARRANT_AZURE_BLOB_CONTAINER", raising=False)
    with pytest.raises(StorageUnavailable):
        build_storage_sink("azure_blob")


def test_s3_sink_blocks_without_dependency_or_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAGWARRANT_S3_BUCKET", raising=False)
    with pytest.raises(StorageUnavailable):
        build_storage_sink("s3")


def test_gcs_sink_blocks_without_dependency_or_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAGWARRANT_GCS_BUCKET", raising=False)
    with pytest.raises(StorageUnavailable):
        build_storage_sink("gcs")


def test_storage_sinks_do_not_log_secrets(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"safe": true}\n', encoding="utf-8")
    sink = build_storage_sink("local", tmp_path / "out")
    sink.put_file(source, "artifact.json")
    captured = capsys.readouterr()
    assert "SECRET" not in captured.out.upper()
    assert "SECRET" not in captured.err.upper()
