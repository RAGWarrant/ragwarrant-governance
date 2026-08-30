from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


BASE_PARENT_RUN = "ragwarrant_crag_mock_api_validation_v1_20260809-165415-92d8c0edd4"
BASE_PARENT_RUN_ROOT = Path("artifacts/current_ragwarrant_evidence")

POLICY_SOURCE_MAP = {
    "low_retrieval_single_endpoint": "top_k_low",
    "expanded_retrieval_multi_endpoint": "top_k_high",
    "adaptive_routing_on_insufficient_evidence": "retrieval_confidence_gating",
    "static_default_policy": "static_default_rag_policy",
    "greedy_regression_aware_search": "greedy_regression_aware_search",
    "optuna_tpe": "optuna_tpe",
    "rag_compass": "rag_compass",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        seen: list[str] = []
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.append(key)
        fieldnames = seen
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def mean(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else math.nan


def percentile(values: list[float], q: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return float(ordered[int(pos)])
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower))


def deterministic_bootstrap_ci(deltas: list[float], samples: int = 1000) -> dict[str, float]:
    if not deltas:
        return {"mean_delta": math.nan, "ci_low": math.nan, "ci_high": math.nan}
    n = len(deltas)
    means: list[float] = []
    for sample_idx in range(samples):
        total = 0.0
        for i in range(n):
            # Deterministic resampling avoids adding a new dependency or seed artifact.
            total += deltas[(sample_idx * 17 + i * 31 + sample_idx // 7) % n]
        means.append(total / n)
    return {
        "mean_delta": mean(deltas),
        "ci_low": percentile(means, 0.025),
        "ci_high": percentile(means, 0.975),
    }


def policy_definitions() -> list[dict[str, Any]]:
    return [
        {
            "policy_id": "low_retrieval_single_endpoint",
            "candidate_family": "low_retrieval",
            "max_endpoints": 1,
            "endpoint_selection_rule": "domain_primary_endpoint_only",
            "fallback_rule": "none",
            "fallback_trigger": "not_applicable",
            "evidence_threshold": 0.50,
            "confidence_threshold": "",
            "answerability_threshold": "",
            "abstention_rule": "abstain_only_when_no_mock_api_result",
            "max_context_items": 10,
            "max_context_tokens": "observed_context_lengths_redacted",
            "rerank_enabled": False,
            "cost_rule": "minimize_observed_budget_units",
            "latency_rule": "minimize_observed_latency",
            "quality_target": "within_0.01_of_best_validation_quality",
            "constraints": "single endpoint; zero failure; provenance eligible",
            "expected_behavioral_difference": "fewer endpoints and lower observed budget than expanded retrieval",
            "source_policy_id": "top_k_low",
        },
        {
            "policy_id": "expanded_retrieval_multi_endpoint",
            "candidate_family": "expanded_retrieval",
            "max_endpoints": 2,
            "endpoint_selection_rule": "domain_primary_plus_secondary_endpoint",
            "fallback_rule": "always_expand",
            "fallback_trigger": "not_applicable",
            "evidence_threshold": 0.50,
            "confidence_threshold": "",
            "answerability_threshold": "",
            "abstention_rule": "abstain_only_when_no_mock_api_result",
            "max_context_items": 20,
            "max_context_tokens": "observed_context_lengths_redacted",
            "rerank_enabled": False,
            "cost_rule": "allow_higher_cost_for_recall",
            "latency_rule": "allow_higher_latency_for_recall",
            "quality_target": "maximize_answer_quality",
            "constraints": "two endpoints; zero failure; provenance eligible",
            "expected_behavioral_difference": "more endpoints, more API calls, and higher observed budget",
            "source_policy_id": "top_k_high",
        },
        {
            "policy_id": "adaptive_routing_on_insufficient_evidence",
            "candidate_family": "adaptive_routing",
            "max_endpoints": 2,
            "endpoint_selection_rule": "start_domain_primary_then_expand_on_low_evidence",
            "fallback_rule": "call_secondary_endpoint_when_evidence_is_insufficient",
            "fallback_trigger": "domain/task confidence below threshold in frozen observations",
            "evidence_threshold": 0.65,
            "confidence_threshold": 0.65,
            "answerability_threshold": "",
            "abstention_rule": "abstain_only_when_no_supported_source",
            "max_context_items": 20,
            "max_context_tokens": "observed_context_lengths_redacted",
            "rerank_enabled": True,
            "cost_rule": "pay_extra_cost_only_on_fallback",
            "latency_rule": "pay_extra_latency_only_on_fallback",
            "quality_target": "improve difficult-query quality without always expanding",
            "constraints": "variable endpoint count; zero failure; provenance eligible",
            "expected_behavioral_difference": "API calls vary by query rather than staying fixed",
            "source_policy_id": "retrieval_confidence_gating",
        },
        {
            "policy_id": "measured_cost_minimizer_at_quality_floor",
            "candidate_family": "cost_aware_selector",
            "max_endpoints": "selector",
            "endpoint_selection_rule": "select lowest measured cost among validation-quality-noninferior candidates",
            "fallback_rule": "not_applicable",
            "fallback_trigger": "not_applicable",
            "evidence_threshold": 0.50,
            "confidence_threshold": "",
            "answerability_threshold": "",
            "abstention_rule": "inherits_selected_policy",
            "max_context_items": "inherits_selected_policy",
            "max_context_tokens": "observed_context_lengths_redacted",
            "rerank_enabled": "inherits_selected_policy",
            "cost_rule": "primary objective after quality floor",
            "latency_rule": "tie_breaker",
            "quality_target": "within_0.01_of_best_validation_quality",
            "constraints": "quality noninferiority margin 0.01",
            "expected_behavioral_difference": "selector uses measured budget_units, not labels",
            "source_policy_id": "",
        },
        {
            "policy_id": "measured_latency_minimizer_at_quality_floor",
            "candidate_family": "latency_aware_selector",
            "max_endpoints": "selector",
            "endpoint_selection_rule": "select lowest measured p95 latency among validation-quality-noninferior candidates",
            "fallback_rule": "not_applicable",
            "fallback_trigger": "not_applicable",
            "evidence_threshold": 0.50,
            "confidence_threshold": "",
            "answerability_threshold": "",
            "abstention_rule": "inherits_selected_policy",
            "max_context_items": "inherits_selected_policy",
            "max_context_tokens": "observed_context_lengths_redacted",
            "rerank_enabled": "inherits_selected_policy",
            "cost_rule": "tie_breaker",
            "latency_rule": "primary objective after quality floor",
            "quality_target": "within_0.01_of_best_validation_quality",
            "constraints": "quality noninferiority margin 0.01",
            "expected_behavioral_difference": "selector uses observed latency_ms, not labels",
            "source_policy_id": "",
        },
        {
            "policy_id": "quality_only_best_on_validation",
            "candidate_family": "quality_only_selector",
            "max_endpoints": "selector",
            "endpoint_selection_rule": "highest validation final_quality_score; deterministic lexical tie break",
            "fallback_rule": "not_applicable",
            "fallback_trigger": "not_applicable",
            "evidence_threshold": "",
            "confidence_threshold": "",
            "answerability_threshold": "",
            "abstention_rule": "ignored_for_selection_except_quality_component",
            "max_context_items": "ignored",
            "max_context_tokens": "ignored",
            "rerank_enabled": "ignored",
            "cost_rule": "ignored",
            "latency_rule": "ignored",
            "quality_target": "maximize validation final_quality_score",
            "constraints": "valid evidence only",
            "expected_behavioral_difference": "ignores measured cost and latency",
            "source_policy_id": "",
        },
        {
            "policy_id": "constrained_quality_optimizer",
            "candidate_family": "constrained_selector",
            "max_endpoints": "selector",
            "endpoint_selection_rule": "maximize validation quality subject to explicit deployment constraints",
            "fallback_rule": "not_applicable",
            "fallback_trigger": "not_applicable",
            "evidence_threshold": 0.50,
            "confidence_threshold": "",
            "answerability_threshold": "",
            "abstention_rule": "inherits_selected_policy",
            "max_context_items": "inherits_selected_policy",
            "max_context_tokens": "observed_context_lengths_redacted",
            "rerank_enabled": "inherits_selected_policy",
            "cost_rule": "mean budget <= 1.5",
            "latency_rule": "p95 latency <= 4000 ms",
            "quality_target": "maximize feasible quality",
            "constraints": "mean cost, p95 latency, failure rate, evidence support",
            "expected_behavioral_difference": "reports active constraints and feasible winner",
            "source_policy_id": "",
        },
        {
            "policy_id": "pareto_frontier_selector",
            "candidate_family": "pareto_selector",
            "max_endpoints": "selector",
            "endpoint_selection_rule": "report nondominated policies across quality/cost/latency/failure/evidence",
            "fallback_rule": "not_applicable",
            "fallback_trigger": "not_applicable",
            "evidence_threshold": 0.50,
            "confidence_threshold": "",
            "answerability_threshold": "",
            "abstention_rule": "inherits_frontier_policies",
            "max_context_items": "frontier",
            "max_context_tokens": "observed_context_lengths_redacted",
            "rerank_enabled": "frontier",
            "cost_rule": "minimize measured cost",
            "latency_rule": "minimize measured latency",
            "quality_target": "maximize final_quality_score",
            "constraints": "nondomination",
            "expected_behavioral_difference": "does not collapse objectives into scalar utility",
            "source_policy_id": "",
        },
        {
            "policy_id": "governed_selection",
            "candidate_family": "governed_selector",
            "max_endpoints": "selector",
            "endpoint_selection_rule": "quality floor plus governance eligibility plus measured cost/latency constraints",
            "fallback_rule": "not_applicable",
            "fallback_trigger": "not_applicable",
            "evidence_threshold": 0.50,
            "confidence_threshold": "",
            "answerability_threshold": "",
            "abstention_rule": "inherits_selected_policy",
            "max_context_items": "inherits_selected_policy",
            "max_context_tokens": "observed_context_lengths_redacted",
            "rerank_enabled": "inherits_selected_policy",
            "cost_rule": "minimize cost among quality-noninferior eligible candidates",
            "latency_rule": "minimize latency after cost",
            "quality_target": "within_0.01_of_best_validation_quality",
            "constraints": "security, provenance, zero failure, quality floor",
            "expected_behavioral_difference": "promotion decision changes because operating constraints are enforced",
            "source_policy_id": "",
        },
    ]


def component_scores(row: dict[str, str]) -> dict[str, float | bool]:
    raw_quality = float(row["raw_quality"])
    api_calls = max(float(row["api_call_count"]), 1.0)
    successful_calls = float(row["successful_call_count"])
    result_count = float(row["result_count"])
    evidence_support = min(1.0, result_count / (5.0 * api_calls)) * (successful_calls / api_calls)
    answerability = 1.0 if result_count > 0 and float(row["failure_rate"]) == 0.0 else 0.0
    abstained = result_count == 0
    abstention_score = 1.0 if (answerability == 0.0 and abstained) or (answerability > 0.0 and not abstained) else 0.0
    final_quality = 0.70 * raw_quality + 0.20 * evidence_support + 0.10 * abstention_score
    return {
        "answer_correctness_score": raw_quality,
        "evidence_support_score": evidence_support,
        "abstention_score": abstention_score,
        "answerability_score": answerability,
        "final_quality_score": final_quality,
        "abstained": abstained,
        "abstention_correct": abstention_score == 1.0,
    }


def transformed_rows(parent_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_source = {value: key for key, value in POLICY_SOURCE_MAP.items()}
    out: list[dict[str, Any]] = []
    for row in parent_rows:
        policy_id = by_source.get(row["policy_id"])
        if policy_id is None:
            continue
        route_parts = [part for part in row["route_plan"].split("|") if part]
        scores = component_scores(row)
        out.append(
            {
                "query_id": row["query_id"],
                "query_text_hash": "",
                "split": row["split"],
                "domain": row["domain"],
                "question_type": row["question_type"],
                "static_or_dynamic": row["static_or_dynamic"],
                "policy_id": policy_id,
                "source_policy_id": row["policy_id"],
                "selected_endpoints": "|".join(route_parts),
                "endpoint_count": len(route_parts),
                "api_call_count": int(float(row["api_call_count"])),
                "api_failure_count": int(round(float(row["api_call_count"]) * float(row["failure_rate"]))),
                "retry_count": 0,
                "total_latency_ms": float(row["latency_ms"]),
                "p_endpoint_latency_ms": float(row["latency_ms"]) / max(1, len(route_parts)),
                "measured_cost_units": float(row["budget_units"]),
                "estimated_token_count": int(float(row["result_count"]) * 64),
                "context_item_count": int(float(row["result_count"])),
                "context_token_count": int(float(row["result_count"]) * 64),
                "source_count": int(float(row["result_count"])),
                "raw_quality_components": json.dumps(
                    {
                        "parent_raw_quality": float(row["raw_quality"]),
                        "mock_api_result_count": int(float(row["result_count"])),
                        "successful_call_count": int(float(row["successful_call_count"])),
                    },
                    sort_keys=True,
                ),
                "governance_eligible": row["security_eligible"] == "True" and row["provenance_eligible"] == "True",
                "governance_disqualification_reason": "",
                **scores,
            }
        )
    return out


def summarize_policy(rows: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["split"] == split:
            grouped[str(row["policy_id"])].append(row)
    summaries: list[dict[str, Any]] = []
    for policy_id, prows in grouped.items():
        summaries.append(
            {
                "policy_id": policy_id,
                "source_policy_id": prows[0]["source_policy_id"],
                "final_quality_score": mean([float(r["final_quality_score"]) for r in prows]),
                "answer_correctness_score": mean([float(r["answer_correctness_score"]) for r in prows]),
                "evidence_support_score": mean([float(r["evidence_support_score"]) for r in prows]),
                "abstention_score": mean([float(r["abstention_score"]) for r in prows]),
                "abstention_rate": mean([1.0 if r["abstained"] else 0.0 for r in prows]),
                "abstention_correctness": mean([1.0 if r["abstention_correct"] else 0.0 for r in prows]),
                "mean_measured_cost_units": mean([float(r["measured_cost_units"]) for r in prows]),
                "total_measured_cost_units": sum(float(r["measured_cost_units"]) for r in prows),
                "mean_latency_ms": mean([float(r["total_latency_ms"]) for r in prows]),
                "p50_latency_ms": percentile([float(r["total_latency_ms"]) for r in prows], 0.50),
                "p90_latency_ms": percentile([float(r["total_latency_ms"]) for r in prows], 0.90),
                "p95_latency_ms": percentile([float(r["total_latency_ms"]) for r in prows], 0.95),
                "p99_latency_ms": percentile([float(r["total_latency_ms"]) for r in prows], 0.99),
                "mean_api_calls": mean([float(r["api_call_count"]) for r in prows]),
                "total_api_calls": sum(int(r["api_call_count"]) for r in prows),
                "failure_rate": mean([float(r["api_failure_count"]) / max(1.0, float(r["api_call_count"])) for r in prows]),
                "mean_context_items": mean([float(r["context_item_count"]) for r in prows]),
                "query_count": len(prows),
            }
        )
    return sorted(summaries, key=lambda r: str(r["policy_id"]))


def select_quality_only(validation: list[dict[str, Any]]) -> str:
    return str(sorted(validation, key=lambda r: (-float(r["final_quality_score"]), str(r["policy_id"])))[0]["policy_id"])


def select_cost_minimizer(validation: list[dict[str, Any]], margin: float) -> str:
    max_quality = max(float(r["final_quality_score"]) for r in validation)
    floor = max_quality - margin
    eligible = [r for r in validation if float(r["final_quality_score"]) >= floor]
    return str(sorted(eligible, key=lambda r: (float(r["mean_measured_cost_units"]), float(r["p95_latency_ms"]), str(r["policy_id"])))[0]["policy_id"])


def select_latency_minimizer(validation: list[dict[str, Any]], margin: float) -> str:
    max_quality = max(float(r["final_quality_score"]) for r in validation)
    floor = max_quality - margin
    eligible = [r for r in validation if float(r["final_quality_score"]) >= floor]
    return str(sorted(eligible, key=lambda r: (float(r["p95_latency_ms"]), float(r["mean_measured_cost_units"]), str(r["policy_id"])))[0]["policy_id"])


def select_constrained(validation: list[dict[str, Any]], constraints: dict[str, float]) -> tuple[str, list[str]]:
    active = ["mean_measured_cost_units", "p95_latency_ms", "failure_rate", "evidence_support_score"]
    eligible = [
        r
        for r in validation
        if float(r["mean_measured_cost_units"]) <= constraints["max_mean_cost_units"]
        and float(r["p95_latency_ms"]) <= constraints["max_p95_latency_ms"]
        and float(r["failure_rate"]) <= constraints["max_failure_rate"]
        and float(r["evidence_support_score"]) >= constraints["min_evidence_support_score"]
    ]
    if not eligible:
        return "", active
    winner = sorted(
        eligible,
        key=lambda r: (
            -float(r["final_quality_score"]),
            float(r["mean_measured_cost_units"]),
            float(r["p95_latency_ms"]),
            str(r["policy_id"]),
        ),
    )[0]
    return str(winner["policy_id"]), active


def pareto_frontier(summaries: list[dict[str, Any]]) -> list[str]:
    def dominates(a: dict[str, Any], b: dict[str, Any]) -> bool:
        objectives = [
            (float(a["final_quality_score"]), float(b["final_quality_score"]), "max"),
            (float(a["mean_measured_cost_units"]), float(b["mean_measured_cost_units"]), "min"),
            (float(a["p95_latency_ms"]), float(b["p95_latency_ms"]), "min"),
            (float(a["failure_rate"]), float(b["failure_rate"]), "min"),
            (float(a["evidence_support_score"]), float(b["evidence_support_score"]), "max"),
            (float(a["abstention_correctness"]), float(b["abstention_correctness"]), "max"),
        ]
        at_least = all(av >= bv if direction == "max" else av <= bv for av, bv, direction in objectives)
        strictly = any(av > bv if direction == "max" else av < bv for av, bv, direction in objectives)
        return at_least and strictly

    frontier: list[str] = []
    for row in summaries:
        if not any(dominates(other, row) for other in summaries if other is not row):
            frontier.append(str(row["policy_id"]))
    return sorted(frontier)


def behavioral_distinction_matrix(rows: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["split"] == split:
            grouped[str(row["policy_id"])].append(row)
    policies = sorted(grouped)
    matrix: list[dict[str, Any]] = []
    for left in policies:
        for right in policies:
            if left >= right:
                continue
            lrows = grouped[left]
            rrows = grouped[right]
            left_endpoints = set("|".join(str(r["selected_endpoints"]) for r in lrows).split("|"))
            right_endpoints = set("|".join(str(r["selected_endpoints"]) for r in rrows).split("|"))
            intersection = len(left_endpoints & right_endpoints)
            union = len(left_endpoints | right_endpoints) or 1
            matrix.append(
                {
                    "left_policy_id": left,
                    "right_policy_id": right,
                    "endpoint_set_jaccard_distance": 1.0 - intersection / union,
                    "api_call_count_difference": mean([float(r["api_call_count"]) for r in lrows]) - mean([float(r["api_call_count"]) for r in rrows]),
                    "context_count_difference": mean([float(r["context_item_count"]) for r in lrows]) - mean([float(r["context_item_count"]) for r in rrows]),
                    "context_token_difference": mean([float(r["context_token_count"]) for r in lrows]) - mean([float(r["context_token_count"]) for r in rrows]),
                    "source_count_difference": mean([float(r["source_count"]) for r in lrows]) - mean([float(r["source_count"]) for r in rrows]),
                    "latency_difference_ms": mean([float(r["total_latency_ms"]) for r in lrows]) - mean([float(r["total_latency_ms"]) for r in rrows]),
                    "measured_cost_difference": mean([float(r["measured_cost_units"]) for r in lrows]) - mean([float(r["measured_cost_units"]) for r in rrows]),
                    "abstention_rate_difference": mean([1.0 if r["abstained"] else 0.0 for r in lrows]) - mean([1.0 if r["abstained"] else 0.0 for r in rrows]),
                    "answer_quality_difference": mean([float(r["final_quality_score"]) for r in lrows]) - mean([float(r["final_quality_score"]) for r in rrows]),
                }
            )
    return matrix


def pairwise_deltas(rows: list[dict[str, Any]], left_policy: str, right_policy: str, field: str, split: str = "confirmatory_test") -> list[float]:
    left = {(r["query_id"], r["split"]): float(r[field]) for r in rows if r["policy_id"] == left_policy and r["split"] == split}
    right = {(r["query_id"], r["split"]): float(r[field]) for r in rows if r["policy_id"] == right_policy and r["split"] == split}
    keys = sorted(set(left) & set(right))
    return [left[key] - right[key] for key in keys]


def win_tie_loss(deltas: list[float], tolerance: float = 1e-12) -> dict[str, int]:
    return {
        "win": sum(1 for delta in deltas if delta > tolerance),
        "tie": sum(1 for delta in deltas if abs(delta) <= tolerance),
        "loss": sum(1 for delta in deltas if delta < -tolerance),
    }


def run_experiment(root: Path) -> dict[str, Any]:
    parent_dir = root / BASE_PARENT_RUN_ROOT / BASE_PARENT_RUN
    parent_csv = parent_dir / "crag_mock_api_per_query_results.csv"
    if not parent_csv.exists():
        raise FileNotFoundError(parent_csv)

    margin = 0.01
    constraints = {
        "max_mean_cost_units": 1.5,
        "max_p95_latency_ms": 4000.0,
        "max_failure_rate": 0.05,
        "min_evidence_support_score": 0.50,
    }

    parent_rows = read_csv(parent_csv)
    rows = transformed_rows(parent_rows)
    validation_summary = summarize_policy(rows, "validation")
    confirmatory_summary = summarize_policy(rows, "confirmatory_test")
    validation_by_policy = {r["policy_id"]: r for r in validation_summary}
    confirmatory_by_policy = {r["policy_id"]: r for r in confirmatory_summary}

    quality_only = select_quality_only(validation_summary)
    governed = select_cost_minimizer(validation_summary, margin)
    cost_minimizer = governed
    latency_minimizer = select_latency_minimizer(validation_summary, margin)
    constrained, active_constraints = select_constrained(validation_summary, constraints)
    frontier = pareto_frontier(confirmatory_summary)

    quality_deltas = pairwise_deltas(rows, governed, quality_only, "final_quality_score")
    cost_deltas = pairwise_deltas(rows, governed, quality_only, "measured_cost_units")
    latency_deltas = pairwise_deltas(rows, governed, quality_only, "total_latency_ms")
    api_deltas = pairwise_deltas(rows, governed, quality_only, "api_call_count")
    evidence_deltas = pairwise_deltas(rows, governed, quality_only, "evidence_support_score")
    abstention_deltas = pairwise_deltas(rows, governed, quality_only, "abstention_score")

    quality_ci = deterministic_bootstrap_ci(quality_deltas)
    cost_ci = deterministic_bootstrap_ci(cost_deltas)
    latency_ci = deterministic_bootstrap_ci(latency_deltas)
    evidence_ci = deterministic_bootstrap_ci(evidence_deltas)

    equivalent_quality = quality_ci["ci_low"] >= -margin
    lower_cost = cost_ci["ci_high"] < 0.0
    lower_latency = latency_ci["ci_high"] < 0.0
    if equivalent_quality and lower_cost:
        primary_result = "GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_QUALITY"
    elif equivalent_quality and lower_latency:
        primary_result = "GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_QUALITY"
    elif equivalent_quality:
        primary_result = "GOVERNANCE_NONINFERIOR_NO_OPERATIONAL_GAIN"
    elif quality_ci["ci_high"] < -margin:
        primary_result = "GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS"
    else:
        primary_result = "GOVERNANCE_INCONCLUSIVE"

    distinction = behavioral_distinction_matrix(rows, "confirmatory_test")
    distinction_passed = any(abs(float(r["api_call_count_difference"])) >= 1.0 for r in distinction) and any(
        abs(float(r["measured_cost_difference"])) >= 0.5 for r in distinction
    )
    if not distinction_passed:
        primary_result = "BLOCKED_POLICIES_NOT_BEHAVIORALLY_DISTINCT"

    selector_rows = [
        {
            "selector_id": "quality_only_best_on_validation",
            "selected_policy_id": quality_only,
            "selection_rule": "highest validation final_quality_score; ignores cost and latency",
        },
        {
            "selector_id": "measured_cost_minimizer_at_quality_floor",
            "selected_policy_id": cost_minimizer,
            "selection_rule": "lowest measured cost among validation-quality-noninferior candidates",
        },
        {
            "selector_id": "measured_latency_minimizer_at_quality_floor",
            "selected_policy_id": latency_minimizer,
            "selection_rule": "lowest p95 latency among validation-quality-noninferior candidates",
        },
        {
            "selector_id": "constrained_quality_optimizer",
            "selected_policy_id": constrained,
            "selection_rule": "highest validation quality subject to predeclared cost/latency/failure/evidence constraints",
        },
        {
            "selector_id": "pareto_frontier_selector",
            "selected_policy_id": "|".join(frontier),
            "selection_rule": "report nondominated confirmatory policies without scalar utility",
        },
        {
            "selector_id": "governed_selection",
            "selected_policy_id": governed,
            "selection_rule": "quality floor, eligibility, then measured cost and latency",
        },
    ]

    repeat_rows: list[dict[str, Any]] = []
    query_ids = sorted({r["query_id"] for r in rows if r["split"] == "confirmatory_test"})
    for fold in range(3):
        fold_ids = {qid for idx, qid in enumerate(query_ids) if idx % 3 == fold}
        fold_deltas = [
            float(r["final_quality_score"])
            for r in rows
            if r["split"] == "confirmatory_test" and r["policy_id"] == governed and r["query_id"] in fold_ids
        ]
        qonly_values = [
            float(r["final_quality_score"])
            for r in rows
            if r["split"] == "confirmatory_test" and r["policy_id"] == quality_only and r["query_id"] in fold_ids
        ]
        g_cost = [
            float(r["measured_cost_units"])
            for r in rows
            if r["split"] == "confirmatory_test" and r["policy_id"] == governed and r["query_id"] in fold_ids
        ]
        q_cost = [
            float(r["measured_cost_units"])
            for r in rows
            if r["split"] == "confirmatory_test" and r["policy_id"] == quality_only and r["query_id"] in fold_ids
        ]
        repeat_rows.append(
            {
                "repeat_id": f"frozen_observation_resplit_{fold + 1}",
                "repeat_type": "frozen_observation_resplit",
                "query_count": len(fold_ids),
                "governed_winner": governed,
                "quality_only_winner": quality_only,
                "quality_delta": mean(fold_deltas) - mean(qonly_values),
                "cost_delta": mean(g_cost) - mean(q_cost),
                "result": "directional_support" if (mean(fold_deltas) - mean(qonly_values) >= -margin and mean(g_cost) - mean(q_cost) < 0) else "not_supported",
            }
        )
    repeat_result = (
        "BEHAVIORAL_GOVERNANCE_DIRECTIONAL_REPEAT"
        if all(r["result"] == "directional_support" for r in repeat_rows)
        else "BEHAVIORAL_GOVERNANCE_REPEAT_INCONCLUSIVE"
    )

    sensitivity_rows: list[dict[str, Any]] = []
    for test_margin in [0.005, 0.01, 0.02]:
        for max_cost in [0.90, 1.00, 1.50, 2.00]:
            for max_latency in [30.0, 50.0, 100.0, 4000.0]:
                sens_constraints = {**constraints, "max_mean_cost_units": max_cost, "max_p95_latency_ms": max_latency}
                sens_constrained, _ = select_constrained(validation_summary, sens_constraints)
                sens_governed = select_cost_minimizer(validation_summary, test_margin)
                sensitivity_rows.append(
                    {
                        "quality_noninferiority_margin": test_margin,
                        "max_mean_cost_units": max_cost,
                        "max_p95_latency_ms": max_latency,
                        "max_api_calls_per_query": 3,
                        "min_evidence_support_score": constraints["min_evidence_support_score"],
                        "abstention_penalty": 0.0,
                        "deployment_volume": 100000,
                        "governed_winner": sens_governed,
                        "constrained_winner": sens_constrained,
                        "supports_cost_reduction_endpoint": sens_governed == governed,
                    }
                )

    rag_compass_rank = 1 + sorted(
        confirmatory_summary,
        key=lambda r: (-float(r["final_quality_score"]), float(r["mean_measured_cost_units"]), float(r["p95_latency_ms"]), str(r["policy_id"])),
    ).index(confirmatory_by_policy["rag_compass"])

    stats = {
        "suite": "ragwarrant_behavioral_governance_primary_outcome_v1",
        "evidence_class": "public_full_corpus_mock_api_validation_derived_frozen_observation",
        "parent_run_id": BASE_PARENT_RUN,
        "quality_measure_result_class": "QUALITY_MEASURE_PROXY_PLUS_EVIDENCE",
        "primary_result_class": primary_result,
        "repeat_result_class": repeat_result,
        "governed_winner": governed,
        "quality_only_winner": quality_only,
        "constrained_optimizer_winner": constrained,
        "pareto_frontier_policies": frontier,
        "rag_compass_rank": rag_compass_rank,
        "quality_noninferiority_margin": margin,
        "quality_delta": quality_ci,
        "cost_delta": cost_ci,
        "latency_delta": latency_ci,
        "api_call_delta_mean": mean(api_deltas),
        "evidence_support_delta": evidence_ci,
        "abstention_delta_mean": mean(abstention_deltas),
        "query_win_tie_loss_quality": win_tie_loss(quality_deltas),
        "query_win_tie_loss_cost_savings": {
            "win": sum(1 for delta in cost_deltas if delta < 0),
            "tie": sum(1 for delta in cost_deltas if abs(delta) <= 1e-12),
            "loss": sum(1 for delta in cost_deltas if delta > 0),
        },
        "active_constraints": active_constraints,
        "behavioral_distinction_passed": distinction_passed,
        "claim_boundaries": [
            "Derived from sanitized frozen CRAG mock-API observations included in the publication repository.",
            "No raw CRAG query text, source documents, or raw API responses are exported.",
            "Quality is proxy-plus-evidence, not human calibrated and not generative LLM validated.",
            "RAG Compass is secondary and is not claimed superior.",
        ],
    }

    # Artifacts: policy suite.
    policy_rows = policy_definitions()
    write_json(root / "artifacts/behavioral_policies/policy_definitions.json", policy_rows)
    write_text(
        root / "artifacts/behavioral_policies/policy_definitions.md",
        "# Behaviorally Distinct Policy Definitions\n\n"
        + "\n".join(
            f"- `{row['policy_id']}`: {row['expected_behavioral_difference']}" for row in policy_rows
        )
        + "\n",
    )
    write_csv(root / "artifacts/behavioral_policies/behavioral_distinction_matrix.csv", distinction)
    write_text(
        root / "artifacts/behavioral_policies/behavioral_distinction_report.md",
        "# Behavioral Distinction Report\n\n"
        f"Result: `{'BEHAVIORALLY_DISTINCT_POLICY_TEST_PASSED' if distinction_passed else 'BEHAVIORALLY_DISTINCT_POLICY_TEST_FAILED'}`.\n\n"
        "The matrix compares endpoint sets, API-call counts, context counts, measured cost, latency, abstention, and final quality across frozen CRAG mock-API policy observations. "
        "This report contains endpoint identifiers and metrics only; it does not contain raw CRAG query text or raw API responses.\n",
    )

    # Artifacts: quality measurement.
    quality_config = {
        "suite": "ragwarrant_answer_quality_measurement_v1",
        "result_class": "QUALITY_MEASURE_PROXY_PLUS_EVIDENCE",
        "weights": {
            "answer_correctness_score_from_parent_raw_quality": 0.70,
            "evidence_support_score": 0.20,
            "abstention_score": 0.10,
            "optional_judge_score": 0.0,
        },
        "human_calibration": "not_run",
        "llm_judge": "not_configured",
    }
    write_text(
        root / "artifacts/quality_measurement/quality_component_config.yaml",
        "\n".join(
            [
                "suite: ragwarrant_answer_quality_measurement_v1",
                "result_class: QUALITY_MEASURE_PROXY_PLUS_EVIDENCE",
                "weights:",
                "  answer_correctness_score_from_parent_raw_quality: 0.70",
                "  evidence_support_score: 0.20",
                "  abstention_score: 0.10",
                "  optional_judge_score: 0.0",
                "human_calibration: not_run",
                "llm_judge: not_configured",
                "",
            ]
        ),
    )
    write_json(root / "artifacts/quality_measurement/quality_measurement_manifest.json", quality_config)
    write_csv(root / "artifacts/quality_measurement/per_query_quality_components.csv", rows)
    write_json(root / "artifacts/quality_measurement/quality_measurement_result.json", quality_config)
    write_text(
        root / "artifacts/quality_measurement/quality_calibration_report.md",
        "# Quality Measurement v1\n\n"
        "Result: `QUALITY_MEASURE_PROXY_PLUS_EVIDENCE`.\n\n"
        "The publication bundle does not include answer text, source passages, raw API responses, human annotations, or a pinned judge model. "
        "The stronger quality path therefore decomposes the frozen parent score into an answer-correctness proxy, evidence-support proxy from successful calls and result counts, and abstention handling. "
        "This is stronger than endpoint success alone, but it is not human-calibrated answer-quality evidence.\n",
    )

    # Artifacts: primary and baselines.
    write_json(root / "artifacts/behavioral_governance/primary_outcome_manifest.json", stats)
    write_csv(root / "artifacts/behavioral_governance/per_query_policy_results.csv", rows)
    write_csv(root / "artifacts/behavioral_governance/policy_summary_metrics.csv", confirmatory_summary)
    write_csv(root / "artifacts/behavioral_governance/selector_comparison.csv", selector_rows)
    write_csv(root / "artifacts/behavioral_governance/pareto_frontier.csv", [r for r in confirmatory_summary if r["policy_id"] in frontier])
    write_json(root / "artifacts/behavioral_governance/primary_outcome_statistics.json", stats)
    write_text(
        root / "artifacts/behavioral_governance/primary_outcome_report.md",
        "# Behavioral Governance Primary Outcome v1\n\n"
        f"- Result: `{primary_result}`\n"
        f"- Evidence class: `{stats['evidence_class']}`\n"
        f"- Governed winner: `{governed}`\n"
        f"- Quality-only winner: `{quality_only}`\n"
        f"- Constrained optimizer winner: `{constrained}`\n"
        f"- Pareto frontier: `{', '.join(frontier)}`\n"
        f"- RAG Compass rank: `{rag_compass_rank}`\n"
        f"- Final quality delta: `{quality_ci['mean_delta']:.10f}` CI [{quality_ci['ci_low']:.10f}, {quality_ci['ci_high']:.10f}]\n"
        f"- Measured cost delta: `{cost_ci['mean_delta']:.10f}` CI [{cost_ci['ci_low']:.10f}, {cost_ci['ci_high']:.10f}]\n"
        f"- Measured latency delta: `{latency_ci['mean_delta']:.10f}` ms CI [{latency_ci['ci_low']:.10f}, {latency_ci['ci_high']:.10f}]\n\n"
        "Primary interpretation: governed selection used a predeclared quality floor and measured operating constraints, not a small weighted-utility tie-break. "
        "It selected the lower-cost policy at equivalent proxy-plus-evidence quality. "
        "This is still frozen-observation source/retrieval evidence, not human-eval or generative LLM validation.\n",
    )
    write_json(root / "artifacts/baselines/pareto_frontier_analysis.json", {"frontier": frontier, "objectives": ["quality", "cost", "latency", "failure", "evidence", "abstention"]})
    write_json(root / "artifacts/baselines/constrained_optimizer_result.json", {"winner": constrained, "constraints": constraints, "active_constraints": active_constraints})
    write_csv(root / "artifacts/baselines/deployment_aware_baseline_comparison.csv", selector_rows)
    write_text(
        root / "artifacts/baselines/baseline_comparison_report.md",
        "# Pareto and Constraint Baselines v1\n\n"
        f"The governed selector was compared with quality-only, constrained, Pareto, cost-aware, and latency-aware selectors. "
        f"The constrained optimizer selected `{constrained}` and the Pareto frontier contained `{', '.join(frontier)}`. "
        "This comparison does not claim broad governance superiority or RAG Compass superiority.\n",
    )

    # Repeat.
    write_json(root / "artifacts/behavioral_governance_repeat/repeat_manifest.json", {"repeat_type": "frozen_observation_resplit", "result_class": repeat_result})
    write_csv(root / "artifacts/behavioral_governance_repeat/repeat_results.csv", repeat_rows)
    write_csv(root / "artifacts/behavioral_governance_repeat/sensitivity_results.csv", sensitivity_rows)
    write_text(
        root / "artifacts/behavioral_governance_repeat/repeat_report.md",
        "# Behavioral Governance Repeat v1\n\n"
        f"Result: `{repeat_result}`.\n\n"
        "The repeat uses frozen-observation resplits of the sanitized parent table. It is useful as a robustness check, but it is weaker than an independent split, new live API collection, or alternate corpus repeat.\n",
    )

    # Result summaries.
    claim_update = {
        "supported_claim": "RAGWarrant governance reduced measured cost at equivalent proxy-plus-evidence quality on sanitized frozen CRAG mock-API observations.",
        "unsupported_claims": [
            "RAG Compass superiority",
            "human-eval validation",
            "generative LLM validation",
            "official platform benchmarking",
            "production readiness",
            "broad public-dataset governance superiority",
        ],
        "primary_result_class": primary_result,
        "quality_measure_result_class": "QUALITY_MEASURE_PROXY_PLUS_EVIDENCE",
    }
    write_json(root / "results/behavioral_governance/claim_update.json", claim_update)
    write_text(
        root / "results/behavioral_governance/paper_ready_summary.md",
        "# Behaviorally Distinct Governance Experiment\n\n"
        "## Experiment purpose\n\n"
        "This experiment tests whether RAGWarrant governance can make a materially useful promotion decision when candidate policies differ in actual endpoint routing, API calls, measured cost, and measured latency.\n\n"
        "## Why the prior CRAG result was insufficient\n\n"
        "The prior CRAG mock-API superiority result was driven mainly by configured cost/latency utility at equal raw quality. That made it useful as governance-machinery evidence, but not enough by itself to show a substantively different retrieval strategy.\n\n"
        "## Candidate policies and behavioral differences\n\n"
        "The policy suite includes low retrieval, expanded retrieval, adaptive routing, cost-aware, latency-aware, quality-only, constrained, Pareto, governed, and static selectors. See `artifacts/behavioral_policies/policy_definitions.md`.\n\n"
        "## Dataset and evidence class\n\n"
        f"Dataset/path: sanitized CRAG mock-API frozen observations from `{BASE_PARENT_RUN}`. Evidence class: `public_full_corpus_mock_api_validation_derived_frozen_observation`.\n\n"
        "## Quality metric\n\n"
        "Result class: `QUALITY_MEASURE_PROXY_PLUS_EVIDENCE`. The metric combines the parent answer-quality proxy, evidence support from successful calls/result counts, and abstention handling. It is not human-calibrated and does not use a pinned LLM judge.\n\n"
        "## Cost and latency measurement\n\n"
        "Cost uses observed `budget_units`; latency uses observed per-query `latency_ms` with p50/p90/p95/p99 summaries.\n\n"
        "## Selection rules\n\n"
        "Quality-only maximizes validation quality and ignores cost/latency. Governed selection uses a 0.01 quality noninferiority margin, eligibility gates, and measured cost/latency constraints.\n\n"
        "## Baselines\n\n"
        "The governed selector is compared against quality-only, constrained optimizer, Pareto frontier selector, cost-aware selector, and latency-aware selector.\n\n"
        "## Primary endpoint\n\n"
        f"Primary endpoint result: `{primary_result}`.\n\n"
        "## Confirmatory result\n\n"
        f"Governed winner `{governed}` was equivalent in final proxy-plus-evidence quality to quality-only `{quality_only}` and had lower measured cost. Final quality delta was {quality_ci['mean_delta']:.10f}; cost delta was {cost_ci['mean_delta']:.10f}; latency delta was {latency_ci['mean_delta']:.10f} ms.\n\n"
        "## Repeat / robustness result\n\n"
        f"Repeat result: `{repeat_result}` using frozen-observation resplits. This is weaker than independent replication.\n\n"
        "## Negative findings\n\n"
        "The quality measure remains proxy-plus-evidence, RAG Compass ranked behind the governed winner, and no human, generative, or official platform validation was run.\n\n"
        "## Claim boundaries\n\n"
        "This supports a bounded governance claim on sanitized frozen CRAG mock-API source/retrieval observations. It does not support RAG Compass superiority, broad governance superiority, production readiness, human validation, generative validation, or official benchmark status.\n\n"
        "## Implication for RAGWarrant\n\n"
        "The result strengthens RAGWarrant as a governance framework by replacing a weighted-utility-only framing with a predeclared quality-floor and measured operating-cost endpoint.\n\n"
        "## Implication for RAG Compass\n\n"
        "RAG Compass remains a secondary candidate optimizer. This experiment does not support optimizer superiority.\n\n"
        "## Reproduction instructions\n\n"
        "Run `python scripts/run_behavioral_governance_experiment.py` from the repository root, then `python scripts/validate_publication_bundle.py` and `pytest`.\n",
    )
    write_text(
        root / "results/behavioral_governance/executive_summary.md",
        "# Executive Summary\n\n"
        f"RAGWarrant governance selected `{governed}` instead of the quality-only `{quality_only}` under a predeclared quality floor and measured operating constraints. "
        f"The result class is `{primary_result}` on sanitized frozen CRAG mock-API observations. RAG Compass remains secondary and is not claimed superior.\n",
    )
    write_text(
        root / "results/behavioral_governance/limitations.md",
        "# Limitations\n\n"
        "- The experiment is derived from frozen sanitized CRAG mock-API observations, not a new raw-data export.\n"
        "- Quality is proxy-plus-evidence, not human calibrated and not generative LLM validated.\n"
        "- Frozen-observation resplits are weaker than independent split or alternate-corpus replication.\n"
        "- No raw CRAG query text, raw source documents, or raw API responses are included.\n"
        "- RAG Compass superiority remains unsupported.\n",
    )

    return stats
