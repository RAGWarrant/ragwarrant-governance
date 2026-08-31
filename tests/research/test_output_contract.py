from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ragwarrant.research.benchmark import run_benchmark
from ragwarrant.research import reporting
from ragwarrant.research.reporting import OUTPUT_FILENAMES, write_benchmark_outputs
from ragwarrant.research.simulator import load_config


CONFIG = Path("configs/research/false_promotion_benchmark_v1.yaml")


def _tiny_result() -> tuple[dict, dict]:
    config = load_config(CONFIG)
    config["scenarios"] = [
        scenario for scenario in config["scenarios"] if scenario["scenario_id"] == "one_clearly_safe"
    ]
    config["scenarios"][0]["sample_sizes"] = [12, 24]
    config["profiles"]["CI"] = {"replicate_count": 2, "bootstrap_resamples": 12}
    config["trial_sample_limit"] = 1
    return config, run_benchmark(copy.deepcopy(config), "CI", master_seed=7)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_required_local_output_contract(tmp_path: Path) -> None:
    _, result = _tiny_result()
    paths = write_benchmark_outputs(result, tmp_path / ".local_data" / "benchmark")
    assert {path.name for path in paths} == set(OUTPUT_FILENAMES)
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths)
    manifest = json.loads((paths[0]).read_text(encoding="utf-8"))
    assert manifest["post_hoc_filtered"] is False
    assert manifest["deployable_method_accessed_population_truth"] is False
    assert manifest["complete"] is True
    assert manifest["seed_schedule_version"] == 2
    assert manifest["evidence_role"] == "developmental"
    assert manifest["full_entropy_protocol"] == "DRAND_QUICKNET_FUTURE_ROUND_V1"
    assert manifest["full_confirmation_status"] == "PENDING_FUTURE_PUBLIC_BEACON_SEAL"
    assert manifest["full_master_seed_persisted"] is False
    assert manifest["full_evidence_generated"] is False
    assert "oracle_safe_objective" not in manifest["deployable_method_ids"]
    assert set(manifest["output_integrity"]) == set(OUTPUT_FILENAMES[1:])
    for name, integrity in manifest["output_integrity"].items():
        payload = (paths[0].parent / name).read_bytes()
        assert integrity["size_bytes"] == len(payload)
        assert integrity["sha256"] == hashlib.sha256(payload).hexdigest()


def test_outputs_contain_no_private_paths_or_secret_markers(tmp_path: Path) -> None:
    _, result = _tiny_result()
    root = tmp_path / "output"
    paths = write_benchmark_outputs(result, root)
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert str(Path.cwd().resolve()) not in combined
    assert str(tmp_path.resolve()) not in combined
    lowered = combined.lower()
    assert "api_key" not in lowered
    assert "authorization: bearer" not in lowered
    assert "private chain-of-thought" not in lowered
    assert "full_seed_secret" not in lowered


def test_run_does_not_modify_tracked_historical_artifacts(tmp_path: Path) -> None:
    tracked_output = subprocess.run(
        ["git", "ls-files", "README.md", "artifacts", "results"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    existing = [Path(path) for path in tracked_output if Path(path).is_file()]
    assert existing
    before = {path: _digest(path) for path in existing}
    _, result = _tiny_result()
    write_benchmark_outputs(result, tmp_path / "isolated-output")
    after = {path: _digest(path) for path in existing}
    assert before == after


def test_config_snapshot_and_truth_output_are_present(tmp_path: Path) -> None:
    config, result = _tiny_result()
    root = tmp_path / "output"
    write_benchmark_outputs(result, root)
    snapshot = load_config(root / "config_snapshot.yaml")
    assert snapshot["protocol_version"] == config["protocol_version"]
    truth_text = (root / "scenario_truth.csv").read_text(encoding="utf-8")
    assert "overall_quality_delta_vs_incumbent" in truth_text
    assert "truly_promotion_safe" in truth_text


def test_failed_first_write_leaves_no_complete_output_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, result = _tiny_result()
    root = tmp_path / "output"

    def fail_csv(*_args, **_kwargs):
        raise OSError("injected CSV failure")

    monkeypatch.setattr(reporting, "_write_csv", fail_csv)
    with pytest.raises(OSError, match="injected CSV failure"):
        write_benchmark_outputs(result, root)
    assert not root.exists()
    assert not tuple(tmp_path.glob(".output.staging-*"))


def test_failed_rerun_preserves_whole_previous_output_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, result = _tiny_result()
    root = tmp_path / "output"
    write_benchmark_outputs(result, root)
    before = {name: (root / name).read_bytes() for name in OUTPUT_FILENAMES}

    def fail_csv(*_args, **_kwargs):
        raise OSError("injected rerun failure")

    monkeypatch.setattr(reporting, "_write_csv", fail_csv)
    with pytest.raises(OSError, match="injected rerun failure"):
        write_benchmark_outputs(result, root)
    after = {name: (root / name).read_bytes() for name in OUTPUT_FILENAMES}
    assert after == before
    assert json.loads(after["benchmark_manifest.json"])["complete"] is True
    assert not tuple(tmp_path.glob(".output.staging-*"))
    assert not tuple(tmp_path.glob(".output.previous-*"))


def test_cli_runs_bounded_profile_without_printing_private_output_path(
    tmp_path: Path,
) -> None:
    config, _ = _tiny_result()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    output_root = tmp_path / "cli-output"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path("src").resolve())
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_false_promotion_benchmark.py",
            "--config",
            str(config_path),
            "--output",
            str(output_root),
            "--profile",
            "CI",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["status"] == "complete"
    assert summary["seed_schedule_version"] == 2
    assert summary["evidence_role"] == "developmental"
    assert str(tmp_path.resolve()) not in completed.stdout
    assert {path.name for path in output_root.iterdir()} == set(OUTPUT_FILENAMES)


def test_nonempty_unrecognized_output_directory_is_preserved(tmp_path: Path) -> None:
    _, result = _tiny_result()
    root = tmp_path / "unrelated"
    root.mkdir()
    unrelated = root / "do-not-delete.txt"
    unrelated.write_bytes(b"owner data")
    with pytest.raises(ValueError, match="not an exact prior"):
        write_benchmark_outputs(result, root)
    assert unrelated.read_bytes() == b"owner data"
    assert tuple(root.iterdir()) == (unrelated,)


def test_extra_file_in_prior_output_blocks_rerun_and_is_preserved(tmp_path: Path) -> None:
    _, result = _tiny_result()
    root = tmp_path / "output"
    write_benchmark_outputs(result, root)
    unrelated = root / "owner-note.txt"
    unrelated.write_bytes(b"keep me")
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    with pytest.raises(ValueError, match="not an exact prior"):
        write_benchmark_outputs(result, root)
    after = {path.name: path.read_bytes() for path in root.iterdir()}
    assert after == before


def test_repository_root_and_ancestor_are_rejected_without_writes() -> None:
    _, result = _tiny_result()
    with pytest.raises(ValueError, match="repository root or an ancestor"):
        write_benchmark_outputs(result, Path.cwd())
    with pytest.raises(ValueError, match="repository root or an ancestor"):
        write_benchmark_outputs(result, Path.cwd().parent)


def test_symlink_output_root_is_rejected_and_target_preserved(tmp_path: Path) -> None:
    _, result = _tiny_result()
    target = tmp_path / "target"
    target.mkdir()
    unrelated = target / "owner-data.txt"
    unrelated.write_bytes(b"preserve")
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this platform")
    with pytest.raises(ValueError, match="must not be symlinks"):
        write_benchmark_outputs(result, link)
    assert unrelated.read_bytes() == b"preserve"
