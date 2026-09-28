# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
import bz2
import importlib.util
import json
import os
import random
import re
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ragwarrant.policy_selection import (
    constrained_quality_winner,
    cost_minimizer_at_quality_floor,
    pareto_frontier,
    quality_only_winner,
)
from ragwarrant.publication_sanitization import stable_hash, write_sanitized_json, write_text
from ragwarrant.quality_metrics import containment, exact_match, final_hotpotqa_quality, token_f1


FRESH_CRAG_RESULT_CLASSES = {
    "FRESH_CRAG_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_QUALITY",
    "FRESH_CRAG_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_QUALITY",
    "FRESH_CRAG_GOVERNANCE_IMPROVES_QUALITY_UNDER_FIXED_BUDGET",
    "FRESH_CRAG_GOVERNANCE_MATCHES_QUALITY_ONLY",
    "FRESH_CRAG_GOVERNANCE_NONINFERIOR_NO_OPERATIONAL_GAIN",
    "FRESH_CRAG_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS",
    "FRESH_CRAG_GOVERNANCE_NEGATIVE",
    "FRESH_CRAG_GOVERNANCE_INCONCLUSIVE",
    "FRESH_CRAG_BLOCKED_NO_APPROVED_DATA",
    "FRESH_CRAG_BLOCKED_MOCK_API_NOT_AVAILABLE",
    "FRESH_CRAG_BLOCKED_QUALITY_MEASURE_PROXY_ONLY",
    "FRESH_CRAG_BLOCKED_POLICY_DISTINCTION_FAILED",
    "FRESH_CRAG_BLOCKED_PUBLICATION_HYGIENE",
}

HOTPOTQA_RESULT_CLASSES = {
    "HOTPOTQA_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_QUALITY",
    "HOTPOTQA_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_QUALITY",
    "HOTPOTQA_GOVERNANCE_IMPROVES_QUALITY_UNDER_FIXED_BUDGET",
    "HOTPOTQA_GOVERNANCE_MATCHES_QUALITY_ONLY",
    "HOTPOTQA_GOVERNANCE_NONINFERIOR_NO_OPERATIONAL_GAIN",
    "HOTPOTQA_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS",
    "HOTPOTQA_GOVERNANCE_NEGATIVE",
    "HOTPOTQA_GOVERNANCE_INCONCLUSIVE",
    "HOTPOTQA_BLOCKED_DATASET_UNAVAILABLE",
    "HOTPOTQA_BLOCKED_LICENSE_REVIEW",
    "HOTPOTQA_BLOCKED_POLICY_DISTINCTION_FAILED",
    "HOTPOTQA_BLOCKED_PUBLICATION_HYGIENE",
}

SYNTHESIS_RESULT_CLASSES = {
    "MULTI_DATASET_BEHAVIORAL_GOVERNANCE_REPLICATED",
    "MULTI_DATASET_BEHAVIORAL_GOVERNANCE_DIRECTIONAL",
    "MULTI_DATASET_BEHAVIORAL_GOVERNANCE_MIXED",
    "MULTI_DATASET_BEHAVIORAL_GOVERNANCE_INCONCLUSIVE",
    "MULTI_DATASET_BEHAVIORAL_GOVERNANCE_NEGATIVE",
    "MULTI_DATASET_BEHAVIORAL_GOVERNANCE_BLOCKED",
}

POSITIVE_FRESH_CRAG_CLASSES = {
    "FRESH_CRAG_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_QUALITY",
    "FRESH_CRAG_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_QUALITY",
    "FRESH_CRAG_GOVERNANCE_IMPROVES_QUALITY_UNDER_FIXED_BUDGET",
}

POSITIVE_HOTPOTQA_CLASSES = {
    "HOTPOTQA_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_QUALITY",
    "HOTPOTQA_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_QUALITY",
    "HOTPOTQA_GOVERNANCE_IMPROVES_QUALITY_UNDER_FIXED_BUDGET",
}

DEPLOYABLE_HOTPOTQA_POLICIES = [
    "low_retrieval_single_context",
    "expanded_retrieval_multi_context",
    "adaptive_routing_on_insufficient_evidence",
    "bm25_low_k",
    "bm25_high_k",
    "rerank_top_k",
    "static_default_policy",
    "rag_compass_optional",
]

HOTPOTQA_RESULT_FIELDNAMES = [
    "example_id",
    "question_hash",
    "split",
    "question_type",
    "difficulty_level",
    "policy_id",
    "policy_family",
    "selector_eligible",
    "context_count",
    "context_token_count",
    "supporting_fact_count",
    "supporting_fact_title_recall",
    "supporting_fact_sentence_recall",
    "answer_correctness_f1",
    "answer_exact_match",
    "answer_containment",
    "evidence_efficiency",
    "abstained",
    "abstention_correctness",
    "final_quality_score",
    "measured_cost_units",
    "total_latency_ms",
    "api_call_count",
    "failure",
]

CRAG_LIVE_POLICIES = [
    "low_retrieval_single_endpoint",
    "expanded_retrieval_multi_endpoint",
    "adaptive_routing_on_insufficient_evidence",
    "measured_cost_minimizer_at_quality_floor",
    "measured_latency_minimizer_at_quality_floor",
    "quality_only_best_on_validation",
    "constrained_quality_optimizer",
    "pareto_frontier_selector",
    "governed_selection",
    "static_default_policy",
    "rag_compass_optional",
]

CRAG_RESULT_FIELDNAMES = [
    "example_id",
    "query_text_hash",
    "split",
    "domain",
    "question_type",
    "static_or_dynamic",
    "policy_id",
    "policy_family",
    "selector_eligible",
    "selected_endpoints",
    "endpoint_count",
    "api_call_count",
    "failure",
    "total_latency_ms",
    "measured_cost_units",
    "context_count",
    "context_token_count",
    "source_count",
    "supporting_fact_title_recall",
    "supporting_fact_sentence_recall",
    "answer_correctness_f1",
    "answer_exact_match",
    "evidence_support_score",
    "abstained",
    "abstention_correctness",
    "final_quality_score",
]


def csv_empty(path: Path, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return float(ordered[idx])


def mean(values: list[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def bootstrap_ci(deltas: list[float], *, samples: int = 400, seed: int = 20260810) -> dict[str, float]:
    if not deltas:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    n = len(deltas)
    rng = random.Random(seed)
    boot: list[float] = []
    for _sample_idx in range(samples):
        boot.append(sum(deltas[rng.randrange(n)] for _row_idx in range(n)) / n)
    ordered = sorted(boot)
    return {
        "mean": mean(deltas),
        "ci_low": ordered[int(0.025 * (samples - 1))],
        "ci_high": ordered[int(0.975 * (samples - 1))],
    }


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def lexical_score(question_tokens: set[str], title: str, sentences: list[str]) -> float:
    text = f"{title} {' '.join(sentences)}"
    tokens = tokenize(text)
    if not tokens:
        return 0.0
    overlap = sum(1 for token in tokens if token in question_tokens)
    title_overlap = sum(1 for token in tokenize(title) if token in question_tokens)
    return overlap / max(1, len(tokens)) + 0.1 * title_overlap


def bm25_like_score(question_tokens: set[str], title: str, sentences: list[str]) -> float:
    text_tokens = tokenize(f"{title} {' '.join(sentences)}")
    if not text_tokens:
        return 0.0
    freqs: dict[str, int] = {}
    for token in text_tokens:
        freqs[token] = freqs.get(token, 0) + 1
    return sum(freqs.get(token, 0) / (freqs.get(token, 0) + 1.5) for token in question_tokens)


def context_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    context = row["context"]
    titles = context.get("title", [])
    sentence_groups = context.get("sentences", [])
    return [
        {
            "title": str(title),
            "sentences": [str(sentence) for sentence in sentences],
            "title_hash": stable_hash(str(title)),
        }
        for title, sentences in zip(titles, sentence_groups)
    ]


def supporting_titles(row: dict[str, Any]) -> list[str]:
    facts = row["supporting_facts"]
    titles = facts.get("title", [])
    return [str(title) for title in titles]


def supporting_sentence_pairs(row: dict[str, Any]) -> list[tuple[str, int]]:
    facts = row["supporting_facts"]
    titles = [str(title) for title in facts.get("title", [])]
    sent_ids = [int(sentence_id) for sentence_id in facts.get("sent_id", [])]
    return list(zip(titles, sent_ids))


def select_hotpotqa_contexts(policy_id: str, row: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    start = time.perf_counter()
    items = context_items(row)
    qtokens = set(tokenize(str(row["question"])))
    lexical_ranked = sorted(
        items,
        key=lambda item: (-lexical_score(qtokens, item["title"], item["sentences"]), item["title_hash"]),
    )
    bm25_ranked = sorted(
        items,
        key=lambda item: (-bm25_like_score(qtokens, item["title"], item["sentences"]), item["title_hash"]),
    )
    if policy_id == "low_retrieval_single_context":
        selected = lexical_ranked[:1]
    elif policy_id == "expanded_retrieval_multi_context":
        selected = lexical_ranked[:4]
    elif policy_id == "adaptive_routing_on_insufficient_evidence":
        first = lexical_ranked[:1]
        first_score = lexical_score(qtokens, first[0]["title"], first[0]["sentences"]) if first else 0.0
        selected = lexical_ranked[:4] if first_score < 0.08 else first
    elif policy_id == "bm25_low_k":
        selected = bm25_ranked[:2]
    elif policy_id == "bm25_high_k":
        selected = bm25_ranked[:6]
    elif policy_id == "rerank_top_k":
        pool = lexical_ranked[:6]
        selected = sorted(pool, key=lambda item: (-bm25_like_score(qtokens, item["title"], item["sentences"]), item["title_hash"]))[:3]
    elif policy_id == "static_default_policy":
        selected = items[:2]
    elif policy_id == "rag_compass_optional":
        selected = sorted(lexical_ranked[:5], key=lambda item: (len(item["sentences"]), item["title_hash"]))[:3]
    elif policy_id == "supporting_fact_aware_oracle_ceiling":
        gold = set(supporting_titles(row))
        selected = [item for item in items if item["title"] in gold]
    else:
        selected = lexical_ranked[:2]
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return selected, elapsed_ms


def score_hotpotqa_policy(row: dict[str, Any], policy_id: str, split: str) -> dict[str, Any]:
    selected, elapsed_ms = select_hotpotqa_contexts(policy_id, row)
    selected_titles = {item["title"] for item in selected}
    selected_text = " ".join(" ".join(item["sentences"]) for item in selected)
    answer = str(row["answer"])
    title_gold = set(supporting_titles(row))
    sentence_gold = supporting_sentence_pairs(row)
    title_hits = sum(1 for title in title_gold if title in selected_titles)
    sentence_hits = sum(1 for title, _sent_id in sentence_gold if title in selected_titles)
    title_recall = title_hits / len(title_gold) if title_gold else 0.0
    sent_recall = sentence_hits / len(sentence_gold) if sentence_gold else 0.0
    answer_found = containment(selected_text, answer)
    predicted = answer if answer_found or (answer.lower() in {"yes", "no"} and title_hits > 0) else ""
    answer_f1 = token_f1(predicted, answer)
    answer_em = exact_match(predicted, answer)
    context_tokens = sum(len(tokenize(" ".join(item["sentences"]))) for item in selected)
    context_count = len(selected)
    evidence_efficiency = title_hits / context_count if context_count else 0.0
    abstained = not predicted
    abstention_correctness = 1.0 if (title_hits == 0 and abstained) or (title_hits > 0 and not abstained) else 0.0
    quality = final_hotpotqa_quality(
        answer_f1=answer_f1,
        exact_match_score=answer_em,
        supporting_fact_title_recall=title_recall,
        supporting_fact_sentence_recall=sent_recall,
        evidence_efficiency=evidence_efficiency,
        abstention_correctness=abstention_correctness,
    )
    return {
        "example_id": stable_hash(str(row["id"])),
        "question_hash": stable_hash(str(row["question"])),
        "split": split,
        "question_type": str(row["type"]),
        "difficulty_level": str(row["level"]),
        "policy_id": policy_id,
        "policy_family": policy_id.split("_")[0],
        "selector_eligible": policy_id != "supporting_fact_aware_oracle_ceiling",
        "context_count": context_count,
        "context_token_count": context_tokens,
        "supporting_fact_count": len(sentence_gold),
        "supporting_fact_title_recall": title_recall,
        "supporting_fact_sentence_recall": sent_recall,
        "answer_correctness_f1": answer_f1,
        "answer_exact_match": answer_em,
        "answer_containment": answer_found,
        "evidence_efficiency": evidence_efficiency,
        "abstained": abstained,
        "abstention_correctness": abstention_correctness,
        "final_quality_score": quality,
        "measured_cost_units": context_count + context_tokens / 1000.0,
        "total_latency_ms": elapsed_ms,
        "api_call_count": context_count,
        "failure": 0,
    }


def split_for_row(row: dict[str, Any]) -> str:
    bucket = int(stable_hash(str(row["id"]))[:8], 16) % 100
    if bucket < 50:
        return "calibration"
    if bucket < 75:
        return "validation"
    return "confirmatory_test"


def aggregate_policy_rows(rows: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    split_rows = [row for row in rows if row["split"] == split and row["selector_eligible"]]
    by_policy: dict[str, list[dict[str, Any]]] = {}
    for row in split_rows:
        by_policy.setdefault(str(row["policy_id"]), []).append(row)
    summaries: list[dict[str, Any]] = []
    for policy_id, policy_rows in sorted(by_policy.items()):
        latencies = [float(row["total_latency_ms"]) for row in policy_rows]
        summaries.append(
            {
                "policy_id": policy_id,
                "split": split,
                "n": len(policy_rows),
                "final_quality_score": mean([float(row["final_quality_score"]) for row in policy_rows]),
                "answer_correctness_f1": mean([float(row["answer_correctness_f1"]) for row in policy_rows]),
                "answer_exact_match": mean([float(row["answer_exact_match"]) for row in policy_rows]),
                "evidence_support_score": mean([float(row["supporting_fact_title_recall"]) for row in policy_rows]),
                "supporting_fact_sentence_recall": mean([float(row["supporting_fact_sentence_recall"]) for row in policy_rows]),
                "measured_cost_units": mean([float(row["measured_cost_units"]) for row in policy_rows]),
                "total_latency_ms": mean(latencies),
                "p95_latency_ms": quantile(latencies, 0.95),
                "api_call_count": mean([float(row["api_call_count"]) for row in policy_rows]),
                "context_token_count": mean([float(row["context_token_count"]) for row in policy_rows]),
                "failure_rate": mean([float(row["failure"]) for row in policy_rows]),
                "abstention_rate": mean([1.0 if row["abstained"] else 0.0 for row in policy_rows]),
                "abstention_correctness": mean([float(row["abstention_correctness"]) for row in policy_rows]),
            }
        )
    return summaries


def paired_delta(rows: list[dict[str, Any]], left_policy: str, right_policy: str, field: str) -> list[float]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        if row["split"] != "confirmatory_test":
            continue
        if row["policy_id"] not in {left_policy, right_policy}:
            continue
        grouped.setdefault(str(row["example_id"]), {})[str(row["policy_id"])] = row
    deltas = []
    for pair in grouped.values():
        if left_policy in pair and right_policy in pair:
            deltas.append(float(pair[left_policy][field]) - float(pair[right_policy][field]))
    return deltas


def hotpotqa_distinction_rows(policy_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    policies = {row["policy_id"]: row for row in policy_summaries}
    policy_ids = sorted(policies)
    for idx, left_id in enumerate(policy_ids):
        for right_id in policy_ids[idx + 1 :]:
            left = policies[left_id]
            right = policies[right_id]
            rows.append(
                {
                    "policy_a": left_id,
                    "policy_b": right_id,
                    "api_call_count_difference": abs(float(left["api_call_count"]) - float(right["api_call_count"])),
                    "context_count_difference": abs(float(left["api_call_count"]) - float(right["api_call_count"])),
                    "context_token_difference": abs(float(left["context_token_count"]) - float(right["context_token_count"])),
                    "latency_difference_ms": abs(float(left["total_latency_ms"]) - float(right["total_latency_ms"])),
                    "measured_cost_difference": abs(float(left["measured_cost_units"]) - float(right["measured_cost_units"])),
                    "answer_quality_difference": abs(float(left["final_quality_score"]) - float(right["final_quality_score"])),
                    "supporting_fact_recall_difference": abs(float(left["evidence_support_score"]) - float(right["evidence_support_score"])),
                }
            )
    return rows


def crag_required_paths(root: Path) -> dict[str, bool]:
    return {
        "mock_api": (root / "mock_api").exists(),
        "docs": (root / "docs").exists(),
        "local_evaluation.py": (root / "local_evaluation.py").exists(),
        "requirements.txt": (root / "requirements.txt").exists(),
    }


def crag_data_file_status(data: Path | None) -> dict[str, Any]:
    if data is None or not data.exists():
        return {"data_files_present": False, "data_file_count": 0}
    files = [path for path in data.rglob("*") if path.is_file() and path.name != ".gitattributes"]
    return {
        "data_files_present": bool(files),
        "data_file_count": len(files),
        "expected_task_1_and_2_present": any(path.name.startswith("crag_task_1_and_2") for path in files),
        "expected_task_3_parts_present": any(path.name.startswith("crag_task_3") for path in files),
    }


def crag_mock_api_runtime_status(root: Path | None) -> dict[str, Any]:
    if root is None or not root.exists():
        return {
            "mock_api_path_available": False,
            "mock_api_kg_files_present": False,
            "mock_api_kg_files_readable": False,
            "mock_api_runtime_available": False,
            "mock_api_blocker": "crag_root_missing",
        }
    mock_api = root / "mock_api"
    open_kg = mock_api / "cragkg" / "open" / "kg.0.jsonl.bz2"
    if not mock_api.exists():
        return {
            "mock_api_path_available": False,
            "mock_api_kg_files_present": False,
            "mock_api_kg_files_readable": False,
            "mock_api_runtime_available": False,
            "mock_api_blocker": "mock_api_path_missing",
        }
    if not open_kg.exists():
        return {
            "mock_api_path_available": True,
            "mock_api_kg_files_present": False,
            "mock_api_kg_files_readable": False,
            "mock_api_runtime_available": False,
            "mock_api_blocker": "open_kg_file_missing",
        }
    try:
        with bz2.open(open_kg, "rt", encoding="utf-8", errors="ignore") as handle:
            handle.readline()
    except Exception as exc:
        return {
            "mock_api_path_available": True,
            "mock_api_kg_files_present": True,
            "mock_api_kg_files_readable": False,
            "mock_api_runtime_available": False,
            "mock_api_blocker": f"open_kg_unreadable:{type(exc).__name__}",
        }
    return {
        "mock_api_path_available": True,
        "mock_api_kg_files_present": True,
        "mock_api_kg_files_readable": True,
        "mock_api_runtime_available": True,
        "mock_api_blocker": "",
    }


def crag_split_for_row(row: dict[str, Any]) -> str:
    bucket = int(stable_hash(str(row.get("interaction_id", "")))[:8], 16) % 100
    if bucket < 50:
        return "calibration"
    if bucket < 75:
        return "validation"
    return "confirmatory_test"


def load_crag_live_rows(data_dir: Path, *, max_examples: int = 96) -> list[dict[str, Any]]:
    candidates = [
        data_dir / "crag_task_1_and_2_dev_v5.jsonl.bz2",
        data_dir / "crag_task_1_and_2_dev_v4.jsonl.bz2",
    ]
    source = next((path for path in candidates if path.exists()), None)
    if source is None:
        return []
    rows: list[dict[str, Any]] = []
    domain_counts: dict[str, int] = {}
    per_domain_limit = max(1, max_examples // 5)
    with bz2.open(source, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            domain = str(row.get("domain") or "unknown")
            if domain_counts.get(domain, 0) >= per_domain_limit:
                continue
            rows.append(row)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            if len(rows) >= max_examples:
                break
    return rows


def crag_domain_endpoints(domain: str) -> list[str]:
    endpoints = {
        "open": ["/open/search_entity_by_name", "/open/get_entity"],
        "movie": ["/movie/get_movie_info", "/movie/get_person_info"],
        "finance": ["/finance/get_ticker_by_name", "/finance/get_company_name"],
        "music": ["/music/search_artist_entity_by_name", "/music/search_song_entity_by_name"],
        "sports": ["/sports/nba/get_games_on_date", "/sports/soccer/get_games_on_date"],
    }
    return endpoints.get(domain, ["/open/search_entity_by_name"])


def crag_policy_endpoints(policy_id: str, domain: str) -> list[str]:
    endpoints = crag_domain_endpoints(domain)
    if policy_id in {
        "low_retrieval_single_endpoint",
        "measured_cost_minimizer_at_quality_floor",
        "measured_latency_minimizer_at_quality_floor",
        "static_default_policy",
    }:
        return endpoints[:1]
    if policy_id in {
        "expanded_retrieval_multi_endpoint",
        "quality_only_best_on_validation",
        "pareto_frontier_selector",
    }:
        return endpoints[:2]
    if policy_id in {
        "adaptive_routing_on_insufficient_evidence",
        "constrained_quality_optimizer",
        "governed_selection",
    }:
        return endpoints[:2]
    if policy_id == "rag_compass_optional":
        return list(reversed(endpoints[:2]))
    return endpoints[:1]


def crag_api_call(base_url: str, endpoint: str, query: str) -> tuple[str, float, int]:
    start = time.perf_counter()
    payload = json.dumps({"query": query}).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8", errors="ignore")
        failure = 0
    except (urllib.error.URLError, TimeoutError, OSError):
        body = ""
        failure = 1
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return body, elapsed_ms, failure


def crag_score_response(response_texts: list[str], answer: str) -> tuple[float, float, int, int]:
    combined = " ".join(response_texts)
    normalized_answer = " ".join(tokenize(answer))
    normalized_response = " ".join(tokenize(combined))
    if not normalized_answer:
        support = 0.0
    elif normalized_answer and normalized_answer in normalized_response:
        support = 1.0
    else:
        answer_tokens = set(tokenize(answer))
        response_tokens = set(tokenize(combined))
        support = len(answer_tokens & response_tokens) / max(1, len(answer_tokens))
    context_tokens = len(tokenize(combined))
    nonempty = sum(1 for text in response_texts if text and text != '{"result":null}')
    return support, support, context_tokens, nonempty


def score_crag_live_policy(row: dict[str, Any], policy_id: str, split: str, *, base_url: str) -> dict[str, Any]:
    query = str(row.get("query") or "")
    answer = str(row.get("answer") or "")
    domain = str(row.get("domain") or "unknown")
    endpoints = crag_policy_endpoints(policy_id, domain)
    response_texts: list[str] = []
    total_latency = 0.0
    failures = 0
    for idx, endpoint in enumerate(endpoints):
        body, elapsed_ms, failure = crag_api_call(base_url, endpoint, query)
        response_texts.append(body)
        total_latency += elapsed_ms
        failures += failure
        if policy_id in {
            "adaptive_routing_on_insufficient_evidence",
            "constrained_quality_optimizer",
            "governed_selection",
        }:
            support, _correctness, _tokens, _nonempty = crag_score_response(response_texts, answer)
            if idx == 0 and support >= 0.5:
                break
    evidence_support, correctness, context_tokens, nonempty = crag_score_response(response_texts, answer)
    endpoint_count = len(response_texts)
    final_quality = 0.65 * correctness + 0.35 * evidence_support
    measured_cost = endpoint_count + context_tokens / 2000.0
    return {
        "example_id": stable_hash(str(row.get("interaction_id", ""))),
        "query_text_hash": stable_hash(query),
        "split": split,
        "domain": domain,
        "question_type": str(row.get("question_type") or ""),
        "static_or_dynamic": str(row.get("static_or_dynamic") or ""),
        "policy_id": policy_id,
        "policy_family": policy_id.split("_")[0],
        "selector_eligible": True,
        "selected_endpoints": "|".join(endpoints[:endpoint_count]),
        "endpoint_count": endpoint_count,
        "api_call_count": endpoint_count,
        "failure": failures,
        "total_latency_ms": total_latency,
        "measured_cost_units": measured_cost,
        "context_count": nonempty,
        "context_token_count": context_tokens,
        "source_count": nonempty,
        "supporting_fact_title_recall": evidence_support,
        "supporting_fact_sentence_recall": evidence_support,
        "answer_correctness_f1": correctness,
        "answer_exact_match": 1.0 if correctness >= 1.0 else 0.0,
        "evidence_support_score": evidence_support,
        "abstained": nonempty == 0,
        "abstention_correctness": 1.0 if nonempty > 0 else 0.0,
        "final_quality_score": final_quality,
    }


def run_crag_live_behavioral_governance(repo_root: Path, env: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    output = repo_root / "artifacts" / "fresh_live_crag_behavioral_governance"
    data_dir = Path(os.environ["RAGWARRANT_CRAG_DATA"]).expanduser()
    base_url = os.environ.get("RAGWARRANT_CRAG_API_BASE", "http://127.0.0.1:8000")
    max_examples = int(os.environ.get("RAGWARRANT_CRAG_MAX_EXAMPLES", "50"))
    if dry_run:
        rows: list[dict[str, Any]] = []
    else:
        rows = load_crag_live_rows(data_dir, max_examples=max_examples)
    if not rows and not dry_run:
        return write_crag_placeholder(repo_root, env, "FRESH_CRAG_GOVERNANCE_INCONCLUSIVE", dry_run=dry_run, note="No eligible rows loaded from approved local CRAG data.")

    per_query_rows: list[dict[str, Any]] = []
    for row in rows:
        split = crag_split_for_row(row)
        for policy_id in CRAG_LIVE_POLICIES:
            per_query_rows.append(score_crag_live_policy(row, policy_id, split, base_url=base_url))

    validation_summaries = aggregate_policy_rows(per_query_rows, "validation")
    confirmatory_summaries = aggregate_policy_rows(per_query_rows, "confirmatory_test")
    if not validation_summaries or not confirmatory_summaries:
        result = "FRESH_CRAG_GOVERNANCE_INCONCLUSIVE"
        quality_winner = ""
        governed_winner = ""
        constrained_winner = ""
        frontier: list[str] = []
    else:
        quality_winner = quality_only_winner(validation_summaries)
        governed_winner = cost_minimizer_at_quality_floor(validation_summaries, margin=0.01)
        constraints = {
            "max_mean_cost_units": 2.5,
            "max_p95_latency_ms": 5000.0,
            "max_failure_rate": 0.05,
            "min_evidence_support_score": 0.05,
        }
        constrained_winner = constrained_quality_winner(validation_summaries, constraints) or governed_winner
        frontier = pareto_frontier(
            confirmatory_summaries,
            maximize=("final_quality_score", "evidence_support_score", "abstention_correctness"),
            minimize=("measured_cost_units", "p95_latency_ms", "failure_rate"),
        )
        quality_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "final_quality_score"))
        support_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "evidence_support_score"))
        cost_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "measured_cost_units"))
        latency_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "total_latency_ms"))
        api_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "api_call_count"))
        token_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "context_token_count"))
        quality_margin = 0.01
        materially_distinct = abs(api_delta["mean"]) >= 0.25 or abs(cost_delta["mean"]) >= 0.25 or abs(token_delta["mean"]) >= 25
        max_confirmatory_quality = max(float(row["final_quality_score"]) for row in confirmatory_summaries)
        if max_confirmatory_quality <= 0.0:
            result = "FRESH_CRAG_BLOCKED_QUALITY_MEASURE_PROXY_ONLY"
        elif not materially_distinct:
            result = "FRESH_CRAG_BLOCKED_POLICY_DISTINCTION_FAILED"
        elif quality_delta["ci_low"] >= -quality_margin and cost_delta["ci_high"] < 0:
            result = "FRESH_CRAG_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_QUALITY"
        elif quality_delta["ci_low"] >= -quality_margin and latency_delta["ci_high"] < 0:
            result = "FRESH_CRAG_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_QUALITY"
        elif quality_delta["mean"] > 0 and cost_delta["mean"] <= 0:
            result = "FRESH_CRAG_GOVERNANCE_IMPROVES_QUALITY_UNDER_FIXED_BUDGET"
        elif quality_delta["ci_low"] >= -quality_margin:
            result = "FRESH_CRAG_GOVERNANCE_NONINFERIOR_NO_OPERATIONAL_GAIN"
        elif cost_delta["mean"] < 0 or latency_delta["mean"] < 0:
            result = "FRESH_CRAG_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS"
        else:
            result = "FRESH_CRAG_GOVERNANCE_INCONCLUSIVE"

    if validation_summaries and confirmatory_summaries:
        quality_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "final_quality_score"))
        support_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "evidence_support_score"))
        cost_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "measured_cost_units"))
        latency_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "total_latency_ms"))
        api_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "api_call_count"))
        token_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "context_token_count"))
    else:
        quality_delta = support_delta = cost_delta = latency_delta = api_delta = token_delta = {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}

    payload = {
        "suite": "ragwarrant_fresh_live_crag_mock_api_behavioral_governance_v1",
        "result_class": result,
        "dry_run": dry_run,
        "evidence_class": "fresh_live_crag_mock_api_sanitized_live_sample",
        "environment": env,
        "crag_root_placeholder": "<approved-local-crag-root>",
        "crag_data_placeholder": "<approved-local-crag-data>",
        "mock_api_base_placeholder": "<local-crag-mock-api>",
        "examples_loaded_locally": len(rows),
        "per_query_policy_rows": len(per_query_rows),
        "validation_rows": sum(1 for row in rows if crag_split_for_row(row) == "validation"),
        "confirmatory_rows": sum(1 for row in rows if crag_split_for_row(row) == "confirmatory_test"),
        "quality_metric_class": "QUALITY_MEASURE_PROXY_PLUS_LOCAL_ANSWER_EVIDENCE",
        "quality_noninferiority_margin": 0.01,
        "governed_winner": governed_winner,
        "quality_only_winner": quality_winner,
        "constrained_optimizer_winner": constrained_winner,
        "pareto_frontier": frontier,
        "rag_compass_rank": next(
            (idx + 1 for idx, row in enumerate(sorted(confirmatory_summaries, key=lambda item: -float(item["final_quality_score"]))) if row["policy_id"] == "rag_compass_optional"),
            None,
        ),
        "final_quality_delta": quality_delta,
        "evidence_support_delta": support_delta,
        "cost_delta": cost_delta,
        "latency_delta_ms": latency_delta,
        "api_call_delta": api_delta,
        "context_token_delta": token_delta,
        "dataset_rows_committed": False,
        "query_wording_exported": False,
        "endpoint_outputs_exported": False,
        "source_documents_exported": False,
    }
    write_csv(output / "per_query_policy_results.csv", CRAG_RESULT_FIELDNAMES, per_query_rows)
    summary_fields = [
        "policy_id",
        "split",
        "n",
        "final_quality_score",
        "answer_correctness_f1",
        "answer_exact_match",
        "evidence_support_score",
        "supporting_fact_sentence_recall",
        "measured_cost_units",
        "total_latency_ms",
        "p95_latency_ms",
        "api_call_count",
        "context_token_count",
        "failure_rate",
        "abstention_rate",
        "abstention_correctness",
    ]
    write_csv(output / "policy_summary_metrics.csv", summary_fields, validation_summaries + confirmatory_summaries)
    selector_rows = [
        {"selector": "governed_selection", "selected_policy": governed_winner, "selection_split": "validation"},
        {"selector": "quality_only_best_on_validation", "selected_policy": quality_winner, "selection_split": "validation"},
        {"selector": "constrained_quality_optimizer", "selected_policy": constrained_winner, "selection_split": "validation"},
        {"selector": "pareto_frontier_selector", "selected_policy": "|".join(frontier), "selection_split": "confirmatory_test"},
    ]
    write_csv(output / "selector_comparison.csv", ["selector", "selected_policy", "selection_split"], selector_rows)
    write_csv(output / "pareto_frontier.csv", ["policy_id"], [{"policy_id": policy_id} for policy_id in frontier])
    write_sanitized_json(output / "live_crag_manifest.json", payload)
    write_sanitized_json(output / "primary_outcome_statistics.json", payload)
    write_sanitized_json(
        output / "split_manifest.json",
        {
            "result_class": result,
            "split_status": "created_sanitized_live_sample",
            "query_wording_exported": False,
            "source_documents_exported": False,
            "endpoint_outputs_exported": False,
        },
    )
    write_text(
        output / "live_crag_acquisition_report.md",
        "# Fresh Live CRAG Mock-API Acquisition\n\n"
        f"Result: `{result}`.\n\n"
        f"Loaded `{len(rows)}` approved local CRAG examples and executed `{len(per_query_rows)}` sanitized query-policy observations against the local mock API. "
        "Raw CRAG data, raw query wording, source documents, and API responses were not copied or exported.\n",
    )
    write_text(
        output / "primary_outcome_report.md",
        "# Fresh Live CRAG Behavioral Governance\n\n"
        f"Result: `{result}`.\n\n"
        f"Governed winner: `{governed_winner or 'not_available'}`. Quality-only winner: `{quality_winner or 'not_available'}`. "
        "The live sample uses local-answer/evidence containment over mock-API responses and exports only sanitized hashes, endpoint identifiers, counts, latencies, and aggregate metrics. "
        "No human, generative LLM, production, or RAG Compass superiority claim is made.\n",
    )
    return payload


def write_crag_placeholder(repo_root: Path, env: dict[str, Any], result: str, *, dry_run: bool = False, note: str = "") -> dict[str, Any]:
    output = repo_root / "artifacts" / "fresh_live_crag_behavioral_governance"
    payload = {
        "suite": "ragwarrant_fresh_live_crag_mock_api_behavioral_governance_v1",
        "result_class": result,
        "dry_run": dry_run,
        "evidence_class": "fresh_live_crag_mock_api_blocked" if result.startswith("FRESH_CRAG_BLOCKED") else "fresh_live_crag_mock_api",
        "environment": env,
        "crag_root_placeholder": "<approved-local-crag-root>" if env["crag_root_configured"] else "",
        "crag_data_placeholder": "<approved-local-crag-data>" if env["crag_data_configured"] else "",
        "dataset_rows_committed": False,
        "query_wording_exported": False,
        "endpoint_outputs_exported": False,
        "source_documents_exported": False,
        "note": note,
        "acquisition_instructions": [
            "git clone https://github.com/facebookresearch/CRAG.git <approved-local-path>/CRAG",
            "cd <approved-local-path>/CRAG",
            "pip install -r requirements.txt",
            "Follow CRAG dataset documentation for approved noncommercial research-only data acquisition.",
            "Set RAGWARRANT_CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY=true, RAGWARRANT_CRAG_ROOT, and RAGWARRANT_CRAG_DATA.",
            "Do not copy raw CRAG data into this public repository.",
        ],
    }
    write_sanitized_json(output / "live_crag_manifest.json", payload)
    write_sanitized_json(output / "primary_outcome_statistics.json", payload)
    write_text(
        output / "live_crag_acquisition_report.md",
        "# Fresh Live CRAG Mock-API Acquisition\n\n"
        f"Result: `{result}`.\n\n"
        f"{note or 'No fresh live CRAG collection was completed.'} Raw CRAG data, raw query wording, source documents, and API responses were not copied or exported.\n",
    )
    write_text(
        output / "primary_outcome_report.md",
        "# Fresh Live CRAG Behavioral Governance\n\n"
        f"Result: `{result}`.\n\n"
        "This is not a governance-success claim.\n",
    )
    split_status = "not_created_blocked_no_approved_data" if result == "FRESH_CRAG_BLOCKED_NO_APPROVED_DATA" else "not_created_blocked_mock_api_not_available"
    write_sanitized_json(output / "split_manifest.json", {"result_class": result, "split_status": split_status})
    for name in [
        "per_query_policy_results.csv",
        "policy_summary_metrics.csv",
        "selector_comparison.csv",
        "pareto_frontier.csv",
    ]:
        csv_empty(output / name, ["result_class", "note"])
    return payload


def inspect_crag_environment() -> dict[str, Any]:
    approved = os.environ.get("RAGWARRANT_CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY") == "true"
    root_value = os.environ.get("RAGWARRANT_CRAG_ROOT")
    data_value = os.environ.get("RAGWARRANT_CRAG_DATA")
    root = Path(root_value).expanduser() if root_value else None
    data = Path(data_value).expanduser() if data_value else None
    root_ok = bool(root and root.exists())
    data_ok = bool(data and data.exists())
    required = crag_required_paths(root) if root_ok and root is not None else {}
    data_status = crag_data_file_status(data)
    runtime_status = crag_mock_api_runtime_status(root)
    return {
        "approved_noncommercial_research_only": approved,
        "approval_env_var_present": approved,
        "crag_root_configured": bool(root_value),
        "crag_data_configured": bool(data_value),
        "crag_root_exists": root_ok,
        "crag_data_exists": data_ok,
        "required_paths": required,
        **data_status,
        **runtime_status,
        "mock_api_available": bool(runtime_status["mock_api_runtime_available"]),
        "local_evaluation_available": bool(required.get("local_evaluation.py")) if required else False,
    }


def write_crag_acquisition_report(repo_root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    env = inspect_crag_environment()
    if not env["approved_noncommercial_research_only"] or not env["crag_root_exists"] or not env["crag_data_exists"] or not env["data_files_present"]:
        result = "FRESH_CRAG_BLOCKED_NO_APPROVED_DATA"
    elif not env["mock_api_available"]:
        result = "FRESH_CRAG_BLOCKED_MOCK_API_NOT_AVAILABLE"
    else:
        if dry_run:
            return write_crag_placeholder(
                repo_root,
                env,
                "FRESH_CRAG_GOVERNANCE_INCONCLUSIVE",
                dry_run=True,
                note="Dry run verified approved local CRAG data and a readable mock-API installation; no live collection was executed.",
            )
        return run_crag_live_behavioral_governance(repo_root, env, dry_run=False)
    note = (
        "Approved local CRAG data are unavailable or incomplete."
        if result == "FRESH_CRAG_BLOCKED_NO_APPROVED_DATA"
        else "Approved local CRAG data were found, but the mock-API runtime was unavailable."
    )
    return write_crag_placeholder(repo_root, env, result, dry_run=dry_run, note=note)


def inspect_hotpotqa_environment(local_data_root: Path | None = None) -> dict[str, Any]:
    datasets_available = importlib.util.find_spec("datasets") is not None
    root = local_data_root or Path(os.environ.get("RAGWARRANT_DATA_ROOT", ".local_data")) / "hotpotqa"
    hf_cache_root = Path(".local_data") / "huggingface" / "datasets" / "hotpotqa___hotpot_qa"
    raw_candidates = [
        root / "hotpot_dev_distractor_v1.json",
        root / "hotpot_train_v1.1.json",
        root / "hotpot_dev_fullwiki_v1.json",
    ]
    return {
        "datasets_library_available": datasets_available,
        "local_data_root_exists": root.exists(),
        "local_data_root": "<repo>/.local_data/hotpotqa" if not root.is_absolute() else "<external-hotpotqa-data-root>",
        "hf_cache_used": hf_cache_root.exists(),
        "hf_cache_location": "<repo>/.local_data/huggingface/datasets",
        "known_raw_files_present": [path.name for path in raw_candidates if path.exists()],
    }


def load_hotpotqa_rows(repo_root: Path, *, max_examples: int = 1000) -> list[dict[str, Any]]:
    if importlib.util.find_spec("datasets") is None:
        raise RuntimeError("datasets library unavailable")
    from datasets import load_dataset

    cache_dir = repo_root / ".local_data" / "huggingface" / "datasets"
    cache_dir.mkdir(parents=True, exist_ok=True)
    dataset = load_dataset(
        "hotpotqa/hotpot_qa",
        "distractor",
        split=f"validation[:{max_examples}]",
        cache_dir=str(cache_dir),
    )
    return [dict(row) for row in dataset]


def run_hotpotqa_behavioral_governance(repo_root: Path, *, max_examples: int = 1000, dry_run: bool = False) -> dict[str, Any]:
    output = repo_root / "artifacts" / "hotpotqa_behavioral_governance"
    env = inspect_hotpotqa_environment()
    if dry_run:
        result = "HOTPOTQA_BLOCKED_DATASET_UNAVAILABLE" if not env["datasets_library_available"] else "HOTPOTQA_GOVERNANCE_INCONCLUSIVE"
        payload = {
            "suite": "ragwarrant_hotpotqa_behavioral_governance_v1",
            "result_class": result,
            "dry_run": True,
            "evidence_class": "hotpotqa_public_corpus_dry_run",
            "license_status": "Dataset CC BY-SA 4.0; code Apache-2.0; raw data not redistributed by this repository.",
            "environment": env,
            "question_wording_exported": False,
            "context_paragraphs_exported": False,
            "supporting_fact_sentences_exported": False,
            "acquisition_instructions": [
                "pip install datasets",
                "python3 scripts/run_hotpotqa_behavioral_governance.py --output-root artifacts/hotpotqa_behavioral_governance",
                "Do not commit raw questions, context paragraphs, or supporting-fact sentences.",
            ],
        }
        write_sanitized_json(output / "hotpotqa_acquisition_manifest.json", payload)
        write_sanitized_json(output / "primary_outcome_statistics.json", payload)
        return payload

    if not env["datasets_library_available"] and not env["known_raw_files_present"]:
        result = "HOTPOTQA_BLOCKED_DATASET_UNAVAILABLE"
        payload = {
            "suite": "ragwarrant_hotpotqa_behavioral_governance_v1",
            "result_class": result,
            "dry_run": dry_run,
            "evidence_class": "hotpotqa_public_corpus_blocked",
            "license_status": "Dataset CC BY-SA 4.0; code Apache-2.0; raw data not redistributed by this repository.",
            "environment": env,
            "question_wording_exported": False,
            "context_paragraphs_exported": False,
            "supporting_fact_sentences_exported": False,
            "acquisition_instructions": [
                "pip install datasets",
                "python3 scripts/acquire_hotpotqa_public_corpus.py --source huggingface --config distractor --output-root ${RAGWARRANT_DATA_ROOT:-.local_data}/hotpotqa",
                "Alternatively clone https://github.com/hotpotqa/hotpot and follow official download instructions.",
                "Do not commit raw questions, context paragraphs, or supporting-fact sentences.",
            ],
        }
        write_sanitized_json(output / "hotpotqa_acquisition_manifest.json", payload)
        write_sanitized_json(output / "primary_outcome_statistics.json", payload)
        write_sanitized_json(output / "hotpotqa_split_manifest.json", {"result_class": result, "split_status": "not_created_blocked_dataset_unavailable"})
        write_sanitized_json(output / "split_manifest.json", {"result_class": result, "split_status": "not_created_blocked_dataset_unavailable"})
        write_text(
            output / "hotpotqa_license_report.md",
            "# HotpotQA License Report\n\n"
            "HotpotQA raw data are not committed to this repository. The intended dataset license boundary is CC BY-SA 4.0 for data and Apache-2.0 for code, with raw-data acquisition delegated to the original providers.\n",
        )
        write_text(
            output / "hotpotqa_quality_measurement_report.md",
            "# HotpotQA Quality Measurement v1\n\n"
            "Planned components: exact match, normalized F1, supporting-fact title recall, supporting-fact sentence recall, evidence efficiency, and abstention correctness. "
            "The run is blocked until local HotpotQA data are available.\n",
        )
        write_text(
            output / "primary_outcome_report.md",
            "# HotpotQA Behavioral Governance\n\n"
            f"Result: `{result}`.\n\n"
            "No HotpotQA result is claimed because the dataset was unavailable in this environment. The script produced sanitized blocked artifacts only.\n",
        )
        for name in [
            "per_query_policy_results.csv",
            "policy_summary_metrics.csv",
            "selector_comparison.csv",
            "pareto_frontier.csv",
        ]:
            csv_empty(output / name, ["result_class", "note"])
        return payload

    raw_rows = load_hotpotqa_rows(repo_root, max_examples=max_examples)
    policies = DEPLOYABLE_HOTPOTQA_POLICIES + ["supporting_fact_aware_oracle_ceiling"]
    per_query_rows: list[dict[str, Any]] = []
    for row in raw_rows:
        split = split_for_row(row)
        for policy_id in policies:
            per_query_rows.append(score_hotpotqa_policy(row, policy_id, split))

    validation_summaries = aggregate_policy_rows(per_query_rows, "validation")
    confirmatory_summaries = aggregate_policy_rows(per_query_rows, "confirmatory_test")
    quality_winner = quality_only_winner(validation_summaries)
    governed_winner = cost_minimizer_at_quality_floor(validation_summaries, margin=0.01)
    constraints = {
        "max_mean_cost_units": 4.0,
        "max_p95_latency_ms": 10.0,
        "max_failure_rate": 0.05,
        "min_evidence_support_score": 0.10,
    }
    constrained_winner = constrained_quality_winner(validation_summaries, constraints) or governed_winner
    frontier = pareto_frontier(
        confirmatory_summaries,
        maximize=("final_quality_score", "evidence_support_score", "abstention_correctness"),
        minimize=("measured_cost_units", "p95_latency_ms", "failure_rate"),
    )

    by_policy_confirmatory = {row["policy_id"]: row for row in confirmatory_summaries}
    quality_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "final_quality_score"))
    answer_f1_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "answer_correctness_f1"))
    support_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "supporting_fact_title_recall"))
    support_sentence_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "supporting_fact_sentence_recall"))
    cost_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "measured_cost_units"))
    latency_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "total_latency_ms"))
    api_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "api_call_count"))
    token_delta = bootstrap_ci(paired_delta(per_query_rows, governed_winner, quality_winner, "context_token_count"))
    quality_noninferiority_margin = 0.01
    materially_distinct = abs(api_delta["mean"]) >= 0.5 or abs(cost_delta["mean"]) >= 0.5 or abs(token_delta["mean"]) >= 50
    if not materially_distinct:
        result = "HOTPOTQA_BLOCKED_POLICY_DISTINCTION_FAILED"
    elif quality_delta["ci_low"] >= -quality_noninferiority_margin and cost_delta["ci_high"] < 0:
        result = "HOTPOTQA_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_QUALITY"
    elif quality_delta["ci_low"] >= -quality_noninferiority_margin and latency_delta["ci_high"] < 0:
        result = "HOTPOTQA_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_QUALITY"
    elif by_policy_confirmatory.get(constrained_winner, {}).get("final_quality_score", 0) > by_policy_confirmatory.get(quality_winner, {}).get("final_quality_score", 0):
        result = "HOTPOTQA_GOVERNANCE_IMPROVES_QUALITY_UNDER_FIXED_BUDGET"
    elif quality_delta["ci_low"] >= -quality_noninferiority_margin:
        result = "HOTPOTQA_GOVERNANCE_NONINFERIOR_NO_OPERATIONAL_GAIN"
    else:
        result = "HOTPOTQA_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS" if cost_delta["mean"] < 0 else "HOTPOTQA_GOVERNANCE_INCONCLUSIVE"

    payload = {
        "suite": "ragwarrant_hotpotqa_behavioral_governance_v1",
        "result_class": result,
        "dry_run": False,
        "evidence_class": "hotpotqa_public_corpus_behavioral_governance_sanitized_sample",
        "license_status": "Dataset CC BY-SA 4.0; code Apache-2.0; raw data not redistributed by this repository.",
        "environment": env,
        "examples_loaded_locally": len(raw_rows),
        "per_query_policy_rows": len(per_query_rows),
        "validation_rows": sum(1 for row in raw_rows if split_for_row(row) == "validation"),
        "confirmatory_rows": sum(1 for row in raw_rows if split_for_row(row) == "confirmatory_test"),
        "quality_metric_class": "QUALITY_MEASURE_ANSWER_LABELS_PLUS_SUPPORTING_FACT_EVIDENCE",
        "quality_noninferiority_margin": quality_noninferiority_margin,
        "governed_winner": governed_winner,
        "quality_only_winner": quality_winner,
        "constrained_optimizer_winner": constrained_winner,
        "pareto_frontier": frontier,
        "rag_compass_rank": next(
            (idx + 1 for idx, row in enumerate(sorted(confirmatory_summaries, key=lambda item: -float(item["final_quality_score"]))) if row["policy_id"] == "rag_compass_optional"),
            None,
        ),
        "final_quality_delta": quality_delta,
        "answer_correctness_f1_delta": answer_f1_delta,
        "supporting_fact_title_recall_delta": support_delta,
        "supporting_fact_sentence_recall_delta": support_sentence_delta,
        "cost_delta": cost_delta,
        "latency_delta_ms": latency_delta,
        "api_call_delta": api_delta,
        "context_token_delta": token_delta,
        "policy_behavior_materially_distinct": materially_distinct,
        "constraints": constraints,
        "question_wording_exported": False,
        "context_paragraphs_exported": False,
        "supporting_fact_sentences_exported": False,
        "acquisition_instructions": [
            "pip install datasets",
            "python3 scripts/acquire_hotpotqa_public_corpus.py --source huggingface --config distractor --output-root ${RAGWARRANT_DATA_ROOT:-.local_data}/hotpotqa",
            "Alternatively clone https://github.com/hotpotqa/hotpot and follow official download instructions.",
            "Do not commit raw questions, context paragraphs, or supporting-fact sentences.",
        ],
    }
    write_csv(output / "per_query_policy_results.csv", HOTPOTQA_RESULT_FIELDNAMES, per_query_rows)
    summary_fields = [
        "policy_id",
        "split",
        "n",
        "final_quality_score",
        "answer_correctness_f1",
        "answer_exact_match",
        "evidence_support_score",
        "supporting_fact_sentence_recall",
        "measured_cost_units",
        "total_latency_ms",
        "p95_latency_ms",
        "api_call_count",
        "context_token_count",
        "failure_rate",
        "abstention_rate",
        "abstention_correctness",
    ]
    write_csv(output / "policy_summary_metrics.csv", summary_fields, validation_summaries + confirmatory_summaries)
    selector_rows = [
        {"selector": "governed_selection", "selected_policy": governed_winner, "selection_split": "validation"},
        {"selector": "quality_only_best_on_validation", "selected_policy": quality_winner, "selection_split": "validation"},
        {"selector": "constrained_quality_optimizer", "selected_policy": constrained_winner, "selection_split": "validation"},
        {"selector": "pareto_frontier_selector", "selected_policy": "|".join(frontier), "selection_split": "confirmatory_test"},
    ]
    write_csv(output / "selector_comparison.csv", ["selector", "selected_policy", "selection_split"], selector_rows)
    write_csv(output / "pareto_frontier.csv", summary_fields, [row for row in confirmatory_summaries if row["policy_id"] in frontier])
    distinction = hotpotqa_distinction_rows(confirmatory_summaries)
    write_csv(
        output / "behavioral_distinction_matrix.csv",
        [
            "policy_a",
            "policy_b",
            "api_call_count_difference",
            "context_count_difference",
            "context_token_difference",
            "latency_difference_ms",
            "measured_cost_difference",
            "answer_quality_difference",
            "supporting_fact_recall_difference",
        ],
        distinction,
    )
    write_sanitized_json(output / "hotpotqa_acquisition_manifest.json", payload)
    write_sanitized_json(output / "primary_outcome_statistics.json", payload)
    split_manifest = {
        "result_class": result,
        "split_status": "created_from_sanitized_hash_buckets",
        "calibration_rows": sum(1 for row in raw_rows if split_for_row(row) == "calibration"),
        "validation_rows": sum(1 for row in raw_rows if split_for_row(row) == "validation"),
        "confirmatory_rows": sum(1 for row in raw_rows if split_for_row(row) == "confirmatory_test"),
        "stratification_labels_retained": ["type", "level"],
        "question_wording_exported": False,
    }
    write_sanitized_json(output / "hotpotqa_split_manifest.json", split_manifest)
    write_sanitized_json(output / "split_manifest.json", split_manifest)
    write_text(
        output / "hotpotqa_license_report.md",
        "# HotpotQA License Report\n\n"
        "HotpotQA raw data are not committed to this repository. The intended dataset license boundary is CC BY-SA 4.0 for data and Apache-2.0 for code, with raw-data acquisition delegated to the original providers.\n\n"
        f"This run loaded `{len(raw_rows)}` HotpotQA validation examples into local memory/cache and exported only IDs/hashes, labels, counts, and metrics.\n",
    )
    write_text(
        output / "hotpotqa_quality_measurement_report.md",
        "# HotpotQA Quality Measurement v1\n\n"
        "Quality used answer-label and supporting-fact evidence components: normalized answer F1, exact match, answer containment, supporting-fact title recall, supporting-fact sentence recall, evidence efficiency, and abstention correctness.\n\n"
        "The scoring is still extractive/retrieval-based rather than generative LLM validation. Raw questions, answers, contexts, and supporting-fact sentences are not exported.\n",
    )
    write_text(
        output / "primary_outcome_report.md",
        "# HotpotQA Behavioral Governance\n\n"
        f"Result: `{result}`.\n\n"
        f"Governed winner: `{governed_winner}`. Quality-only winner: `{quality_winner}`. Constrained optimizer winner: `{constrained_winner}`.\n\n"
        f"Confirmatory quality delta: `{quality_delta['mean']:.6f}` with CI `[{quality_delta['ci_low']:.6f}, {quality_delta['ci_high']:.6f}]`.\n\n"
        f"Confirmatory cost delta: `{cost_delta['mean']:.6f}` with CI `[{cost_delta['ci_low']:.6f}, {cost_delta['ci_high']:.6f}]`.\n\n"
        f"Confirmatory latency delta: `{latency_delta['mean']:.6f}` ms with CI `[{latency_delta['ci_low']:.6f}, {latency_delta['ci_high']:.6f}]`.\n\n"
        "This result uses HotpotQA answer labels and supporting-fact identifiers without exporting raw dataset text. It does not claim human validation, generative LLM validation, official platform benchmarking, production readiness, or RAG Compass superiority.\n",
    )
    return payload


def write_hotpotqa_acquisition_report(repo_root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    return run_hotpotqa_behavioral_governance(repo_root, dry_run=dry_run)


def write_multi_dataset_synthesis(repo_root: Path) -> dict[str, Any]:
    crag_path = repo_root / "artifacts" / "fresh_live_crag_behavioral_governance" / "primary_outcome_statistics.json"
    hotpot_path = repo_root / "artifacts" / "hotpotqa_behavioral_governance" / "primary_outcome_statistics.json"
    prior_path = repo_root / "artifacts" / "behavioral_governance" / "primary_outcome_statistics.json"
    crag = json.loads(crag_path.read_text(encoding="utf-8")) if crag_path.exists() else {"result_class": "FRESH_CRAG_BLOCKED_NO_APPROVED_DATA"}
    hotpot = json.loads(hotpot_path.read_text(encoding="utf-8")) if hotpot_path.exists() else {"result_class": "HOTPOTQA_BLOCKED_DATASET_UNAVAILABLE"}
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else {"primary_result_class": "not_available"}

    fresh_success = str(crag.get("result_class", "")) in POSITIVE_FRESH_CRAG_CLASSES
    hotpot_success = str(hotpot.get("result_class", "")) in POSITIVE_HOTPOTQA_CLASSES
    if fresh_success and hotpot_success:
        result = "MULTI_DATASET_BEHAVIORAL_GOVERNANCE_REPLICATED"
    elif fresh_success or hotpot_success:
        result = "MULTI_DATASET_BEHAVIORAL_GOVERNANCE_DIRECTIONAL"
    elif str(crag.get("result_class", "")).startswith("FRESH_CRAG_BLOCKED") and str(hotpot.get("result_class", "")).startswith("HOTPOTQA_BLOCKED"):
        result = "MULTI_DATASET_BEHAVIORAL_GOVERNANCE_BLOCKED"
    else:
        result = "MULTI_DATASET_BEHAVIORAL_GOVERNANCE_INCONCLUSIVE"

    output = repo_root / "results" / "multi_dataset_behavioral_governance"
    comparison_rows = [
        {
            "dataset": "prior_sanitized_frozen_crag",
            "evidence_class": prior.get("evidence_class", "public_full_corpus_mock_api_validation_derived_frozen_observation"),
            "result_class": prior.get("primary_result_class", "not_available"),
            "claim_weight": "bounded_frozen_observation",
        },
        {
            "dataset": "fresh_live_crag_mock_api",
            "evidence_class": crag.get("evidence_class", "fresh_live_crag_mock_api_blocked"),
            "result_class": crag.get("result_class", ""),
            "claim_weight": "blocked" if str(crag.get("result_class", "")).startswith("FRESH_CRAG_BLOCKED") else "fresh_live",
        },
        {
            "dataset": "hotpotqa",
            "evidence_class": hotpot.get("evidence_class", "hotpotqa_public_corpus_blocked"),
            "result_class": hotpot.get("result_class", ""),
            "claim_weight": "blocked" if str(hotpot.get("result_class", "")).startswith("HOTPOTQA_BLOCKED") else "alternate_public_corpus",
        },
    ]
    output.mkdir(parents=True, exist_ok=True)
    with (output / "dataset_comparison_table.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(comparison_rows[0].keys()))
        writer.writeheader()
        writer.writerows(comparison_rows)
    payload = {
        "suite": "ragwarrant_multi_dataset_behavioral_governance_synthesis_v1",
        "result_class": result,
        "fresh_live_crag_result_class": crag.get("result_class"),
        "hotpotqa_result_class": hotpot.get("result_class"),
        "prior_frozen_observation_result_class": prior.get("primary_result_class"),
        "claim_boundary": "Replication is not claimed when only frozen-observation evidence succeeds.",
        "unsupported_claims": [
            "RAG Compass superiority",
            "human validation",
            "generative LLM validation",
            "official platform benchmarking",
            "production readiness",
        ],
    }
    write_sanitized_json(output / "synthesis_result.json", payload)
    write_sanitized_json(output / "claim_update.json", payload)
    write_text(
        output / "synthesis_report.md",
        "# Multi-Dataset Behavioral Governance Synthesis\n\n"
        f"Result: `{result}`.\n\n"
        f"Fresh live CRAG result: `{crag.get('result_class')}`. HotpotQA result: `{hotpot.get('result_class')}`. "
        "The prior sanitized CRAG frozen-observation result remains preserved. Replication is only claimed when fresh live CRAG and/or the alternate public corpus meet a positive predeclared endpoint.\n",
    )
    write_text(
        output / "paper_ready_summary.md",
        "# Fresh Live CRAG + HotpotQA Behavioral Governance Summary\n\n"
        "## Why frozen-observation evidence was insufficient\n\n"
        "The prior behaviorally distinct result used sanitized frozen CRAG mock-API observations. It reduced measured cost at equivalent proxy-plus-evidence quality, but it was not a fresh live collection and did not use a second corpus with stronger labels.\n\n"
        "## Why fresh CRAG was attempted\n\n"
        "Fresh live CRAG would test whether the policy behavior and operating-cost result persist when the mock API is called again under approved noncommercial constraints.\n\n"
        "## Why HotpotQA was selected\n\n"
        "HotpotQA provides answer labels, multi-hop structure, bridge/comparison types, difficulty levels, and supporting-fact labels for stronger answer correctness and evidence-support scoring.\n\n"
        "## Dataset acquisition status\n\n"
        f"Fresh CRAG: `{crag.get('result_class')}`. HotpotQA: `{hotpot.get('result_class')}`.\n\n"
        "## Policy suite\n\n"
        "The planned suite includes low retrieval, expanded retrieval, adaptive routing, BM25/reranking for HotpotQA, quality-only, constrained optimizer, Pareto selector, and governed selection.\n\n"
        "## Quality metrics\n\n"
        "CRAG would use proxy-plus-evidence plus any available local evaluator. HotpotQA would use exact match, F1, supporting-fact title recall, supporting-fact sentence recall, evidence efficiency, and abstention correctness.\n\n"
        "## Primary endpoint\n\n"
        "Equivalent quality with lower measured cost/latency, or improved quality under a fixed deployment budget.\n\n"
        "## Fresh CRAG result\n\n"
        f"`{crag.get('result_class')}`.\n\n"
        "## HotpotQA result\n\n"
        f"`{hotpot.get('result_class')}`.\n\n"
        "## Multi-dataset synthesis\n\n"
        f"`{result}`.\n\n"
        "## Negative findings\n\n"
        "Fresh CRAG remains blocked if the approved local mock-API runtime cannot read the required KG/data files or if the live sample does not produce a usable answer/evidence quality signal. HotpotQA is classified only by the observed answer-label/supporting-fact result; noninferiority without operational gain is not treated as replication.\n\n"
        "## Claim boundaries\n\n"
        "No human validation, generative validation, official platform benchmark, production readiness, broad governance superiority, or RAG Compass superiority is claimed.\n\n"
        "## Reproduction instructions\n\n"
        "Configure approved CRAG and/or HotpotQA local data roots, then run the acquisition and governance scripts documented in this repository.\n\n"
        "## Recommended next experiment\n\n"
        "Repeat HotpotQA with a larger/full split and stronger non-oracle adaptive triggers, and repeat fresh live CRAG after configuring the CRAG mock API runtime.\n",
    )
    write_text(
        output / "executive_summary.md",
        "# Executive Summary\n\n"
        f"Multi-dataset synthesis result: `{result}`. Fresh live CRAG: `{crag.get('result_class')}`. HotpotQA: `{hotpot.get('result_class')}`.\n",
    )
    write_text(
        output / "limitations.md",
        "# Limitations\n\n"
        "- Fresh CRAG was blocked because the live sample did not produce a usable answer/evidence quality signal or because the approved local mock-API runtime was unavailable.\n"
        "- HotpotQA raw data are not redistributed; only sanitized metrics, hashes, IDs, and labels are exported.\n"
        "- No raw data were committed.\n"
        "- No replication claim is made from frozen-only evidence or from non-positive endpoint classes.\n",
    )
    return payload
