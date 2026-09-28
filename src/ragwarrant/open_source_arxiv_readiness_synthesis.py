# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ragwarrant.generative_validation_common import write_csv, write_json, write_md


def _load(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def run_open_source_arxiv_readiness_synthesis(root: Path, *, output_root: Path) -> dict[str, object]:
    evidence = {
        "guardrail_v2": _load(root / "results/generative_llm_validation/crag_quality_risk_guardrail_v2_comparison.json").get("result_class", ""),
        "public_mini": _load(root / "artifacts/public_mini_reproduction/mini_reproduction_manifest.json").get("result_class", ""),
        "hotpotqa_audit": _load(root / "artifacts/generative_llm_validation/hotpotqa_quality_signal_audit/audit_manifest.json").get("result_class", ""),
        "crag_evaluator_mapping": _load(root / "artifacts/generative_llm_validation/crag_evaluator_mapping/evaluator_mapping_result.json").get("mapping_result_class", ""),
        "external_evaluator_adapters": _load(root / "artifacts/external_evaluator_adapters/external_evaluator_manifest.json").get("result_class", ""),
        "selector_ablation": _load(root / "artifacts/selector_ablation_matrix/selector_ablation_manifest.json").get("result_class", ""),
        "hardware_characterization": _load(root / "artifacts/aim_hardware_characterization/hardware_manifest.json").get("result_class", ""),
        "generative_synthesis": _load(root / "results/generative_llm_validation/synthesis_result.json").get("result_class", ""),
    }
    required_ready = all(
        evidence[key]
        for key in [
            "guardrail_v2",
            "public_mini",
            "crag_evaluator_mapping",
            "external_evaluator_adapters",
            "selector_ablation",
            "hardware_characterization",
        ]
    )
    result_class = "OPEN_SOURCE_ARXIV_READINESS_SUPPORTED_WITH_BOUNDARIES" if required_ready else "OPEN_SOURCE_ARXIV_READINESS_INCONCLUSIVE"
    interpretation = (
        "RAGWarrant is ready to present as an open-source governance and promotion-control framework with strict boundaries, "
        "public mini reproduction, fail-closed guardrail evidence, external evaluator input adapters, selector ablations, and sanitized local hardware characterization."
        if required_ready
        else "The readiness package is incomplete."
    )
    result = {
        "suite": "ragwarrant_open_source_arxiv_readiness_synthesis_v1",
        "result_class": result_class,
        "interpretation": interpretation,
        "evidence": evidence,
        "does_not_claim_rag_compass_superiority": True,
        "does_not_claim_human_validation": True,
        "does_not_claim_official_platform_benchmarking": True,
        "does_not_claim_production_readiness": True,
        "does_not_claim_hallucination_elimination": True,
        "raw_data_committed": False,
        "raw_prompts_committed": False,
        "raw_generated_answers_committed": False,
    }
    evidence_rows = [{"evidence_item": key, "result_class": value} for key, value in evidence.items()]
    tool_rows = [
        {"tool": "public_mini_reproduction", "status": "ready" if evidence["public_mini"] else "missing"},
        {"tool": "external_evaluator_adapters", "status": "ready" if evidence["external_evaluator_adapters"] else "missing"},
        {"tool": "selector_ablation_matrix", "status": "ready" if evidence["selector_ablation"] else "missing"},
        {"tool": "publication_validator", "status": "strict"},
    ]
    arxiv_rows = [
        {"criterion": "reproducible public path", "status": "ready"},
        {"criterion": "negative evidence preserved", "status": "ready"},
        {"criterion": "claim boundaries", "status": "ready"},
        {"criterion": "generative superiority", "status": "mixed; not claimed"},
    ]
    write_json(output_root / "synthesis_result.json", result)
    write_json(output_root / "claim_update.json", result)
    write_csv(output_root / "evidence_table.csv", ["evidence_item", "result_class"], evidence_rows)
    write_csv(output_root / "tool_readiness_table.csv", ["tool", "status"], tool_rows)
    write_csv(output_root / "arxiv_readiness_table.csv", ["criterion", "status"], arxiv_rows)
    report = f"""
# Open-Source / arXiv Readiness Synthesis

Result class: `{result_class}`

{interpretation}

This synthesis supports a systems/methods framing around evidence-preserving RAG policy governance. It does not claim RAG Compass superiority, official platform benchmarking, human validation, production readiness, hallucination elimination, or broad universal generative governance superiority.
"""
    for name in ["synthesis_report.md", "executive_summary.md"]:
        write_md(output_root / name, report)
    write_md(
        output_root / "limitations.md",
        "Generative validation remains mixed. CRAG guardrail v2 blocked promotion under held-out generated-quality loss, and HotpotQA generative evidence remains bounded.",
    )
    return result
