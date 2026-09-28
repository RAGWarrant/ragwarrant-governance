#!/usr/bin/env python3
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

"""Run the planning-only stratified joint-warrant power study."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SRC = REPOSITORY_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ragwarrant.research.fixed_sample_warrant import HOLM, freeze_candidate_family
from ragwarrant.research.stratified_joint_power import (
    BLOCKED_PENDING_OWNER_OPERATIONAL_FIELDS,
    CONTRACT_ID,
    FULL_STATUS,
    PLANNER_ID,
    SamplingContract,
    recruitment_cost_plan,
    simulate_joint_power,
    stable_hash,
)
from ragwarrant.research.types import PolicyConfig


FOCUS1_DIGEST = "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"


def load_config(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("joint-power config must be a mapping")
    exact = {
        "schema_version": "ragwarrant_stratified_joint_power_v1",
        "contract_id": CONTRACT_ID,
        "planner_id": PLANNER_ID,
        "focus1_digest": FOCUS1_DIGEST,
        "research_only": True,
        "execution_authorized": False,
        "evidence_collected": False,
        "full_executed": False,
        "drand_round_selected": False,
        "original_full_status": FULL_STATUS,
    }
    for key, expected in exact.items():
        if loaded.get(key) != expected:
            raise ValueError(f"{key} must equal {expected!r}")
    warrant = loaded.get("warrant")
    if not isinstance(warrant, dict) or warrant.get("candidate_count") != 24:
        raise ValueError("warrant must retain the frozen 24-candidate family")
    ids = warrant.get("candidate_ids")
    expected_ids = [f"policy_{index:03d}" for index in range(24)]
    if ids != expected_ids:
        raise ValueError("candidate_ids must be the complete sorted frozen family")
    if warrant.get("multiplicity") != "HOLM_ACROSS_CANDIDATES":
        raise ValueError("joint-power v1 freezes candidate-level Holm")
    if warrant.get("candidate_p_value") != "max_all_enabled_component_p_values":
        raise ValueError("candidate IUT must use every enabled component")
    expected_warrant = {
        "safe_planning_candidate_ids": expected_ids[:3],
        "familywise_error_level": 0.05,
        "enabled_risks": ["overall_quality", "group_quality", "safety_violation_probability", "execution_failure_probability", "insufficient_evidence_probability"],
        "enabled_group_risks": ["safety_violation_probability"],
        "quality_support": [-0.25, 0.25],
        "overall_quality_margin": 0.02,
        "group_quality_margin": 0.03,
        "binary_thresholds": {
            "safety_violation_probability": 0.05,
            "execution_failure_probability": 0.03,
            "insufficient_evidence_probability": 0.10,
        },
    }
    for key, expected in expected_warrant.items():
        if warrant.get(key) != expected:
            raise ValueError(f"warrant.{key} differs from the frozen contract")
    labels = loaded.get("groups", {}).get("labels")
    if labels != [
        {"id": "majority", "prevalence": 0.90},
        {"id": "minority", "prevalence": 0.10},
    ]:
        raise ValueError("group labels or prevalences differ from the frozen contract")
    if loaded.get("dependence", {}).get("levels") != {
        "low": 0.0,
        "medium": 0.5,
        "high": 0.9,
    }:
        raise ValueError("dependence grid differs from the frozen contract")
    if loaded.get("designs") != [
        {"id": "COMPONENT_50", "core_n": 898, "group_quota": 536},
        {"id": "COMPONENT_80", "core_n": 1383, "group_quota": 826},
        {"id": "COMPONENT_90", "core_n": 1720, "group_quota": 1028},
        {"id": "JOINT_EXPANSION_1", "core_n": 2304, "group_quota": 1380},
        {"id": "JOINT_EXPANSION_2", "core_n": 3072, "group_quota": 1840},
    ]:
        raise ValueError("design grid differs from the frozen contract")
    alternatives = loaded.get("planning_alternatives")
    if alternatives != {
        "quality_slack": 0.10,
        "quality_noise_half_width": 0.05,
        "binary_probabilities": {
            "safety_violation_probability": 0.025,
            "execution_failure_probability": 0.015,
            "insufficient_evidence_probability": 0.05,
        },
        "unsafe_boundary_offset": {
            "quality": 0.01,
            "safety_violation_probability": 0.005,
            "execution_failure_probability": 0.005,
            "insufficient_evidence_probability": 0.01,
        },
    }:
        raise ValueError("planning alternatives differ from the frozen contract")
    if loaded.get("operating_targets") != [0.50, 0.80, 0.90]:
        raise ValueError("operating targets differ from the frozen contract")
    if loaded.get("operational_cost_rank_rule") != "multiplicative_permutation_mod24_multiplier7_offset3":
        raise ValueError("operational cost ordering differs from the frozen contract")
    if loaded.get("operational_latency_rank_rule") != "multiplicative_permutation_mod24_multiplier11_offset5":
        raise ValueError("operational latency ordering differs from the frozen contract")
    if loaded.get("replicates") != 96 or loaded.get("master_seed") != 740771201:
        raise ValueError("planning Monte Carlo schedule differs from the frozen contract")
    if loaded.get("operating_point_rule") != (
        "first prespecified design whose point estimate reaches the target in every dependence level; report Wilson uncertainty and do not treat as a guarantee"
    ):
        raise ValueError("operating-point rule must be prespecified")
    return loaded


def build_inputs(config: dict[str, object]):
    warrant = config["warrant"]
    groups_config = config["groups"]
    groups = tuple(sorted(item["id"] for item in groups_config["labels"]))
    prevalence = {item["id"]: float(item["prevalence"]) for item in groups_config["labels"]}
    policy = PolicyConfig(
        quality_noninferiority_margin=float(warrant["overall_quality_margin"]),
        group_quality_noninferiority_margin=float(warrant["group_quality_margin"]),
        max_safety_violation_probability=float(warrant["binary_thresholds"]["safety_violation_probability"]),
        max_execution_failure_probability=float(warrant["binary_thresholds"]["execution_failure_probability"]),
        max_insufficient_evidence_probability=float(warrant["binary_thresholds"]["insufficient_evidence_probability"]),
        cost_weight=1.0,
        latency_weight=0.0,
        confidence_level=0.95,
        bootstrap_resamples=0,
        enabled_risks=tuple(warrant["enabled_risks"]),
        enabled_group_risks=tuple(warrant["enabled_group_risks"]),
        group_ids=groups,
    )
    return warrant, groups, prevalence, policy


def run_study(config: dict[str, object]) -> dict[str, object]:
    warrant, groups, prevalence, policy = build_inputs(config)
    target = config["target_population"]
    sampling = config["sampling"]
    freeze = config["freeze_points"]
    family_stub = freeze_candidate_family(
        candidate_policy_ids=warrant["candidate_ids"],
        incumbent_policy_id=freeze["incumbent_version"],
        confirmatory_unit_count=1,
        policy=policy,
        quality_delta_bounds=tuple(float(value) for value in warrant["quality_support"]),
        familywise_error_level=float(warrant["familywise_error_level"]),
        multiplicity_method=HOLM,
        selection_objective="minimize_cost",
    )
    contract = SamplingContract(
        target_population_id=target["id"],
        sampling_frame_id=target["sampling_frame_id"],
        unit_definition=target["unit_definition"],
        group_ids=groups,
        group_prevalence=tuple(sorted(prevalence.items())),
        core_mechanism=sampling["core_mechanism"],
        topup_mechanism=sampling["topup_mechanism"],
        replacement=bool(sampling["replacement"]),
        max_elapsed_days=int(sampling["max_elapsed_days"]),
        screening_cap=int(sampling["screening_cap"]),
        recruitment_deadline_days=int(sampling["recruitment_deadline_days"]),
        candidate_family_hash=family_stub.family_hash,
        incumbent_version=freeze["incumbent_version"],
        model_version=freeze["model_version"],
        evaluator_version=freeze["evaluator_version"],
    )
    alternatives = config["planning_alternatives"]
    binary_alternatives = {
        key: float(value) for key, value in alternatives["binary_probabilities"].items()
    }
    outputs: list[dict[str, object]] = []
    costs: dict[str, dict[str, object]] = {}
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
        costs[design["id"]] = recruitment_cost_plan(
            core_n=core_n,
            group_quotas=quotas,
            prevalence=prevalence,
            eligibility_rate=float(config["cost_model"]["eligibility_rate"]),
            usable_rate=float(config["cost_model"]["usable_rate"]),
            duplicate_rate=float(config["cost_model"]["duplicate_rate"]),
            acquisition_probability=float(config["cost_model"]["acquisition_probability"]),
            screening_cap=int(sampling["screening_cap"]),
            unit_costs=config["cost_model"]["unit_costs"],
        )
        for dependence in config["dependence"]["levels"]:
            result = simulate_joint_power(
                family=family,
                policy=policy,
                core_n=core_n,
                group_quotas=quotas,
                group_prevalence=prevalence,
                safe_policy_ids=warrant["safe_planning_candidate_ids"],
                binary_alternatives=binary_alternatives,
                quality_slack=float(alternatives["quality_slack"]),
                dependence_level=dependence,
                replicates=int(config["replicates"]),
                master_seed=int(config["master_seed"]),
            )
            result["design_id"] = design["id"]
            outputs.append(result)
    targets: dict[str, str | None] = {}
    for target_power in config["operating_targets"]:
        selected = None
        for design in config["designs"]:
            cells = [item for item in outputs if item["design_id"] == design["id"]]
            if all(item["at_least_one_safe_certification_probability"] >= float(target_power) for item in cells):
                selected = design["id"]
                break
        targets[str(target_power)] = selected
    return {
        "contract": contract,
        "contract_hash": stable_hash(contract.__dict__),
        "config_hash": stable_hash(config),
        "cells": outputs,
        "costs": costs,
        "operating_points": targets,
        "execution_status": BLOCKED_PENDING_OWNER_OPERATIONAL_FIELDS,
        "focus1_digest": FOCUS1_DIGEST,
        "evidence_collected": False,
        "full_executed": False,
        "drand_round_selected": False,
    }


def _csv_rows(result: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cell in result["cells"]:
        common = {
            "design_id": cell["design_id"],
            "core_n": cell["core_n"],
            "group_quota": next(iter(cell["group_quotas"].values())),
            "dependence_level": cell["dependence_level"],
            "shared_variation_fraction": cell["shared_variation_fraction"],
            "replicates": cell["replicates"],
            "at_least_one_safe_power": cell["at_least_one_safe_certification_probability"],
            "at_least_one_safe_wilson_low": cell["at_least_one_safe_wilson"][0],
            "at_least_one_safe_wilson_high": cell["at_least_one_safe_wilson"][1],
            "false_certification_probability": cell["false_certification_probability"],
            "false_certification_wilson_low": cell["false_certification_wilson"][0],
            "false_certification_wilson_high": cell["false_certification_wilson"][1],
            "expected_certified_set_size": cell["expected_certified_set_size"],
            "safe_selection_probability": cell["safe_selection_probability"],
            "unsafe_selection_probability": cell["unsafe_selection_probability"],
            "no_selection_probability": cell["no_selection_probability"],
        }
        for candidate in cell["candidate_results"]:
            row = dict(common)
            row.update(
                {
                    "safe_policy_id": candidate["policy_id"],
                    "candidate_joint_power": candidate["monte_carlo_joint_power"],
                    "candidate_joint_wilson_low": candidate["monte_carlo_joint_power_wilson"][0],
                    "candidate_joint_wilson_high": candidate["monte_carlo_joint_power_wilson"][1],
                    "union_bound_lower_bound": candidate["union_bound_joint_lower_bound"],
                    "independence_approximation": candidate["independence_approximation"],
                    "marginal_component_powers": json.dumps(candidate["marginal_component_powers"], sort_keys=True),
                }
            )
            rows.append(row)
    return rows


def write_outputs(result: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "JOINT_WARRANT_POWER_STUDY.csv"
    rows = _csv_rows(result)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Joint warrant power study",
        "",
        "Planning simulation only; no confirmatory evidence was collected. Monte Carlo intervals describe planning-simulation uncertainty.",
        "",
        f"- Focus 1 digest: `{result['focus1_digest']}`",
        f"- Contract hash: `{result['contract_hash']}`",
        f"- Config hash: `{result['config_hash']}`",
        f"- Execution status: `{result['execution_status']}`",
        f"- Original FULL status: `{FULL_STATUS}`",
        "- FULL executed: `false`",
        "- Drand round selected: `false`",
        "",
        "## Scenario cells",
        "",
        "| Design | Core | Quota/group | Dependence | Any safe certifies | 95% Wilson | Any unsafe certifies | Expected set | Safe selected | None selected |",
        "|---|---:|---:|---|---:|---|---:|---:|---:|---:|",
    ]
    for cell in result["cells"]:
        lines.append(
            f"| `{cell['design_id']}` | {cell['core_n']} | {next(iter(cell['group_quotas'].values()))} | `{cell['dependence_level']}` | {cell['at_least_one_safe_certification_probability']:.4f} | [{cell['at_least_one_safe_wilson'][0]:.4f}, {cell['at_least_one_safe_wilson'][1]:.4f}] | {cell['false_certification_probability']:.4f} | {cell['expected_certified_set_size']:.3f} | {cell['safe_selection_probability']:.4f} | {cell['no_selection_probability']:.4f} |"
        )
    lines.extend(["", "## Prespecified operating points", ""])
    for target, design in result["operating_points"].items():
        lines.append(f"- {float(target):.0%}: `{design or 'NOT_REACHED_ON_PRESPECIFIED_GRID'}`")
    lines.extend(
        [
            "",
            "The union-bound lower bound uses marginal component rejections at the fixed alpha/24 threshold. The product is an independence approximation only. Actual candidate and family power uses the complete preserved IUT/Holm decision.",
            "",
            "Unsafe planning candidates are retained in the full family. False certification means at least one such candidate was certified in the planning simulation; it is not a guarantee or an estimate from confirmatory evidence.",
        ]
    )
    (output_dir / "JOINT_WARRANT_POWER_STUDY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    current = result["costs"]["COMPONENT_80"]
    cost_lines = [
        "# Screening and recruitment cost",
        "",
        "Costs are normalized planning inputs. They are not vendor quotes or evidence-collection records.",
        "",
        f"- Component-level 80% design expected screened units: `{current['expected_screened_units']:.2f}`",
        f"- Expected valid full-family evaluated units: `{current['expected_evaluated_units']:.2f}`",
        f"- Expected total normalized acquisition cost: `{current['total_acquisition_cost']:.2f}`",
        f"- Conservative 95% screened-unit bounds by group with no core credit: `{json.dumps(current['conservative_high_probability_screened_units_by_group_no_core_credit'], sort_keys=True)}`",
        f"- Conservative simultaneous 95% screened-unit bound (union allocation; no core credit in group bounds): `{current['conservative_simultaneous_high_probability_screened_units']}`",
        f"- Per-requirement acquisition probability used for the simultaneous bound: `{current['union_bound_per_requirement_probability']:.6f}`",
        "- The preserved 2,070.70 figure is evaluated valid rows under ideal routing, not total workload.",
        "- The preserved 3,035 figure is a no-reuse valid-row ceiling, not a screening or attempted-evaluation cap.",
        "- Imperfect positive-only group screening is not authorized because cost correction cannot repair selection bias.",
    ]
    (output_dir / "SCREENING_AND_RECRUITMENT_COST.md").write_text("\n".join(cost_lines) + "\n", encoding="utf-8")

    contract = result["contract"]
    contract_lines = [
        "# Stratified sampling contract",
        "",
        f"Contract: `{CONTRACT_ID}`; digest `{result['contract_hash']}`.",
        "",
        "This freezes a synthetic planning contract. Real collection remains blocked until the owner supplies and hashes the operational population, frame, unit/cluster definition, group codebook, channels, calendar window, screening mechanism, and privacy rules.",
        "",
        "- Overall tests: representative IID core only.",
        "- Group tests: matching core observations plus eligible outcome-blind random within-group top-ups.",
        "- Core observations count once toward their matching quota.",
        "- Top-ups never enter unweighted overall estimates.",
        "- Missing/ambiguous labels, duplicates, quota shortfalls, caps, or deadlines fail closed.",
        "- Recruitment failure: `BLOCKED_INSUFFICIENT_GROUP_EVIDENCE`.",
        "- Execution authorization: `false`.",
        "- Group assignment must precede candidate output and evaluation outcomes.",
        f"- Maximum core/top-up elapsed period: `{contract.max_elapsed_days}` days.",
        "- Future weighted overall inference requires a separate version and review.",
    ]
    (output_dir / "STRATIFIED_SAMPLING_CONTRACT.md").write_text("\n".join(contract_lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=REPOSITORY_ROOT / "configs/research/stratified_joint_warrant_power_v1.yaml")
    parser.add_argument("--output-dir", type=Path, default=REPOSITORY_ROOT / ".local_data/research_review")
    args = parser.parse_args()
    result = run_study(load_config(args.config))
    write_outputs(result, args.output_dir)
    print(json.dumps({"contract_hash": result["contract_hash"], "cells": len(result["cells"]), "operating_points": result["operating_points"], "evidence_collected": False, "full_executed": False, "drand_round_selected": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
