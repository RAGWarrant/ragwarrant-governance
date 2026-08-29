from __future__ import annotations

from pathlib import Path
import os

from ragwarrant.storage.base import ArtifactSink, StorageUnavailable, StoredArtifact


class S3ArtifactSink(ArtifactSink):
    mode = "s3"

    def __init__(self, *, bucket: str | None, prefix: str = ""):
        if not bucket:
            raise StorageUnavailable("RAGWARRANT_S3_BUCKET is required")
        try:
            import boto3
        except Exception as exc:
            raise StorageUnavailable("boto3 optional dependency is not installed") from exc
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("RAGWARRANT_S3_ENDPOINT_URL"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "emulator-access-key"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "emulator-secret-key"),
            region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        )
        try:
            self.client.create_bucket(Bucket=self.bucket)
        except Exception:
            pass

    def put_file(self, local_path: Path, artifact_name: str) -> StoredArtifact:
        key = "/".join(part for part in (self.prefix, artifact_name) if part)
        self.client.upload_file(str(local_path), self.bucket, key)
        return StoredArtifact(uri=f"s3://{self.bucket}/{key}", local_path=artifact_name)
