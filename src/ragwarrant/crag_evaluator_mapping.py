# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
import json
from pathlib import Path

from ragwarrant.generative_validation_common import mean, write_csv, write_json, write_md


ALLOWED_MAPPING_CLASSES = {
    "CRAG_GENERATED_QUALITY_LOCAL_EVALUATOR_ACTIVE",
    "CRAG_GENERATED_QUALITY_LOCAL_EVALUATOR_PARTIAL",
    "CRAG_GENERATED_QUALITY_PROXY_PLUS_EVIDENCE_ONLY",
    "CRAG_GENERATED_QUALITY_BLOCKED_SCHEMA_MAPPING",
    "CRAG_GENERATED_QUALITY_BLOCKED_NO_LABELS",
    "CRAG_GENERATED_QUALITY_BLOCKED_NO_USABLE_SIGNAL",
    "CRAG_GENERATED_QUALITY_BLOCKED_NO_LOCAL_EVALUATOR",
    "CRAG_GENERATED_QUALITY_BLOCKED_PUBLICATION_HYGIENE",
}


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def diagnose_crag_evaluator_mapping(root: Path, *, output_root: Path) -> dict[str, object]:
    stats_path = root / "artifacts/generative_llm_validation/crag/primary_outcome_statistics.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    result_class = str(stats.get("crag_evaluator_mapping_result_class", "CRAG_GENERATED_QUALITY_BLOCKED_NO_LOCAL_EVALUATOR"))
    if result_class not in ALLOWED_MAPPING_CLASSES:
        result_class = "CRAG_GENERATED_QUALITY_BLOCKED_SCHEMA_MAPPING"
    payload = {
        "suite": "ragwarrant_crag_generated_answer_evaluator_mapping_v1",
        "mapping_result_class": result_class,
        "local_evaluator_available": result_class in {"CRAG_GENERATED_QUALITY_LOCAL_EVALUATOR_ACTIVE", "CRAG_GENERATED_QUALITY_LOCAL_EVALUATOR_PARTIAL"},
        "generated_answers_scored_locally": result_class == "CRAG_GENERATED_QUALITY_LOCAL_EVALUATOR_ACTIVE",
        "raw_query_text_required_for_public_artifacts": False,
        "raw_generated_answers_required_for_public_artifacts": False,
        "public_outputs_hashes_and_scores_only": True,
        "private_paths_exported": False,
        "raw_crag_text_committed": False,
        "raw_generated_answers_committed": False,
        "raw_api_responses_committed": False,
    }
    write_json(output_root / "evaluator_mapping_manifest.json", payload)
    write_md(
        output_root / "evaluator_schema_report.md",
        f"""
# CRAG Generated-Answer Evaluator Mapping

Mapping result class: `{result_class}`

The public artifact records schema diagnostics only. Local evaluator inputs, if any, remain under a gitignored local data area and are not committed because they may contain raw questions or generated answers.
""",
    )
    return payload


def run_crag_evaluator_mapping(root: Path, *, output_root: Path) -> dict[str, object]:
    manifest = diagnose_crag_evaluator_mapping(root, output_root=output_root)
    rows = _read_rows(root / "artifacts/generative_llm_validation/crag/per_query_generation_metrics.csv")
    quality_values = [float(row.get("final_generated_quality_score", 0.0)) for row in rows]
    evidence_values = [float(row.get("evidence_support_score", 0.0)) for row in rows]
    unique_quality = len({round(value, 12) for value in quality_values})
    usable = bool(rows) and unique_quality > 1 and any(value > 0 for value in quality_values)
    result_class = str(manifest["mapping_result_class"])
    if result_class == "CRAG_GENERATED_QUALITY_LOCAL_EVALUATOR_ACTIVE" and not usable:
        result_class = "CRAG_GENERATED_QUALITY_BLOCKED_NO_USABLE_SIGNAL"
    result = {
        **manifest,
        "mapping_result_class": result_class,
        "generation_rows_checked": len(rows),
        "quality_signal_nonconstant": unique_quality > 1,
        "quality_signal_usable": usable,
        "mean_generated_quality_score": mean(quality_values),
        "mean_evidence_support_score": mean(evidence_values),
        "raw_text_exported": False,
    }
    write_csv(
        output_root / "evaluator_mapping_diagnostics.csv",
        ["metric", "value"],
        [{"metric": key, "value": value} for key, value in result.items()],
    )
    write_json(output_root / "evaluator_mapping_result.json", result)
    write_md(
        output_root / "evaluator_mapping_report.md",
        f"""
# CRAG Evaluator Mapping Result

Result class: `{result_class}`

Generation rows checked: {len(rows)}
Quality signal usable: {usable}

Public outputs contain only IDs, hashes, counts, scores, and aggregate diagnostics. Raw CRAG questions, source text, API responses, prompts, and generated answers are not committed.
""",
    )
    return result
