from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


RAW_TEXT_KEYS = {
    "query_text",
    "question_text",
    "raw_query",
    "raw_question",
    "raw_response",
    "api_response",
    "context_text",
    "document_text",
    "source_snippet",
    "supporting_fact_text",
}


def stable_hash(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def assert_no_raw_text_keys(payload: Any, prefix: str = "") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            child = f"{prefix}.{key}" if prefix else key
            if key in RAW_TEXT_KEYS:
                raise ValueError(f"raw text key not allowed: {child}")
            assert_no_raw_text_keys(value, child)
    elif isinstance(payload, list):
        for idx, value in enumerate(payload):
            assert_no_raw_text_keys(value, f"{prefix}[{idx}]")


def write_sanitized_json(path: Path, payload: Any) -> None:
    assert_no_raw_text_keys(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
