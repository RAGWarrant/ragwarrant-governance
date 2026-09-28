#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDED_PATHS = [
    ".dockerignore",
    "Dockerfile",
    "pyproject.toml",
    "requirements-runtime.lock",
    "configs",
    "schemas",
    "src",
]


def iter_files() -> list[Path]:
    files: list[Path] = []
    for item in INCLUDED_PATHS:
        path = ROOT / item
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith((".pyc", ".pyo"))))
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix())


def compute_hash() -> str:
    digest = hashlib.sha256()
    for path in iter_files():
        rel = path.relative_to(ROOT).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> int:
    print(compute_hash())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

