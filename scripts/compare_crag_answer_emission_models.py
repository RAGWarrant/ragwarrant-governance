#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_diagnostics(path: Path) -> dict[str, str]:
    diag_path = path.parent / "quality_signal_diagnostics.csv"
    if not diag_path.exists():
        return {}
    with diag_path.open(newline="", encoding="utf-8") as handle:
        return {row["metric"]: row["value"] for row in csv.DictReader(handle)}


def summarize(paths: list[Path]) -> dict[str, Any]:
    runs = []
    for path in paths:
        stats = load_json(path)
        diag = load_diagnostics(path)
        generation_rows = int(stats.get("generation_rows", 0))
        parse_failures = int(float(diag.get("parse_failures", 0)))
        non_empty = int(stats.get("non_empty_generated_answers", diag.get("non_empty_generated_answers", 0) or 0))
        runs.append(
            {
                "path": path.as_posix(),
                "sample_offset": stats.get("sample_offset", ""),
                "example_count": int(stats.get("example_count", 0)),
                "generation_rows": generation_rows,
                "parse_failures": parse_failures,
                "parse_failure_rate": parse_failures / generation_rows if generation_rows else 0.0,
                "non_empty_generated_answers": non_empty,
                "unique_answer_hash_count": int(stats.get("unique_answer_hash_count", diag.get("unique_answer_hash_count", 0) or 0)),
                "usable_quality_signal": bool(stats.get("usable_quality_signal", False)),
                "result_class": stats.get("result_class", ""),
                "positive_cost_result": stats.get("result_class") == "GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY_CRAG",
            }
        )
    total_rows = sum(run["generation_rows"] for run in runs)
    total_failures = sum(run["parse_failures"] for run in runs)
    return {
        "generator_provider": load_json(paths[0]).get("generator_provider", "") if paths else "",
        "generator_model": load_json(paths[0]).get("generator_model", "") if paths else "",
        "run_count": len(runs),
        "generation_rows": total_rows,
        "parse_failures": total_failures,
        "parse_failure_rate": total_failures / total_rows if total_rows else 0.0,
        "usable_quality_signal_run_count": sum(1 for run in runs if run["usable_quality_signal"]),
        "positive_cost_result_count": sum(1 for run in runs if run["positive_cost_result"]),
        "runs": runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-stats", nargs="+", required=True)
    parser.add_argument("--candidate-stats", nargs="+", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    baseline = summarize([Path(path) for path in args.baseline_stats])
    candidate = summarize([Path(path) for path in args.candidate_stats])
    failure_delta = candidate["parse_failure_rate"] - baseline["parse_failure_rate"]
    materially_reduced = candidate["parse_failure_rate"] <= max(0.05, baseline["parse_failure_rate"] * 0.25)
    candidate_cost_positive = candidate["positive_cost_result_count"] > 0
    if materially_reduced and not candidate_cost_positive:
        result_class = "CRAG_GEN_LLM_ANSWER_EMISSION_REPAIRED_NO_COST_RESULT"
    elif materially_reduced and candidate_cost_positive:
        result_class = "CRAG_GEN_LLM_ANSWER_EMISSION_REPAIRED_WITH_COST_SIGNAL"
    else:
        result_class = "CRAG_GEN_LLM_ANSWER_EMISSION_NOT_REPAIRED"
    payload = {
        "suite": "ragwarrant_crag_answer_emission_model_comparison_v1",
        "result_class": result_class,
        "baseline": baseline,
        "candidate": candidate,
        "parse_failure_rate_delta": failure_delta,
        "materially_reduced_parse_failures": materially_reduced,
        "interpretation": (
            "The faster non-thinking instruct model repaired answer emission but did not recover a stable cost-at-equivalent-generated-quality result."
            if result_class == "CRAG_GEN_LLM_ANSWER_EMISSION_REPAIRED_NO_COST_RESULT"
            else "The answer-emission repair comparison did not produce a stronger bounded governance claim."
        ),
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
        "raw_questions_committed": False,
        "raw_evidence_committed": False,
    }
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "crag_answer_emission_model_comparison.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (output_root / "crag_answer_emission_model_comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["model_role", "generator_model", "run_count", "generation_rows", "parse_failures", "parse_failure_rate", "positive_cost_result_count"],
        )
        writer.writeheader()
        writer.writerow({"model_role": "baseline", **{key: baseline[key] for key in writer.fieldnames if key in baseline}})
        writer.writerow({"model_role": "candidate", **{key: candidate[key] for key in writer.fieldnames if key in candidate}})
    (output_root / "crag_answer_emission_model_comparison.md").write_text(
        "\n".join(
            [
                "# CRAG Answer-Emission Model Comparison",
                "",
                f"Result class: `{result_class}`",
                "",
                f"Baseline model: `{baseline['generator_model']}` parse failures `{baseline['parse_failures']}` / `{baseline['generation_rows']}`.",
                f"Candidate model: `{candidate['generator_model']}` parse failures `{candidate['parse_failures']}` / `{candidate['generation_rows']}`.",
                "",
                str(payload["interpretation"]),
                "",
                "Raw CRAG questions, evidence text, prompts, and generated answers are not committed.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"CRAG answer-emission model comparison: {result_class}")


if __name__ == "__main__":
    main()
