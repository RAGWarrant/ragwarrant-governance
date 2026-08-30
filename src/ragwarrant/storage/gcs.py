from __future__ import annotations

from pathlib import Path
import os

from ragwarrant.storage.base import ArtifactSink, StorageUnavailable, StoredArtifact


class GCSArtifactSink(ArtifactSink):
    mode = "gcs"

    def __init__(self, *, bucket: str | None, prefix: str = ""):
        if not bucket:
            raise StorageUnavailable("RAGWARRANT_GCS_BUCKET is required")
        try:
            from google.api_core.exceptions import Conflict
            from google.cloud import storage
        except Exception as exc:
            raise StorageUnavailable("google-cloud-storage optional dependency is not installed") from exc
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        if os.environ.get("STORAGE_EMULATOR_HOST"):
            self.client = storage.Client.create_anonymous_client()
        else:
            self.client = storage.Client(project=os.environ.get("RAGWARRANT_GCS_PROJECT", "ragwarrant-publication-test"))
        try:
            self.bucket_obj = self.client.create_bucket(self.bucket)
        except Conflict:
            self.bucket_obj = self.client.bucket(self.bucket)

    def put_file(self, local_path: Path, artifact_name: str) -> StoredArtifact:
        blob_name = "/".join(part for part in (self.prefix, artifact_name) if part)
        blob = self.bucket_obj.blob(blob_name)
        blob.upload_from_filename(str(local_path))
        return StoredArtifact(uri=f"gs://{self.bucket}/{blob_name}", local_path=artifact_name)
