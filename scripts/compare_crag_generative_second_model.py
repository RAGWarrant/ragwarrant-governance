#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


STABLE_CLASS = "CRAG_GEN_LLM_COST_RESULT_STABLE_ACROSS_REPEATS"
NOT_STABLE_CLASS = "CRAG_GEN_LLM_COST_RESULT_NOT_STABLE_ACROSS_REPEATS"


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def classify(primary_model: dict[str, object], second_model: dict[str, object]) -> tuple[str, str]:
    first_class = str(primary_model.get("result_class", ""))
    second_class = str(second_model.get("result_class", ""))
    if first_class == STABLE_CLASS and second_class == STABLE_CLASS:
        return (
            "CRAG_GEN_LLM_COST_RESULT_STABLE_ACROSS_MODELS",
            "Both pinned local generators showed stable cost reduction across deterministic CRAG offsets.",
        )
    if first_class == NOT_STABLE_CLASS and second_class == NOT_STABLE_CLASS:
        return (
            "CRAG_GEN_LLM_COST_RESULT_NOT_STABLE_ACROSS_MODELS",
            "Neither pinned local generator showed stable cost reduction across deterministic CRAG offsets.",
        )
    if second_class == STABLE_CLASS:
        return (
            "CRAG_GEN_LLM_COST_RESULT_SECOND_MODEL_ONLY",
            "The second pinned local generator showed stable cost reduction, but the first did not.",
        )
    if first_class == STABLE_CLASS:
        return (
            "CRAG_GEN_LLM_COST_RESULT_PRIMARY_MODEL_ONLY",
            "The first pinned local generator showed stable cost reduction, but the second did not.",
        )
    return (
        "CRAG_GEN_LLM_COST_RESULT_MIXED_OR_INCONCLUSIVE_ACROSS_MODELS",
        "The pinned local generator comparison is mixed or inconclusive.",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary-model-stability", default="results/generative_llm_validation/crag_stability_comparison.json")
    parser.add_argument("--second-model-stability", required=True)
    parser.add_argument("--output-root", default="results/generative_llm_validation")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    primary = load_json(Path(args.primary_model_stability))
    second = load_json(Path(args.second_model_stability))
    result_class, interpretation = classify(primary, second)
    rows = [
        {
            "model_role": "primary_model",
            "generator_provider": primary.get("generator_provider", ""),
            "generator_model": primary.get("generator_model", ""),
            "stability_result_class": primary.get("result_class", ""),
            "run_count": primary.get("run_count", 0),
            "usable_generated_quality_runs": primary.get("usable_quality_signal_run_count", 0),
            "positive_cost_result_runs": primary.get("positive_cost_result_count", 0),
        },
        {
            "model_role": "second_model",
            "generator_provider": second.get("generator_provider", ""),
            "generator_model": second.get("generator_model", ""),
            "stability_result_class": second.get("result_class", ""),
            "run_count": second.get("run_count", 0),
            "usable_generated_quality_runs": second.get("usable_quality_signal_run_count", 0),
            "positive_cost_result_runs": second.get("positive_cost_result_count", 0),
        },
    ]
    payload = {
        "suite": "ragwarrant_crag_generative_second_model_comparison_v1",
        "result_class": result_class,
        "interpretation": interpretation,
        "primary_model_stability_result": primary.get("result_class", ""),
        "second_model_stability_result": second.get("result_class", ""),
        "primary_generator_model": primary.get("generator_model", ""),
        "second_generator_model": second.get("generator_model", ""),
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
        "raw_questions_committed": False,
        "raw_evidence_committed": False,
        "models": rows,
    }
    (output_root / "crag_second_model_comparison.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output_root / "crag_second_model_comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (output_root / "crag_second_model_comparison.md").write_text(
        f"""# CRAG Generative Second-Model Comparison

Result class: `{result_class}`

Interpretation: {interpretation}

Primary model: `{payload['primary_generator_model']}`  
Second model: `{payload['second_generator_model']}`

Public artifacts contain only hashes, policy identifiers, counts, and metrics. Raw CRAG questions, raw evidence, raw prompts, raw generated answers, and raw API responses are not committed.
""",
        encoding="utf-8",
    )
    print(f"CRAG generative second-model comparison: {result_class}")


if __name__ == "__main__":
    main()
