"""Atomic research-local reporting for the Focus 2 v2 ablation."""

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
    METHOD_ID as V1_METHOD_ID,
    SEED_SCHEDULE_VERSION,
)
from .fixed_sample_warrant_v2 import (
    METHOD_ID,
    PRESPECIFIED_V2_VARIANTS,
    VARIANT_A_ID,
    VARIANT_D_ID,
)
from .focus2_v2_benchmark import (
    FOCUS2_V2_BENCHMARK_ID,
    V1_BASELINE_COMMIT,
    V1_BASELINE_TAG,
    V2_CONFIG_CANONICAL_HASH,
    V2_CONFIG_FILE_SHA256,
)


OUTPUT_FILENAMES = (
    "benchmark_manifest.json",
    "focus1_config_snapshot.yaml",
    "focus2_v2_config_snapshot.yaml",
    "variant_specifications.json",
    "scenario_truth.csv",
    "scenario_summary.csv",
    "method_summary.csv",
    "trial_summary_sample.csv",
    "risk_bottleneck_summary.csv",
    "power_diagnostics_sample.csv",
    "warrant_samples.json",
    "focus2_v2_benchmark_report.md",
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
    if entries != set(OUTPUT_FILENAMES) or any(
        not path.is_file() for path in root.iterdir()
    ):
        raise ValueError("nonempty output root is not an exact prior Focus 2 v2 set")
    manifest = json.loads((root / "benchmark_manifest.json").read_text("utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("benchmark_id") != FOCUS2_V2_BENCHMARK_ID
        or manifest.get("complete") is not True
        or set(manifest.get("output_files", ())) != set(OUTPUT_FILENAMES)
    ):
        raise ValueError("prior Focus 2 v2 output manifest is invalid")
    expected = manifest.get("output_integrity")
    if not isinstance(expected, dict) or set(expected) != set(OUTPUT_FILENAMES[1:]):
        raise ValueError("prior Focus 2 v2 output integrity metadata is incomplete")
    for name in OUTPUT_FILENAMES[1:]:
        if expected[name] != _integrity(root / name):
            raise ValueError(f"prior Focus 2 v2 output integrity mismatch: {name}")


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
        "fixed_sample_warrant_v2",
    ):
        raise ValueError(
            "repository-local v2 outputs must stay under .local_data/fixed_sample_warrant_v2"
        )
    if root.exists():
        if not root.is_dir():
            raise ValueError("Focus 2 v2 output root exists and is not a directory")
        _validate_existing(root)
    return root


def _validate_manifest(manifest: Mapping[str, object]) -> None:
    if manifest.get("profile") not in {"CI", "LOCAL"}:
        raise ValueError("Focus 2 v2 reporting accepts only CI or LOCAL")
    required_exact = {
        "benchmark_id": FOCUS2_V2_BENCHMARK_ID,
        "focus1_benchmark_freeze_digest": FOCUS1_FREEZE_DIGEST,
        "v1_frozen_baseline_tag": V1_BASELINE_TAG,
        "v1_frozen_baseline_commit": V1_BASELINE_COMMIT,
        "v2_method_id": METHOD_ID,
        "seed_schedule_version": SEED_SCHEDULE_VERSION,
        "evidence_role": "developmental",
        "full_profile_used": False,
        "full_evidence_generated": False,
        "full_results_inspected": False,
        "target_drand_round_selected": False,
        "focus2_v2_config_hash": V2_CONFIG_CANONICAL_HASH,
        "focus2_v2_config_file_sha256": V2_CONFIG_FILE_SHA256,
        "truth_isolated_method_accessed_population_truth": False,
        "same_observed_evidence_object_shared_by_all_variants": True,
        "candidate_families_frozen_before_confirmatory_evidence": True,
        "post_hoc_filtered": False,
        "post_hoc_method_switching": False,
        "scenario_results_aggregated_into_headline": False,
        "complete": True,
    }
    for field, expected in required_exact.items():
        if manifest.get(field) != expected:
            raise ValueError(f"Focus 2 v2 manifest {field} must equal {expected!r}")
    if manifest.get("truth_access_method_ids") != []:
        raise ValueError("Focus 2 v2 truth-isolated variants may not access truth")
    variants = manifest.get("executed_method_variants")
    if not isinstance(variants, list) or len(variants) != 5:
        raise ValueError("Focus 2 v2 manifest must contain the five frozen variants")


def _validate_warrant_samples(samples: object) -> None:
    expected_method_ids = {
        VARIANT_A_ID: V1_METHOD_ID,
        **{
            specification.variant_id: specification.method_id
            for specification in PRESPECIFIED_V2_VARIANTS
        },
    }
    if not isinstance(samples, Mapping) or set(samples) != set(expected_method_ids):
        raise ValueError("one warrant sample is required for every frozen variant")
    for variant_id, artifact in samples.items():
        if not isinstance(artifact, Mapping):
            raise ValueError("warrant sample must be a mapping")
        required = {
            "method_id": expected_method_ids[variant_id],
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
        for field, expected in required.items():
            if artifact.get(field) != expected:
                raise ValueError(f"warrant sample {variant_id} has invalid {field}")
        if variant_id == VARIANT_A_ID:
            if "variant_id" in artifact:
                raise ValueError("the frozen v1 warrant sample must remain byte-contract exact")
        elif artifact.get("variant_id") != variant_id:
            raise ValueError(f"warrant sample {variant_id} has invalid variant_id")
        certified = artifact.get("certified_policy_ids")
        selected = artifact.get("selected_policy_id")
        if not isinstance(certified, list) or (selected is not None and selected not in certified):
            raise ValueError("warrant sample selection is not certified")


def _report(method_rows: Sequence[Mapping[str, object]], profile: str) -> str:
    lines = [
        "# Focus 2 v2 Power Redesign Benchmark",
        "",
        f"Profile: **{profile} seed-schedule-v2 developmental evidence**.",
        "",
        "Every row is a separate scenario/sample-size/method cell. No heterogeneous headline error rate is calculated. Wilson intervals describe Monte Carlo uncertainty, not candidate-risk uncertainty.",
        "",
        "| Scenario cell | Variant | n | Trials | False promotion count/rate (95% MC Wilson) | False certification | False block | Correct promotion | Correct no-safe block | Inconclusive | Mean certified set | Mean regret |",
        "|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in method_rows:
        interval = json.loads(str(row["false_promotion_rate_confidence_interval"]))
        regret = row["mean_operational_regret_when_safe_selection_occurs"]
        lines.append(
            "| {scenario} | {variant} | {sample} | {trials} | {fp_count}/{fp_rate:.4f} ([{low:.4f}, {high:.4f}]) | {fc_count}/{fc_rate:.4f} | {fb_count}/{fb_rate:.4f} | {cp_count}/{cp_rate:.4f} | {cb_count}/{cb_rate:.4f} | {inc_count}/{inc_rate:.4f} | {set_size:.4f} | {regret} |".format(
                scenario=row["scenario_id"],
                variant=row["variant_id"],
                sample=row["sample_size"],
                trials=row["trial_count"],
                fp_count=row["false_promotion_count"],
                fp_rate=float(row["false_promotion_rate"]),
                low=float(interval[0]),
                high=float(interval[1]),
                fc_count=row["false_certification_count"],
                fc_rate=float(row["false_certification_rate"]),
                fb_count=row["false_block_count"],
                fb_rate=float(row["false_block_rate"]),
                cp_count=row["correct_promotion_count"],
                cp_rate=float(row["correct_promotion_rate"]),
                cb_count=row["correct_no_safe_candidate_block_count"],
                cb_rate=float(row["correct_no_safe_candidate_block_rate"]),
                inc_count=row["inconclusive_count"],
                inc_rate=float(row["inconclusive_rate"]),
                set_size=float(row["mean_certified_set_size"]),
                regret="NA" if regret is None else f"{float(regret):.6f}",
            )
        )
    lines.extend(
        [
            "",
            f"Variant `{VARIANT_D_ID}` was prespecified as `{METHOD_ID}` before execution. Mixed and negative results are retained without retuning.",
            "",
        ]
    )
    return "\n".join(lines)


def _claim_boundaries() -> str:
    return """# Focus 2 v2 Claim Boundaries

This developmental research output does not establish a novel intersection-union principle, a novel Hoeffding-Bentkus result, guaranteed control from Monte Carlo outcomes, universal superiority, production readiness, human or clinical validation, or evaluator-platform performance.

Analytic validity depends on fixed candidate/risk families, valid marginal component p-values, bounded losses, and independent confirmatory units. Dependence among risks and candidates within a unit is permitted. CI-v2 and LOCAL-v2 remain developmental. FULL was not executed or inspected, and no target drand round was selected.
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


def write_focus2_v2_outputs(
    result: Mapping[str, Any], output_root: str | Path
) -> tuple[Path, ...]:
    root = _safe_output_root(output_root)
    manifest = dict(result["manifest"])
    _validate_manifest(manifest)
    _validate_warrant_samples(result.get("warrant_samples"))

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
            staging / "focus2_v2_config_snapshot.yaml",
            yaml.safe_dump(result["focus2_v2_config_snapshot"], sort_keys=False),
        )
        _atomic_text(
            staging / "variant_specifications.json",
            json.dumps(
                result["variant_specifications"], indent=2, sort_keys=True, allow_nan=False
            )
            + "\n",
        )
        _write_csv(staging / "scenario_truth.csv", result["scenario_truth_rows"])
        _write_csv(staging / "scenario_summary.csv", result["scenario_summary_rows"])
        _write_csv(staging / "method_summary.csv", result["method_summary_rows"])
        _write_csv(
            staging / "trial_summary_sample.csv", result["trial_summary_sample_rows"]
        )
        _write_csv(
            staging / "risk_bottleneck_summary.csv",
            result["risk_bottleneck_summary_rows"],
        )
        _write_csv(
            staging / "power_diagnostics_sample.csv",
            result["power_diagnostics_sample_rows"],
        )
        _atomic_text(
            staging / "warrant_samples.json",
            json.dumps(result["warrant_samples"], indent=2, sort_keys=True, allow_nan=False)
            + "\n",
        )
        _atomic_text(
            staging / "focus2_v2_benchmark_report.md",
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


__all__ = ["OUTPUT_FILENAMES", "write_focus2_v2_outputs"]
