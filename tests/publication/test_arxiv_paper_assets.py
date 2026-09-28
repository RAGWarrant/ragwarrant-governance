# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_paper_main_exists() -> None:
    assert (ROOT / "paper/main.tex").exists()


def test_paper_has_required_sections() -> None:
    text = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
    for section in [
        "Introduction",
        "Problem Statement",
        "Governance Model",
        "Policy Promotion and Refusal Taxonomy",
        "Claim-Boundary Validation",
        "External Evaluator Adapter Architecture",
        "Public Mini Reproduction",
        "Selector Ablation Matrix",
        "Generative Validation and Fail-Closed Results",
        "Docker and Deployment Readiness",
        "AIM Hardware Characterization",
        "Limitations",
        "Reproducibility",
        "Conclusion",
    ]:
        assert section in text


def test_paper_claim_boundaries_present() -> None:
    text = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
    assert "RAG Compass superiority is unsupported" in text
    assert "Production readiness is unsupported" in text


def test_paper_tables_exist() -> None:
    for name in [
        "result_taxonomy_table.tex",
        "claim_boundary_table.tex",
        "selector_ablation_summary.tex",
        "deployment_readiness_table.tex",
        "reproducibility_table.tex",
    ]:
        assert (ROOT / "paper/tables" / name).exists()


def test_paper_does_not_claim_rag_compass_superiority() -> None:
    assert "RAG Compass is proven superior" not in (ROOT / "paper/main.tex").read_text(encoding="utf-8")


def test_paper_does_not_claim_production_readiness() -> None:
    assert "production validated" not in (ROOT / "paper/main.tex").read_text(encoding="utf-8").lower()
