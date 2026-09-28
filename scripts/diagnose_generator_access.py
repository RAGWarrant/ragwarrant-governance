#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ragwarrant.generative_validation_common import write_json, write_md
from ragwarrant.generators.base import GeneratorUnavailable
from ragwarrant.generators.factory import discover_generator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default=os.environ.get("RAGWARRANT_GENERATOR_PROVIDER", "ollama"))
    parser.add_argument("--model", default=os.environ.get("RAGWARRANT_GENERATOR_MODEL", "qwen3:8b"))
    parser.add_argument("--output-root", default="deployment_review/generative_llm_validation_quality_signal_audit")
    parser.add_argument("--timeout-s", type=float, default=60.0)
    args = parser.parse_args()
    os.environ["RAGWARRANT_GENERATOR_PROVIDER"] = args.provider
    os.environ["RAGWARRANT_GENERATOR_MODEL"] = args.model
    discovery = discover_generator(dry_run=False)
    started = time.perf_counter()
    payload: dict[str, object] = {
        "provider": args.provider,
        "model": args.model,
        "available": discovery.available,
        "status": discovery.status,
        "local_or_hosted": discovery.local_or_hosted,
        "instructions": discovery.instructions,
        "ollama_base_url_configured": bool(os.environ.get("RAGWARRANT_OLLAMA_BASE_URL", "http://localhost:11434")),
        "local_openai_base_url_configured": bool(os.environ.get("RAGWARRANT_LOCAL_OPENAI_BASE_URL", "")),
        "test_prompt_hash_only": True,
        "raw_test_response_committed": False,
    }
    if discovery.generator is not None:
        try:
            result = discovery.generator.generate(
                "Return exactly: OK",
                model=discovery.model,
                temperature=0.0,
                max_tokens=128,
                timeout_s=args.timeout_s,
            )
            payload.update(
                {
                    "test_generation_available": True,
                    "test_answer_hash": result.answer_hash,
                    "test_answer_char_count": result.answer_char_count,
                    "test_answer_token_estimate": result.answer_token_estimate,
                    "test_latency_ms": result.latency_ms,
                    "finish_reason": result.finish_reason,
                    "error_type": result.error_type,
                    "raw_answer_local_path_committed": False,
                }
            )
        except GeneratorUnavailable as exc:
            payload.update(
                {
                    "test_generation_available": False,
                    "failure_reason": str(exc),
                }
            )
    payload["diagnosis_latency_ms"] = (time.perf_counter() - started) * 1000.0
    output_root = ROOT / args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "generator_access_diagnosis.json", payload)
    write_md(
        output_root / "generator_access_diagnosis.md",
        f"""
# Generator Access Diagnosis

Provider: `{payload['provider']}`
Model: `{payload['model']}`
Available: `{payload['available']}`
Test generation available: `{payload.get('test_generation_available', False)}`
Test answer character count: `{payload.get('test_answer_char_count', 0)}`

Only hashes, counts, timings, and status fields are written. The fixed diagnostic response text is not committed.
""",
    )
    print(f"generator access diagnosis: {payload.get('test_generation_available', False)}")


if __name__ == "__main__":
    main()
