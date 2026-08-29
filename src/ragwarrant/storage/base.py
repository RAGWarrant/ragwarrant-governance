from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class StorageUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredArtifact:
    uri: str
    local_path: str


class ArtifactSink:
    mode = "base"

    def put_file(self, local_path: Path, artifact_name: str) -> StoredArtifact:
        raise NotImplementedError

    def healthcheck(self) -> dict[str, object]:
        return {"mode": self.mode, "available": True, "secrets_logged": False}
