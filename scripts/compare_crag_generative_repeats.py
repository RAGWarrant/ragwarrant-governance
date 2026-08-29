#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def delta_mean(payload: dict[str, object], key: str) -> float:
    value = payload.get(key, {})
    if isinstance(value, dict):
        return float(value.get("mean", 0.0))
    return 0.0


def positive_cost_result(payload: dict[str, object]) -> bool:
    return (
        payload.get("result_class") == "GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY_CRAG"
        and bool(payload.get("usable_quality_signal"))
        and delta_mean(payload, "cost_delta") < 0
        and delta_mean(payload, "generated_quality_delta") >= -0.01
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", default="artifacts/generative_llm_validation/crag/primary_outcome_statistics.json")
    parser.add_argument("--repeat", default="artifacts/generative_llm_validation/crag_repeat/primary_outcome_statistics.json")
    parser.add_argument("--output-root", default="results/generative_llm_validation")
    args = parser.parse_args()

    primary_path = Path(args.primary)
    repeat_path = Path(args.repeat)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    primary = load_json(primary_path)
    repeat = load_json(repeat_path)
    primary_positive = positive_cost_result(primary)
    repeat_positive = positive_cost_result(repeat)
    if primary_positive and repeat_positive:
        result_class = "CRAG_GEN_LLM_COST_RESULT_PERSISTED_IN_INDEPENDENT_REPEAT"
        interpretation = "Both deterministic CRAG slices support reduced measured cost at equivalent generated-answer quality."
    elif primary_positive and not repeat_positive:
        result_class = "CRAG_GEN_LLM_COST_RESULT_NOT_REPLICATED"
        interpretation = "The primary CRAG slice supports cost reduction, but the independent deterministic repeat does not."
    elif repeat_positive:
        result_class = "CRAG_GEN_LLM_COST_RESULT_DIRECTIONAL_REPEAT_ONLY"
        interpretation = "Only the independent deterministic repeat supports cost reduction."
    else:
        result_class = "CRAG_GEN_LLM_COST_RESULT_INCONCLUSIVE"
        interpretation = "Neither deterministic CRAG slice supports cost reduction with usable generated-answer quality."

    payload = {
        "suite": "ragwarrant_crag_generative_repeat_comparison_v1",
        "result_class": result_class,
        "interpretation": interpretation,
        "primary_result_class": primary.get("result_class", ""),
        "repeat_result_class": repeat.get("result_class", ""),
        "primary_sample_offset": primary.get("sample_offset", 0),
        "repeat_sample_offset": repeat.get("sample_offset", 0),
        "primary_example_count": primary.get("example_count", 0),
        "repeat_example_count": repeat.get("example_count", 0),
        "primary_governed_winner": primary.get("governed_winner", ""),
        "repeat_governed_winner": repeat.get("governed_winner", ""),
        "primary_quality_only_winner": primary.get("quality_only_winner", ""),
        "repeat_quality_only_winner": repeat.get("quality_only_winner", ""),
        "primary_quality_delta_mean": delta_mean(primary, "generated_quality_delta"),
        "repeat_quality_delta_mean": delta_mean(repeat, "generated_quality_delta"),
        "primary_cost_delta_mean": delta_mean(primary, "cost_delta"),
        "repeat_cost_delta_mean": delta_mean(repeat, "cost_delta"),
        "primary_latency_delta_ms_mean": delta_mean(primary, "latency_delta_ms"),
        "repeat_latency_delta_ms_mean": delta_mean(repeat, "latency_delta_ms"),
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
        "raw_questions_committed": False,
        "raw_evidence_committed": False,
    }
    (output_root / "crag_repeat_comparison.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output_root / "crag_repeat_comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["run", "result_class", "sample_offset", "example_count", "governed_winner", "quality_only_winner", "quality_delta_mean", "cost_delta_mean", "latency_delta_ms_mean"])
        writer.writeheader()
        writer.writerow({
            "run": "primary",
            "result_class": primary.get("result_class", ""),
            "sample_offset": primary.get("sample_offset", 0),
            "example_count": primary.get("example_count", 0),
            "governed_winner": primary.get("governed_winner", ""),
            "quality_only_winner": primary.get("quality_only_winner", ""),
            "quality_delta_mean": delta_mean(primary, "generated_quality_delta"),
            "cost_delta_mean": delta_mean(primary, "cost_delta"),
            "latency_delta_ms_mean": delta_mean(primary, "latency_delta_ms"),
        })
        writer.writerow({
            "run": "repeat",
            "result_class": repeat.get("result_class", ""),
            "sample_offset": repeat.get("sample_offset", 0),
            "example_count": repeat.get("example_count", 0),
            "governed_winner": repeat.get("governed_winner", ""),
            "quality_only_winner": repeat.get("quality_only_winner", ""),
            "quality_delta_mean": delta_mean(repeat, "generated_quality_delta"),
            "cost_delta_mean": delta_mean(repeat, "cost_delta"),
            "latency_delta_ms_mean": delta_mean(repeat, "latency_delta_ms"),
        })
    (output_root / "crag_repeat_comparison.md").write_text(
        f"""# CRAG Generative Repeat Comparison

Result class: `{result_class}`

Interpretation: {interpretation}

Primary CRAG sample offset: `{payload['primary_sample_offset']}`  
Repeat CRAG sample offset: `{payload['repeat_sample_offset']}`

Public artifacts contain only hashes, policy identifiers, counts, and metrics. Raw CRAG questions, raw evidence, raw prompts, raw generated answers, and raw API responses are not committed.
""",
        encoding="utf-8",
    )
    print(f"CRAG generative repeat comparison: {result_class}")


if __name__ == "__main__":
    main()
