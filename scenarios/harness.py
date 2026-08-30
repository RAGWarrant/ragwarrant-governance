"""Minimal publication harness placeholder.

The full validation harness lives in `src/ragwarrant` and the selected run
artifacts. Licensed-data reproduction requires external data mounts.
"""

from pathlib import Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]
