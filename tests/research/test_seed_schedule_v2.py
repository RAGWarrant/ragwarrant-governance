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

from ragwarrant.research import benchmark as benchmark_module
from ragwarrant.research.benchmark import run_benchmark
from ragwarrant.research.reporting import classify_benchmark_manifest
from ragwarrant.research.seed_schedule import (
    AMENDMENT_ID,
    SEED_SCHEDULE_VERSION,
    build_seed_schedule_manifest,
    canonical_trial_identity,
    enumerate_profile_trial_identities,
    trial_seed_digest,
)
from ragwarrant.research.public_beacon import (
    FULL_CONFIRMATION_STATUS,
    FULL_ENTROPY_AMENDMENT_ID,
    FULL_ENTROPY_PROTOCOL,
    RETIRED_FULL_SEED_STATUS,
    VerifiedFullEntropy,
)
from ragwarrant.research.simulator import generate_evidence, load_config, simulate_trial


CONFIG = Path("configs/research/false_promotion_benchmark_v1.yaml")


def _config() -> dict:
    return load_config(CONFIG)


def _tiny_config() -> dict:
    config = _config()
    config["scenarios"] = [
        scenario
        for scenario in config["scenarios"]
        if scenario["scenario_id"] == "one_clearly_safe"
    ]
    config["scenarios"][0]["sample_sizes"] = [16, 32]
    for profile in ("CI", "LOCAL", "FULL"):
        config["profiles"][profile]["replicate_count"] = 2
    config["profiles"]["CI"]["bootstrap_resamples"] = 8
    config["trial_sample_limit"] = 2
    return config


def _historical_digests() -> dict[Path, str]:
    tracked = subprocess.run(
        ["git", "ls-files", "README.md", "artifacts", "results"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return {
        Path(name): hashlib.sha256(Path(name).read_bytes()).hexdigest()
        for name in tracked
        if Path(name).is_file()
    }


def test_same_identity_produces_same_seed_digest() -> None:
    identity = canonical_trial_identity(2, "CI", "all_unsafe_boundary", 256, 21)
    assert identity == "v2|CI|all_unsafe_boundary|256|21"
    assert trial_seed_digest(20260829, identity) == trial_seed_digest(20260829, identity)


def test_different_profiles_produce_different_identities() -> None:
    identities = {
        canonical_trial_identity(2, profile, "all_unsafe_boundary", 256, 21)
        for profile in ("CI", "LOCAL", "FULL")
    }
    assert len(identities) == 3


def test_configured_profile_identity_sets_are_disjoint() -> None:
    config = _config()
    identities = {
        profile: set(enumerate_profile_trial_identities(config, profile))
        for profile in ("CI", "LOCAL", "FULL")
    }
    assert len(identities["CI"]) == 384
    assert len(identities["LOCAL"]) == 4_000
    assert len(identities["FULL"]) == 80_000
    assert identities["CI"].isdisjoint(identities["LOCAL"])
    assert identities["CI"].isdisjoint(identities["FULL"])
    assert identities["LOCAL"].isdisjoint(identities["FULL"])


def test_complete_schedule_has_no_seed_fingerprint_duplicates() -> None:
    manifest = build_seed_schedule_manifest(_config())
    assert manifest["overlap_counts"] == {
        "CI_LOCAL": 0,
        "CI_FULL": 0,
        "LOCAL_FULL": 0,
    }
    assert manifest["duplicate_seed_count"] == 0
    assert manifest["full_entropy_protocol"] == FULL_ENTROPY_PROTOCOL
    assert manifest["full_target_round_selected"] is False
    assert manifest["full_evidence_generated"] is False
    assert manifest["full_results_inspected"] is False


def test_different_development_master_seeds_change_evidence() -> None:
    config = _config()
    scenario = config["scenarios"][0]
    first = generate_evidence(
        config, scenario, 64, 0, "confirmatory", "CI", master_seed=101
    )
    second = generate_evidence(
        config, scenario, 64, 0, "confirmatory", "CI", master_seed=102
    )
    assert first.evidence_hash != second.evidence_hash
    first_trial = simulate_trial(config, scenario, 64, 0, "CI", master_seed=101)
    second_trial = simulate_trial(config, scenario, 64, 0, "CI", master_seed=102)
    assert first_trial.trial_identity == second_trial.trial_identity
    assert first_trial.seed_fingerprint != second_trial.seed_fingerprint


def test_methods_share_evidence_and_output_records_identity() -> None:
    result = run_benchmark(_tiny_config(), "CI", master_seed=71)
    by_identity: dict[str, set[str]] = {}
    for row in result["trial_summary_sample_rows"]:
        identity = str(row["evidence_trial_identity"])
        by_identity.setdefault(identity, set()).add(str(row["evidence_hash"]))
        assert identity.startswith("v2|CI|")
        assert row["seed_schedule_version"] == SEED_SCHEDULE_VERSION
    assert by_identity
    assert all(len(hashes) == 1 for hashes in by_identity.values())
    assert result["manifest"]["seed_schedule_version"] == SEED_SCHEDULE_VERSION
    assert result["manifest"]["seed_schedule_amendment_id"] == AMENDMENT_ID
    assert result["manifest"]["evidence_role"] == "developmental"


@pytest.mark.parametrize("profile", ["ci", "UNKNOWN", ""])
def test_invalid_or_unknown_profiles_fail_closed(profile: str) -> None:
    with pytest.raises(ValueError, match="unknown profile"):
        canonical_trial_identity(2, profile, "all_unsafe_boundary", 64, 0)
    with pytest.raises(ValueError, match="unknown profile"):
        run_benchmark(_tiny_config(), profile)


def test_full_requires_published_verified_beacon_before_simulation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_simulation(*_args, **_kwargs):
        raise AssertionError("evidence generation must not start")

    monkeypatch.setattr(benchmark_module, "simulate_trial", forbidden_simulation)
    with pytest.raises(ValueError, match="published seal"):
        run_benchmark(_tiny_config(), "FULL")
    with pytest.raises(ValueError, match="rejects public"):
        run_benchmark(_tiny_config(), "FULL", master_seed=7)


def test_direct_simulator_full_calls_reject_public_seed_before_rng(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _tiny_config()
    scenario = config["scenarios"][0]

    def forbidden_rng(*_args, **_kwargs):
        raise AssertionError("FULL evidence RNG must not start")

    monkeypatch.setattr("ragwarrant.research.simulator.np.random.default_rng", forbidden_rng)
    with pytest.raises(ValueError, match="verified future-public-beacon"):
        generate_evidence(
            config, scenario, 16, 0, "confirmatory", "FULL", master_seed=7
        )
    with pytest.raises(ValueError, match="verified future-public-beacon"):
        simulate_trial(config, scenario, 16, 0, "FULL", master_seed=7)
    with pytest.raises(ValueError, match="verified future-public-beacon"):
        simulate_trial(config, scenario, 16, 0, "FULL")


def test_verified_full_entropy_context_cannot_be_constructed_directly() -> None:
    with pytest.raises(TypeError, match="only be created"):
        VerifiedFullEntropy(b"\x00" * 32, {})


def test_schedule_enumeration_never_calls_evidence_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_generation(*_args, **_kwargs):
        raise AssertionError("schedule enumeration called evidence generation")

    import ragwarrant.research.simulator as simulator

    monkeypatch.setattr(simulator, "generate_evidence", forbidden_generation)
    manifest = build_seed_schedule_manifest(_config())
    assert manifest["schedule_enumeration_generated_evidence"] is False


def test_v1_manifest_is_readable_but_retired_from_confirmation() -> None:
    legacy = {
        "benchmark_id": "known_truth_false_promotion_benchmark_v1",
        "profile": "CI",
        "complete": True,
    }
    assert classify_benchmark_manifest(legacy) == "exploratory_retired"


def test_static_schedule_proof_does_not_modify_historical_evidence() -> None:
    before = _historical_digests()
    assert before
    build_seed_schedule_manifest(_config())
    assert _historical_digests() == before


def test_development_cli_refuses_full_before_creating_output(tmp_path: Path) -> None:
    config = _tiny_config()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    output = tmp_path / "full-output"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path("src").resolve())
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_false_promotion_benchmark.py",
            "--config",
            str(config_path),
            "--output",
            str(output),
            "--profile",
            "FULL",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode != 0
    assert "autonomous sealed public-beacon workflow" in completed.stderr
    assert not output.exists()


def test_config_retires_local_seed_commitment_for_future_beacon() -> None:
    config_text = CONFIG.read_text(encoding="utf-8")
    config = _config()
    assert config["seed_schedule_version"] == 2
    assert config["seed_schedule_amendment_id"] == AMENDMENT_ID
    assert config["full_entropy_protocol"] == FULL_ENTROPY_PROTOCOL
    assert config["full_entropy_amendment_id"] == FULL_ENTROPY_AMENDMENT_ID
    assert config["full_confirmation_status"] == FULL_CONFIRMATION_STATUS
    assert config["retired_full_seed_status"] == RETIRED_FULL_SEED_STATUS
    assert "full_seed_commitment_sha256" not in config_text
