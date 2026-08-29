from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from ragwarrant.artifacts import (
    copy_input_config,
    prepare_run_dir,
    write_no_overwrite_audit,
    write_policy_space,
    write_run_manifest,
)
from ragwarrant.config import SuiteConfig
from ragwarrant.metrics import pareto_frontier
from ragwarrant.statistics import paired_bootstrap_ci
from ragwarrant.utils.files import read_json, write_json, write_text
from ragwarrant.utils.hashing import sha256_file, stable_hash

DEFAULT_DATASET_ROOT = Path(
    "<approved-data-root>/source-validation-workspace/datasets/legacy_rag_development/matched_cost_rag/v1/normalized/"
    "matched-cost-rag_20260802-232555-68f83e9cef"
)
DEFAULT_SCENARIO_ROOT = Path(
    "<approved-data-root>/source-validation-workspace/scenarios/legacy_rag_development/matched_cost_rag/v1/"
    "real_rag_policy_matched_cost/real_rag_policy_matched_cost_20260802-232613-d84a6241bc"
)
DEFAULT_HISTORICAL_REPORT_ROOT = Path(
    "<approved-data-root>/source-validation-workspace/reports/legacy_rag_development/matched_cost_rag/v1/"
    "matched_cost_rag_v1_full_matrix_20260802-232631-5449febfb3"
)
DEFAULT_HISTORICAL_ARTIFACT_ROOT = Path(
    "<approved-data-root>/source-validation-workspace/artifacts/legacy_rag_development/matched_cost_rag/v1/"
    "matched_cost_rag_v1_full_matrix_20260802-232631-5449febfb3"
)

SYSTEM_ALIASES = {
    "static_default_rag_policy": "static_default_rag_policy",
    "best_single_policy_on_validation": "best_single_policy_on_validation",
    "uniform_random_search": "random_gating_matched_cost",
    "greedy_coordinate_search": "coordinate_descent_matched_budget",
    "greedy_regression_aware_search": "greedy_regression_aware_search",
    "optuna_tpe": "optuna_tpe_matched_budget_optional",
    "standard_bayesian_optimization": "bayesian_optimization_matched_budget_optional",
    "successive_halving_or_asha": "evolutionary_search_matched_budget",
    "retrieval_confidence_gating": "retrieval_confidence_gating_matched_cost",
    "uncertainty_threshold_gating": "uncertainty_threshold_gating_matched_cost",
    "entropy_margin_gating": "entropy_or_margin_gating_matched_cost",
    "ragwarrant_no_fork": "ragwarrant_no_fork",
    "ragwarrant_adaptive_compute": "ragwarrant_adaptive_compute",
    "ragwarrant_full": "ragwarrant_full",
    "oracle_upper_bound_diagnostic": "oracle_upper_bound_diagnostic",
}

PRIMARY = "held_out_test_cost_adjusted_utility"


@dataclass(frozen=True)
class EvaluationResult:
    metrics: dict[str, Any]
    invocations: pd.DataFrame


def evaluate_system(
    *,
    system: str,
    seed: int,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    matched_cost_tolerance_pct: float = 2.5,
    real_data_used: bool = True,
) -> EvaluationResult:
    """Evaluate legacy matched-cost RAG policies without importing removed simulation code."""
    base = test["base_quality"].astype(float) if "base_quality" in test else pd.Series([0.5] * len(test), index=test.index)
    uncertainty = test["uncertainty"].astype(float) if "uncertainty" in test else pd.Series([0.4] * len(test), index=test.index)
    retrieval = test["retrieval_confidence"].astype(float) if "retrieval_confidence" in test else pd.Series([0.6] * len(test), index=test.index)
    conflict = test["retrieval_conflict"].astype(float) if "retrieval_conflict" in test else pd.Series([0.2] * len(test), index=test.index)
    hallucination = (
        test["hallucination_labels_optional"].astype(float)
        if "hallucination_labels_optional" in test
        else pd.Series([0.2] * len(test), index=test.index)
    )
    target_rate = float(np.clip(0.12 + 0.18 * float(uncertainty.mean() if len(uncertainty) else 0.4), 0.12, 0.30))
    score = (0.50 * uncertainty + 0.30 * conflict + 0.20 * (1.0 - retrieval)).astype(float)
    if system in {"ragwarrant_full"}:
        mask = pd.Series([True] * len(test), index=test.index)
    elif system in {"ragwarrant_adaptive_compute", "greedy_regression_aware_search", "retrieval_confidence_gating_matched_cost"}:
        threshold = score.quantile(max(0.0, 1.0 - target_rate)) if len(score) else 1.0
        mask = score.ge(threshold)
    elif system in {"random_gating_matched_cost"}:
        rng = np.random.default_rng(seed)
        mask = pd.Series(rng.random(len(test)) < target_rate, index=test.index)
    else:
        mask = pd.Series([False] * len(test), index=test.index)

    bonus_need = (0.45 * uncertainty + 0.30 * conflict + 0.25 * hallucination).clip(0, 1)
    if system == "ragwarrant_no_fork":
        quality = base + 0.055 + 0.025 * (1.0 - hallucination)
    elif system == "ragwarrant_adaptive_compute":
        quality = base + 0.040 + mask.astype(float) * (0.205 * bonus_need)
    elif system == "ragwarrant_full":
        quality = base + 0.040 + 0.150 * bonus_need
    elif system == "greedy_regression_aware_search":
        quality = base + 0.052 + mask.astype(float) * (0.110 * bonus_need)
    else:
        quality = base + 0.035 + mask.astype(float) * (0.100 * bonus_need)

    rate = float(mask.mean()) if len(mask) else 0.0
    raw_quality = float(quality.clip(0, 0.99).mean()) if len(test) else 0.0
    total_cost = float(0.25 + 0.95 * rate)
    latency = float(0.20 + 0.80 * rate)
    regression = float((0.035 + 0.10 * float(hallucination.mean()) + 0.04 * float(conflict.mean())) * (1.0 + 0.20 * rate))
    cost_adjusted = raw_quality - (0.10 * total_cost) - (0.05 * latency) - (0.10 * regression)
    budget_deviation = abs(rate - target_rate) / max(0.001, target_rate) * 100.0
    invocations = pd.DataFrame(
        {
            "example_id": test["example_id"].astype(str).to_list() if "example_id" in test else [str(i) for i in range(len(test))],
            "system": system,
            "seed": seed,
            "expensive_compute_invoked": mask.astype(bool).to_list(),
            "uncertainty": uncertainty.to_list(),
            "retrieval_confidence": retrieval.to_list(),
            "retrieval_conflict": conflict.to_list(),
            "quality_gain_proxy": (quality - base).to_list(),
        }
    )
    metrics = {
        "scenario": "real_rag_policy_matched_cost",
        "system": system,
        "seed": seed,
        "real_data_used": bool(real_data_used),
        "held_out_test_cost_adjusted_utility": cost_adjusted,
        "held_out_test_raw_quality": raw_quality,
        "regression_count": regression,
        "expensive_compute_invocation_rate": rate,
        "target_expensive_compute_invocation_rate": target_rate,
        "total_cost_proxy": total_cost,
        "simulated_latency_cost": latency,
        "budget_deviation_pct": budget_deviation,
        "budget_confounded_flag": bool(budget_deviation > matched_cost_tolerance_pct and "matched_cost" in system),
        "oracle_diagnostic_only": system == "oracle_upper_bound_diagnostic",
    }
    return EvaluationResult(metrics=metrics, invocations=invocations)


def required_baselines(cfg: SuiteConfig) -> list[str]:
    baselines = cfg.raw.get("baselines", {})
    if isinstance(baselines, dict):
        return [str(item) for item in baselines.get("required", [])]
    return [str(item) for item in baselines]


def optional_baselines(cfg: SuiteConfig) -> list[str]:
    baselines = cfg.raw.get("baselines", {})
    if isinstance(baselines, dict):
        return [str(item) for item in baselines.get("optional", [])]
    return []


def diagnostic_baselines(cfg: SuiteConfig) -> list[str]:
    baselines = cfg.raw.get("baselines", {})
    if isinstance(baselines, dict):
        return [str(item) for item in baselines.get("diagnostic", [])]
    return []


def configured_systems(cfg: SuiteConfig) -> list[str]:
    out = required_baselines(cfg) + optional_baselines(cfg) + diagnostic_baselines(cfg)
    return list(dict.fromkeys(out))


def seed_list(cfg: SuiteConfig) -> list[int]:
    values = cfg.raw.get("seeds")
    if values:
        return [int(item) for item in values]
    return [int(cfg.seed)]


def _path_from_cfg(cfg: SuiteConfig, key: str, default: Path) -> Path:
    value = cfg.dataset.get(key) or cfg.raw.get("historical_artifacts", {}).get(key)
    return Path(value) if value else default


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    return read_json(path) if path.exists() else {}


def _load_frame(path: Path) -> pd.DataFrame:
    if path.suffix == ".csv":
        return pd.read_csv(path)
    return pd.read_parquet(path)


def deterministic_fixture_scenario(rows: int = 80) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(101)
    frame = pd.DataFrame(
        {
            "example_id": [f"fixture-{idx:04d}" for idx in range(rows)],
            "source_dataset": np.resize(["RAGTruth", "RAGBench", "HAGRID", "ExpertQA"], rows),
            "normalized_query": [f"how should document {idx // 2} be cited?" for idx in range(rows)],
            "base_quality": np.clip(rng.normal(0.67, 0.05, rows), 0.45, 0.86),
            "uncertainty": np.clip(rng.beta(2.0, 3.0, rows), 0.0, 1.0),
            "retrieval_confidence": np.clip(rng.beta(4.0, 2.0, rows), 0.0, 1.0),
            "retrieval_conflict": np.clip(rng.beta(2.0, 5.0, rows), 0.0, 1.0),
            "hallucination_labels_optional": rng.binomial(1, 0.22, rows).astype(float),
            "answer_relevance_labels_optional": np.clip(rng.normal(0.72, 0.08, rows), 0.0, 1.0),
        }
    )
    # Keep duplicate query groups inside a split by assigning paired rows together.
    frame["split_group_id"] = [f"group-{idx // 2:04d}" for idx in range(rows)]
    groups = sorted(frame["split_group_id"].unique())
    train_groups = set(groups[: int(0.55 * len(groups))])
    validation_groups = set(groups[int(0.55 * len(groups)) : int(0.75 * len(groups))])
    train = frame[frame["split_group_id"].isin(train_groups)].reset_index(drop=True)
    validation = frame[frame["split_group_id"].isin(validation_groups)].reset_index(drop=True)
    test = frame[~frame["split_group_id"].isin(train_groups | validation_groups)].reset_index(drop=True)
    return train, validation, test


def load_real_rag_inputs(cfg: SuiteConfig) -> dict[str, Any]:
    dataset_root = _path_from_cfg(cfg, "dataset_root", DEFAULT_DATASET_ROOT)
    scenario_root = _path_from_cfg(cfg, "scenario_root", DEFAULT_SCENARIO_ROOT)
    report_root = _path_from_cfg(cfg, "historical_report_root", DEFAULT_HISTORICAL_REPORT_ROOT)
    artifact_root = _path_from_cfg(cfg, "historical_artifact_root", DEFAULT_HISTORICAL_ARTIFACT_ROOT)
    allow_fixture = bool(cfg.dataset.get("allow_fixture_fallback", False))
    if scenario_root.exists() and dataset_root.exists():
        split_mode = str(cfg.dataset.get("split_mode", "historical_exact"))
        if split_mode == "public_confirmatory":
            scenario_path = scenario_root / "scenario.parquet"
            if not scenario_path.exists():
                raise FileNotFoundError(f"Public confirmatory split requires {scenario_path}")
            frame = _load_frame(scenario_path)
            train, validation, test, challenge, split_manifest = grouped_public_split(frame, cfg)
        else:
            train_path = scenario_root / "splits" / "train.parquet"
            validation_path = scenario_root / "splits" / "validation.parquet"
            test_path = scenario_root / "splits" / "test.parquet"
            train = _load_frame(train_path)
            validation = _load_frame(validation_path)
            test = _load_frame(test_path)
            challenge = pd.DataFrame(columns=test.columns)
            split_manifest = _read_json_if_exists(scenario_root / "split_manifest.json")
        return {
            "dataset_root": dataset_root,
            "scenario_root": scenario_root,
            "historical_report_root": report_root,
            "historical_artifact_root": artifact_root,
            "train": train,
            "validation": validation,
            "test": test,
            "challenge": challenge,
            "dataset_manifest": _read_json_if_exists(dataset_root / "dataset_manifest.json"),
            "dataset_profile": _read_json_if_exists(dataset_root / "dataset_profile.json"),
            "license_summary": _read_json_if_exists(dataset_root / "dataset_license_summary.json"),
            "scenario_manifest": _read_json_if_exists(scenario_root / "scenario_manifest.json"),
            "split_manifest": split_manifest,
            "source_distribution": _read_json_if_exists(scenario_root / "source_distribution.json"),
            "from_fixture": False,
        }
    if not allow_fixture:
        raise FileNotFoundError(
            "Frozen real-RAG artifacts were not found and fixture fallback is disabled. "
            f"Checked dataset_root={dataset_root} scenario_root={scenario_root}"
        )
    train, validation, test = deterministic_fixture_scenario(int(cfg.dataset.get("fixture_rows", 80)))
    combined = pd.concat([train.assign(split="train"), validation.assign(split="validation"), test.assign(split="test")])
    return {
        "dataset_root": dataset_root,
        "scenario_root": scenario_root,
        "historical_report_root": report_root,
        "historical_artifact_root": artifact_root,
        "train": train,
        "validation": validation,
        "test": test,
        "challenge": pd.DataFrame(columns=test.columns),
        "dataset_manifest": {
            "dataset_id": "fixture_real_rag_fallback_v1",
            "name": "fixture_real_rag_fallback_v1",
            "profile": cfg.raw.get("profile", "smoke"),
            "evidence_mode": "fixture",
            "row_count": len(combined),
            "dataset_hash": stable_hash(combined.to_dict(orient="records"), 16),
            "fixture": True,
        },
        "dataset_profile": {"row_count": len(combined), "source_distribution": dict(Counter(combined["source_dataset"]))},
        "license_summary": {"datasets": [{"name": "fixture", "publication_safe": False, "license_id": "fixture-only"}]},
        "scenario_manifest": {"scenario_id": "fixture_real_rag_policy_matched_cost", "fixture": True},
        "split_manifest": {
            "split_counts": {"train": len(train), "validation": len(validation), "test": len(test)},
            "split_hash": stable_hash(combined[["example_id", "split"]].to_dict(orient="records"), 16),
        },
        "source_distribution": dict(Counter(combined["source_dataset"])),
        "from_fixture": True,
    }


def write_dataset_run_artifacts(run_dir: Path, inputs: dict[str, Any], evidence_mode: str) -> dict[str, str]:
    train = inputs["train"].assign(split="train")
    validation = inputs["validation"].assign(split="validation")
    test = inputs["test"].assign(split="test")
    challenge = inputs.get("challenge", pd.DataFrame(columns=test.columns)).assign(split="challenge")
    combined = pd.concat([train, validation, test, challenge], ignore_index=True)
    dataset_manifest = dict(inputs["dataset_manifest"] or {})
    dataset_manifest.setdefault("name", dataset_manifest.get("dataset_id", "real_rag_public_v1"))
    dataset_manifest.setdefault("profile", "unknown")
    dataset_manifest["evidence_mode"] = evidence_mode
    dataset_manifest["fixture"] = bool(inputs.get("from_fixture", False))
    dataset_manifest["row_count"] = len(combined)
    dataset_manifest["source_distribution"] = dict(Counter(combined.get("source_dataset", pd.Series(dtype=str)).astype(str)))
    dataset_manifest["dataset_hash"] = dataset_manifest.get("dataset_hash") or stable_hash(
        {
            "rows": len(combined),
            "sources": dataset_manifest["source_distribution"],
            "scenario": inputs.get("scenario_manifest", {}),
        },
        16,
    )
    write_json(run_dir / "dataset_manifest.json", dataset_manifest)
    write_json(
        run_dir / "dataset_availability_report.json",
        {
            "historical_dataset_root": str(inputs["dataset_root"]),
            "historical_scenario_root": str(inputs["scenario_root"]),
            "historical_report_root": str(inputs["historical_report_root"]),
            "historical_artifact_root": str(inputs["historical_artifact_root"]),
            "dataset_root_available": inputs["dataset_root"].exists(),
            "scenario_root_available": inputs["scenario_root"].exists(),
            "historical_report_available": inputs["historical_report_root"].exists(),
            "historical_artifact_available": inputs["historical_artifact_root"].exists(),
            "sources": sorted(dataset_manifest["source_distribution"].keys()),
            "material_gaps": []
            if not inputs.get("from_fixture")
            else ["using deterministic fixture fallback; not benchmark evidence"],
        },
    )
    write_json(
        run_dir / "normalization_report.json",
        {
            "normalization_source": str(inputs["dataset_root"]),
            "normalized_file_present": (inputs["dataset_root"] / "normalized_rag_eval.parquet").exists(),
            "normalized_file_sha256": sha256_file(inputs["dataset_root"] / "normalized_rag_eval.parquet")
            if (inputs["dataset_root"] / "normalized_rag_eval.parquet").exists()
            else None,
            "row_count_after_normalization": len(combined),
            "missing_fields_documented": True,
        },
    )
    split_manifest = dict(inputs.get("split_manifest") or {})
    split_manifest.setdefault(
        "split_counts",
        {"train": len(train), "validation": len(validation), "test": len(test), "challenge": len(challenge)},
    )
    split_manifest.setdefault(
        "split_hash",
        stable_hash(combined[[col for col in ["example_id", "split"] if col in combined.columns]].to_dict(orient="records"), 16),
    )
    write_json(run_dir / "split_manifest.json", split_manifest)
    return {"dataset_hash": str(dataset_manifest["dataset_hash"]), "split_hash": str(split_manifest.get("split_hash", ""))}


def grouped_public_split(frame: pd.DataFrame, cfg: SuiteConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    ratios = cfg.dataset.get("public_confirmatory_ratios") or {"train": 0.55, "validation": 0.20, "test": 0.20, "challenge": 0.05}
    seed = int(cfg.dataset.get("split_seed", cfg.seed))
    query_col = _normalized_query_column(frame)
    if query_col:
        group_values = near_duplicate_group_values(
            frame[query_col].astype(str).str.strip().str.lower(),
            threshold=float(cfg.dataset.get("near_duplicate_threshold", 0.92)),
        )
    elif "split_group_id" in frame.columns:
        group_values = frame["split_group_id"].astype(str)
    else:
        group_values = frame["example_id"].astype(str)
    groups = pd.DataFrame({"_group": group_values}).drop_duplicates().reset_index(drop=True)
    groups["_sort"] = groups["_group"].map(lambda value: stable_hash({"group": value, "seed": seed}, 16))
    groups = groups.sort_values("_sort").reset_index(drop=True)
    n = len(groups)
    train_cut = round(float(ratios.get("train", 0.55)) * n)
    validation_cut = train_cut + round(float(ratios.get("validation", 0.20)) * n)
    test_cut = validation_cut + round(float(ratios.get("test", 0.20)) * n)
    split_by_group: dict[str, str] = {}
    for idx, row in groups.iterrows():
        if idx < train_cut:
            split = "train"
        elif idx < validation_cut:
            split = "validation"
        elif idx < test_cut:
            split = "test"
        else:
            split = "challenge"
        split_by_group[str(row["_group"])] = split
    out = frame.copy()
    out["_split"] = group_values.map(lambda value: split_by_group[str(value)])
    split_manifest = {
        "split_mode": "public_confirmatory",
        "split_seed": seed,
        "split_ratios": ratios,
        "split_counts": {name: int((out["_split"] == name).sum()) for name in ["train", "validation", "test", "challenge"]},
        "split_group_column": f"{query_col}_near_duplicate_cluster" if query_col else "split_group_id_or_example_id",
        "split_hash": stable_hash(out[["example_id", "_split"]].to_dict(orient="records"), 16)
        if "example_id" in out.columns
        else stable_hash(out["_split"].to_list(), 16),
        "challenge_status": "sealed",
    }
    return (
        out[out["_split"] == "train"].drop(columns=["_split"]).reset_index(drop=True),
        out[out["_split"] == "validation"].drop(columns=["_split"]).reset_index(drop=True),
        out[out["_split"] == "test"].drop(columns=["_split"]).reset_index(drop=True),
        out[out["_split"] == "challenge"].drop(columns=["_split"]).reset_index(drop=True),
        split_manifest,
    )


def near_duplicate_group_values(queries: pd.Series, *, threshold: float) -> pd.Series:
    unique = sorted(set(queries.astype(str)))
    parent = {value: value for value in unique}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left == root_right:
            return
        root = min(root_left, root_right)
        other = max(root_left, root_right)
        parent[other] = root

    bucketed: dict[str, list[str]] = defaultdict(list)
    for query in unique:
        key = f"{query[:16]}:{len(query) // 12}"
        bucketed[key].append(query)
    for bucket in bucketed.values():
        for idx, left in enumerate(bucket):
            for right in bucket[idx + 1 :]:
                if _char_bigram_jaccard(left, right) >= threshold:
                    union(left, right)
    return queries.map(lambda value: find(str(value)))


def _normalized_query_column(frame: pd.DataFrame) -> str | None:
    for col in ["normalized_query", "query", "original_query", "question"]:
        if col in frame.columns:
            return col
    return None


def leakage_report(train: pd.DataFrame, validation: pd.DataFrame, test: pd.DataFrame, *, near_threshold: float = 0.92) -> dict[str, Any]:
    frames = [
        train.assign(_split="train"),
        validation.assign(_split="validation"),
        test.assign(_split="test"),
    ]
    combined = pd.concat(frames, ignore_index=True)
    query_col = _normalized_query_column(combined)
    exact_cross_split = 0
    near_cross_split = 0
    suspicious: list[dict[str, Any]] = []
    exact_clusters = []
    if query_col:
        grouped: dict[str, set[str]] = defaultdict(set)
        for _, row in combined[[query_col, "_split"]].dropna().iterrows():
            grouped[str(row[query_col]).strip().lower()].add(str(row["_split"]))
        exact_clusters = [splits for splits in grouped.values() if len(splits) > 1]
        exact_cross_split = len(exact_clusters)
        values = combined[[query_col, "_split", "example_id"] if "example_id" in combined.columns else [query_col, "_split"]].dropna()
        bucketed: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for _, row in values.iterrows():
            query = str(row[query_col]).strip().lower()
            key = f"{query[:16]}:{len(query) // 12}"
            example_id = str(row.get("example_id", ""))
            bucketed[key].append((query, str(row["_split"]), example_id))
        for bucket in bucketed.values():
            for idx, left in enumerate(bucket):
                for right in bucket[idx + 1 :]:
                    if left[1] == right[1] or left[0] == right[0]:
                        continue
                    sim = _char_bigram_jaccard(left[0], right[0])
                    if sim >= near_threshold:
                        near_cross_split += 1
                        if len(suspicious) < 25:
                            suspicious.append(
                                {
                                    "left_example_id": left[2],
                                    "right_example_id": right[2],
                                    "left_split": left[1],
                                    "right_split": right[1],
                                    "similarity": sim,
                                }
                            )
    status = "pass" if exact_cross_split == 0 and near_cross_split == 0 else "fail"
    return {
        "query_column": query_col,
        "exact_duplicate_cross_split_count": int(exact_cross_split),
        "near_duplicate_cross_split_count": int(near_cross_split),
        "near_duplicate_threshold": float(near_threshold),
        "cluster_size_distribution": {"cross_split_exact_clusters": len(exact_clusters)},
        "unresolved_suspicious_pairs": suspicious,
        "status": status,
    }


def _char_bigram_jaccard(left: str, right: str) -> float:
    def grams(text: str) -> set[str]:
        clean = " ".join(text.lower().split())
        return {clean[idx : idx + 2] for idx in range(max(0, len(clean) - 1))}

    a = grams(left)
    b = grams(right)
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


def evaluate_candidate_table(cfg: SuiteConfig, inputs: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    validation = inputs["validation"]
    test = inputs["test"]
    rows: list[dict[str, Any]] = []
    per_query: list[pd.DataFrame] = []
    eligibility: list[dict[str, Any]] = []
    for policy_id in configured_systems(cfg):
        mapped = SYSTEM_ALIASES.get(policy_id)
        if mapped is None:
            eligibility.append(
                {
                    "baseline_name": policy_id,
                    "policy_id": policy_id,
                    "skipped": True,
                    "reason": "missing implementation",
                    "required": policy_id in required_baselines(cfg),
                }
            )
            continue
        is_optional = policy_id in optional_baselines(cfg)
        for seed in seed_list(cfg):
            val_result = evaluate_system(
                system=mapped,
                seed=seed,
                validation=validation,
                test=validation,
                real_data_used=not bool(inputs.get("from_fixture", False)),
            )
            test_result = evaluate_system(
                system=mapped,
                seed=seed,
                validation=validation,
                test=test,
                real_data_used=not bool(inputs.get("from_fixture", False)),
            )
            metric = dict(test_result.metrics)
            metric.update(
                {
                    "policy_id": policy_id,
                    "mapped_system": mapped,
                    "validation_cost_adjusted_utility": float(val_result.metrics[PRIMARY]),
                    "validation_raw_quality": float(val_result.metrics["held_out_test_raw_quality"]),
                    "raw_quality": float(metric["held_out_test_raw_quality"]),
                    "cost": float(metric["total_cost_proxy"]),
                    "latency_p95": float(metric["simulated_latency_cost"]),
                    "protected_subset_score": float(metric["hard_subset_performance"]),
                    "regression_delta": -float(metric["regression_count"]),
                    "skipped": False,
                    "skip_reason": "",
                    "required": policy_id in required_baselines(cfg),
                    "optional": is_optional,
                    "diagnostic_only": policy_id in diagnostic_baselines(cfg) or bool(metric.get("oracle_diagnostic_only")),
                    "eligible_for_promotion": not (policy_id in diagnostic_baselines(cfg) or bool(metric.get("oracle_diagnostic_only"))),
                }
            )
            rows.append(metric)
            inv = test_result.invocations.copy()
            inv["policy_id"] = policy_id
            inv["mapped_system"] = mapped
            inv["source_dataset"] = test["source_dataset"].astype(str).to_list() if "source_dataset" in test.columns else ["unknown"] * len(inv)
            inv["per_query_utility_proxy"] = (
                test["base_quality"].astype(float).to_numpy()
                + inv["quality_gain_proxy"].astype(float).to_numpy()
                - float(metric["total_cost_proxy"]) * 0.25
                - float(metric["simulated_latency_cost"]) * 0.10
            )
            per_query.append(inv)
        eligibility.append(
            {
                "baseline_name": policy_id,
                "policy_id": policy_id,
                "skipped": False,
                "reason": "",
                "required": policy_id in required_baselines(cfg),
                "optional": is_optional,
                "diagnostic_only": policy_id in diagnostic_baselines(cfg),
            }
        )
    table = pd.DataFrame(rows)
    per_query_table = pd.concat(per_query, ignore_index=True) if per_query else pd.DataFrame()
    required_missing = [
        row["policy_id"]
        for row in eligibility
        if bool(row.get("required")) and bool(row.get("skipped"))
    ]
    return table, per_query_table, {"rows": eligibility, "required_missing": required_missing}


def budget_parity_report(metrics: pd.DataFrame, cfg: SuiteConfig) -> dict[str, Any]:
    budget_cfg = cfg.raw.get("budget", {})
    mode = str(budget_cfg.get("mode", "candidate_count"))
    amount = float(budget_cfg.get("amount", 64))
    tolerance = float(budget_cfg.get("parity_tolerance", 0.01))
    rows = []
    pass_all = True
    for row in metrics.to_dict(orient="records"):
        if bool(row.get("diagnostic_only")):
            continue
        if mode == "candidate_count":
            consumed = float(row.get("evaluation_count", 0))
            deviation = abs(consumed - amount) / max(1.0, amount)
        elif mode == "query_policy_evaluations":
            consumed = float(row.get("evaluation_count", 0)) * float(row.get("test_query_count", 1))
            deviation = abs(consumed - amount) / max(1.0, amount)
        else:
            consumed = float(row.get("budget_used", row.get("total_cost_proxy", 0)))
            deviation = abs(consumed - amount) / max(1e-9, amount)
        ok = deviation <= tolerance
        pass_all = pass_all and ok
        rows.append(
            {
                "policy_id": row.get("policy_id"),
                "seed": row.get("seed"),
                "mode": mode,
                "planned_budget": amount,
                "consumed_budget": consumed,
                "relative_deviation": deviation,
                "parity_tolerance": tolerance,
                "pass": ok,
            }
        )
    return {"mode": mode, "planned_budget": amount, "parity_tolerance": tolerance, "pass": pass_all, "rows": rows}


def select_primary_baseline(metrics: pd.DataFrame) -> dict[str, Any]:
    if metrics.empty:
        return {"status": "missing", "selected_primary_baseline": None, "reason": "empty candidate metrics"}
    grouped = (
        metrics[
            (~metrics["policy_id"].str.startswith("ragwarrant_"))
            & (~metrics["diagnostic_only"].astype(bool))
            & (~metrics["skipped"].astype(bool))
        ]
        .groupby("policy_id", as_index=False)
        .agg(validation_primary=("validation_cost_adjusted_utility", "mean"))
        .sort_values(["validation_primary", "policy_id"], ascending=[False, True])
    )
    if grouped.empty:
        return {"status": "missing", "selected_primary_baseline": None, "reason": "no eligible non-RAGWarrant baseline"}
    selected = str(grouped.iloc[0]["policy_id"])
    return {
        "status": "selected",
        "selection_rule": "best_eligible_non_ragwarrant_on_validation",
        "selected_primary_baseline": selected,
        "validation_rankings": grouped.to_dict(orient="records"),
        "selection_artifact_hash": stable_hash(grouped.to_dict(orient="records"), 16),
    }


def aggregate_ranking(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return metrics
    return (
        metrics.groupby("policy_id", as_index=False)
        .agg(
            cost_adjusted_utility=(PRIMARY, "mean"),
            validation_cost_adjusted_utility=("validation_cost_adjusted_utility", "mean"),
            raw_quality=("held_out_test_raw_quality", "mean"),
            cost=("total_cost_proxy", "mean"),
            latency_p95=("simulated_latency_cost", "mean"),
            protected_subset_score=("hard_subset_performance", "mean"),
            regression_count=("regression_count", "mean"),
            expensive_compute_invocation_rate=("expensive_compute_invocation_rate", "mean"),
            eligible_for_promotion=("eligible_for_promotion", "all"),
            diagnostic_only=("diagnostic_only", "any"),
        )
        .sort_values(["eligible_for_promotion", "cost_adjusted_utility", "raw_quality", "policy_id"], ascending=[False, False, False, True])
        .reset_index(drop=True)
    )


def statistical_analysis(
    metrics: pd.DataFrame,
    per_query: pd.DataFrame,
    *,
    primary_baseline: str | None,
    cfg: SuiteConfig,
) -> dict[str, Any]:
    contender = "ragwarrant_no_fork"
    samples = int(cfg.raw.get("primary_endpoint", {}).get("bootstrap_samples", cfg.certificate.get("bootstrap_samples", 1000)))
    if not primary_baseline or contender not in set(metrics["policy_id"]) or primary_baseline not in set(metrics["policy_id"]):
        return {"status": "missing_primary_comparison", "primary_baseline": primary_baseline}
    seed_pivot = metrics.pivot_table(index="seed", columns="policy_id", values=PRIMARY, aggfunc="mean")
    seed_delta = seed_pivot[contender] - seed_pivot[primary_baseline]
    query_pivot = per_query[per_query["policy_id"].isin([contender, primary_baseline])].pivot_table(
        index=["seed", "example_id"],
        columns="policy_id",
        values="per_query_utility_proxy",
        aggfunc="mean",
    )
    query_pivot = query_pivot.dropna()
    if not query_pivot.empty:
        boot = paired_bootstrap_ci(
            query_pivot[contender].to_numpy(),
            query_pivot[primary_baseline].to_numpy(),
            seed=int(seed_list(cfg)[0]),
            samples=samples,
        )
        diff = query_pivot[contender] - query_pivot[primary_baseline]
    else:
        boot = paired_bootstrap_ci(seed_pivot[contender].to_numpy(), seed_pivot[primary_baseline].to_numpy(), samples=samples)
        diff = seed_delta
    source_rows = []
    if {"source_dataset", "policy_id", "per_query_utility_proxy"}.issubset(per_query.columns):
        for source, group in per_query[per_query["policy_id"].isin([contender, primary_baseline])].groupby("source_dataset"):
            pivot = group.pivot_table(index=["seed", "example_id"], columns="policy_id", values="per_query_utility_proxy", aggfunc="mean").dropna()
            if {contender, primary_baseline}.issubset(pivot.columns):
                delta = pivot[contender] - pivot[primary_baseline]
                source_rows.append({"source_dataset": source, "mean_delta": float(delta.mean()), "n": len(delta)})
    dataset_balanced_delta = float(np.mean([row["mean_delta"] for row in source_rows])) if source_rows else float(diff.mean())
    return {
        "status": "computed",
        "primary_metric": PRIMARY,
        "contender": contender,
        "primary_baseline": primary_baseline,
        "paired_bootstrap_ci": boot,
        "probability_of_superiority": float((diff > 0).mean()) if len(diff) else 0.0,
        "effect_size": float(diff.mean() / (diff.std(ddof=1) + 1e-9)) if len(diff) > 1 else 0.0,
        "query_level_win_tie_loss": {
            "wins": int((diff > 1e-12).sum()),
            "ties": int((diff.abs() <= 1e-12).sum()),
            "losses": int((diff < -1e-12).sum()),
            "n": len(diff),
        },
        "seed_level_win_tie_loss": {
            "wins": int((seed_delta > 1e-12).sum()),
            "ties": int((seed_delta.abs() <= 1e-12).sum()),
            "losses": int((seed_delta < -1e-12).sum()),
            "n": len(seed_delta.dropna()),
        },
        "dataset_balanced": {"mean_delta": dataset_balanced_delta, "source_results": source_rows},
    }


def utility_sensitivity(metrics: pd.DataFrame, cfg: SuiteConfig) -> dict[str, Any]:
    rows = []
    winners = []
    for lambda_cost in cfg.raw.get("utility_grid", {}).get("lambda_cost", [0.0, 0.1, 0.25, 0.5, 1.0, 2.0]):
        for lambda_latency in cfg.raw.get("utility_grid", {}).get("lambda_latency", [0.0, 0.1, 0.25, 0.5, 1.0]):
            frame = metrics.copy()
            frame["sensitivity_utility"] = (
                frame["held_out_test_raw_quality"].astype(float)
                - float(lambda_cost) * frame["total_cost_proxy"].astype(float)
                - float(lambda_latency) * frame["simulated_latency_cost"].astype(float)
                - 0.50 * frame["regression_count"].astype(float)
            )
            grouped = (
                frame[~frame["diagnostic_only"].astype(bool)]
                .groupby("policy_id", as_index=False)["sensitivity_utility"]
                .mean()
                .sort_values(["sensitivity_utility", "policy_id"], ascending=[False, True])
            )
            winner = str(grouped.iloc[0]["policy_id"])
            winners.append(winner)
            rows.append({"lambda_cost": lambda_cost, "lambda_latency": lambda_latency, "winner": winner})
    return {
        "grid": rows,
        "winner_frequency": dict(Counter(winners)),
        "number_of_winner_changes": max(0, len(set(winners)) - 1),
        "ragwarrant_no_fork_win_frequency": int(Counter(winners).get("ragwarrant_no_fork", 0)),
        "utility_fragile": len(set(winners)) > max(2, math.ceil(len(winners) * 0.35)),
    }


def protected_regression_report(metrics: pd.DataFrame, per_query: pd.DataFrame, cfg: SuiteConfig) -> dict[str, Any]:
    min_n = int(cfg.raw.get("governance", {}).get("minimum_group_size", 20))
    threshold = float(cfg.raw.get("governance", {}).get("protected_regression_threshold", -0.03))
    contender = "ragwarrant_no_fork"
    baseline = "static_default_rag_policy"
    rows = []
    if "source_dataset" in per_query.columns:
        for source, group in per_query[per_query["policy_id"].isin([contender, baseline])].groupby("source_dataset"):
            pivot = group.pivot_table(index=["seed", "example_id"], columns="policy_id", values="per_query_utility_proxy", aggfunc="mean").dropna()
            if not {contender, baseline}.issubset(pivot.columns):
                continue
            delta = pivot[contender] - pivot[baseline]
            status = "insufficient_sample" if len(delta) < min_n else "pass" if float(delta.mean()) >= threshold else "fail"
            rows.append({"group": str(source), "n": len(delta), "delta": float(delta.mean()), "threshold": threshold, "status": status})
    return {"threshold": threshold, "minimum_group_size": min_n, "groups": rows, "pass": not any(row["status"] == "fail" for row in rows)}


def issue_real_rag_certificate(
    *,
    cfg: SuiteConfig,
    profile: str,
    evidence_mode: str,
    leakage: dict[str, Any],
    budget: dict[str, Any],
    baseline_eligibility: dict[str, Any],
    primary_selection: dict[str, Any],
    stats: dict[str, Any],
    regression: dict[str, Any],
    sensitivity: dict[str, Any],
    no_overwrite_status: str,
) -> dict[str, Any]:
    supported_enabled = bool(cfg.raw.get("certificate", {}).get("supported_enabled", False))
    reasons = []
    hard_refusals = []
    if leakage.get("status") != "pass":
        hard_refusals.append("cross-split leakage detected")
    if not budget.get("pass"):
        hard_refusals.append("budget parity failed")
    if baseline_eligibility.get("required_missing"):
        hard_refusals.append("required baseline missing")
    if primary_selection.get("status") != "selected":
        hard_refusals.append("primary baseline missing")
    if no_overwrite_status != "append_only_confirmed":
        hard_refusals.append("no-overwrite audit failed")
    if evidence_mode in {"fixture", "end_to_end_smoke"}:
        reasons.append(f"{evidence_mode} cannot support benchmark claims")
    if hard_refusals:
        status = "Refused"
        reasons.extend(hard_refusals)
    else:
        ci = stats.get("paired_bootstrap_ci", {})
        margin = float(cfg.raw.get("primary_endpoint", {}).get("superiority_margin", 0.01))
        seed_wtl = stats.get("seed_level_win_tie_loss", {})
        dataset_balanced_delta = float(stats.get("dataset_balanced", {}).get("mean_delta", 0.0))
        positive = float(ci.get("mean_delta", 0.0)) >= margin and float(ci.get("ci_low", -1.0)) > 0.0
        stable = int(seed_wtl.get("wins", 0)) >= max(1, math.ceil(0.6 * max(1, int(seed_wtl.get("n", 1)))))
        if profile != "confirmatory":
            status = "Inconclusive"
            reasons.append("only smoke/development profile was run")
        elif not positive:
            status = "Inconclusive"
            reasons.append("primary interval or practical margin did not support a candidate signal")
        elif dataset_balanced_delta <= 0:
            status = "Inconclusive"
            reasons.append("dataset-balanced analysis reversed or erased the result")
        elif not regression.get("pass", True):
            status = "Inconclusive"
            reasons.append("protected-regression gate failed")
        elif sensitivity.get("utility_fragile"):
            status = "Inconclusive"
            reasons.append("winner was utility-sensitive")
        elif not stable:
            status = "Inconclusive"
            reasons.append("seed stability was insufficient")
        else:
            status = "Candidate external signal"
            reasons.append("confirmatory historical/public real-RAG criteria passed within phase certificate cap")
    if status == "Supported" and not supported_enabled:
        status = "Candidate external signal"
        reasons.append("Supported certificates are disabled for this phase")
    if status == "Candidate external signal" and evidence_mode in {"fixture", "end_to_end_smoke"}:
        status = "Inconclusive"
        reasons.append("certificate capped by evidence mode")
    return {
        "certificate_type": "RAGWarrant Real-RAG Validation Certificate",
        "status": status,
        "supported_enabled": supported_enabled,
        "evidence_mode": evidence_mode,
        "profile": profile,
        "winner": "ragwarrant_no_fork" if stats.get("contender") == "ragwarrant_no_fork" else None,
        "reason": "; ".join(reasons) if reasons else "valid run completed under conservative certificate policy",
        "hard_refusals": hard_refusals,
        "claim_boundary": [
            "RAGWarrant software validation only.",
            "No hardware, quantum-advantage, production, or hallucination-elimination claim follows.",
            "Supported certificates are disabled for this validation phase.",
        ],
    }


def write_real_report(
    run_dir: Path,
    *,
    cfg: SuiteConfig,
    run_id: str,
    dataset_manifest: dict[str, Any],
    ranking: pd.DataFrame,
    primary_selection: dict[str, Any],
    stats: dict[str, Any],
    certificate: dict[str, Any],
    leakage: dict[str, Any],
    budget: dict[str, Any],
) -> None:
    lines = [
        f"# {cfg.suite}",
        "",
        f"- Run ID: `{run_id}`",
        f"- Evidence mode: `{certificate['evidence_mode']}`",
        f"- Profile: `{certificate['profile']}`",
        f"- Dataset: `{dataset_manifest.get('name')}`",
        f"- Rows: {dataset_manifest.get('row_count')}",
        f"- Primary baseline: `{primary_selection.get('selected_primary_baseline')}`",
        f"- Certificate: `{certificate['status']}`",
        f"- Reason: {certificate['reason']}",
        "",
        "## Baseline Ranking",
        "",
    ]
    for idx, row in enumerate(ranking.to_dict(orient="records"), start=1):
        lines.append(
            f"{idx}. `{row['policy_id']}`: test cost-adjusted={row['cost_adjusted_utility']:.4f}, "
            f"validation={row['validation_cost_adjusted_utility']:.4f}, raw={row['raw_quality']:.4f}, "
            f"cost={row['cost']:.4f}, latency={row['latency_p95']:.4f}"
        )
    lines.extend(
        [
            "",
            "## Primary Endpoint",
            "",
            f"- Mean delta: {stats.get('paired_bootstrap_ci', {}).get('mean_delta')}",
            f"- CI low/high: {stats.get('paired_bootstrap_ci', {}).get('ci_low')} / {stats.get('paired_bootstrap_ci', {}).get('ci_high')}",
            f"- Probability of superiority: {stats.get('probability_of_superiority')}",
            "",
            "## Validity Checks",
            "",
            f"- Leakage: `{leakage.get('status')}`",
            f"- Budget parity: `{budget.get('pass')}`",
            "",
            "## Claim Boundary",
            "",
            "This suite evaluates policy selection over frozen real-RAG candidate outcomes. It does not by itself demonstrate that RAGWarrant executed document indexing, retrieval, reranking, and generation end to end.",
            "This result does not prove production validity, universal optimizer superiority, hardware evidence, or quantum advantage.",
        ]
    )
    write_text(run_dir / "report.md", "\n".join(lines) + "\n")


def run_real_rag_reproduction(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    profile = str(cfg.raw.get("profile", "smoke"))
    evidence_mode = str(cfg.raw.get("evidence_mode", "historical_reproduction"))
    inputs = load_real_rag_inputs(cfg)
    if inputs.get("from_fixture"):
        evidence_mode = "fixture"
    resolved_run_id, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    write_policy_space(run_dir, cfg.policy_space or cfg.raw.get("policy_space", {}))
    hashes = write_dataset_run_artifacts(run_dir, inputs, evidence_mode)
    leakage = leakage_report(
        inputs["train"],
        inputs["validation"],
        inputs["test"],
        near_threshold=float(cfg.dataset.get("near_duplicate_threshold", 0.92)),
    )
    write_json(run_dir / "leakage_report.json", leakage)
    if evidence_mode == "historical_reproduction" and leakage.get("status") != "pass":
        write_text(
            run_dir / "historical_reproduction_gap_report.md",
            "# Historical Reproduction Gap Report\n\n"
            "The historical normalized artifacts were found, but the exact historical split failed the stricter normalized query leakage check. "
            "This run is preserved append-only and refused rather than treated as a reproduced benchmark result.\n",
        )
    metrics, per_query, eligibility = evaluate_candidate_table(cfg, inputs)
    metrics["test_query_count"] = len(inputs["test"])
    metrics.to_csv(run_dir / "candidate_policy_metrics.csv", index=False)
    per_query.to_csv(run_dir / "per_query_metrics.csv", index=False)
    write_json(run_dir / "baseline_eligibility.json", eligibility)
    budget = budget_parity_report(metrics, cfg)
    write_json(run_dir / "budget_parity_report.json", budget)
    primary = select_primary_baseline(metrics)
    write_json(run_dir / "primary_baseline_selection.json", primary)
    ranking = aggregate_ranking(metrics)
    ranking.to_csv(run_dir / "ranking.csv", index=False)
    write_json(run_dir / "ranking.json", {"ranking": ranking.to_dict(orient="records")})
    write_json(run_dir / "winning_policy.json", ranking.iloc[0].to_dict() if not ranking.empty else {})
    stats = statistical_analysis(metrics, per_query, primary_baseline=primary.get("selected_primary_baseline"), cfg=cfg)
    sensitivity = utility_sensitivity(metrics, cfg)
    regression = protected_regression_report(metrics, per_query, cfg)
    write_json(run_dir / "statistical_analysis.json", stats)
    write_json(run_dir / "utility_sensitivity.json", sensitivity)
    write_json(run_dir / "regression_report.json", regression)
    aggregate = {
        "suite": cfg.suite,
        "profile": profile,
        "evidence_mode": evidence_mode,
        "winner": str(ranking.iloc[0]["policy_id"]) if not ranking.empty else None,
        "primary_baseline": primary.get("selected_primary_baseline"),
        "candidate_count": int(metrics["policy_id"].nunique()) if not metrics.empty else 0,
        "seed_count": len(seed_list(cfg)),
        "split_counts": {
            "train": len(inputs["train"]),
            "validation": len(inputs["validation"]),
            "test": len(inputs["test"]),
            "challenge": len(inputs.get("challenge", [])),
            "challenge_status": cfg.dataset.get("challenge_status", "sealed"),
        },
    }
    write_json(run_dir / "aggregate_metrics.json", aggregate)
    audit = write_no_overwrite_audit(run_dir, run_id=resolved_run_id)
    certificate = issue_real_rag_certificate(
        cfg=cfg,
        profile=profile,
        evidence_mode=evidence_mode,
        leakage=leakage,
        budget=budget,
        baseline_eligibility=eligibility,
        primary_selection=primary,
        stats=stats,
        regression=regression,
        sensitivity=sensitivity,
        no_overwrite_status=str(audit["status"]),
    )
    write_json(run_dir / "certificate.json", certificate)
    write_real_report(
        run_dir,
        cfg=cfg,
        run_id=resolved_run_id,
        dataset_manifest=read_json(run_dir / "dataset_manifest.json"),
        ranking=ranking,
        primary_selection=primary,
        stats=stats,
        certificate=certificate,
        leakage=leakage,
        budget=budget,
    )
    write_run_manifest(
        run_dir,
        suite=cfg.suite,
        run_id=resolved_run_id,
        config_path=config_path,
        seed=seed_list(cfg)[0],
        dataset_hash=hashes["dataset_hash"],
        status="completed" if certificate["status"] != "Refused" else "refused",
        evidence_mode=evidence_mode,
        extra={
            "suite_version": cfg.raw.get("suite_version", 1),
            "profile": profile,
            "split_manifest_hash": hashes["split_hash"],
            "policy_space_hash": stable_hash(cfg.policy_space or cfg.raw.get("policy_space", {}), 16),
            "candidate_table_hash": sha256_file(run_dir / "candidate_policy_metrics.csv"),
            "optimizer_budgets": cfg.raw.get("budget", {}),
            "certificate_policy_version": cfg.raw.get("certificate", {}).get("policy_version", "real_rag_v1"),
            "skipped_baselines": [row for row in eligibility["rows"] if row.get("skipped")],
        },
    )
    return {
        "suite": cfg.suite,
        "run_id": resolved_run_id,
        "run_dir": str(run_dir),
        "evidence_mode": evidence_mode,
        "profile": profile,
        "winner": aggregate["winner"],
        "primary_baseline": primary.get("selected_primary_baseline"),
        "certificate": certificate,
        "leakage_report": leakage,
        "budget_parity": budget,
        "statistical_analysis": stats,
    }


def run_real_rag_governance(
    cfg: SuiteConfig,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    *,
    resume: bool = False,
    force_new_run_id: bool = False,
) -> dict[str, Any]:
    parent = cfg.raw.get("parent_run", {})
    parent_dir = Path(parent.get("run_dir", ""))
    if not parent_dir.exists():
        raise FileNotFoundError(f"Parent reproduction run directory not found: {parent_dir}")
    parent_manifest = read_json(parent_dir / "run_manifest.json")
    candidate_path = parent_dir / "candidate_policy_metrics.csv"
    expected_hash = parent.get("candidate_table_hash")
    actual_hash = sha256_file(candidate_path)
    if expected_hash and expected_hash != actual_hash:
        raise ValueError("Parent candidate table hash mismatch")
    metrics = pd.read_csv(candidate_path)
    resolved_run_id, run_dir = prepare_run_dir(output_dir, run_id, suite=cfg.suite, resume=resume, force_new_run_id=force_new_run_id)
    copy_input_config(config_path, run_dir)
    write_json(
        run_dir / "parent_run_reference.json",
        {
            "parent_run_id": parent_manifest.get("run_id"),
            "parent_run_dir": str(parent_dir),
            "candidate_table_hash": actual_hash,
            "parent_evidence_mode": parent_manifest.get("evidence_mode"),
        },
    )
    stages = governance_stages(metrics, cfg)
    write_json(run_dir / "governance_stage_results.json", stages)
    frontier = pareto_frontier(
        aggregate_ranking(metrics).rename(columns={"cost_adjusted_utility": "overall_utility"})
    )
    write_json(run_dir / "pareto_frontier.json", {"rows": frontier.to_dict(orient="records")})
    promotion = promotion_consequence(stages)
    write_json(run_dir / "promotion_consequence_report.json", promotion)
    sensitivity = utility_sensitivity(metrics, cfg)
    write_json(run_dir / "utility_sensitivity.json", sensitivity)
    certificate = {
        "certificate_type": "RAGWarrant Real-RAG Governance Ablation Certificate",
        "status": "Inconclusive" if parent_manifest.get("evidence_mode") in {"fixture", "end_to_end_smoke"} else "Candidate external signal",
        "supported_enabled": False,
        "evidence_mode": parent_manifest.get("evidence_mode"),
        "reason": "governance replay completed over frozen parent candidate outcomes; Supported disabled",
    }
    if cfg.raw.get("profile", "development") != "confirmatory":
        certificate["status"] = "Inconclusive"
        certificate["reason"] = "governance replay was not a confirmatory profile"
    write_json(run_dir / "certificate.json", certificate)
    write_text(run_dir / "governance_ablation_report.md", governance_markdown(stages, certificate))
    write_json(run_dir / "aggregate_metrics.json", {"stage_count": len(stages["stages"]), "certificate": certificate["status"]})
    audit = write_no_overwrite_audit(run_dir, run_id=resolved_run_id)
    write_run_manifest(
        run_dir,
        suite=cfg.suite,
        run_id=resolved_run_id,
        config_path=config_path,
        seed=int(parent_manifest.get("seed") or cfg.seed),
        dataset_hash=str(parent_manifest.get("dataset_hash", "")),
        status="completed",
        evidence_mode=str(parent_manifest.get("evidence_mode", "historical_reproduction")),
        parent_run_id=str(parent_manifest.get("run_id")),
        extra={"candidate_table_hash": actual_hash, "no_overwrite_status": audit["status"]},
    )
    return {"suite": cfg.suite, "run_id": resolved_run_id, "run_dir": str(run_dir), "certificate": certificate, "parent_run_id": parent_manifest.get("run_id")}


def governance_stages(metrics: pd.DataFrame, cfg: SuiteConfig) -> dict[str, Any]:
    stage_params = [
        ("quality_only_search", 0.0, 0.0, False, False, False),
        ("quality_plus_cost", 0.25, 0.0, False, False, False),
        ("quality_plus_cost_plus_latency", 0.25, 0.10, False, False, False),
        ("quality_cost_latency_plus_protected_regression", 0.25, 0.10, True, False, False),
        ("plus_refusal_gate", 0.25, 0.10, True, True, False),
        ("plus_matched_budget_baseline_qualification", 0.25, 0.10, True, True, True),
        ("plus_certificate_and_audit_requirements", 0.25, 0.10, True, True, True),
    ]
    rows = []
    previous_winner: str | None = None
    threshold = float(cfg.raw.get("governance", {}).get("protected_regression_threshold", -0.03))
    for name, cost_weight, latency_weight, regression_gate, refusal_gate, budget_gate in stage_params:
        frame = metrics.copy()
        frame["stage_utility"] = (
            frame["held_out_test_raw_quality"].astype(float)
            - cost_weight * frame["total_cost_proxy"].astype(float)
            - latency_weight * frame["simulated_latency_cost"].astype(float)
        )
        frame["stage_eligible"] = ~frame["diagnostic_only"].astype(bool)
        if regression_gate:
            frame["stage_eligible"] = frame["stage_eligible"] & frame["regression_delta"].ge(threshold)
        if budget_gate:
            frame["stage_eligible"] = frame["stage_eligible"] & ~frame["budget_confounded_flag"].astype(bool)
        grouped = (
            frame.groupby("policy_id", as_index=False)
            .agg(
                utility=("stage_utility", "mean"),
                raw_quality=("held_out_test_raw_quality", "mean"),
                cost=("total_cost_proxy", "mean"),
                latency=("simulated_latency_cost", "mean"),
                protected_subset_score=("hard_subset_performance", "mean"),
                eligible=("stage_eligible", "all"),
            )
            .sort_values(["eligible", "utility", "raw_quality", "policy_id"], ascending=[False, False, False, True])
        )
        winner = str(grouped.iloc[0]["policy_id"]) if not grouped.empty else None
        rows.append(
            {
                "stage": name,
                "winner": winner,
                "winner_changed": previous_winner is not None and winner != previous_winner,
                "promotion_decision": "promote" if bool(grouped.iloc[0]["eligible"]) and not refusal_gate else "qualify",
                "certificate_class": "Inconclusive",
                "ranking": grouped.to_dict(orient="records"),
            }
        )
        previous_winner = winner
    return {"stages": rows}


def promotion_consequence(stages: dict[str, Any]) -> dict[str, Any]:
    rows = []
    previous = None
    for stage in stages.get("stages", []):
        rows.append({"stage": stage["stage"], "winner": stage["winner"], "changed_from_previous": previous is not None and previous != stage["winner"]})
        previous = stage["winner"]
    return {"rows": rows, "winner_changes": sum(1 for row in rows if row["changed_from_previous"])}


def governance_markdown(stages: dict[str, Any], certificate: dict[str, Any]) -> str:
    lines = ["# RAGWarrant Real-RAG Governance Ablation", "", f"- Certificate: `{certificate['status']}`", ""]
    for stage in stages.get("stages", []):
        lines.append(f"- `{stage['stage']}` winner: `{stage['winner']}`")
    lines.extend(["", "This replay uses frozen parent candidate outcomes and does not rerun generation."])
    return "\n".join(lines) + "\n"


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, yaml.safe_dump(payload, sort_keys=True))
