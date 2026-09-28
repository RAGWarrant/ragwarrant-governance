# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from pathlib import Path

from ragwarrant.storage.azure_blob import AzureBlobArtifactSink
from ragwarrant.storage.base import ArtifactSink, StorageUnavailable
from ragwarrant.storage.gcs import GCSArtifactSink
from ragwarrant.storage.local import LocalArtifactSink
from ragwarrant.storage.s3 import S3ArtifactSink


class DisabledArtifactSink(ArtifactSink):
    mode = "disabled"

    def put_file(self, local_path: Path, artifact_name: str):
        raise StorageUnavailable("artifact storage is disabled")

    def healthcheck(self) -> dict[str, object]:
        return {"mode": self.mode, "available": False, "secrets_logged": False}


def build_storage_sink(mode: str | None = None, output_root: str | Path | None = None) -> ArtifactSink:
    selected = (mode or os.environ.get("RAGWARRANT_STORAGE_MODE") or "local").strip().lower()
    root = Path(output_root or os.environ.get("RAGWARRANT_OUTPUT_ROOT") or "artifacts/storage")
    if selected == "local":
        return LocalArtifactSink(root)
    if selected == "disabled":
        return DisabledArtifactSink()
    if selected == "azure_blob":
        return AzureBlobArtifactSink(container=os.environ.get("RAGWARRANT_AZURE_BLOB_CONTAINER"), prefix=os.environ.get("RAGWARRANT_AZURE_BLOB_PREFIX", ""))
    if selected == "s3":
        return S3ArtifactSink(bucket=os.environ.get("RAGWARRANT_S3_BUCKET"), prefix=os.environ.get("RAGWARRANT_S3_PREFIX", ""))
    if selected == "gcs":
        return GCSArtifactSink(bucket=os.environ.get("RAGWARRANT_GCS_BUCKET"), prefix=os.environ.get("RAGWARRANT_GCS_PREFIX", ""))
    raise StorageUnavailable(f"unknown storage mode: {selected}")
