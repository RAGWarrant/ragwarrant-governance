# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ragwarrant.utils.hashing import stable_hash


class WriteOnceError(RuntimeError):
    """Raised when an append-only write would overwrite an existing artifact."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def unique_id(prefix: str, payload: dict[str, Any] | None = None) -> str:
    timestamp = utc_timestamp()
    digest = stable_hash({"timestamp": timestamp, **(payload or {})}, 10)
    return f"{prefix}_{timestamp}-{digest}"


def backup_existing(path: Path) -> Path:
    backup = path.with_name(f"{path.name}.bak-{utc_timestamp()}")
    if path.is_dir():
        shutil.copytree(path, backup)
    else:
        shutil.copy2(path, backup)
    return backup


def write_text_once(path: Path, text: str, *, overwrite: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise WriteOnceError(f"Refusing to overwrite existing file: {path}")
    if path.exists() and overwrite:
        backup_existing(path)
    mode = "w" if overwrite else "x"
    with path.open(mode, encoding="utf-8") as handle:
        handle.write(text)
    return path


def write_json_once(path: Path, payload: dict[str, Any], *, overwrite: bool = False) -> Path:
    return write_text_once(path, json.dumps(payload, indent=2, sort_keys=True) + "\n", overwrite=overwrite)


@dataclass(frozen=True)
class WriteOncePathManager:
    root: Path
    protected_paths: list[Path]

    def is_protected(self, path: Path) -> bool:
        resolved = path.expanduser().resolve()
        for protected in self.protected_paths:
            protected_resolved = protected.expanduser().resolve()
            if resolved == protected_resolved or protected_resolved in resolved.parents:
                return True
        return False

    def ensure_writable_path(self, path: Path, *, overwrite: bool = False) -> None:
        if self.is_protected(path):
            raise WriteOnceError(f"Refusing to write inside protected result path: {path}")
        if path.exists() and not overwrite:
            raise WriteOnceError(f"Refusing to overwrite existing path: {path}")

    def create_experiment_dir(self, prefix: str, payload: dict[str, Any] | None = None) -> tuple[str, Path]:
        for attempt in range(100):
            experiment_id = unique_id(prefix, {**(payload or {}), "attempt": attempt})
            path = self.root / experiment_id
            if path.exists():
                continue
            self.ensure_writable_path(path)
            path.mkdir(parents=True)
            return experiment_id, path
        raise WriteOnceError(f"Could not allocate unique experiment directory under {self.root}")

    def write_json(self, path: Path, payload: dict[str, Any], *, overwrite: bool = False) -> Path:
        self.ensure_writable_path(path, overwrite=overwrite)
        return write_json_once(path, payload, overwrite=overwrite)

    def write_text(self, path: Path, text: str, *, overwrite: bool = False) -> Path:
        self.ensure_writable_path(path, overwrite=overwrite)
        return write_text_once(path, text, overwrite=overwrite)
