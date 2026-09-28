# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.generative_validation_common import write_csv, write_json, write_md


POSITIVE = {
    "GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY",
    "GEN_LLM_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_GENERATED_QUALITY",
    "GEN_LLM_GOVERNANCE_IMPROVES_GENERATED_QUALITY_UNDER_FIXED_BUDGET",
    "GEN_LLM_GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_GENERATED_QUALITY_CRAG",
    "GEN_LLM_GOVERNANCE_REDUCES_LATENCY_AT_EQUIVALENT_GENERATED_QUALITY_CRAG",
    "GEN_LLM_GOVERNANCE_IMPROVES_GENERATED_QUALITY_UNDER_FIXED_BUDGET_CRAG",
    "GEN_LLM_VALIDATION_LOCAL_OPEN_MODEL_COMPLETED",
    "GEN_LLM_VALIDATION_HOSTED_MODEL_COMPLETED",
    "GEN_LLM_VALIDATION_CRAG_GENERATED_ANSWER_SIGNAL",
    "GEN_LLM_VALIDATION_HOTPOTQA_GENERATED_ANSWER_SIGNAL",
}

NEGATIVE = {
    "GEN_LLM_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS",
    "GEN_LLM_GOVERNANCE_NEGATIVE",
}


def load_result(path: Path, default: str) -> dict[str, object]:
    if not path.exists():
        return {"result_class": default}
    return json.loads(path.read_text(encoding="utf-8"))


def synthesize_generative_validation(root: Path, *, output_root: Path) -> dict[str, object]:
    crag = load_result(root / "artifacts/generative_llm_validation/crag/primary_outcome_statistics.json", "GEN_LLM_VALIDATION_BLOCKED_CRAG_UNAVAILABLE")
    audit_hotpotqa = root / "artifacts/generative_llm_validation/hotpotqa_quality_signal_audit/primary_outcome_statistics.json"
    hotpotqa = load_result(
        audit_hotpotqa if audit_hotpotqa.exists() else root / "artifacts/generative_llm_validation/hotpotqa/primary_outcome_statistics.json",
        "GEN_LLM_VALIDATION_BLOCKED_HOTPOTQA_UNAVAILABLE",
    )
    crag_class = str(crag.get("result_class", ""))
    hotpotqa_class = str(hotpotqa.get("result_class", ""))
    repeat_comparison = load_result(
        root / "results/generative_llm_validation/crag_repeat_comparison.json",
        "",
    )
    repeat_comparison_class = str(repeat_comparison.get("result_class", ""))
    stability_comparison = load_result(
        root / "results/generative_llm_validation/crag_stability_comparison.json",
        "",
    )
    stability_comparison_class = str(stability_comparison.get("result_class", ""))
    stability_endpoint = str(stability_comparison.get("primary_endpoint", "cost") or "cost")
    stability_endpoint_label = "latency" if stability_endpoint == "latency" else "cost"
    second_model_comparison = load_result(
        root / "results/generative_llm_validation/crag_second_model_comparison.json",
        "",
    )
    second_model_comparison_class = str(second_model_comparison.get("result_class", ""))
    answer_emission_comparison = load_result(
        root / "results/generative_llm_validation/crag_answer_emission_model_comparison.json",
        "",
    )
    answer_emission_comparison_class = str(answer_emission_comparison.get("result_class", ""))
    learned_risk_comparison = load_result(
        root / "results/generative_llm_validation/crag_learned_quality_risk_predictor_comparison.json",
        "",
    )
    learned_risk_comparison_class = str(learned_risk_comparison.get("result_class", ""))
    guardrail_v2_comparison = load_result(
        root / "results/generative_llm_validation/crag_quality_risk_guardrail_v2_comparison.json",
        "",
    )
    guardrail_v2_comparison_class = str(guardrail_v2_comparison.get("result_class", ""))
    crag_usable = bool(crag.get("usable_quality_signal", crag_class in POSITIVE))
    hotpotqa_usable = bool(hotpotqa.get("usable_quality_signal", hotpotqa_class in POSITIVE))
    crag_positive = crag_class in POSITIVE and crag_usable
    hotpotqa_positive = hotpotqa_class in POSITIVE and hotpotqa_usable
    if "NO_GENERATOR" in crag_class and "NO_GENERATOR" in hotpotqa_class:
        result_class = "GEN_LLM_SYNTHESIS_BLOCKED"
        interpretation = "No pinned local or hosted generator was available, so generative validation remains blocked."
    elif stability_comparison_class in {
        "CRAG_GEN_LLM_COST_RESULT_STABLE_ACROSS_REPEATS",
        "CRAG_GEN_LLM_LATENCY_RESULT_STABLE_ACROSS_REPEATS",
    } and crag_positive and hotpotqa_positive:
        result_class = "GEN_LLM_SYNTHESIS_GENERATIVE_VALIDATION_SUPPORTED"
        interpretation = "CRAG generative operational reduction was stable across independent deterministic repeats and HotpotQA also produced generative support."
    elif stability_comparison_class in {
        "CRAG_GEN_LLM_COST_RESULT_STABLE_ACROSS_REPEATS",
        "CRAG_GEN_LLM_LATENCY_RESULT_STABLE_ACROSS_REPEATS",
    } and crag_positive:
        result_class = "GEN_LLM_SYNTHESIS_DIRECTIONAL"
        interpretation = "CRAG generative operational reduction was stable across independent deterministic repeats, while HotpotQA did not independently support the same endpoint."
    elif stability_comparison_class in {
        "CRAG_GEN_LLM_COST_RESULT_MIXED_ACROSS_REPEATS",
        "CRAG_GEN_LLM_COST_RESULT_NOT_STABLE_ACROSS_REPEATS",
        "CRAG_GEN_LLM_COST_RESULT_DIRECTIONAL_BUT_UNSTABLE",
        "CRAG_GEN_LLM_LATENCY_RESULT_MIXED_ACROSS_REPEATS",
        "CRAG_GEN_LLM_LATENCY_RESULT_NOT_STABLE_ACROSS_REPEATS",
        "CRAG_GEN_LLM_LATENCY_RESULT_DIRECTIONAL_BUT_UNSTABLE",
    }:
        result_class = "GEN_LLM_SYNTHESIS_MIXED"
        if second_model_comparison_class:
            if stability_endpoint_label == "latency":
                interpretation = "CRAG generative latency reduction was mixed across independent deterministic repeats. The earlier cost-reduction result was not recovered by a second pinned local generator."
            else:
                interpretation = "CRAG generative cost reduction was not stable across independent deterministic repeats and was not recovered by a second pinned local generator."
        else:
            interpretation = f"CRAG generative {stability_endpoint_label} reduction was not stable across independent deterministic repeats."
        if answer_emission_comparison_class == "CRAG_GEN_LLM_ANSWER_EMISSION_REPAIRED_NO_COST_RESULT":
            if stability_endpoint_label == "latency":
                interpretation += " A faster non-thinking instruct model repaired answer emission; the follow-up latency-endpoint selector comparison was mixed across fixed offsets."
            else:
                interpretation += " A faster non-thinking instruct model repaired answer emission, but still did not recover a stable cost result."
        if learned_risk_comparison_class:
            interpretation += " A validation-trained deployable quality-risk predictor reduced expansions, but confirmatory quality protection did not persist across fixed offsets."
        if guardrail_v2_comparison_class:
            interpretation += " A pooled cross-offset quality-risk guardrail v2 was tested on held-out offsets and blocked promotion after held-out generated-quality loss."
    elif repeat_comparison_class == "CRAG_GEN_LLM_COST_RESULT_NOT_REPLICATED":
        result_class = "GEN_LLM_SYNTHESIS_MIXED"
        if stability_comparison_class in {
            "CRAG_GEN_LLM_COST_RESULT_INCONCLUSIVE_ACROSS_REPEATS",
            "CRAG_GEN_LLM_LATENCY_RESULT_INCONCLUSIVE_ACROSS_REPEATS",
        }:
            interpretation = (
                "The primary CRAG slice produced generative support, an independent deterministic CRAG repeat did not "
                f"reproduce the cost result, and the latest {stability_endpoint_label}-endpoint fixed-offset comparison "
                "was inconclusive."
            )
        else:
            interpretation = "The primary CRAG slice produced generative support, but an independent deterministic CRAG repeat did not reproduce the cost result."
    elif stability_comparison_class in {
        "CRAG_GEN_LLM_COST_RESULT_INCONCLUSIVE_ACROSS_REPEATS",
        "CRAG_GEN_LLM_LATENCY_RESULT_INCONCLUSIVE_ACROSS_REPEATS",
    } and crag_positive:
        result_class = "GEN_LLM_SYNTHESIS_MIXED"
        interpretation = (
            f"The primary CRAG slice produced bounded generative support, but the latest {stability_endpoint_label}-endpoint "
            "stability comparison was inconclusive across deterministic fixed offsets."
        )
    elif crag_positive and hotpotqa_positive:
        result_class = "GEN_LLM_SYNTHESIS_GENERATIVE_VALIDATION_SUPPORTED"
        interpretation = "Both datasets produced generative validation support."
    elif crag_positive or hotpotqa_positive:
        result_class = "GEN_LLM_SYNTHESIS_DIRECTIONAL"
        interpretation = "One dataset produced generative support while the other did not."
    elif crag_class in NEGATIVE and hotpotqa_class in NEGATIVE:
        result_class = "GEN_LLM_SYNTHESIS_NEGATIVE"
        interpretation = "Both datasets showed negative or quality-loss generative results."
    else:
        result_class = "GEN_LLM_SYNTHESIS_INCONCLUSIVE"
        interpretation = "Generative validation did not produce enough usable evidence for a governance claim."
    payload = {
        "suite": "ragwarrant_generative_llm_validation_synthesis_v1",
        "result_class": result_class,
        "crag_result_class": crag_class,
        "hotpotqa_result_class": hotpotqa_class,
        "prior_frozen_crag_behavioral_result": "GOVERNANCE_REDUCES_COST_AT_EQUIVALENT_QUALITY",
        "fresh_live_crag_proxy_result": "FRESH_CRAG_BLOCKED_QUALITY_MEASURE_PROXY_ONLY",
        "hotpotqa_non_generative_result": "HOTPOTQA_GOVERNANCE_OPERATIONAL_GAIN_QUALITY_LOSS",
        "crag_repeat_comparison_result": repeat_comparison_class,
        "crag_stability_comparison_result": stability_comparison_class,
        "crag_second_model_comparison_result": second_model_comparison_class,
        "crag_answer_emission_model_comparison_result": answer_emission_comparison_class,
        "crag_learned_quality_risk_predictor_comparison_result": learned_risk_comparison_class,
        "crag_quality_risk_guardrail_v2_comparison_result": guardrail_v2_comparison_class,
        "interpretation": interpretation,
        "unsupported_claims": [
            "official platform benchmarking",
            "human validation",
            "production readiness",
            "RAG Compass superiority",
        ],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "synthesis_result.json", payload)
    write_json(output_root / "claim_update.json", payload)
    write_csv(
        output_root / "dataset_comparison_table.csv",
        ["dataset", "result_class", "generator_provider", "quality_metric_class"],
        [
            {"dataset": "CRAG", "result_class": crag_class, "generator_provider": crag.get("generator_provider", ""), "quality_metric_class": crag.get("quality_metric_class", "")},
            {"dataset": "HotpotQA", "result_class": hotpotqa_class, "generator_provider": hotpotqa.get("generator_provider", ""), "quality_metric_class": hotpotqa.get("quality_metric_class", "")},
        ],
    )
    report = f"""
# Generative LLM Validation Synthesis

Result class: `{result_class}`

CRAG generative result: `{crag_class}`

HotpotQA generative result: `{hotpotqa_class}`

Interpretation: {interpretation}

No raw prompts, raw generated answers, raw dataset questions, raw source documents, secrets, or private local paths are included.
"""
    for filename in ["synthesis_report.md", "paper_ready_summary.md", "executive_summary.md"]:
        write_md(output_root / filename, report)
    if result_class == "GEN_LLM_SYNTHESIS_MIXED":
        if stability_comparison_class:
            limitation_text = (
                "Generative validation is currently mixed bounded local evidence. The primary CRAG slice produced "
                f"a cost-reduction signal, but the latest CRAG stability comparison did not show stable {stability_endpoint_label} reduction "
                "across independent deterministic repeats"
                + (", and a second pinned local generator did not recover a stable cost result" if second_model_comparison_class else "")
                + (
                    ", a faster non-thinking instruct model repaired answer emission and the guarded latency-endpoint selector comparison was inconclusive across fixed offsets"
                    if answer_emission_comparison_class and stability_comparison_class == "CRAG_GEN_LLM_LATENCY_RESULT_INCONCLUSIVE_ACROSS_REPEATS"
                    else ""
                )
                + (
                    ", a faster non-thinking instruct model repaired answer emission and the latency-endpoint selector comparison was mixed across fixed offsets"
                    if answer_emission_comparison_class and stability_endpoint_label == "latency" and stability_comparison_class != "CRAG_GEN_LLM_LATENCY_RESULT_INCONCLUSIVE_ACROSS_REPEATS"
                    else ""
                )
                + (
                    ", and a validation-trained deployable quality-risk predictor reduced expansions but did not reliably prevent confirmatory generated-quality loss"
                    if learned_risk_comparison_class
                    else ""
                )
                + (
                    ", and pooled cross-offset quality-risk guardrail v2 blocked promotion after held-out generated-quality loss"
                    if guardrail_v2_comparison_class
                    else ""
                )
                + (", a faster non-thinking instruct model repaired answer emission but still did not recover a stable cost result" if answer_emission_comparison_class and stability_endpoint_label != "latency" else "")
                + ", and HotpotQA remained inconclusive. This is not broad generative validation, not official "
                "platform benchmarking, not human validation, and not production readiness."
            )
        else:
            limitation_text = (
                "Generative validation is currently mixed bounded local evidence. The primary CRAG slice produced "
                "a cost-reduction signal, but an independent deterministic CRAG repeat did not reproduce it, and "
                "HotpotQA remained inconclusive. This is not broad generative validation, not official platform "
                "benchmarking, not human validation, and not production readiness."
            )
    elif result_class == "GEN_LLM_SYNTHESIS_DIRECTIONAL":
        limitation_text = (
            "Generative validation is currently bounded local evidence. One dataset produced generative "
            "support while the other did not. This is not broad generative validation, not official "
            "platform benchmarking, not human validation, and not production readiness."
        )
    elif result_class == "GEN_LLM_SYNTHESIS_GENERATIVE_VALIDATION_SUPPORTED":
        limitation_text = (
            "Generative validation is supported for the bounded configured datasets and generator path. "
            "This is not official platform benchmarking, not human validation, and not production readiness."
        )
    else:
        limitation_text = (
            "Generative validation remains blocked or inconclusive unless a pinned local or hosted generator "
            "actually runs and produces a usable generated-answer quality signal. Local generator validation "
            "is not official platform benchmarking. No human validation or production readiness is claimed."
        )
    write_md(
        output_root / "limitations.md",
        f"""
# Generative LLM Validation Limitations

{limitation_text}
""",
    )
    return payload
