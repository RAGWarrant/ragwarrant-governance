# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

"""Atomic, research-local reporting for the Focus 2 warrant benchmark."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .fixed_sample_warrant import (
    FOCUS1_FREEZE_DIGEST,
    METHOD_ID,
    SEED_SCHEDULE_VERSION,
    SUPPORTED_MULTIPLICITY_METHODS,
)
from .focus2_benchmark import (
    FOCUS2_BENCHMARK_ID,
    FOCUS2_CONFIG_CANONICAL_HASH,
    FOCUS2_CONFIG_FILE_SHA256,
)


OUTPUT_FILENAMES = (
    "benchmark_manifest.json",
    "focus1_config_snapshot.yaml",
    "focus2_config_snapshot.yaml",
    "scenario_truth.csv",
    "scenario_summary.csv",
    "method_summary.csv",
    "trial_summary_sample.csv",
    "promotion_warrant.json",
    "promotion_warrant_bonferroni.json",
    "holm_bonferroni_comparison.csv",
    "focus2_benchmark_report.md",
    "claim_boundaries.md",
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WARRANT_FIELDS = {
    "schema_version",
    "method",
    "method_id",
    "status",
    "decision",
    "decision_reason",
    "familywise_error_level",
    "multiplicity_method",
    "candidate_family_frozen",
    "family_hash",
    "incumbent_policy_id",
    "confirmatory_unit_count",
    "certified_policy_ids",
    "selected_policy_id",
    "selection_objective",
    "risk_tests",
    "enabled_risks",
    "operational_selection_objective",
    "diagnostics",
    "observed_evidence_only",
    "truth_isolated",
    "benchmark_control_only",
    "benchmark_freeze_digest",
    "seed_schedule_version",
    "full_profile_used",
    "population_truth_accessed",
    "research_only",
    "production_integrated",
}
RISK_TEST_FIELDS = {
    "hypothesis_id",
    "policy_id",
    "risk_id",
    "group_id",
    "null_hypothesis",
    "alternative_hypothesis",
    "null_boundary",
    "support_bounds",
    "sample_count",
    "observed_statistic",
    "raw_p_value",
    "adjusted_p_value",
    "rejection_threshold",
    "rejected",
    "failure_reason",
}


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty required CSV: {path.name}")
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _integrity(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if not payload:
        raise ValueError(f"required output is empty: {path.name}")
    return {"sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}


def _git_state() -> tuple[str, bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unavailable", False


def _validate_existing(root: Path) -> None:
    entries = {path.name for path in root.iterdir()}
    if not entries:
        return
    if entries != set(OUTPUT_FILENAMES) or any(not path.is_file() for path in root.iterdir()):
        raise ValueError("nonempty output root is not an exact prior Focus 2 output set")
    try:
        manifest = json.loads((root / "benchmark_manifest.json").read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("prior Focus 2 manifest is unreadable") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("benchmark_id") != "fixed_sample_multi_risk_warrant_benchmark_v1"
        or manifest.get("complete") is not True
        or set(manifest.get("output_files", ())) != set(OUTPUT_FILENAMES)
    ):
        raise ValueError("nonempty output root is not a verified complete Focus 2 run")
    expected = manifest.get("output_integrity")
    if not isinstance(expected, dict) or set(expected) != set(OUTPUT_FILENAMES[1:]):
        raise ValueError("prior Focus 2 output integrity metadata is incomplete")
    for name in OUTPUT_FILENAMES[1:]:
        if expected[name] != _integrity(root / name):
            raise ValueError(f"prior Focus 2 output integrity mismatch: {name}")


def _safe_output_root(output_root: str | Path) -> Path:
    requested = Path(output_root).absolute()
    for component in (requested, *requested.parents):
        if component.exists() and component.is_symlink():
            raise ValueError("output root and its existing ancestors must not be symlinks")
    root = requested.resolve(strict=False)
    repository = REPOSITORY_ROOT.resolve()
    if root == repository or root in repository.parents:
        raise ValueError("output root must not be the repository root or an ancestor")
    try:
        relative = root.relative_to(repository)
    except ValueError:
        relative = None
    if relative is not None and tuple(relative.parts[:2]) != (
        ".local_data",
        "fixed_sample_warrant",
    ):
        raise ValueError("repository-local Focus 2 outputs must stay under .local_data/fixed_sample_warrant")
    if root.exists():
        if not root.is_dir():
            raise ValueError("Focus 2 output root exists and is not a directory")
        _validate_existing(root)
    return root


def _validate_manifest(manifest: Mapping[str, object]) -> None:
    if manifest.get("profile") not in {"CI", "LOCAL"}:
        raise ValueError("Focus 2 reporting accepts only CI or LOCAL profiles")
    required_exact = {
        "benchmark_id": FOCUS2_BENCHMARK_ID,
        "focus1_benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST,
        "seed_schedule_version": SEED_SCHEDULE_VERSION,
        "evidence_role": "developmental",
        "full_profile_used": False,
        "full_evidence_generated": False,
        "full_results_inspected": False,
        "target_drand_round_selected": False,
        "truth_isolated_method_accessed_population_truth": False,
        "same_observed_evidence_object_shared_by_truth_isolated_methods": True,
        "candidate_families_frozen_before_confirmatory_evidence": True,
        "post_hoc_filtered": False,
        "scenario_results_aggregated_into_headline": False,
        "focus2_config_hash": FOCUS2_CONFIG_CANONICAL_HASH,
        "focus2_config_file_sha256": FOCUS2_CONFIG_FILE_SHA256,
        "complete": True,
    }
    for field, expected in required_exact.items():
        if manifest.get(field) != expected:
            raise ValueError(
                f"Focus 2 manifest {field} must equal {expected!r}"
            )
    if manifest.get("truth_access_method_ids") != ["oracle_safe_objective"]:
        raise ValueError("only the truth-using oracle may report population-truth access")


def _sha256_string(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _probability(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a probability")
    result = float(value)
    if not 0.0 <= result <= 1.0 or not np.isfinite(result):
        raise ValueError(f"{name} must be a probability")
    return result


def _validate_warrant_artifact(
    artifact: object, expected_procedure: str
) -> None:
    if not isinstance(artifact, Mapping) or set(artifact) != WARRANT_FIELDS:
        raise ValueError("promotion warrant fields do not match the research schema")
    required_exact = {
        "schema_version": "1.0",
        "method": METHOD_ID,
        "method_id": METHOD_ID,
        "status": "COMPLETED",
        "multiplicity_method": expected_procedure,
        "candidate_family_frozen": True,
        "observed_evidence_only": True,
        "truth_isolated": True,
        "benchmark_control_only": False,
        "benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST,
        "seed_schedule_version": SEED_SCHEDULE_VERSION,
        "full_profile_used": False,
        "population_truth_accessed": False,
        "research_only": True,
        "production_integrated": False,
    }
    for field, expected in required_exact.items():
        if artifact.get(field) != expected:
            raise ValueError(f"promotion warrant {field} must equal {expected!r}")
    if expected_procedure not in SUPPORTED_MULTIPLICITY_METHODS:
        raise ValueError("promotion warrant uses an unknown multiplicity procedure")
    alpha = _probability(artifact.get("familywise_error_level"), "familywise error level")
    if alpha in {0.0, 1.0}:
        raise ValueError("familywise error level must be strictly between zero and one")
    _sha256_string(artifact.get("family_hash"), "family hash")
    if (
        not isinstance(artifact.get("incumbent_policy_id"), str)
        or not artifact["incumbent_policy_id"]
    ):
        raise ValueError("promotion warrant incumbent ID is invalid")
    if (
        isinstance(artifact.get("confirmatory_unit_count"), bool)
        or not isinstance(artifact.get("confirmatory_unit_count"), int)
        or int(artifact["confirmatory_unit_count"]) <= 0
    ):
        raise ValueError("promotion warrant confirmatory unit count must be positive")

    certified = artifact.get("certified_policy_ids")
    if (
        not isinstance(certified, list)
        or any(not isinstance(value, str) or not value for value in certified)
        or len(set(certified)) != len(certified)
    ):
        raise ValueError("promotion warrant certified policy IDs are invalid")
    selected = artifact.get("selected_policy_id")
    if selected is not None and (not isinstance(selected, str) or not selected):
        raise ValueError("promotion warrant selected policy ID is invalid")
    if selected is not None and selected not in certified:
        raise ValueError("promotion warrant selected policy must be certified")
    decision = artifact.get("decision")
    if decision not in {"PROMOTE", "INCONCLUSIVE", "BLOCKED_INVALID_EVIDENCE"}:
        raise ValueError("promotion warrant decision is invalid")
    if (decision == "PROMOTE") != (selected is not None):
        raise ValueError("promotion warrant decision disagrees with selected policy")
    if decision != "PROMOTE" and certified:
        raise ValueError("nonpromotion warrant cannot contain certified policies")

    diagnostics = artifact.get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        raise ValueError("promotion warrant diagnostics must be a mapping")
    _sha256_string(diagnostics.get("evidence_hash"), "evidence hash")
    family = diagnostics.get("family_definition")
    if not isinstance(family, Mapping):
        raise ValueError("promotion warrant family definition must be a mapping")
    candidate_ids = family.get("candidate_policy_ids")
    if (
        not isinstance(candidate_ids, list)
        or len(set(candidate_ids)) != len(candidate_ids)
        or not set(certified).issubset(set(candidate_ids))
    ):
        raise ValueError("promotion warrant candidate family is invalid")
    if family.get("multiplicity_method") != expected_procedure:
        raise ValueError("promotion warrant family procedure is inconsistent")
    selection_objective = artifact.get("selection_objective")
    if selection_objective not in {"minimize_cost", "minimize_latency"}:
        raise ValueError("promotion warrant selection objective is invalid")
    if family.get("selection_objective") != selection_objective:
        raise ValueError("promotion warrant selection objective is inconsistent")
    primary = "mean_cost" if selection_objective == "minimize_cost" else "mean_latency"
    secondary = "mean_latency" if primary == "mean_cost" else "mean_cost"
    operational = artifact.get("operational_selection_objective")
    if (
        not isinstance(operational, Mapping)
        or set(operational) != {"primary", "secondary", "tertiary", "selected_value"}
        or operational.get("primary") != primary
        or operational.get("secondary") != secondary
        or operational.get("tertiary") != "lexical_policy_id"
    ):
        raise ValueError("promotion warrant operational selection objective is inconsistent")
    summaries = diagnostics.get("candidate_summaries")
    if not isinstance(summaries, Mapping):
        raise ValueError("promotion warrant candidate summaries are invalid")
    if decision == "BLOCKED_INVALID_EVIDENCE":
        if not set(summaries).issubset(set(candidate_ids)):
            raise ValueError("promotion warrant candidate summaries name an unknown policy")
    elif set(summaries) != set(candidate_ids):
        raise ValueError("promotion warrant candidate summaries are incomplete")
    for policy_id, summary in summaries.items():
        if not isinstance(summary, Mapping):
            raise ValueError(f"promotion warrant candidate summary is invalid for {policy_id}")
        for field in ("mean_cost", "mean_latency"):
            value = summary.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not np.isfinite(float(value))
                or float(value) <= 0.0
            ):
                raise ValueError(
                    f"promotion warrant candidate {field} is invalid for {policy_id}"
                )
    selected_value = operational.get("selected_value")
    if selected is None:
        if selected_value is not None:
            raise ValueError("promotion warrant unselected result has an operational value")
    else:
        if (
            isinstance(selected_value, bool)
            or not isinstance(selected_value, (int, float))
            or not np.isfinite(float(selected_value))
            or float(selected_value) != float(summaries[selected][primary])
        ):
            raise ValueError("promotion warrant selected operational value is inconsistent")

    risk_tests = artifact.get("risk_tests")
    if not isinstance(risk_tests, list):
        raise ValueError("promotion warrant risk tests must be a list")
    hypothesis_ids: list[str] = []
    for risk_test in risk_tests:
        if not isinstance(risk_test, Mapping) or set(risk_test) != RISK_TEST_FIELDS:
            raise ValueError("promotion warrant risk-test fields are invalid")
        hypothesis_id = risk_test.get("hypothesis_id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            raise ValueError("promotion warrant hypothesis ID is invalid")
        hypothesis_ids.append(hypothesis_id)
        if risk_test.get("policy_id") not in candidate_ids:
            raise ValueError("promotion warrant risk test names an unknown policy")
        for field in ("raw_p_value", "adjusted_p_value", "rejection_threshold"):
            _probability(risk_test.get(field), field)
        if not isinstance(risk_test.get("rejected"), bool):
            raise ValueError("promotion warrant rejection flag must be boolean")
    if len(set(hypothesis_ids)) != len(hypothesis_ids):
        raise ValueError("promotion warrant contains duplicate hypotheses")
    if diagnostics.get("hypothesis_count") != len(risk_tests):
        raise ValueError("promotion warrant hypothesis count is inconsistent")


def _comparison_rows(method_rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    selected = [
        row
        for row in method_rows
        if row.get("method_id") == "fixed_sample_multi_risk_warrant_v1"
    ]
    return [dict(row) for row in selected]


def _report(method_rows: Sequence[Mapping[str, object]], profile: str) -> str:
    lines = [
        "# Focus 2 Fixed-Sample Multi-Risk Warrant Benchmark",
        "",
        f"Profile: **{profile} v2 developmental evidence**.",
        "",
        "Results remain scenario- and sample-size-specific. They are not a production qualification or a universal method ranking. Wilson intervals quantify Monte Carlo event-rate uncertainty, not candidate-risk uncertainty.",
        "",
        "| Scenario cell | Method | Multiplicity | Trials | False promotion | 95% MC Wilson interval | False certification | False block | Correct promotion | No decision |",
        "|---|---|---|---:|---:|---|---:|---:|---:|---:|",
    ]
    for row in method_rows:
        interval = json.loads(str(row["false_promotion_rate_confidence_interval"]))
        lines.append(
            "| {scenario} | {method} | {multiplicity} | {trials} | {fp:.4f} | [{low:.4f}, {high:.4f}] | {fc:.4f} | {fb:.4f} | {cp:.4f} | {nd:.4f} |".format(
                scenario=row["scenario_id"],
                method=row["method_id"],
                multiplicity=row["multiplicity_method"],
                trials=row["trial_count"],
                fp=float(row["false_promotion_rate"]),
                low=float(interval[0]),
                high=float(interval[1]),
                fc=float(row["false_certification_rate"]),
                fb=float(row["false_block_rate"]),
                cp=float(row["correct_promotion_rate"]),
                nd=float(row["no_decision_rate"]),
            )
        )
    lines.extend(
        [
            "",
            "Holm is the prespecified primary procedure; Bonferroni is the prespecified conservative comparison. Mixed, negative, and inconclusive outcomes are retained without retuning.",
            "",
        ]
    )
    return "\n".join(lines)


def _claim_boundaries() -> str:
    return """# Focus 2 Claim Boundaries

This developmental research output does not establish a new statistical theorem, universal false-promotion control, production readiness, human or clinical validation, official evaluator-platform performance, RAG Compass superiority, or universal governance superiority.

The fixed-sample warrant uses established exact-binomial, Hoeffding, Holm, and Bonferroni methods under stated bounded and independent-unit assumptions. Public method metadata states `observed_evidence_only=true`, `truth_isolated=true`, `research_only=true`, and `production_integrated=false`; it does not indicate production adoption. CI-v2 and LOCAL-v2 are developmental. FULL remains unexecuted; no target drand round has been selected, and the FULL seal has not started.
"""


def _commit_directory(staging: Path, root: Path) -> None:
    backup = root.parent / f".{root.name}.previous-{uuid.uuid4().hex}"
    moved = False
    committed = False
    try:
        if root.exists():
            _validate_existing(root)
            os.replace(root, backup)
            moved = True
        os.replace(staging, root)
        committed = True
    except BaseException:
        if moved and backup.exists() and not root.exists():
            os.replace(backup, root)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if committed and backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def write_focus2_outputs(
    result: Mapping[str, Any], output_root: str | Path
) -> tuple[Path, ...]:
    """Write one complete CI-v2 or LOCAL-v2 output set atomically."""

    root = _safe_output_root(output_root)
    manifest = dict(result["manifest"])
    _validate_manifest(manifest)
    warrants = result.get("warrant_artifacts")
    if not isinstance(warrants, Mapping) or set(warrants) != {"holm", "bonferroni"}:
        raise ValueError("result must contain one predeclared warrant per procedure")
    for procedure, artifact in warrants.items():
        _validate_warrant_artifact(artifact, str(procedure))

    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.staging-", dir=root.parent))
    try:
        commit, dirty = _git_state()
        manifest.update(
            {
                "complete": False,
                "code_commit": commit,
                "code_worktree_dirty": dirty,
                "runtime_environment": {
                    "python_version": platform.python_version(),
                    "operating_system": platform.system(),
                    "machine": platform.machine(),
                    "numpy_version": np.__version__,
                    "pyyaml_version": yaml.__version__,
                },
                "output_files": list(OUTPUT_FILENAMES),
                "output_integrity": {},
            }
        )
        _atomic_text(
            staging / "benchmark_manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        )
        _atomic_text(
            staging / "focus1_config_snapshot.yaml",
            yaml.safe_dump(result["config_snapshot"], sort_keys=False),
        )
        _atomic_text(
            staging / "focus2_config_snapshot.yaml",
            yaml.safe_dump(result["focus2_config_snapshot"], sort_keys=False),
        )
        _write_csv(staging / "scenario_truth.csv", result["scenario_truth_rows"])
        _write_csv(staging / "scenario_summary.csv", result["scenario_summary_rows"])
        _write_csv(staging / "method_summary.csv", result["method_summary_rows"])
        _write_csv(
            staging / "trial_summary_sample.csv", result["trial_summary_sample_rows"]
        )
        _atomic_text(
            staging / "promotion_warrant.json",
            json.dumps(warrants["holm"], indent=2, sort_keys=True, allow_nan=False) + "\n",
        )
        _atomic_text(
            staging / "promotion_warrant_bonferroni.json",
            json.dumps(warrants["bonferroni"], indent=2, sort_keys=True, allow_nan=False)
            + "\n",
        )
        _write_csv(
            staging / "holm_bonferroni_comparison.csv",
            _comparison_rows(result["method_summary_rows"]),
        )
        _atomic_text(
            staging / "focus2_benchmark_report.md",
            _report(result["method_summary_rows"], str(manifest["profile"])),
        )
        _atomic_text(staging / "claim_boundaries.md", _claim_boundaries())
        manifest["output_integrity"] = {
            name: _integrity(staging / name) for name in OUTPUT_FILENAMES[1:]
        }
        manifest["complete"] = True
        _atomic_text(
            staging / "benchmark_manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        )
        _integrity(staging / "benchmark_manifest.json")
        _commit_directory(staging, root)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    return tuple(root / name for name in OUTPUT_FILENAMES)


__all__ = ["OUTPUT_FILENAMES", "write_focus2_outputs"]
