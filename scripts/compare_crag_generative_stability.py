#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


POSITIVE_COST_CLASS = "GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY_CRAG"
POSITIVE_LATENCY_CLASS = "GEN_LLM_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_GENERATED_QUALITY_CRAG"


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def delta_mean(payload: dict[str, object], key: str) -> float:
    value = payload.get(key, {})
    if isinstance(value, dict):
        return float(value.get("mean", 0.0))
    return 0.0


def delta_ci_low(payload: dict[str, object], key: str) -> float:
    value = payload.get(key, {})
    if isinstance(value, dict):
        return float(value.get("ci_low", 0.0))
    return 0.0


def delta_ci_high(payload: dict[str, object], key: str) -> float:
    value = payload.get(key, {})
    if isinstance(value, dict):
        return float(value.get("ci_high", 0.0))
    return 0.0


def positive_cost_result(payload: dict[str, object]) -> bool:
    return (
        payload.get("result_class") == POSITIVE_COST_CLASS
        and bool(payload.get("usable_quality_signal"))
        and delta_mean(payload, "generated_quality_delta") >= -0.01
        and delta_ci_high(payload, "cost_delta") < 0
    )


def positive_latency_result(payload: dict[str, object]) -> bool:
    return (
        payload.get("result_class") == POSITIVE_LATENCY_CLASS
        and bool(payload.get("usable_quality_signal"))
        and delta_mean(payload, "generated_quality_delta") >= -0.01
        and delta_ci_high(payload, "latency_delta_ms") < 0
    )


def positive_endpoint_result(payload: dict[str, object]) -> bool:
    if str(payload.get("primary_endpoint", "cost")) == "latency":
        return positive_latency_result(payload)
    return positive_cost_result(payload)


def run_label(payload: dict[str, object], index: int) -> str:
    offset = payload.get("sample_offset", "")
    if offset == 0:
        return "primary_offset_0"
    return f"repeat_offset_{offset or index}"


def classify(rows: list[dict[str, object]]) -> tuple[str, str]:
    if not rows:
        return "CRAG_GEN_LLM_STABILITY_BLOCKED_NO_RUNS", "No CRAG generative runs were available."
    endpoint = str(rows[0].get("primary_endpoint", "cost"))
    endpoint_label = "latency" if endpoint == "latency" else "cost"
    stable_class = (
        "CRAG_GEN_LLM_LATENCY_RESULT_STABLE_ACROSS_REPEATS"
        if endpoint_label == "latency"
        else "CRAG_GEN_LLM_COST_RESULT_STABLE_ACROSS_REPEATS"
    )
    mixed_class = (
        "CRAG_GEN_LLM_LATENCY_RESULT_MIXED_ACROSS_REPEATS"
        if endpoint_label == "latency"
        else "CRAG_GEN_LLM_COST_RESULT_MIXED_ACROSS_REPEATS"
    )
    not_stable_class = (
        "CRAG_GEN_LLM_LATENCY_RESULT_NOT_STABLE_ACROSS_REPEATS"
        if endpoint_label == "latency"
        else "CRAG_GEN_LLM_COST_RESULT_NOT_STABLE_ACROSS_REPEATS"
    )
    directional_class = (
        "CRAG_GEN_LLM_LATENCY_RESULT_DIRECTIONAL_BUT_UNSTABLE"
        if endpoint_label == "latency"
        else "CRAG_GEN_LLM_COST_RESULT_DIRECTIONAL_BUT_UNSTABLE"
    )
    inconclusive_class = (
        "CRAG_GEN_LLM_LATENCY_RESULT_INCONCLUSIVE_ACROSS_REPEATS"
        if endpoint_label == "latency"
        else "CRAG_GEN_LLM_COST_RESULT_INCONCLUSIVE_ACROSS_REPEATS"
    )
    usable = [row for row in rows if bool(row.get("usable_quality_signal"))]
    positives = [row for row in usable if positive_endpoint_result(row)]
    repeats = [row for row in usable if row.get("sample_offset", 0) != 0]
    positive_repeats = [row for row in repeats if positive_endpoint_result(row)]
    if not usable:
        return "CRAG_GEN_LLM_STABILITY_BLOCKED_NO_USABLE_QUALITY_SIGNAL", "No CRAG generative slice had a usable generated-answer quality signal."
    if len(usable) == len(rows) and len(positives) == len(rows) and len(rows) >= 3:
        return stable_class, f"Every available CRAG generative slice supported {endpoint_label} reduction at equivalent generated quality."
    if positives and positive_repeats and len(positives) < len(usable):
        return mixed_class, f"At least one independent CRAG repeat reproduced the {endpoint_label} result, but at least one usable slice did not."
    if positive_endpoint_result(rows[0]) and not positive_repeats:
        return not_stable_class, f"The primary CRAG slice was positive, but no independent usable repeat reproduced the {endpoint_label} result."
    if positives:
        return directional_class, "Some CRAG generative slices were positive, but the pattern was not stable across repeats."
    return inconclusive_class, f"Usable CRAG generative slices did not support a stable {endpoint_label}-at-equivalent-generated-quality result."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", nargs="+", required=True, help="Primary/repeat statistics JSON paths.")
    parser.add_argument("--output-root", default="results/generative_llm_validation")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    payloads = [load_json(Path(path)) for path in args.stats]
    result_class, interpretation = classify(payloads)
    positive_count = sum(1 for payload in payloads if positive_endpoint_result(payload))
    positive_cost_count = sum(1 for payload in payloads if positive_cost_result(payload))
    positive_latency_count = sum(1 for payload in payloads if positive_latency_result(payload))
    usable_count = sum(1 for payload in payloads if bool(payload.get("usable_quality_signal")))
    rows = []
    for index, payload in enumerate(payloads):
        rows.append(
            {
                "run": run_label(payload, index),
                "sample_offset": payload.get("sample_offset", ""),
                "sample_strategy": payload.get("sample_strategy", ""),
                "result_class": payload.get("result_class", ""),
                "example_count": payload.get("example_count", 0),
                "generation_rows": payload.get("generation_rows", 0),
                "governed_winner": payload.get("governed_winner", ""),
                "quality_only_winner": payload.get("quality_only_winner", ""),
                "rag_compass_rank": payload.get("rag_compass_rank", ""),
                "usable_quality_signal": payload.get("usable_quality_signal", False),
                "positive_cost_result": positive_cost_result(payload),
                "positive_latency_result": positive_latency_result(payload),
                "positive_endpoint_result": positive_endpoint_result(payload),
                "primary_endpoint": payload.get("primary_endpoint", ""),
                "generated_quality_delta_mean": delta_mean(payload, "generated_quality_delta"),
                "generated_quality_delta_ci_low": delta_ci_low(payload, "generated_quality_delta"),
                "generated_quality_delta_ci_high": delta_ci_high(payload, "generated_quality_delta"),
                "cost_delta_mean": delta_mean(payload, "cost_delta"),
                "cost_delta_ci_low": delta_ci_low(payload, "cost_delta"),
                "cost_delta_ci_high": delta_ci_high(payload, "cost_delta"),
                "latency_delta_ms_mean": delta_mean(payload, "latency_delta_ms"),
                "latency_delta_ms_ci_low": delta_ci_low(payload, "latency_delta_ms"),
                "latency_delta_ms_ci_high": delta_ci_high(payload, "latency_delta_ms"),
                "api_call_delta_mean": delta_mean(payload, "api_call_delta"),
            }
        )

    summary = {
        "suite": "ragwarrant_crag_generative_stability_comparison_v1",
        "result_class": result_class,
        "interpretation": interpretation,
        "run_count": len(payloads),
        "usable_quality_signal_run_count": usable_count,
        "positive_endpoint_result_count": positive_count,
        "positive_cost_result_count": positive_cost_count,
        "positive_latency_result_count": positive_latency_count,
        "sample_offsets": [payload.get("sample_offset", "") for payload in payloads],
        "primary_endpoint": payloads[0].get("primary_endpoint", "") if payloads else "",
        "generator_provider": payloads[0].get("generator_provider", "") if payloads else "",
        "generator_model": payloads[0].get("generator_model", "") if payloads else "",
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
        "raw_questions_committed": False,
        "raw_evidence_committed": False,
        "runs": rows,
    }
    (output_root / "crag_stability_comparison.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output_root / "crag_stability_comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "run",
            "sample_offset",
            "sample_strategy",
            "result_class",
            "example_count",
            "generation_rows",
            "governed_winner",
            "quality_only_winner",
            "rag_compass_rank",
            "usable_quality_signal",
            "positive_cost_result",
            "positive_latency_result",
            "positive_endpoint_result",
            "primary_endpoint",
            "generated_quality_delta_mean",
            "generated_quality_delta_ci_low",
            "generated_quality_delta_ci_high",
            "cost_delta_mean",
            "cost_delta_ci_low",
            "cost_delta_ci_high",
            "latency_delta_ms_mean",
            "latency_delta_ms_ci_low",
            "latency_delta_ms_ci_high",
            "api_call_delta_mean",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    (output_root / "crag_stability_comparison.md").write_text(
        f"""# CRAG Generative Stability Comparison

Result class: `{result_class}`

Interpretation: {interpretation}

Runs compared: `{len(payloads)}`  
Usable generated-quality runs: `{usable_count}`  
Positive endpoint-at-equivalent-generated-quality runs: `{positive_count}`  
Positive cost runs: `{positive_cost_count}`  
Positive latency runs: `{positive_latency_count}`  
Sample offsets: `{', '.join(str(item) for item in summary['sample_offsets'])}`

Public artifacts contain only hashes, policy identifiers, counts, and metrics. Raw CRAG questions, raw evidence, raw prompts, raw generated answers, and raw API responses are not committed.
""",
        encoding="utf-8",
    )
    print(f"CRAG generative stability comparison: {result_class}")


if __name__ == "__main__":
    main()
