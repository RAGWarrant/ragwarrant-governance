from __future__ import annotations

import shutil
from pathlib import Path

from ragwarrant.storage.base import ArtifactSink, StoredArtifact


class LocalArtifactSink(ArtifactSink):
    mode = "local"

    def __init__(self, output_root: Path):
        self.output_root = output_root
        self.output_root.mkdir(parents=True, exist_ok=True)

    def put_file(self, local_path: Path, artifact_name: str) -> StoredArtifact:
        destination = self.output_root / artifact_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if local_path.resolve() != destination.resolve():
            shutil.copy2(local_path, destination)
        return StoredArtifact(uri=f"file://{artifact_name}", local_path=artifact_name)
