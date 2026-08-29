from __future__ import annotations

from pathlib import Path
from typing import Any

from ragwarrant.config import SuiteConfig
from ragwarrant.end_to_end import mini_corpus
from ragwarrant.experiments.common import finalize_policy_suite
from ragwarrant.robustness import perturb_corpus, perturb_query, security_violation


def robustness_payload(seed: int) -> dict[str, Any]:
    families = ["duplicate_documents", "contradictory_sources", "prompt_injection", "ocr_corruption"]
    corpus = mini_corpus()
    return {
        "corpus_perturbations": {
            family: sorted(perturb_corpus(corpus, family=family, seed=seed).keys())
            for family in families
        },
        "query_perturbations": {
            family: perturb_query("What does RAGWarrant optimize?", family=family, seed=seed)
            for family in ["typos", "false_premise", "very_long", "unanswerable"]
        },
        "security_violation_blocks_promotion": security_violation(
            "The answer contains SECRET_API_KEY_PLACEHOLDER."
        ),
    }


def run(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    return finalize_policy_suite(
        cfg=cfg,
        config_path=config_path,
        output_dir=output_dir,
        run_id=run_id,
        resume=resume,
        force_new_run_id=force_new_run_id,
        robustness_report=robustness_payload(cfg.seed),
    )

