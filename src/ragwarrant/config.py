from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SuiteConfig:
    suite: str
    seed: int
    dataset: dict[str, Any]
    policy_space: dict[str, list[Any]]
    objectives: dict[str, Any]
    baselines: list[str]
    certificate: dict[str, Any]
    output: dict[str, Any]
    raw: dict[str, Any]

    @classmethod
    def from_path(cls, path: Path) -> SuiteConfig:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            suite=str(raw.get("suite", path.stem)),
            seed=int(raw.get("seed", 12345)),
            dataset=dict(raw.get("dataset") or {}),
            policy_space=dict(raw.get("policy_space") or {}),
            objectives=dict(raw.get("objectives") or {}),
            baselines=[str(item) for item in raw.get("baselines", [])],
            certificate=dict(raw.get("certificate") or {}),
            output=dict(raw.get("output") or {}),
            raw=raw,
        )


DEFAULT_POLICY_SPACE = {
    "top_k": [3, 5, 8],
    "reranker_enabled": [False, True],
    "citation_required": [False, True],
    "abstention_threshold": [0.2, 0.5, 0.8],
}

DEFAULT_BASELINES = [
    "static_default_rag_policy",
    "best_single_policy_on_validation",
    "uniform_random_search",
    "greedy_coordinate_search",
    "greedy_regression_aware_search",
    "optuna_tpe_optional",
    "bayesian_optimization_optional",
    "successive_halving_or_asha_optional",
    "retrieval_confidence_gating",
    "uncertainty_threshold_gating",
    "entropy_margin_gating",
    "ragwarrant_no_fork",
    "ragwarrant_adaptive_compute_optional",
    "ragwarrant_full_optional",
]

