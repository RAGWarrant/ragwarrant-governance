from __future__ import annotations

import csv
import json
import statistics
import math
from pathlib import Path
from typing import Any

GEN_LLM_RESULT_CLASSES = {
    "GEN_LLM_VALIDATION_LOCAL_OPEN_MODEL_COMPLETED",
    "GEN_LLM_VALIDATION_HOSTED_MODEL_COMPLETED",
    "GEN_LLM_VALIDATION_CRAG_GENERATED_ANSWER_SIGNAL",
    "GEN_LLM_VALIDATION_HOTPOTQA_GENERATED_ANSWER_SIGNAL",
    "GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY",
    "GEN_LLM_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_GENERATED_QUALITY",
    "GEN_LLM_GOVERNANCE_IMPROVES_GENERATED_QUALITY_UNDER_FIXED_BUDGET",
    "GEN_LLM_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS",
    "GEN_LLM_GOVERNANCE_MATCHES_QUALITY_ONLY",
    "GEN_LLM_GOVERNANCE_INCONCLUSIVE",
    "GEN_LLM_GOVERNANCE_NEGATIVE",
    "GEN_LLM_VALIDATION_BLOCKED_NO_GENERATOR",
    "GEN_LLM_VALIDATION_BLOCKED_NO_MODEL_CREDENTIALS",
    "GEN_LLM_VALIDATION_BLOCKED_CRAG_UNAVAILABLE",
    "GEN_LLM_VALIDATION_BLOCKED_HOTPOTQA_UNAVAILABLE",
    "GEN_LLM_VALIDATION_BLOCKED_EVALUATOR_MAPPING",
    "GEN_LLM_VALIDATION_BLOCKED_NO_USABLE_QUALITY_SIGNAL",
    "GEN_LLM_VALIDATION_BLOCKED_PUBLICATION_HYGIENE",
    "GEN_LLM_VALIDATION_BLOCKED_RATE_LIMIT",
    "GEN_LLM_VALIDATION_BLOCKED_COST_LIMIT",
    "GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY_CRAG",
    "GEN_LLM_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_GENERATED_QUALITY_CRAG",
    "GEN_LLM_GOVERNANCE_IMPROVES_GENERATED_QUALITY_UNDER_FIXED_BUDGET_CRAG",
    "GEN_LLM_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS_CRAG",
    "GEN_LLM_GOVERNANCE_NEGATIVE_CRAG",
    "GEN_LLM_GOVERNANCE_INCONCLUSIVE_CRAG",
    "GEN_LLM_VALIDATION_BLOCKED_NO_GENERATOR_CRAG",
    "GEN_LLM_VALIDATION_BLOCKED_EVALUATOR_MAPPING_CRAG",
    "GEN_LLM_VALIDATION_BLOCKED_NO_USABLE_QUALITY_SIGNAL_CRAG",
    "GEN_LLM_VALIDATION_BLOCKED_PUBLICATION_HYGIENE_CRAG",
}

GEN_LLM_SYNTHESIS_CLASSES = {
    "GEN_LLM_SYNTHESIS_GENERATIVE_VALIDATION_SUPPORTED",
    "GEN_LLM_SYNTHESIS_DIRECTIONAL",
    "GEN_LLM_SYNTHESIS_MIXED",
    "GEN_LLM_SYNTHESIS_INCONCLUSIVE",
    "GEN_LLM_SYNTHESIS_BLOCKED",
    "GEN_LLM_SYNTHESIS_NEGATIVE",
}

GENERATION_FIELDNAMES = [
    "example_id",
    "question_hash",
    "split",
    "dataset",
    "policy_id",
    "provider",
    "model",
    "prompt_hash",
    "generated_answer_hash",
    "generated_answer_char_count",
    "generated_answer_token_estimate",
    "retrieval_latency_ms",
    "generation_latency_ms",
    "total_latency_ms",
    "retrieval_cost_units",
    "generation_cost_units",
    "total_cost_units",
    "input_token_estimate",
    "output_token_estimate",
    "api_call_count",
    "generator_call_count",
    "answer_correctness_f1",
    "answer_exact_match",
    "answer_containment",
    "evidence_support_score",
    "citation_support_score",
    "abstention_correctness",
    "final_generated_quality_score",
    "raw_prompt_exported",
    "raw_generated_answer_exported",
]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def mean(values: list[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def zero_ci() -> dict[str, float]:
    return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}


def variance(values: list[float]) -> float:
    return float(statistics.pvariance(values)) if len(values) > 1 else 0.0


def entropy(values: list[str]) -> float:
    if not values:
        return 0.0
    counts = {value: values.count(value) for value in set(values)}
    total = float(len(values))
    return float(-sum((count / total) * math.log2(count / total) for count in counts.values()))


def quality_signal_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    qualities = [float(row.get("final_generated_quality_score", 0.0)) for row in rows]
    answer_hashes = [str(row.get("generated_answer_hash", "")) for row in rows]
    answer_lengths = [int(float(row.get("generated_answer_char_count", 0))) for row in rows]
    f1_values = [float(row.get("answer_correctness_f1", 0.0)) for row in rows]
    exact_values = [float(row.get("answer_exact_match", 0.0)) for row in rows]
    containment_values = [float(row.get("answer_containment", 0.0)) for row in rows]
    evidence_values = [float(row.get("evidence_support_score", 0.0)) for row in rows]
    citation_values = [float(row.get("citation_support_score", 0.0)) for row in rows]
    policy_ids = sorted({str(row.get("policy_id", "")) for row in rows})
    example_ids = sorted({str(row.get("example_id", "")) for row in rows})
    per_policy_variances = []
    for policy in policy_ids:
        subset = [float(row.get("final_generated_quality_score", 0.0)) for row in rows if str(row.get("policy_id", "")) == policy]
        per_policy_variances.append(variance(subset))
    answer_disagreement_examples = 0
    quality_disagreement_examples = 0
    answer_hash_diversities = []
    for example_id in example_ids:
        subset = [row for row in rows if str(row.get("example_id", "")) == example_id]
        hashes = {str(row.get("generated_answer_hash", "")) for row in subset}
        qualities_for_example = {round(float(row.get("final_generated_quality_score", 0.0)), 12) for row in subset}
        answer_hash_diversities.append(len(hashes))
        if len(hashes) > 1:
            answer_disagreement_examples += 1
        if len(qualities_for_example) > 1:
            quality_disagreement_examples += 1
    unique_quality_count = len({round(value, 12) for value in qualities})
    non_empty = sum(1 for length in answer_lengths if length > 0)
    constant_zero_quality = bool(rows) and all(value == 0.0 for value in qualities)
    constant_quality = bool(rows) and unique_quality_count <= 1
    usable_generated_answer_signal = non_empty > 0 and len(set(answer_hashes)) > 1
    usable_quality_signal = usable_generated_answer_signal and not constant_zero_quality and not constant_quality
    if not rows:
        audit_result_class = "HOTPOTQA_GEN_LLM_BLOCKED_NO_USABLE_QUALITY_SIGNAL"
        zero_delta_explanation = "no generation rows were produced"
    elif non_empty == 0:
        audit_result_class = "HOTPOTQA_GEN_LLM_BLOCKED_NO_USABLE_QUALITY_SIGNAL"
        zero_delta_explanation = "all generated answers were empty, so answer-quality equivalence is not scientifically usable"
    elif len(set(answer_hashes)) <= 1:
        audit_result_class = "HOTPOTQA_GEN_LLM_ZERO_DELTAS_GENERATOR_INSENSITIVE"
        zero_delta_explanation = "the generator produced identical answer hashes across policies"
    elif constant_zero_quality:
        audit_result_class = "HOTPOTQA_GEN_LLM_BLOCKED_NO_USABLE_QUALITY_SIGNAL"
        zero_delta_explanation = "all generated quality scores were zero"
    elif constant_quality:
        audit_result_class = "HOTPOTQA_GEN_LLM_ZERO_DELTAS_TRUE_EQUIVALENCE"
        zero_delta_explanation = "generated answers were nonempty but quality scores were constant under the configured metric"
    else:
        audit_result_class = "HOTPOTQA_GEN_LLM_QUALITY_SIGNAL_CONFIRMED"
        zero_delta_explanation = "generated answers and configured quality scores vary across the audited sample"
    return {
        "generation_rows": len(rows),
        "empty_generated_answers": len(rows) - non_empty,
        "non_empty_generated_answers": non_empty,
        "abstentions": 0,
        "parse_failures": len(rows) - non_empty,
        "unique_answer_hash_count": len(set(answer_hashes)),
        "answer_hash_entropy": entropy(answer_hashes),
        "answer_length_min": min(answer_lengths) if answer_lengths else 0,
        "answer_length_mean": mean([float(value) for value in answer_lengths]),
        "answer_length_max": max(answer_lengths) if answer_lengths else 0,
        "answer_f1_min": min(f1_values) if f1_values else 0.0,
        "answer_f1_mean": mean(f1_values),
        "answer_f1_max": max(f1_values) if f1_values else 0.0,
        "exact_match_mean": mean(exact_values),
        "answer_containment_mean": mean(containment_values),
        "evidence_support_mean": mean(evidence_values),
        "citation_support_mean": mean(citation_values),
        "quality_min": min(qualities) if qualities else 0.0,
        "quality_mean": mean(qualities),
        "quality_max": max(qualities) if qualities else 0.0,
        "quality_variance": variance(qualities),
        "per_policy_quality_variance_mean": mean(per_policy_variances),
        "between_policy_quality_variance": variance([
            mean([float(row.get("final_generated_quality_score", 0.0)) for row in rows if str(row.get("policy_id", "")) == policy])
            for policy in policy_ids
        ]),
        "per_query_policy_disagreement_rate": answer_disagreement_examples / len(example_ids) if example_ids else 0.0,
        "per_query_answer_hash_diversity_mean": mean([float(value) for value in answer_hash_diversities]),
        "examples_with_different_answer_hashes": answer_disagreement_examples,
        "examples_with_different_quality_scores": quality_disagreement_examples,
        "constant_zero_quality": constant_zero_quality,
        "constant_quality": constant_quality,
        "usable_generated_answer_signal": usable_generated_answer_signal,
        "usable_quality_signal": usable_quality_signal,
        "quality_signal_audit_result_class": audit_result_class,
        "prior_zero_delta_explanation": zero_delta_explanation,
    }
