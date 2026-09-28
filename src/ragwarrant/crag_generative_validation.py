# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import bz2
import json
import os
from pathlib import Path
from typing import Any

from ragwarrant.fresh_live_behavioral_governance import CRAG_LIVE_POLICIES, inspect_crag_environment
from ragwarrant.generated_answer_quality import containment, exact_match, generated_quality_score, token_f1
from ragwarrant.generative_prompts import build_answer_emission_repair_prompt, build_rag_prompt
from ragwarrant.generative_validation_common import (
    GENERATION_FIELDNAMES,
    mean,
    quality_signal_diagnostics,
    write_csv,
    write_json,
    write_md,
    zero_ci,
)
from ragwarrant.generators.factory import discover_generator
from ragwarrant.publication_sanitization import stable_hash

QUALITY_GUARDED_LATENCY_POLICY = "quality_guarded_latency_adaptive_expansion"
LEARNED_QUALITY_RISK_LATENCY_POLICY = "learned_quality_risk_latency_adaptive_expansion"
DEPLOYABLE_CRAG_GENERATIVE_POLICIES = {
    "low_retrieval_single_endpoint",
    "expanded_retrieval_multi_endpoint",
    "adaptive_routing_on_insufficient_evidence",
    "static_default_policy",
    "rag_compass_optional",
}
GUARDED_LATENCY_CRAG_GENERATIVE_POLICIES = {
    QUALITY_GUARDED_LATENCY_POLICY,
    LEARNED_QUALITY_RISK_LATENCY_POLICY,
    "adaptive_routing_on_insufficient_evidence",
    "rag_compass_optional",
}
QUALITY_ONLY_CRAG_GENERATIVE_POLICIES = {
    "expanded_retrieval_multi_endpoint",
    "quality_only_best_on_validation",
}
CRAG_GENERATIVE_POLICIES = list(CRAG_LIVE_POLICIES) + [QUALITY_GUARDED_LATENCY_POLICY]


class QualityRiskPredictor:
    def __init__(
        self,
        *,
        rule_id: str,
        feature_name: str,
        operator: str,
        threshold: float | str,
        positive_values: set[str] | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.feature_name = feature_name
        self.operator = operator
        self.threshold = threshold
        self.positive_values = positive_values or set()

    def predict_expand(self, row: dict[str, Any]) -> bool:
        features = deployable_quality_risk_features(row)
        value = features[self.feature_name]
        if self.operator == "<=":
            return float(value) <= float(self.threshold)
        if self.operator == ">=":
            return float(value) >= float(self.threshold)
        if self.operator == "==":
            return str(value) == str(self.threshold)
        if self.operator == "in":
            return str(value) in self.positive_values
        return False

    def to_public_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "feature_name": self.feature_name,
            "operator": self.operator,
            "threshold": self.threshold,
            "positive_values": sorted(self.positive_values),
            "deployable_features_only": True,
            "raw_text_features_used": False,
        }


def crag_data_file() -> Path | None:
    data_root = os.environ.get("RAGWARRANT_CRAG_DATA")
    if not data_root:
        return None
    path = Path(data_root) / "crag_task_1_and_2_dev_v5.jsonl.bz2"
    return path if path.exists() else None


def load_crag_rows(max_examples: int, *, offset: int = 0) -> list[dict[str, Any]]:
    path = crag_data_file()
    if path is None:
        return []
    rows: list[dict[str, Any]] = []
    with bz2.open(path, "rt", encoding="utf-8") as handle:
        for idx, line in enumerate(handle):
            if idx < offset:
                continue
            if len(rows) >= max_examples:
                break
            rows.append(json.loads(line))
    return rows


def split_for_row(row: dict[str, Any]) -> str:
    bucket = int(stable_hash(str(row["interaction_id"]))[:8], 16) % 100
    if bucket < 50:
        return "calibration"
    if bucket < 75:
        return "validation"
    return "confirmatory_test"


def row_references(row: dict[str, Any]) -> list[str]:
    references = [str(row.get("answer", ""))] + [str(value) for value in row.get("alt_ans", [])]
    return [value for value in references if value]


def evidence_supports_references(items: list[dict[str, Any]], references: list[str]) -> bool:
    evidence_text = " ".join(
        f"{item.get('page_name', '')} {item.get('page_snippet', '')} {item.get('page_result', '')}"
        for item in items
    )
    return any(containment(evidence_text, ref) > 0.0 for ref in references)


def deployable_quality_risk_features(row: dict[str, Any]) -> dict[str, object]:
    results = list(row.get("search_results", []))
    first_two = results[:2]
    first_two_text = [
        f"{item.get('page_name', '')} {item.get('page_snippet', '')} {item.get('page_result', '')}"
        for item in first_two
    ]
    first_five_text = [
        f"{item.get('page_name', '')} {item.get('page_snippet', '')} {item.get('page_result', '')}"
        for item in results[:5]
    ]
    title_hashes = {stable_hash(str(item.get("page_name", "")))[:8] for item in first_two if item.get("page_name")}
    return {
        "domain": str(row.get("domain", "")),
        "question_type": str(row.get("question_type", "")),
        "static_or_dynamic": str(row.get("static_or_dynamic", "")),
        "result_count": len(results),
        "low_context_item_count": len(first_two),
        "low_context_token_count": sum(len(text.split()) for text in first_two_text),
        "low_context_char_count": sum(len(text) for text in first_two_text),
        "expanded_context_token_count": sum(len(text.split()) for text in first_five_text),
        "expanded_context_char_count": sum(len(text) for text in first_five_text),
        "low_title_hash_diversity": len(title_hashes),
    }


def _policy_quality_by_example(rows: list[dict[str, object]], policy_id: str) -> dict[str, float]:
    return {
        str(row["example_id"]): float(row["final_generated_quality_score"])
        for row in rows
        if row["policy_id"] == policy_id
    }


def _policy_api_calls_by_example(rows: list[dict[str, object]], policy_id: str) -> dict[str, float]:
    return {
        str(row["example_id"]): float(row["api_call_count"])
        for row in rows
        if row["policy_id"] == policy_id
    }


def _candidate_predictors(validation_crag_rows: list[dict[str, Any]]) -> list[QualityRiskPredictor]:
    numeric_features = [
        "result_count",
        "low_context_token_count",
        "low_context_char_count",
        "expanded_context_token_count",
        "expanded_context_char_count",
        "low_title_hash_diversity",
    ]
    categorical_features = ["domain", "question_type", "static_or_dynamic"]
    predictors = [
        QualityRiskPredictor(
            rule_id="never_expand",
            feature_name="result_count",
            operator=">=",
            threshold=10**9,
        ),
        QualityRiskPredictor(
            rule_id="always_expand",
            feature_name="result_count",
            operator=">=",
            threshold=0,
        ),
    ]
    feature_rows = [deployable_quality_risk_features(row) for row in validation_crag_rows]
    for feature in numeric_features:
        values = sorted({float(row[feature]) for row in feature_rows})
        for threshold in values:
            predictors.append(
                QualityRiskPredictor(
                    rule_id=f"expand_when_{feature}_le_{threshold:g}",
                    feature_name=feature,
                    operator="<=",
                    threshold=threshold,
                )
            )
            predictors.append(
                QualityRiskPredictor(
                    rule_id=f"expand_when_{feature}_ge_{threshold:g}",
                    feature_name=feature,
                    operator=">=",
                    threshold=threshold,
                )
            )
    for feature in categorical_features:
        values = sorted({str(row[feature]) for row in feature_rows if row[feature] != ""})
        for value in values:
            predictors.append(
                QualityRiskPredictor(
                    rule_id=f"expand_when_{feature}_is_{stable_hash(value)[:8]}",
                    feature_name=feature,
                    operator="==",
                    threshold=value,
                )
            )
    return predictors


def learn_quality_risk_predictor(
    *,
    crag_rows: list[dict[str, Any]],
    result_rows: list[dict[str, object]],
    margin: float = 0.01,
) -> tuple[QualityRiskPredictor | None, dict[str, object]]:
    validation_rows = [row for row in crag_rows if split_for_row(row) == "validation"]
    if not validation_rows:
        validation_rows = [row for row in crag_rows if split_for_row(row) == "calibration"] or crag_rows
    expanded_quality = _policy_quality_by_example(result_rows, "expanded_retrieval_multi_endpoint")
    two_item_quality = _policy_quality_by_example(result_rows, "pareto_frontier_selector")
    old_guardrail_calls = _policy_api_calls_by_example(result_rows, QUALITY_GUARDED_LATENCY_POLICY)
    training_examples = []
    for row in validation_rows:
        example_id = stable_hash(str(row["interaction_id"]))
        if example_id not in expanded_quality or example_id not in two_item_quality:
            continue
        old_expanded = float(old_guardrail_calls.get(example_id, 2.0)) > 2.0
        training_examples.append(
            {
                "row": row,
                "example_id": example_id,
                "expanded_quality": expanded_quality[example_id],
                "two_item_quality": two_item_quality[example_id],
                "old_guardrail_expanded": old_expanded,
                "label_quality_risk": two_item_quality[example_id] < expanded_quality[example_id] - margin,
            }
        )
    if not training_examples:
        return None, {
            "predictor_result_class": "CRAG_GEN_LLM_RISK_PREDICTOR_BLOCKED_NO_VALIDATION_ROWS",
            "training_row_count": 0,
            "deployable_features_only": True,
            "raw_text_features_used": False,
        }
    old_expansion_rate = mean([1.0 if item["old_guardrail_expanded"] else 0.0 for item in training_examples])
    candidates: list[tuple[QualityRiskPredictor, dict[str, object]]] = []
    for predictor in _candidate_predictors([item["row"] for item in training_examples]):
        predicted_expansions = [predictor.predict_expand(item["row"]) for item in training_examples]
        expansion_rate = mean([1.0 if value else 0.0 for value in predicted_expansions])
        learned_quality = [
            float(item["expanded_quality"]) if expand else float(item["two_item_quality"])
            for item, expand in zip(training_examples, predicted_expansions)
        ]
        quality_only = [float(item["expanded_quality"]) for item in training_examples]
        quality_delta = mean([learned - baseline for learned, baseline in zip(learned_quality, quality_only)])
        protected_quality_loss_count = sum(
            1
            for item, expand in zip(training_examples, predicted_expansions)
            if not expand and float(item["two_item_quality"]) < float(item["expanded_quality"]) - margin
        )
        candidates.append(
            (
                predictor,
                {
                    "validation_expansion_rate": expansion_rate,
                    "old_guardrail_validation_expansion_rate": old_expansion_rate,
                    "validation_generated_quality_delta_vs_expanded": quality_delta,
                    "validation_quality_risk_count": sum(1 for item in training_examples if item["label_quality_risk"]),
                    "validation_unprotected_quality_risk_count": protected_quality_loss_count,
                    "validation_predicted_expansion_count": sum(1 for value in predicted_expansions if value),
                },
            )
        )
    feasible = [
        (predictor, metrics)
        for predictor, metrics in candidates
        if float(metrics["validation_expansion_rate"]) < old_expansion_rate
        and float(metrics["validation_generated_quality_delta_vs_expanded"]) >= -margin
        and int(metrics["validation_unprotected_quality_risk_count"]) == 0
    ]
    if not feasible:
        best_predictor, best_metrics = max(
            candidates,
            key=lambda item: (
                float(item[1]["validation_generated_quality_delta_vs_expanded"]),
                -float(item[1]["validation_expansion_rate"]),
            ),
        )
        return None, {
            **best_predictor.to_public_dict(),
            **best_metrics,
            "predictor_result_class": "CRAG_GEN_LLM_RISK_PREDICTOR_VALIDATION_GATE_FAILED",
            "training_row_count": len(training_examples),
            "quality_noninferiority_margin": margin,
            "gate_requires_reduced_expansions": True,
            "gate_requires_validation_noninferiority": True,
        }
    selected_predictor, selected_metrics = min(
        feasible,
        key=lambda item: (
            float(item[1]["validation_expansion_rate"]),
            -float(item[1]["validation_generated_quality_delta_vs_expanded"]),
            item[0].rule_id,
        ),
    )
    return selected_predictor, {
        **selected_predictor.to_public_dict(),
        **selected_metrics,
        "predictor_result_class": "CRAG_GEN_LLM_RISK_PREDICTOR_VALIDATION_GATE_PASSED",
        "training_row_count": len(training_examples),
        "quality_noninferiority_margin": margin,
        "gate_requires_reduced_expansions": True,
        "gate_requires_validation_noninferiority": True,
    }


def select_crag_evidence(
    row: dict[str, Any],
    policy_id: str,
    *,
    quality_risk_predictor: QualityRiskPredictor | None = None,
) -> tuple[list[dict[str, str]], float, float]:
    results = list(row.get("search_results", []))
    if policy_id in {"low_retrieval_single_endpoint", "measured_cost_minimizer_at_quality_floor"}:
        selected = results[:1]
    elif policy_id in {"expanded_retrieval_multi_endpoint", "quality_only_best_on_validation"}:
        selected = results[:5]
    elif policy_id == "adaptive_routing_on_insufficient_evidence":
        selected = results[:3] if len(results) >= 3 else results
    elif policy_id == "measured_latency_minimizer_at_quality_floor":
        selected = results[:1]
    elif policy_id == "constrained_quality_optimizer":
        selected = results[:3]
    elif policy_id == "pareto_frontier_selector":
        selected = results[:2]
    elif policy_id == "governed_selection":
        selected = results[:2]
    elif policy_id == "rag_compass_optional":
        selected = sorted(results, key=lambda item: stable_hash(str(item.get("page_name", ""))))[:3]
    elif policy_id == QUALITY_GUARDED_LATENCY_POLICY:
        references = row_references(row)
        selected = results[:2]
        if references and not evidence_supports_references(selected, references):
            selected = results[:5]
    elif policy_id == LEARNED_QUALITY_RISK_LATENCY_POLICY:
        selected = results[:5] if quality_risk_predictor and quality_risk_predictor.predict_expand(row) else results[:2]
    else:
        selected = results[:2]
    evidence = [
        {
            "evidence_id": f"crag_{idx}_{stable_hash(str(item.get('page_url', item.get('page_name', idx))))[:8]}",
            "text": f"{item.get('page_name', '')}\n{item.get('page_snippet', '')}\n{item.get('page_result', '')}"[:1600],
        }
        for idx, item in enumerate(selected)
    ]
    context_tokens = sum(len(item["text"].split()) for item in evidence)
    retrieval_cost = len(evidence) + context_tokens / 1000.0
    return evidence, retrieval_cost, context_tokens


def simple_ci(values: list[float]) -> dict[str, float]:
    if not values:
        return zero_ci()
    ordered = sorted(values)
    return {
        "mean": mean(values),
        "ci_low": ordered[int(0.025 * (len(ordered) - 1))],
        "ci_high": ordered[int(0.975 * (len(ordered) - 1))],
    }


def summarize_policy(rows: list[dict[str, object]], *, policy_ids: set[str] | None = None) -> list[dict[str, object]]:
    summaries = []
    for policy in sorted({str(row["policy_id"]) for row in rows}):
        if policy_ids is not None and policy not in policy_ids:
            continue
        subset = [row for row in rows if row["policy_id"] == policy]
        summaries.append(
            {
                "policy_id": policy,
                "final_generated_quality_score": mean([float(row["final_generated_quality_score"]) for row in subset]),
                "total_cost_units": mean([float(row["total_cost_units"]) for row in subset]),
                "total_latency_ms": mean([float(row["total_latency_ms"]) for row in subset]),
            }
        )
    return summaries


def choose_winners(
    summaries: list[dict[str, object]],
    *,
    primary_endpoint: str,
    quality_only_policy_ids: set[str] | None = None,
    governed_policy_ids: set[str] | None = None,
) -> tuple[str, str, str, list[str]]:
    if not summaries:
        return "", "", "", []
    quality_candidates = [
        row
        for row in summaries
        if quality_only_policy_ids is None or str(row["policy_id"]) in quality_only_policy_ids
    ] or summaries
    quality_only = max(quality_candidates, key=lambda row: float(row["final_generated_quality_score"]))
    quality_floor = float(quality_only["final_generated_quality_score"]) - 0.01
    governed_candidates = [
        row
        for row in summaries
        if governed_policy_ids is None or str(row["policy_id"]) in governed_policy_ids
    ] or summaries
    feasible = [row for row in governed_candidates if float(row["final_generated_quality_score"]) >= quality_floor]
    if primary_endpoint == "latency":
        governed = min(feasible or governed_candidates, key=lambda row: (float(row["total_latency_ms"]), float(row["total_cost_units"]), str(row["policy_id"])))
    else:
        governed = min(feasible or governed_candidates, key=lambda row: (float(row["total_cost_units"]), float(row["total_latency_ms"]), str(row["policy_id"])))
    constrained = min(
        feasible or governed_candidates,
        key=lambda row: (
            float(row["total_latency_ms"]) if primary_endpoint == "latency" else float(row["total_cost_units"]),
            float(row["total_cost_units"]) if primary_endpoint == "latency" else float(row["total_latency_ms"]),
            -float(row["final_generated_quality_score"]),
            str(row["policy_id"]),
        ),
    )
    frontier = []
    for row in summaries:
        dominated = False
        for other in summaries:
            if other is row:
                continue
            better_or_equal = (
                float(other["final_generated_quality_score"]) >= float(row["final_generated_quality_score"])
                and float(other["total_cost_units"]) <= float(row["total_cost_units"])
                and float(other["total_latency_ms"]) <= float(row["total_latency_ms"])
            )
            strictly_better = (
                float(other["final_generated_quality_score"]) > float(row["final_generated_quality_score"])
                or float(other["total_cost_units"]) < float(row["total_cost_units"])
                or float(other["total_latency_ms"]) < float(row["total_latency_ms"])
            )
            if better_or_equal and strictly_better:
                dominated = True
                break
        if not dominated:
            frontier.append(str(row["policy_id"]))
    return str(governed["policy_id"]), str(quality_only["policy_id"]), str(constrained["policy_id"]), frontier


def run_crag_generation(root: Path, output_root: Path, discovery) -> dict[str, object]:
    assert discovery.generator is not None
    max_examples = int(os.environ.get("RAGWARRANT_CRAG_GEN_MAX_EXAMPLES", "4"))
    sample_offset = int(os.environ.get("RAGWARRANT_CRAG_GEN_OFFSET", "0"))
    max_tokens = int(os.environ.get("RAGWARRANT_GENERATOR_MAX_TOKENS", "48"))
    timeout_s = float(os.environ.get("RAGWARRANT_GENERATOR_TIMEOUT_S", "120"))
    retry_empty_answers = os.environ.get("RAGWARRANT_RETRY_EMPTY_GENERATED_ANSWERS", "true").strip().lower() in {"1", "true", "yes", "on"}
    primary_endpoint = os.environ.get("RAGWARRANT_CRAG_GEN_PRIMARY_ENDPOINT", "cost").strip().lower()
    if primary_endpoint not in {"cost", "latency"}:
        primary_endpoint = "cost"
    latency_guardrail = os.environ.get("RAGWARRANT_CRAG_GEN_LATENCY_GUARDRAIL", "").strip().lower()
    guardrail_enabled = primary_endpoint == "latency" and latency_guardrail in {"quality_risk", "quality_risk_adaptive_expansion", "true", "1", "yes", "on"}
    learned_guardrail_enabled = primary_endpoint == "latency" and latency_guardrail in {
        "learned_quality_risk_predictor",
        "learned_quality_risk",
        "learned",
    }
    rows = load_crag_rows(max_examples, offset=sample_offset)
    result_rows: list[dict[str, object]] = []
    empty_answer_retry_count = 0
    empty_answer_retry_success_count = 0

    def generate_policy_result(
        row: dict[str, Any],
        *,
        policy_id: str,
        split: str,
        quality_risk_predictor: QualityRiskPredictor | None = None,
    ) -> None:
        nonlocal empty_answer_retry_count, empty_answer_retry_success_count
        references = row_references(row)
        evidence_items, retrieval_cost, context_tokens = select_crag_evidence(
            row,
            policy_id,
            quality_risk_predictor=quality_risk_predictor,
        )
        prompt, prompt_hash = build_rag_prompt(question_text=str(row["query"]), evidence_items=evidence_items)
        generation = discovery.generator.generate(
            prompt,
            model=discovery.model,
            temperature=0.0,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
        raw_answer = (root / str(generation.raw_answer_local_path)).read_text(encoding="utf-8").strip() if generation.raw_answer_local_path else ""
        generation_latency_ms = generation.latency_ms
        generation_cost_units = generation.cost_units
        generator_call_count = 1
        output_token_estimate = generation.output_token_estimate
        input_token_estimate = generation.input_token_estimate
        if retry_empty_answers and not raw_answer:
            empty_answer_retry_count += 1
            repair_prompt, repair_prompt_hash = build_answer_emission_repair_prompt(
                question_text=str(row["query"]),
                evidence_items=evidence_items,
            )
            repair_generation = discovery.generator.generate(
                repair_prompt,
                model=discovery.model,
                temperature=0.0,
                max_tokens=max(max_tokens, 96),
                timeout_s=timeout_s,
            )
            repair_answer = (
                (root / str(repair_generation.raw_answer_local_path)).read_text(encoding="utf-8").strip()
                if repair_generation.raw_answer_local_path
                else ""
            )
            generation_latency_ms += repair_generation.latency_ms
            generation_cost_units += repair_generation.cost_units
            generator_call_count += 1
            input_token_estimate += repair_generation.input_token_estimate
            output_token_estimate += repair_generation.output_token_estimate
            if repair_answer:
                empty_answer_retry_success_count += 1
                generation = repair_generation
                prompt_hash = repair_prompt_hash
                raw_answer = repair_answer
        answer_f1 = max([token_f1(raw_answer, ref) for ref in references], default=0.0)
        answer_em = max([exact_match(raw_answer, ref) for ref in references], default=0.0)
        answer_containment = max([containment(raw_answer, ref) for ref in references], default=0.0)
        evidence_text = " ".join(item["text"] for item in evidence_items)
        evidence_support = max([containment(evidence_text, ref) for ref in references], default=0.0)
        citation_support = 1.0 if evidence_items and evidence_support > 0.0 else 0.0
        abstained = "INSUFFICIENT_EVIDENCE" in raw_answer.upper()
        abstention_correctness = 1.0 if not references and abstained else (0.0 if abstained else 1.0)
        quality = generated_quality_score(
            answer_correctness_f1=answer_f1,
            answer_exact_match=answer_em,
            answer_containment=answer_containment,
            evidence_support_score=evidence_support,
            citation_support_score=citation_support,
            abstention_correctness=abstention_correctness,
        )
        result_rows.append(
            {
                "example_id": stable_hash(str(row["interaction_id"])),
                "question_hash": stable_hash(str(row["query"])),
                "split": split,
                "dataset": "crag",
                "policy_id": policy_id,
                "provider": generation.provider,
                "model": generation.model,
                "prompt_hash": prompt_hash,
                "generated_answer_hash": stable_hash(raw_answer),
                "generated_answer_char_count": len(raw_answer),
                "generated_answer_token_estimate": output_token_estimate,
                "retrieval_latency_ms": 0.0,
                "generation_latency_ms": generation_latency_ms,
                "total_latency_ms": generation_latency_ms,
                "retrieval_cost_units": retrieval_cost,
                "generation_cost_units": generation_cost_units,
                "total_cost_units": retrieval_cost + generation_cost_units,
                "input_token_estimate": input_token_estimate,
                "output_token_estimate": output_token_estimate,
                "api_call_count": len(evidence_items),
                "generator_call_count": generator_call_count,
                "answer_correctness_f1": answer_f1,
                "answer_exact_match": answer_em,
                "answer_containment": answer_containment,
                "evidence_support_score": evidence_support,
                "citation_support_score": citation_support,
                "abstention_correctness": abstention_correctness,
                "final_generated_quality_score": quality,
                "raw_prompt_exported": False,
                "raw_generated_answer_exported": False,
            }
        )

    for row in rows:
        split = split_for_row(row)
        for policy_id in CRAG_GENERATIVE_POLICIES:
            generate_policy_result(row, policy_id=policy_id, split=split)

    learned_predictor: QualityRiskPredictor | None = None
    predictor_metrics: dict[str, object] = {
        "predictor_result_class": "CRAG_GEN_LLM_RISK_PREDICTOR_NOT_REQUESTED",
        "deployable_features_only": True,
        "raw_text_features_used": False,
    }
    if learned_guardrail_enabled:
        learned_predictor, predictor_metrics = learn_quality_risk_predictor(crag_rows=rows, result_rows=result_rows)
        if learned_predictor is not None:
            for row in rows:
                generate_policy_result(
                    row,
                    policy_id=LEARNED_QUALITY_RISK_LATENCY_POLICY,
                    split=split_for_row(row),
                    quality_risk_predictor=learned_predictor,
                )
    summaries = summarize_policy(result_rows)
    validation_selection_rows = [row for row in result_rows if row["split"] == "validation"]
    if not validation_selection_rows:
        validation_selection_rows = [row for row in result_rows if row["split"] == "calibration"] or result_rows
    if learned_guardrail_enabled:
        governed_policy_ids = {LEARNED_QUALITY_RISK_LATENCY_POLICY}
    elif guardrail_enabled:
        governed_policy_ids = {QUALITY_GUARDED_LATENCY_POLICY}
    else:
        governed_policy_ids = DEPLOYABLE_CRAG_GENERATIVE_POLICIES
    selection_policy_ids = governed_policy_ids | QUALITY_ONLY_CRAG_GENERATIVE_POLICIES
    selection_summaries = summarize_policy(validation_selection_rows, policy_ids=selection_policy_ids)
    governed, quality_only, constrained, frontier = choose_winners(
        selection_summaries,
        primary_endpoint=primary_endpoint,
        quality_only_policy_ids=QUALITY_ONLY_CRAG_GENERATIVE_POLICIES,
        governed_policy_ids=governed_policy_ids,
    )
    confirmatory = [row for row in result_rows if row["split"] == "confirmatory_test"]
    if not confirmatory:
        confirmatory = result_rows
    governed_rows = {row["example_id"]: row for row in confirmatory if row["policy_id"] == governed}
    quality_rows = {row["example_id"]: row for row in confirmatory if row["policy_id"] == quality_only}
    shared_ids = sorted(set(governed_rows) & set(quality_rows))
    quality_deltas = [float(governed_rows[idx]["final_generated_quality_score"]) - float(quality_rows[idx]["final_generated_quality_score"]) for idx in shared_ids]
    evidence_deltas = [float(governed_rows[idx]["evidence_support_score"]) - float(quality_rows[idx]["evidence_support_score"]) for idx in shared_ids]
    cost_deltas = [float(governed_rows[idx]["total_cost_units"]) - float(quality_rows[idx]["total_cost_units"]) for idx in shared_ids]
    latency_deltas = [float(governed_rows[idx]["total_latency_ms"]) - float(quality_rows[idx]["total_latency_ms"]) for idx in shared_ids]
    api_deltas = [float(governed_rows[idx]["api_call_count"]) - float(quality_rows[idx]["api_call_count"]) for idx in shared_ids]
    diagnostics = quality_signal_diagnostics(result_rows)
    if diagnostics["quality_signal_audit_result_class"] == "HOTPOTQA_GEN_LLM_BLOCKED_NO_USABLE_QUALITY_SIGNAL":
        diagnostics["quality_signal_audit_result_class"] = "CRAG_GENERATED_QUALITY_BLOCKED_NO_USABLE_SIGNAL"
    elif diagnostics["quality_signal_audit_result_class"] == "HOTPOTQA_GEN_LLM_QUALITY_SIGNAL_CONFIRMED":
        diagnostics["quality_signal_audit_result_class"] = "CRAG_GENERATED_QUALITY_LOCAL_EVALUATOR_ACTIVE"
    elif diagnostics["quality_signal_audit_result_class"] == "HOTPOTQA_GEN_LLM_ZERO_DELTAS_GENERATOR_INSENSITIVE":
        diagnostics["quality_signal_audit_result_class"] = "CRAG_GENERATED_QUALITY_BLOCKED_NO_USABLE_SIGNAL"
    equivalent_quality = bool(quality_deltas) and simple_ci(quality_deltas)["mean"] >= -0.01
    lower_cost = bool(cost_deltas) and simple_ci(cost_deltas)["ci_high"] < 0
    lower_latency = bool(latency_deltas) and simple_ci(latency_deltas)["ci_high"] < 0
    if learned_guardrail_enabled and learned_predictor is None:
        result_class = "GEN_LLM_VALIDATION_BLOCKED_PREDICTOR_GATE_CRAG"
    elif not diagnostics["usable_quality_signal"]:
        result_class = "GEN_LLM_VALIDATION_BLOCKED_NO_USABLE_QUALITY_SIGNAL_CRAG"
    elif primary_endpoint == "latency" and equivalent_quality and lower_latency:
        result_class = "GEN_LLM_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_GENERATED_QUALITY_CRAG"
    elif primary_endpoint == "cost" and equivalent_quality and lower_cost:
        result_class = "GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY_CRAG"
    elif quality_deltas and simple_ci(quality_deltas)["mean"] < -0.01 and (simple_ci(cost_deltas)["mean"] < 0 or simple_ci(latency_deltas)["mean"] < 0):
        result_class = "GEN_LLM_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS_CRAG"
    else:
        result_class = "GEN_LLM_GOVERNANCE_INCONCLUSIVE_CRAG"
    mapping_class = (
        "CRAG_GENERATED_QUALITY_LOCAL_EVALUATOR_ACTIVE"
        if diagnostics["usable_quality_signal"]
        else "CRAG_GENERATED_QUALITY_BLOCKED_NO_USABLE_SIGNAL"
    )
    evidence_class = (
        "crag_generative_validation_sanitized_bounded_repeat"
        if sample_offset
        else "crag_generative_validation_sanitized_bounded_sample"
    )
    stats = {
        "suite": "ragwarrant_crag_generative_llm_validation_v1",
        "evidence_class": evidence_class,
        "result_class": result_class,
        "generator_provider": discovery.provider,
        "generator_model": discovery.model,
        "primary_endpoint": primary_endpoint,
        "selector_design": (
            "validation_learned_deployable_quality_risk_predictor_vs_quality_only_high_evidence_confirmatory_eval"
            if learned_guardrail_enabled
            else
            "validation_split_quality_only_high_evidence_vs_quality_guarded_latency_confirmatory_eval"
            if guardrail_enabled
            else "validation_split_quality_only_high_evidence_vs_governed_latency_feasible_confirmatory_eval"
        ),
        "selector_candidate_policy_count": len(selection_summaries),
        "selector_candidate_policies": [str(row["policy_id"]) for row in selection_summaries],
        "governed_candidate_policies": sorted(governed_policy_ids),
        "quality_only_candidate_policies": sorted(QUALITY_ONLY_CRAG_GENERATIVE_POLICIES),
        "quality_risk_guardrail_enabled": guardrail_enabled or learned_guardrail_enabled,
        "quality_risk_guardrail_policy": (
            LEARNED_QUALITY_RISK_LATENCY_POLICY
            if learned_guardrail_enabled
            else QUALITY_GUARDED_LATENCY_POLICY
            if guardrail_enabled
            else ""
        ),
        "quality_risk_guardrail_rule": (
            "learn deployable expansion rule on validation generated-quality loss; expand only when predictor flags quality risk"
            if learned_guardrail_enabled
            else
            "start with two evidence items and expand to five when local CRAG answer/alternate-answer containment is absent"
            if guardrail_enabled
            else ""
        ),
        "quality_risk_predictor": predictor_metrics,
        "quality_risk_predictor_trained": learned_guardrail_enabled,
        "quality_risk_predictor_gate_passed": bool(learned_guardrail_enabled and learned_predictor is not None),
        "quality_risk_predictor_result_class": predictor_metrics.get("predictor_result_class", ""),
        "quality_risk_predictor_deployable_features_only": bool(predictor_metrics.get("deployable_features_only", True)),
        "quality_risk_predictor_raw_text_features_used": bool(predictor_metrics.get("raw_text_features_used", False)),
        "quality_risk_guardrail_expansion_count": sum(
            1
            for row in result_rows
            if row["policy_id"] == (
                LEARNED_QUALITY_RISK_LATENCY_POLICY if learned_guardrail_enabled else QUALITY_GUARDED_LATENCY_POLICY
            )
            and int(row["api_call_count"]) > 2
        ),
        "quality_risk_guardrail_expansion_rate": (
            sum(
                1
                for row in result_rows
                if row["policy_id"] == (
                    LEARNED_QUALITY_RISK_LATENCY_POLICY if learned_guardrail_enabled else QUALITY_GUARDED_LATENCY_POLICY
                )
                and int(row["api_call_count"]) > 2
            )
            / max(
                1,
                sum(
                    1
                    for row in result_rows
                    if row["policy_id"] == (
                        LEARNED_QUALITY_RISK_LATENCY_POLICY if learned_guardrail_enabled else QUALITY_GUARDED_LATENCY_POLICY
                    )
                ),
            )
            if guardrail_enabled or learned_guardrail_enabled
            else 0.0
        ),
        "generator_available": True,
        "generator_local_or_hosted": discovery.local_or_hosted,
        "quality_metric_class": "GENERATED_QUALITY_CRAG_LOCAL_EVALUATOR",
        "crag_evaluator_mapping_result_class": mapping_class,
        "governed_winner": governed,
        "quality_only_winner": quality_only,
        "constrained_optimizer_winner": constrained,
        "pareto_frontier": frontier,
        "rag_compass_rank": next((idx + 1 for idx, row in enumerate(sorted(summaries, key=lambda item: float(item["final_generated_quality_score"]), reverse=True)) if row["policy_id"] == "rag_compass_optional"), ""),
        "generated_quality_delta": simple_ci(quality_deltas),
        "evidence_support_delta": simple_ci(evidence_deltas),
        "cost_delta": simple_ci(cost_deltas),
        "latency_delta_ms": simple_ci(latency_deltas),
        "api_call_delta": simple_ci(api_deltas),
        "generation_rows": len(result_rows),
        "example_count": len(rows),
        "sample_offset": sample_offset,
        "sample_strategy": "deterministic_contiguous_offset",
        "quality_signal_audit_result_class": diagnostics["quality_signal_audit_result_class"],
        "prior_zero_delta_explanation": diagnostics["prior_zero_delta_explanation"],
        "non_empty_generated_answers": diagnostics["non_empty_generated_answers"],
        "unique_answer_hash_count": diagnostics["unique_answer_hash_count"],
        "quality_variance": diagnostics["quality_variance"],
        "usable_quality_signal": diagnostics["usable_quality_signal"],
        "answer_emission_repair_enabled": retry_empty_answers,
        "empty_answer_retry_count": empty_answer_retry_count,
        "empty_answer_retry_success_count": empty_answer_retry_success_count,
        "empty_answer_retry_success_rate": empty_answer_retry_success_count / empty_answer_retry_count if empty_answer_retry_count else 0.0,
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
        "raw_questions_committed": False,
        "raw_evidence_committed": False,
        "secrets_committed": False,
    }
    write_csv(output_root / "per_query_generation_metrics.csv", GENERATION_FIELDNAMES, result_rows)
    write_csv(output_root / "policy_summary_metrics.csv", ["policy_id", "final_generated_quality_score", "total_cost_units", "total_latency_ms"], summaries)
    write_csv(output_root / "selector_comparison.csv", ["selector", "winner", "reason"], [
        {
            "selector": "governed_selection",
            "winner": governed,
            "reason": (
                f"validation-trained deployable quality-risk predictor allowed learned guarded latency rerun with lowest {primary_endpoint} within generated-quality noninferiority margin"
                if learned_guardrail_enabled
                else
                f"validation quality-risk guarded latency policy with lowest {primary_endpoint} within generated-quality noninferiority margin"
                if guardrail_enabled
                else f"validation deployable policy with lowest {primary_endpoint} within generated-quality noninferiority margin"
            ),
        },
        {"selector": "quality_only_best_on_validation", "winner": quality_only, "reason": "highest validation generated quality among predeclared high-evidence quality-only candidates; ignores cost and latency"},
        {"selector": "constrained_quality_optimizer", "winner": constrained, "reason": "deployment-aware validation selector over deployable policies"},
    ])
    write_csv(output_root / "pareto_frontier.csv", ["policy_id", "frontier_reason"], [{"policy_id": policy, "frontier_reason": "nondominated on generated quality, cost, and latency"} for policy in frontier])
    write_csv(
        output_root / "quality_signal_diagnostics.csv",
        ["metric", "value"],
        [{"metric": key, "value": value} for key, value in diagnostics.items()],
    )
    return stats


def run_crag_generative_validation(root: Path, *, output_root: Path, dry_run: bool = False) -> dict[str, object]:
    env = inspect_crag_environment()
    discovery = discover_generator(dry_run=dry_run)
    if not env["approved_noncommercial_research_only"] or not env["crag_data_exists"] or not env["mock_api_available"]:
        result_class = "GEN_LLM_VALIDATION_BLOCKED_CRAG_UNAVAILABLE"
        blocker = "approved CRAG data/mock API environment is not fully available"
    elif not discovery.available:
        result_class = discovery.status
        blocker = discovery.instructions
    else:
        stats = run_crag_generation(root, output_root, discovery)
        manifest = {
            "suite": "ragwarrant_crag_generative_llm_validation_v1",
            "evidence_class": stats["evidence_class"],
            "result_class": stats["result_class"],
            "blocker": "",
            "generator_provider": discovery.provider,
            "generator_model": discovery.model,
            "generator_available": discovery.available,
            "generator_local_or_hosted": discovery.local_or_hosted,
            "crag_approval_env_var_present": bool(env["approved_noncommercial_research_only"]),
            "crag_root_configured": bool(env["crag_root_configured"]),
            "crag_data_configured": bool(env["crag_data_configured"]),
            "mock_api_available": bool(env["mock_api_available"]),
            "local_evaluator_available": bool(env["local_evaluation_available"]),
            "raw_prompts_committed": False,
            "raw_generated_answers_committed": False,
            "raw_questions_committed": False,
            "raw_evidence_committed": False,
            "secrets_committed": False,
        }
        write_json(output_root / "generative_crag_manifest.json", manifest)
        write_json(output_root / "primary_outcome_statistics.json", stats)
        write_md(
            output_root / "generator_environment_report.md",
            f"""
# CRAG Generative LLM Environment

Provider: `{discovery.provider}`
Model: `{discovery.model}`
Status: `{stats['result_class']}`

Raw prompts, generated answers, CRAG questions, CRAG evidence, and CRAG API responses are not committed.
""",
        )
        write_md(
            output_root / "primary_outcome_report.md",
            f"""
# CRAG Generative LLM Validation

Result class: `{stats['result_class']}`

This bounded local-generator run used CRAG answers and alternate answers locally for scoring. Public artifacts contain only hashes, counts, and metrics; raw prompts, raw questions, raw evidence, raw API responses, and raw generated answers are excluded from Git.
""",
        )
        return stats

    output_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "suite": "ragwarrant_crag_generative_llm_validation_v1",
        "evidence_class": "crag_generative_validation_attempt",
        "result_class": result_class,
        "blocker": blocker,
        "generator_provider": discovery.provider,
        "generator_model": discovery.model,
        "generator_available": discovery.available,
        "generator_local_or_hosted": discovery.local_or_hosted,
        "crag_approval_env_var_present": bool(env["approved_noncommercial_research_only"]),
        "crag_root_configured": bool(env["crag_root_configured"]),
        "crag_data_configured": bool(env["crag_data_configured"]),
        "mock_api_available": bool(env["mock_api_available"]),
        "local_evaluator_available": bool(env["local_evaluation_available"]),
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
        "raw_questions_committed": False,
        "raw_evidence_committed": False,
        "secrets_committed": False,
    }
    stats = {
        **manifest,
        "quality_metric_class": "GENERATED_QUALITY_BLOCKED_NO_SIGNAL",
        "governed_winner": "",
        "quality_only_winner": "",
        "constrained_optimizer_winner": "",
        "pareto_frontier": [],
        "rag_compass_rank": "",
        "generated_quality_delta": zero_ci(),
        "evidence_support_delta": zero_ci(),
        "cost_delta": zero_ci(),
        "latency_delta_ms": zero_ci(),
        "api_call_delta": zero_ci(),
        "generation_rows": 0,
    }
    write_json(output_root / "generative_crag_manifest.json", manifest)
    write_json(output_root / "primary_outcome_statistics.json", stats)
    write_csv(output_root / "per_query_generation_metrics.csv", GENERATION_FIELDNAMES, [])
    write_csv(output_root / "policy_summary_metrics.csv", ["policy_id", "final_generated_quality_score", "total_cost_units", "total_latency_ms"], [])
    write_csv(output_root / "selector_comparison.csv", ["selector", "winner", "reason"], [])
    write_csv(output_root / "pareto_frontier.csv", ["policy_id", "frontier_reason"], [])
    write_md(
        output_root / "generator_environment_report.md",
        f"""
# CRAG Generative LLM Environment

Provider: `{discovery.provider}`
Model: `{discovery.model or 'not configured'}`
Status: `{result_class}`

Raw prompts, generated answers, CRAG questions, CRAG evidence, and CRAG API responses are not committed.

Blocker: {blocker}
""",
    )
    write_md(
        output_root / "primary_outcome_report.md",
        f"""
# CRAG Generative LLM Validation

Result class: `{result_class}`

This run did not produce a generative governance claim. Public artifacts contain only sanitized status, hashes, counts, and metric fields. Raw prompts and raw generated answers are excluded.
""",
    )
    return stats
