from __future__ import annotations

import hashlib
import re
from pathlib import Path


def hash_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    return max(1, int(len(re.findall(r"\S+", text)) * 1.25)) if text else 0


def safe_model_slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", model)[:80] or "model"


def write_local_answer(provider: str, model: str, answer: str) -> str:
    root = Path(".local_data/generative_answers") / provider / safe_model_slug(model)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{hash_text(answer)}.txt"
    path.write_text(answer, encoding="utf-8")
    return path.as_posix()
