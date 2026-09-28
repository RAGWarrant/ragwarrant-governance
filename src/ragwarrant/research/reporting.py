# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

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


OUTPUT_FILENAMES = (
    "benchmark_manifest.json",
    "config_snapshot.yaml",
    "scenario_truth.csv",
    "scenario_summary.csv",
    "method_summary.csv",
    "trial_summary_sample.csv",
    "false_promotion_report.md",
    "claim_boundaries.md",
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _git_state() -> tuple[str, bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=REPOSITORY_ROOT,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
                cwd=REPOSITORY_ROOT,
            ).stdout.strip()
        )
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unavailable", False


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


def classify_benchmark_manifest(manifest: Mapping[str, object]) -> str:
    version = manifest.get("seed_schedule_version", 1)
    if version == 1:
        return "exploratory_retired"
    if version != 2:
        return "invalid"
    profile = manifest.get("profile")
    if profile in {"CI", "LOCAL"}:
        return "developmental"
    if profile == "FULL":
        if manifest.get("full_seed_commitment_verified") is True:
            return "exploratory_retired"
        provenance = manifest.get("full_beacon_provenance")
        if (
            manifest.get("full_entropy_protocol")
            == "DRAND_QUICKNET_FUTURE_ROUND_V1"
            and isinstance(provenance, Mapping)
            and provenance.get("beacon_signature_verified") is True
            and provenance.get("full_master_seed_persisted") is False
            and provenance.get("github_oidc_execution_verified") is True
        ):
            return "confirmatory"
    return "invalid"


def _report(
    method_rows: Sequence[Mapping[str, object]], evidence_role: str
) -> str:
    lines = [
        "# Known-Truth False-Promotion Benchmark Report",
        "",
        f"Evidence role: **{evidence_role}**.",
        "",
        "This report preserves scenario-specific outcomes. It does not select a preferred method or establish real-world safety.",
        "",
        "The confidence interval is a two-sided 95% Wilson interval for Monte Carlo trial-event estimation, not a candidate-risk interval.",
        "",
        "| Scenario | Method | Research role | Trials | False promotion | 95% MC interval | False certification | False block | Correct promotion |",
        "|---|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    for row in method_rows:
        interval = json.loads(str(row["false_promotion_rate_confidence_interval"]))
        lines.append(
            "| {scenario} | {method} | {role} | {trials} | {false_promotion:.4f} | [{low:.4f}, {high:.4f}] | {false_certification:.4f} | {false_block:.4f} | {correct_promotion:.4f} |".format(
                scenario=row["scenario_id"],
                method=row["method_id"],
                role=(
                    "benchmark_control"
                    if bool(row["benchmark_control_only"])
                    else "research_candidate"
                ),
                trials=row["trial_count"],
                false_promotion=float(row["false_promotion_rate"]),
                low=float(interval[0]),
                high=float(interval[1]),
                false_certification=float(row["false_certification_rate"]),
                false_block=float(row["false_block_rate"]),
                correct_promotion=float(row["correct_promotion_rate"]),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "Negative, mixed, weak, and inconclusive results are retained. The oracle is a truth-using benchmark control. The always-block method is a trivial control. Unsupported methods have no trial denominators.",
            "",
        ]
    )
    return "\n".join(lines)


def _claim_boundaries() -> str:
    return """# Claim Boundaries

This local research run measures repeated-trial governance correctness under synthetic population truth known by construction.

It does not establish a novel theorem, universal method superiority, production readiness, human or clinical validation, official evaluator-platform performance, Learn-Then-Test novelty, conformal-risk novelty, sequential-testing novelty, or RAG Compass superiority.

The oracle uses population truth and is excluded from truth-isolated method IDs. The naive point-estimate and corrected paired-bootstrap gates are benchmark controls without a family-wise error-control claim. They remain executed in scenario-level false-promotion and false-block comparisons. Monte Carlo Wilson intervals describe simulation estimation uncertainty, not uncertainty bounds used to certify a candidate. `research_only=true` and `production_integrated=false` for every method in this package.

No scenario-specific result is pooled into a headline score, and `post_hoc_filtered` is false.
"""


def _file_integrity(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if not payload:
        raise ValueError(f"required output is empty: {path.name}")
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def _validate_existing_output_set(root: Path) -> None:
    entries = {path.name for path in root.iterdir()}
    if not entries:
        return
    if entries != set(OUTPUT_FILENAMES) or any(not path.is_file() for path in root.iterdir()):
        raise ValueError(
            "nonempty output root is not an exact prior false-promotion benchmark output set"
        )
    try:
        manifest = json.loads((root / "benchmark_manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("prior benchmark manifest is unreadable") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("benchmark_id") != "known_truth_false_promotion_benchmark_v1"
        or manifest.get("complete") is not True
        or set(manifest.get("output_files", ())) != set(OUTPUT_FILENAMES)
    ):
        raise ValueError("nonempty output root is not a verified complete prior benchmark run")
    integrity = manifest.get("output_integrity")
    if not isinstance(integrity, dict) or set(integrity) != set(OUTPUT_FILENAMES[1:]):
        raise ValueError("prior benchmark manifest has incomplete output integrity metadata")
    for name in OUTPUT_FILENAMES[1:]:
        expected = integrity[name]
        actual = _file_integrity(root / name)
        if not isinstance(expected, dict) or expected != actual:
            raise ValueError(f"prior benchmark output integrity mismatch: {name}")


def _safe_output_root(output_root: str | Path) -> Path:
    requested = Path(output_root).absolute()
    for component in (requested, *requested.parents):
        if component.exists() and component.is_symlink():
            raise ValueError("benchmark output root and its existing ancestors must not be symlinks")
    root = requested.resolve(strict=False)
    repository = REPOSITORY_ROOT.resolve()
    if root == repository or root in repository.parents:
        raise ValueError("benchmark output root must not be the repository root or an ancestor")
    if root.exists():
        if root.is_symlink():
            raise ValueError("benchmark output root must not be a symlink")
        if not root.is_dir():
            raise ValueError(f"output root exists and is not a directory: {root}")
        _validate_existing_output_set(root)
    return root


def _remove_tree_best_effort(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except OSError:
        pass


def _commit_output_directory(staging: Path, root: Path) -> None:
    backup = root.parent / f".{root.name}.previous-{uuid.uuid4().hex}"
    moved_previous = False
    committed = False
    try:
        if root.exists():
            if _safe_output_root(root) != root:
                raise ValueError("output root changed during benchmark publication")
            os.replace(root, backup)
            moved_previous = True
        os.replace(staging, root)
        committed = True
    except BaseException:
        if moved_previous and backup.exists() and not root.exists():
            os.replace(backup, root)
        raise
    finally:
        if staging.exists():
            _remove_tree_best_effort(staging)
        if committed and backup.exists():
            _remove_tree_best_effort(backup)


def write_benchmark_outputs(
    result: Mapping[str, Any], output_root: str | Path
) -> tuple[Path, ...]:
    root = _safe_output_root(output_root)
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{root.name}.staging-", dir=root.parent)
    )
    try:
        commit, dirty = _git_state()
        manifest = dict(result["manifest"])
        evidence_role = classify_benchmark_manifest(manifest)
        if evidence_role == "invalid" or manifest.get("evidence_role") != evidence_role:
            raise ValueError("benchmark manifest evidence role is invalid or inconsistent")
        manifest["complete"] = False
        manifest["code_commit"] = commit
        manifest["code_worktree_dirty"] = dirty
        manifest["runtime_environment"] = {
            "python_version": platform.python_version(),
            "operating_system": platform.system(),
            "machine": platform.machine(),
            "numpy_version": np.__version__,
            "pyyaml_version": yaml.__version__,
        }
        manifest["output_files"] = list(OUTPUT_FILENAMES)
        manifest["output_integrity"] = {}

        _atomic_text(
            staging / "benchmark_manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        )
        _atomic_text(
            staging / "config_snapshot.yaml",
            yaml.safe_dump(result["config_snapshot"], sort_keys=False),
        )
        _write_csv(staging / "scenario_truth.csv", result["scenario_truth_rows"])
        _write_csv(staging / "scenario_summary.csv", result["scenario_summary_rows"])
        _write_csv(staging / "method_summary.csv", result["method_summary_rows"])
        _write_csv(
            staging / "trial_summary_sample.csv", result["trial_summary_sample_rows"]
        )
        _atomic_text(
            staging / "false_promotion_report.md",
            _report(result["method_summary_rows"], evidence_role),
        )
        _atomic_text(staging / "claim_boundaries.md", _claim_boundaries())

        non_manifest = OUTPUT_FILENAMES[1:]
        manifest["output_integrity"] = {
            name: _file_integrity(staging / name) for name in non_manifest
        }
        manifest["complete"] = True
        _atomic_text(
            staging / "benchmark_manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        )
        _file_integrity(staging / "benchmark_manifest.json")
        _commit_output_directory(staging, root)
    except BaseException:
        if staging.exists():
            _remove_tree_best_effort(staging)
        raise
    return tuple(root / name for name in OUTPUT_FILENAMES)
