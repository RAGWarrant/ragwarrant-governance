# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import os

from ragwarrant.storage.base import ArtifactSink, StorageUnavailable, StoredArtifact


class AzureBlobArtifactSink(ArtifactSink):
    mode = "azure_blob"

    def __init__(self, *, container: str | None, prefix: str = ""):
        if not container:
            raise StorageUnavailable("RAGWARRANT_AZURE_BLOB_CONTAINER is required")
        try:
            from azure.core.exceptions import ResourceExistsError
            from azure.storage.blob import BlobServiceClient
        except Exception as exc:
            raise StorageUnavailable("azure-storage-blob optional dependency is not installed") from exc
        self.container = container
        self.prefix = prefix.strip("/")
        connection_string = os.environ.get("RAGWARRANT_AZURE_BLOB_CONNECTION_STRING") or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        account_url = os.environ.get("RAGWARRANT_AZURE_BLOB_ENDPOINT")
        if connection_string:
            self.client = BlobServiceClient.from_connection_string(connection_string)
        elif account_url:
            self.client = BlobServiceClient(account_url=account_url, credential=os.environ.get("RAGWARRANT_AZURE_BLOB_CREDENTIAL"))
        else:
            raise StorageUnavailable("RAGWARRANT_AZURE_BLOB_CONNECTION_STRING or RAGWARRANT_AZURE_BLOB_ENDPOINT is required")
        try:
            self.client.create_container(self.container)
        except ResourceExistsError:
            pass

    def put_file(self, local_path: Path, artifact_name: str) -> StoredArtifact:
        blob_name = "/".join(part for part in (self.prefix, artifact_name) if part)
        blob = self.client.get_blob_client(container=self.container, blob=blob_name)
        with local_path.open("rb") as handle:
            blob.upload_blob(handle, overwrite=True)
        return StoredArtifact(uri=f"azure-blob://{self.container}/{blob_name}", local_path=artifact_name)
