# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.generative_validation_common import write_json, write_md
from ragwarrant.hotpotqa_generative_validation import run_hotpotqa_quality_signal_audit


def audit_hotpotqa_quality_signal(root: Path, *, output_root: Path, dry_run: bool = False) -> dict[str, object]:
    result = run_hotpotqa_quality_signal_audit(root, output_root=output_root, dry_run=dry_run)
    configured_target = 600
    actual = int(result.get("sample_size", 0))
    manifest_path = output_root / "audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "configured_larger_sample_target": configured_target,
            "larger_sample_status": "actual_generation_rows_recorded; target remains bounded and publication-safe",
            "larger_sample_target_met": actual >= configured_target,
        }
    )
    write_json(manifest_path, manifest)
    write_md(
        output_root / "quality_signal_audit_report.md",
        f"""
# HotpotQA Generative Quality-Signal Audit

Result class: `{manifest['result_class']}`

Configured larger bounded sample target: {configured_target}
Actual sanitized sample size available in this run: {actual}

The audit confirms whether generated answers and quality scores are nonconstant in the sanitized artifacts. It does not commit HotpotQA questions, contexts, supporting-fact text, prompts, or generated answers.
""",
    )
    return {**result, **manifest}
