from __future__ import annotations

from pathlib import Path


def docker_smoke_command_documented(root: Path = Path(".")) -> bool:
    dockerfile = root / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8") if dockerfile.exists() else ""
    return dockerfile.exists() and "ragwarrant" in text and "run-suite" in text
