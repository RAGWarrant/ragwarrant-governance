#!/usr/bin/env python3
"""Run the frozen STRATIFIED_JOINT_POWER_CONFIRMATION_V1 protocol."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SRC = REPOSITORY_ROOT / "src"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ragwarrant.research.fixed_sample_warrant import HOLM, freeze_candidate_family
from ragwarrant.research.joint_power_confirmation import (
    DEPENDENCE_CONDITIONS,
    DESIGN_IDS,
    FOCUS1_DIGEST,
    PROTOCOL_ID,
    PUBLIC_MASTER_SEED,
    REPLICATES_PER_CELL,
    V1_BASELINE_COMMIT,
    run_confirmation_cell,
    schedule_fingerprints,
)
from ragwarrant.research.stratified_joint_power import (
    FULL_STATUS,
    recruitment_cost_plan,
    stable_hash,
)
from scripts.run_stratified_joint_power_study import build_inputs, load_config


DEFAULT_CONFIG = REPOSITORY_ROOT / "configs/research/stratified_joint_power_confirmation_v1.yaml"
PARENT_CONFIG = REPOSITORY_ROOT / "configs/research/stratified_joint_warrant_power_v1.yaml"
DEFAULT_PROTOCOL_JSON = REPOSITORY_ROOT / ".local_data/research_review/JOINT_POWER_CONFIRMATION_PROTOCOL.json"
DEFAULT_PROTOCOL_MD = REPOSITORY_ROOT / ".local_data/research_review/JOINT_POWER_CONFIRMATION_PROTOCOL.md"
DEFAULT_PROTOCOL_FREEZE = REPOSITORY_ROOT / ".local_data/research_review/JOINT_POWER_CONFIRMATION_PROTOCOL_FREEZE.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / ".local_data/research_review/joint_power_confirmation_v1"
EXECUTOR_PATH = REPOSITORY_ROOT / "src/ragwarrant/research/joint_power_confirmation.py"
RUNNER_PATH = Path(__file__).resolve()
FOCUSED_TEST_PATH = REPOSITORY_ROOT / "tests/research/test_joint_power_confirmation.py"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_confirmation_config(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("confirmation config must be a mapping")
    exact = {
        "schema_version": "ragwarrant_stratified_joint_power_confirmation_v1",
        "protocol_id": PROTOCOL_ID,
        "focus1_digest": FOCUS1_DIGEST,
        "v1_baseline_commit": V1_BASELINE_COMMIT,
        "research_only": True,
        "planning_only": True,
        "execution_authorized": False,
        "evidence_collected": False,
        "full_executed": False,
        "drand_round_selected": False,
        "replicates_per_design_dependence_cell": REPLICATES_PER_CELL,
        "cell_count": 6,
        "total_replicates": 6000,
    }
    for key, expected in exact.items():
        if loaded.get(key) != expected:
            raise ValueError(f"{key} must equal {expected!r}")
    if loaded.get("designs") != [
        {
            "id": DESIGN_IDS[0],
            "core_n": 1383,
            "group_quota": 826,
        },
        {
            "id": DESIGN_IDS[1],
            "core_n": 1720,
            "group_quota": 1028,
        },
    ]:
        raise ValueError("confirmation designs differ from the frozen two-design schedule")
    if loaded.get("dependence_conditions") != {
        "low": 0.0,
        "medium": 0.5,
        "high": 0.9,
    }:
        raise ValueError("confirmation dependence conditions differ from the frozen schedule")
    seed = loaded.get("seed_schedule")
    if not isinstance(seed, dict):
        raise ValueError("seed_schedule must be a mapping")
    if seed.get("public_master_seed") != PUBLIC_MASTER_SEED:
        raise ValueError("confirmation master seed differs from the frozen schedule")
    if seed.get("identity_format") != (
        "STRATIFIED_JOINT_POWER_CONFIRMATION_V1|{design_id}|"
        "{dependence_condition}|{replicate_index}"
    ):
        raise ValueError("confirmation identity format differs from the frozen schedule")
    if seed.get("python_builtin_hash_permitted") is not False:
        raise ValueError("Python built-in hash must remain prohibited")
    parent = loaded.get("frozen_parent")
    if not isinstance(parent, dict):
        raise ValueError("frozen_parent must be a mapping")
    parent_path = REPOSITORY_ROOT / str(parent.get("config"))
    implementation_path = REPOSITORY_ROOT / str(parent.get("implementation"))
    if sha256_file(parent_path) != parent.get("config_sha256"):
        raise ValueError("frozen parent config hash changed")
    if sha256_file(implementation_path) != parent.get("implementation_sha256"):
        raise ValueError("frozen parent implementation hash changed")
    executor = loaded.get("frozen_executor")
    if not isinstance(executor, dict):
        raise ValueError("frozen_executor must be a mapping")
    for path_key, hash_key in (
        ("implementation", "implementation_sha256"),
        ("runner", "runner_sha256"),
        ("focused_tests", "focused_tests_sha256"),
    ):
        executor_path = REPOSITORY_ROOT / str(executor.get(path_key))
        if sha256_file(executor_path) != executor.get(hash_key):
            raise ValueError(f"frozen confirmation {path_key} hash changed")
    return loaded


def verify_protocol_freeze(
    protocol_json: Path,
    protocol_md: Path,
    freeze_path: Path,
    *,
    config_path: Path,
    executor_path: Path,
    runner_path: Path,
    focused_test_path: Path,
) -> dict[str, Any]:
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("protocol_id") != PROTOCOL_ID or freeze.get("frozen_before_execution") is not True:
        raise ValueError("confirmation protocol is not frozen before execution")
    if sha256_file(protocol_json) != freeze.get("protocol_json_sha256"):
        raise ValueError("frozen confirmation JSON protocol hash changed")
    if sha256_file(protocol_md) != freeze.get("protocol_markdown_sha256"):
        raise ValueError("frozen confirmation Markdown protocol hash changed")
    for name, path, key in (
        ("tracked config", config_path, "tracked_config_sha256"),
        ("executor", executor_path, "executor_sha256"),
        ("runner", runner_path, "runner_sha256"),
        ("focused tests", focused_test_path, "focused_tests_sha256"),
    ):
        if sha256_file(path) != freeze.get(key):
            raise ValueError(f"frozen confirmation {name} hash changed")
    if freeze.get("confirmation_output_existed_at_freeze") is not False:
        raise ValueError("protocol freeze did not precede confirmation output")
    return freeze


def validate_execution_paths(config_path: Path, parent_config_path: Path) -> None:
    if config_path.resolve() != DEFAULT_CONFIG.resolve():
        raise ValueError("confirmation config must use the canonical frozen path")
    if parent_config_path.resolve() != PARENT_CONFIG.resolve():
        raise ValueError("parent config must use the canonical frozen path")


def run_confirmation(config: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    warrant, groups, prevalence, policy = build_inputs(parent)
    freeze = parent["freeze_points"]
    alternatives = parent["planning_alternatives"]
    binary_alternatives = {
        key: float(value)
        for key, value in alternatives["binary_probabilities"].items()
    }
    design_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    for design in config["designs"]:
        core_n = int(design["core_n"])
        quota = int(design["group_quota"])
        quotas = {group: quota for group in groups}
        family = freeze_candidate_family(
            candidate_policy_ids=warrant["candidate_ids"],
            incumbent_policy_id=freeze["incumbent_version"],
            confirmatory_unit_count=core_n,
            policy=policy,
            quality_delta_bounds=tuple(float(value) for value in warrant["quality_support"]),
            familywise_error_level=float(warrant["familywise_error_level"]),
            multiplicity_method=HOLM,
            selection_objective="minimize_cost",
        )
        cost = recruitment_cost_plan(
            core_n=core_n,
            group_quotas=quotas,
            prevalence=prevalence,
            eligibility_rate=float(parent["cost_model"]["eligibility_rate"]),
            usable_rate=float(parent["cost_model"]["usable_rate"]),
            duplicate_rate=float(parent["cost_model"]["duplicate_rate"]),
            acquisition_probability=float(parent["cost_model"]["acquisition_probability"]),
            screening_cap=int(parent["sampling"]["screening_cap"]),
            unit_costs=parent["cost_model"]["unit_costs"],
        )
        cost_rows.append(
            {
                "protocol_id": PROTOCOL_ID,
                "design_id": design["id"],
                "core_n": core_n,
                "group_quota": quota,
                "expected_screened_units": cost["expected_screened_units"],
                "expected_evaluated_units": cost["expected_evaluated_units"],
                "conservative_simultaneous_high_probability_screened_units": cost[
                    "conservative_simultaneous_high_probability_screened_units"
                ],
                "total_acquisition_cost": cost["total_acquisition_cost"],
                "cost_unit": cost["cost_unit"],
            }
        )
        for dependence in DEPENDENCE_CONDITIONS:
            design_row, candidates = run_confirmation_cell(
                design_id=str(design["id"]),
                family=family,
                policy=policy,
                core_n=core_n,
                group_quotas=quotas,
                group_prevalence=prevalence,
                safe_policy_ids=warrant["safe_planning_candidate_ids"],
                binary_alternatives=binary_alternatives,
                quality_slack=float(alternatives["quality_slack"]),
                dependence_condition=dependence,
            )
            design_rows.append(design_row)
            candidate_rows.extend(candidates)
    return {
        "protocol_id": PROTOCOL_ID,
        "focus1_digest": FOCUS1_DIGEST,
        "v1_baseline_commit": V1_BASELINE_COMMIT,
        "design_results": design_rows,
        "candidate_results": candidate_rows,
        "cost_results": cost_rows,
        "schedule": schedule_fingerprints(),
        "evidence_collected": False,
        "original_full_status": FULL_STATUS,
        "full_executed": False,
        "drand_round_selected": False,
        "operational_fields_status": "OWNER_OR_DEPLOYER_INPUT_REQUIRED",
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(
    result: dict[str, Any],
    output_dir: Path,
    *,
    config_path: Path,
    protocol_json: Path,
    protocol_md: Path,
    freeze_path: Path,
) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("confirmation output already exists; frozen protocol may run only once")
    output_dir.mkdir(parents=True, exist_ok=True)
    design_path = output_dir / "design_results.csv"
    candidate_path = output_dir / "candidate_results.csv"
    cost_path = output_dir / "cost_results.csv"
    report_path = output_dir / "confirmation_report.md"
    _write_csv(design_path, result["design_results"])
    _write_csv(candidate_path, result["candidate_results"])
    _write_csv(cost_path, result["cost_results"])

    lines = [
        "# Independent joint-power planning confirmation",
        "",
        "This is a deterministic planning simulation, not sealed confirmation or real-world evidence.",
        "",
        f"- Protocol: `{PROTOCOL_ID}`",
        f"- Focus 1 digest: `{FOCUS1_DIGEST}`",
        f"- Frozen v1 baseline: `{V1_BASELINE_COMMIT}`",
        "- Replicates: `1,000 per design x dependence cell`",
        "- Evidence collected: `false`",
        "- Original FULL executed: `false`",
        "- Drand round selected: `false`",
        "- Operational fields: `OWNER_OR_DEPLOYER_INPUT_REQUIRED`",
        "",
        "## Results",
        "",
        "| Design | Core | Quota/group | Dependence | At least one safe | 95% Wilson | 80% label | 90% label | False certification | Mean set | Operational selection |",
        "|---|---:|---:|---|---:|---|---|---|---:|---:|---:|",
    ]
    for row in result["design_results"]:
        lines.append(
            f"| `{row['design_id']}` | {row['core_n']} | {row['group_quota']} | `{row['dependence_condition']}` | "
            f"{row['at_least_one_safe_certification_probability']:.4f} | "
            f"[{row['at_least_one_safe_wilson_low']:.4f}, {row['at_least_one_safe_wilson_high']:.4f}] | "
            f"`{row['planning_label_80']}` | `{row['planning_label_90']}` | "
            f"{row['false_certification_probability']:.4f} | {row['mean_certified_set_size']:.3f} | "
            f"{row['operational_selection_probability']:.4f} |"
        )
    lines.extend(
        [
            "",
            "Family-level success and per-candidate joint certification are reported separately in `candidate_results.csv`; family success must not be used to conceal weak per-candidate power.",
            "",
            "Observed false certification is a developmental-model estimate, not proof of universal control. Screening costs use the frozen normalized assumptions and do not replace owner-supplied real operational inputs.",
            "",
            "The design grid was not changed after results. A negative result does not trigger another design run.",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": "ragwarrant_joint_power_confirmation_manifest.v1",
        "protocol_id": PROTOCOL_ID,
        "focus1_digest": FOCUS1_DIGEST,
        "v1_baseline_commit": V1_BASELINE_COMMIT,
        "config_sha256": sha256_file(config_path),
        "protocol_json_sha256": sha256_file(protocol_json),
        "protocol_markdown_sha256": sha256_file(protocol_md),
        "protocol_freeze_sha256": sha256_file(freeze_path),
        "implementation_sha256": sha256_file(EXECUTOR_PATH),
        "runner_sha256": sha256_file(RUNNER_PATH),
        "parent_config_sha256": sha256_file(PARENT_CONFIG),
        "parent_implementation_sha256": sha256_file(REPOSITORY_ROOT / "src/ragwarrant/research/stratified_joint_power.py"),
        "schedule": result["schedule"],
        "design_count": 2,
        "dependence_condition_count": 3,
        "replicates_per_cell": REPLICATES_PER_CELL,
        "total_replicates": 6000,
        "result_sha256": {
            "design_results.csv": sha256_file(design_path),
            "candidate_results.csv": sha256_file(candidate_path),
            "cost_results.csv": sha256_file(cost_path),
            "confirmation_report.md": sha256_file(report_path),
        },
        "confirmatory_evidence_collected": False,
        "original_full_executed": False,
        "future_stratified_full_executed": False,
        "full_results_inspected": False,
        "drand_round_selected": False,
        "public_beacon_queried": False,
        "github_workflow_executed": False,
        "operational_fields_status": "OWNER_OR_DEPLOYER_INPUT_REQUIRED",
        "post_result_design_search": False,
    }
    (output_dir / "confirmation_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--parent-config", type=Path, default=PARENT_CONFIG)
    parser.add_argument("--protocol-json", type=Path, default=DEFAULT_PROTOCOL_JSON)
    parser.add_argument("--protocol-markdown", type=Path, default=DEFAULT_PROTOCOL_MD)
    parser.add_argument("--protocol-freeze", type=Path, default=DEFAULT_PROTOCOL_FREEZE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    validate_execution_paths(args.config, args.parent_config)
    config = load_confirmation_config(args.config)
    if sha256_file(args.parent_config) != config["frozen_parent"]["config_sha256"]:
        raise ValueError("actual parent config does not match the frozen parent hash")
    parent = load_config(args.parent_config)
    verify_protocol_freeze(
        args.protocol_json,
        args.protocol_markdown,
        args.protocol_freeze,
        config_path=args.config,
        executor_path=EXECUTOR_PATH,
        runner_path=RUNNER_PATH,
        focused_test_path=FOCUSED_TEST_PATH,
    )
    fingerprints = schedule_fingerprints()
    if fingerprints["identity_count"] != 6000:
        raise ValueError("confirmation schedule does not contain exactly 6000 identities")
    if fingerprints["duplicate_identity_count"] or fingerprints["duplicate_seed_count"]:
        raise ValueError("confirmation schedule contains duplicate identities or seeds")
    result = run_confirmation(config, parent)
    write_outputs(
        result,
        args.output_dir,
        config_path=args.config,
        protocol_json=args.protocol_json,
        protocol_md=args.protocol_markdown,
        freeze_path=args.protocol_freeze,
    )
    print(
        json.dumps(
            {
                "protocol_id": PROTOCOL_ID,
                "cells": len(result["design_results"]),
                "total_replicates": 6000,
                "evidence_collected": False,
                "full_executed": False,
                "drand_round_selected": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
