from __future__ import annotations

import os
from pathlib import Path

from ragwarrant.fresh_live_behavioral_governance import (
    DEPLOYABLE_HOTPOTQA_POLICIES,
    load_hotpotqa_rows,
    select_hotpotqa_contexts,
    split_for_row,
    supporting_sentence_pairs,
    supporting_titles,
    tokenize,
)
from ragwarrant.generated_answer_quality import containment, exact_match, generated_quality_score, token_f1
from ragwarrant.generative_prompts import build_rag_prompt
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


def hotpotqa_cache_available(root: Path) -> bool:
    return (root / ".local_data/hotpotqa").exists() or (root / ".local_data/huggingface/datasets/hotpotqa___hotpot_qa").exists()


def simple_ci(values: list[float]) -> dict[str, float]:
    if not values:
        return zero_ci()
    ordered = sorted(values)
    return {
        "mean": mean(values),
        "ci_low": ordered[int(0.025 * (len(ordered) - 1))],
        "ci_high": ordered[int(0.975 * (len(ordered) - 1))],
    }


def summarize_policy(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    policies = sorted({str(row["policy_id"]) for row in rows})
    summaries: list[dict[str, object]] = []
    for policy in policies:
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


def choose_winners(summaries: list[dict[str, object]]) -> tuple[str, str, list[str]]:
    if not summaries:
        return "", "", []
    quality_only = max(summaries, key=lambda row: float(row["final_generated_quality_score"]))
    quality_floor = float(quality_only["final_generated_quality_score"]) - 0.01
    feasible = [row for row in summaries if float(row["final_generated_quality_score"]) >= quality_floor]
    governed = min(feasible or summaries, key=lambda row: (float(row["total_cost_units"]), float(row["total_latency_ms"])))
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
    return str(governed["policy_id"]), str(quality_only["policy_id"]), frontier


def run_hotpotqa_generation(root: Path, output_root: Path, discovery) -> dict[str, object]:
    assert discovery.generator is not None
    max_examples = int(os.environ.get("RAGWARRANT_GEN_MAX_EXAMPLES", "6"))
    max_tokens = int(os.environ.get("RAGWARRANT_GENERATOR_MAX_TOKENS", "48"))
    timeout_s = float(os.environ.get("RAGWARRANT_GENERATOR_TIMEOUT_S", "120"))
    rows = load_hotpotqa_rows(root, max_examples=max_examples)
    result_rows: list[dict[str, object]] = []
    for row in rows:
        split = split_for_row(row)
        answer = str(row["answer"])
        title_gold = set(supporting_titles(row))
        sentence_gold = supporting_sentence_pairs(row)
        for policy_id in DEPLOYABLE_HOTPOTQA_POLICIES:
            selected, retrieval_latency_ms = select_hotpotqa_contexts(policy_id, row)
            evidence_items = [
                {
                    "evidence_id": f"ctx_{idx}_{stable_hash(item['title'])[:8]}",
                    "text": " ".join(item["sentences"])[:1200],
                }
                for idx, item in enumerate(selected)
            ]
            prompt, prompt_hash = build_rag_prompt(question_text=str(row["question"]), evidence_items=evidence_items)
            generation = discovery.generator.generate(
                prompt,
                model=discovery.model,
                temperature=0.0,
                max_tokens=max_tokens,
                timeout_s=timeout_s,
            )
            # The raw answer is written only under .local_data by the adapter.
            raw_answer = (root / str(generation.raw_answer_local_path)).read_text(encoding="utf-8") if generation.raw_answer_local_path else ""
            selected_titles = {str(item["title"]) for item in selected}
            title_hits = sum(1 for title in title_gold if title in selected_titles)
            sentence_hits = sum(1 for title, _sent_id in sentence_gold if title in selected_titles)
            title_recall = title_hits / len(title_gold) if title_gold else 0.0
            sentence_recall = sentence_hits / len(sentence_gold) if sentence_gold else 0.0
            answer_f1 = token_f1(raw_answer, answer)
            answer_em = exact_match(raw_answer, answer)
            answer_containment = containment(raw_answer, answer)
            citation_support = 1.0 if title_hits else 0.0
            abstained = "INSUFFICIENT_EVIDENCE" in raw_answer.upper()
            abstention_correctness = 1.0 if (title_hits == 0 and abstained) or (title_hits > 0 and not abstained) else 0.0
            quality = generated_quality_score(
                answer_correctness_f1=answer_f1,
                answer_exact_match=answer_em,
                answer_containment=answer_containment,
                evidence_support_score=0.5 * title_recall + 0.5 * sentence_recall,
                citation_support_score=citation_support,
                abstention_correctness=abstention_correctness,
            )
            context_tokens = sum(len(tokenize(" ".join(item["sentences"]))) for item in selected)
            retrieval_cost = len(selected) + context_tokens / 1000.0
            result_rows.append(
                {
                    "example_id": stable_hash(str(row["id"])),
                    "question_hash": stable_hash(str(row["question"])),
                    "split": split,
                    "dataset": "hotpotqa",
                    "policy_id": policy_id,
                    "provider": generation.provider,
                    "model": generation.model,
                    "prompt_hash": prompt_hash,
                    "generated_answer_hash": generation.answer_hash,
                    "generated_answer_char_count": generation.answer_char_count,
                    "generated_answer_token_estimate": generation.answer_token_estimate,
                    "retrieval_latency_ms": retrieval_latency_ms,
                    "generation_latency_ms": generation.latency_ms,
                    "total_latency_ms": retrieval_latency_ms + generation.latency_ms,
                    "retrieval_cost_units": retrieval_cost,
                    "generation_cost_units": generation.cost_units,
                    "total_cost_units": retrieval_cost + generation.cost_units,
                    "input_token_estimate": generation.input_token_estimate,
                    "output_token_estimate": generation.output_token_estimate,
                    "api_call_count": len(selected),
                    "generator_call_count": 1,
                    "answer_correctness_f1": answer_f1,
                    "answer_exact_match": answer_em,
                    "answer_containment": answer_containment,
                    "evidence_support_score": 0.5 * title_recall + 0.5 * sentence_recall,
                    "citation_support_score": citation_support,
                    "abstention_correctness": abstention_correctness,
                    "final_generated_quality_score": quality,
                    "raw_prompt_exported": False,
                    "raw_generated_answer_exported": False,
                }
            )
    summaries = summarize_policy(result_rows)
    governed, quality_only, frontier = choose_winners(summaries)
    confirmatory = [row for row in result_rows if row["split"] == "confirmatory_test"]
    governed_rows = {row["example_id"]: row for row in confirmatory if row["policy_id"] == governed}
    quality_rows = {row["example_id"]: row for row in confirmatory if row["policy_id"] == quality_only}
    shared_ids = sorted(set(governed_rows) & set(quality_rows))
    quality_deltas = [float(governed_rows[idx]["final_generated_quality_score"]) - float(quality_rows[idx]["final_generated_quality_score"]) for idx in shared_ids]
    cost_deltas = [float(governed_rows[idx]["total_cost_units"]) - float(quality_rows[idx]["total_cost_units"]) for idx in shared_ids]
    latency_deltas = [float(governed_rows[idx]["total_latency_ms"]) - float(quality_rows[idx]["total_latency_ms"]) for idx in shared_ids]
    answer_deltas = [float(governed_rows[idx]["answer_correctness_f1"]) - float(quality_rows[idx]["answer_correctness_f1"]) for idx in shared_ids]
    evidence_deltas = [float(governed_rows[idx]["evidence_support_score"]) - float(quality_rows[idx]["evidence_support_score"]) for idx in shared_ids]
    diagnostics = quality_signal_diagnostics(result_rows)
    if not diagnostics["usable_quality_signal"]:
        result_class = "GEN_LLM_VALIDATION_BLOCKED_NO_USABLE_QUALITY_SIGNAL"
    elif quality_deltas and simple_ci(quality_deltas)["mean"] >= -0.01 and simple_ci(cost_deltas)["ci_high"] < 0:
        result_class = "GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY"
    elif quality_deltas and simple_ci(quality_deltas)["mean"] < -0.01 and simple_ci(cost_deltas)["mean"] < 0:
        result_class = "GEN_LLM_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS"
    else:
        result_class = "GEN_LLM_GOVERNANCE_INCONCLUSIVE"
    stats = {
        "suite": "ragwarrant_hotpotqa_generative_llm_validation_v1",
        "evidence_class": "hotpotqa_local_generative_validation_sanitized_bounded_sample",
        "result_class": result_class,
        "generator_provider": discovery.provider,
        "generator_model": discovery.model,
        "generator_available": True,
        "generator_local_or_hosted": discovery.local_or_hosted,
        "quality_metric_class": "GENERATED_QUALITY_HOTPOTQA_ANSWER_LABELS_PLUS_SUPPORTING_FACTS",
        "governed_winner": governed,
        "quality_only_winner": quality_only,
        "constrained_optimizer_winner": governed,
        "pareto_frontier": frontier,
        "rag_compass_rank": next((idx + 1 for idx, row in enumerate(sorted(summaries, key=lambda item: float(item["final_generated_quality_score"]), reverse=True)) if row["policy_id"] == "rag_compass_optional"), ""),
        "generated_quality_delta": simple_ci(quality_deltas),
        "answer_correctness_delta": simple_ci(answer_deltas),
        "supporting_fact_evidence_delta": simple_ci(evidence_deltas),
        "cost_delta": simple_ci(cost_deltas),
        "latency_delta_ms": simple_ci(latency_deltas),
        "generation_rows": len(result_rows),
        "example_count": len(rows),
        "quality_signal_audit_result_class": diagnostics["quality_signal_audit_result_class"],
        "prior_zero_delta_explanation": diagnostics["prior_zero_delta_explanation"],
        "non_empty_generated_answers": diagnostics["non_empty_generated_answers"],
        "unique_answer_hash_count": diagnostics["unique_answer_hash_count"],
        "quality_variance": diagnostics["quality_variance"],
        "usable_quality_signal": diagnostics["usable_quality_signal"],
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
        "raw_questions_committed": False,
        "raw_contexts_committed": False,
        "raw_supporting_fact_text_committed": False,
        "secrets_committed": False,
    }
    write_csv(output_root / "per_query_generation_metrics.csv", GENERATION_FIELDNAMES, result_rows)
    write_csv(output_root / "policy_summary_metrics.csv", ["policy_id", "final_generated_quality_score", "total_cost_units", "total_latency_ms"], summaries)
    write_csv(output_root / "selector_comparison.csv", ["selector", "winner", "reason"], [
        {"selector": "governed_selection", "winner": governed, "reason": "lowest cost within generated-quality noninferiority margin"},
        {"selector": "quality_only_best_on_validation", "winner": quality_only, "reason": "highest generated quality"},
    ])
    write_csv(output_root / "pareto_frontier.csv", ["policy_id", "frontier_reason"], [{"policy_id": policy, "frontier_reason": "nondominated on generated quality, cost, and latency"} for policy in frontier])
    write_csv(
        output_root / "quality_signal_diagnostics.csv",
        ["metric", "value"],
        [{"metric": key, "value": value} for key, value in diagnostics.items()],
    )
    return stats


def run_hotpotqa_quality_signal_audit(root: Path, *, output_root: Path, dry_run: bool = False) -> dict[str, object]:
    previous = os.environ.get("RAGWARRANT_GEN_MAX_EXAMPLES")
    os.environ.setdefault("RAGWARRANT_GEN_MAX_EXAMPLES", "12")
    try:
        stats = run_hotpotqa_generative_validation(root, output_root=output_root, dry_run=dry_run)
    finally:
        if previous is None:
            os.environ.pop("RAGWARRANT_GEN_MAX_EXAMPLES", None)
        else:
            os.environ["RAGWARRANT_GEN_MAX_EXAMPLES"] = previous
    diagnostics_path = output_root / "quality_signal_diagnostics.csv"
    audit_result_class = str(stats.get("quality_signal_audit_result_class", "HOTPOTQA_GEN_LLM_ZERO_DELTAS_INCONCLUSIVE"))
    manifest = {
        "suite": "ragwarrant_hotpotqa_generative_quality_signal_audit_v1",
        "result_class": audit_result_class,
        "primary_result_class": stats.get("result_class", ""),
        "generator_provider": stats.get("generator_provider", ""),
        "generator_model": stats.get("generator_model", ""),
        "sample_size": stats.get("example_count", 0),
        "generation_rows": stats.get("generation_rows", 0),
        "unique_answer_hash_count": stats.get("unique_answer_hash_count", 0),
        "non_empty_generated_answers": stats.get("non_empty_generated_answers", 0),
        "quality_variance": stats.get("quality_variance", 0.0),
        "prior_zero_delta_explanation": stats.get("prior_zero_delta_explanation", ""),
        "diagnostics_path": diagnostics_path.relative_to(root).as_posix() if diagnostics_path.exists() else "",
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
        "raw_questions_committed": False,
        "raw_contexts_committed": False,
        "raw_supporting_fact_text_committed": False,
        "secrets_committed": False,
    }
    write_json(output_root / "audit_manifest.json", manifest)
    write_md(
        output_root / "quality_signal_audit_report.md",
        f"""
# HotpotQA Generative Quality-Signal Audit

Result class: `{audit_result_class}`

Primary generated-governance result class: `{stats.get('result_class', '')}`

Sample size: {stats.get('example_count', 0)}
Generation rows: {stats.get('generation_rows', 0)}
Unique answer hashes: {stats.get('unique_answer_hash_count', 0)}
Non-empty generated answers: {stats.get('non_empty_generated_answers', 0)}
Quality variance: {stats.get('quality_variance', 0.0)}

Zero-delta explanation: {stats.get('prior_zero_delta_explanation', '')}

The audit stores only hashes, counts, and metrics. Raw HotpotQA questions, context paragraphs, supporting-fact sentences, prompts, and generated answers are not committed.
""",
    )
    return {**stats, **manifest}


def run_hotpotqa_generative_validation(root: Path, *, output_root: Path, dry_run: bool = False) -> dict[str, object]:
    discovery = discover_generator(dry_run=dry_run)
    cache_available = hotpotqa_cache_available(root)
    if not cache_available:
        result_class = "GEN_LLM_VALIDATION_BLOCKED_HOTPOTQA_UNAVAILABLE"
        blocker = "HotpotQA local cache is unavailable"
    elif not discovery.available:
        result_class = discovery.status
        blocker = discovery.instructions
    else:
        stats = run_hotpotqa_generation(root, output_root, discovery)
        manifest = {
            "suite": "ragwarrant_hotpotqa_generative_llm_validation_v1",
            "evidence_class": stats["evidence_class"],
            "result_class": stats["result_class"],
            "blocker": "",
            "generator_provider": discovery.provider,
            "generator_model": discovery.model,
            "generator_available": discovery.available,
            "generator_local_or_hosted": discovery.local_or_hosted,
            "hotpotqa_cache_available": cache_available,
            "raw_prompts_committed": False,
            "raw_generated_answers_committed": False,
            "raw_questions_committed": False,
            "raw_contexts_committed": False,
            "raw_supporting_fact_text_committed": False,
            "secrets_committed": False,
        }
        write_json(output_root / "generative_hotpotqa_manifest.json", manifest)
        write_json(output_root / "primary_outcome_statistics.json", stats)
        write_md(
            output_root / "generator_environment_report.md",
            f"""
# HotpotQA Generative LLM Environment

Provider: `{discovery.provider}`
Model: `{discovery.model}`
Status: `{stats['result_class']}`

Raw prompts, generated answers, questions, context paragraphs, and supporting-fact sentences are not committed.
""",
        )
        write_md(
            output_root / "primary_outcome_report.md",
            f"""
# HotpotQA Generative LLM Validation

Result class: `{stats['result_class']}`

This bounded local-generator run used sanitized generated-answer metrics only. Raw prompts and raw generated answers are excluded from Git.
""",
        )
        return stats

    output_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "suite": "ragwarrant_hotpotqa_generative_llm_validation_v1",
        "evidence_class": "hotpotqa_generative_validation_attempt",
        "result_class": result_class,
        "blocker": blocker,
        "generator_provider": discovery.provider,
        "generator_model": discovery.model,
        "generator_available": discovery.available,
        "generator_local_or_hosted": discovery.local_or_hosted,
        "hotpotqa_cache_available": cache_available,
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
        "raw_questions_committed": False,
        "raw_contexts_committed": False,
        "raw_supporting_fact_text_committed": False,
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
        "answer_correctness_delta": zero_ci(),
        "supporting_fact_evidence_delta": zero_ci(),
        "cost_delta": zero_ci(),
        "latency_delta_ms": zero_ci(),
        "generation_rows": 0,
    }
    write_json(output_root / "generative_hotpotqa_manifest.json", manifest)
    write_json(output_root / "primary_outcome_statistics.json", stats)
    write_csv(output_root / "per_query_generation_metrics.csv", GENERATION_FIELDNAMES, [])
    write_csv(output_root / "policy_summary_metrics.csv", ["policy_id", "final_generated_quality_score", "total_cost_units", "total_latency_ms"], [])
    write_csv(output_root / "selector_comparison.csv", ["selector", "winner", "reason"], [])
    write_csv(output_root / "pareto_frontier.csv", ["policy_id", "frontier_reason"], [])
    write_md(
        output_root / "generator_environment_report.md",
        f"""
# HotpotQA Generative LLM Environment

Provider: `{discovery.provider}`
Model: `{discovery.model or 'not configured'}`
Status: `{result_class}`

Raw prompts, generated answers, questions, context paragraphs, and supporting-fact sentences are not committed.

Blocker: {blocker}
""",
    )
    write_md(
        output_root / "primary_outcome_report.md",
        f"""
# HotpotQA Generative LLM Validation

Result class: `{result_class}`

This run did not produce a generative governance claim. Public artifacts contain only sanitized status, hashes, counts, and metric fields. Raw prompts and raw generated answers are excluded.
""",
    )
    return stats
