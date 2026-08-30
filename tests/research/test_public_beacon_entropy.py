from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from ragwarrant.research import benchmark as benchmark_module
from ragwarrant.research.benchmark import run_benchmark
from ragwarrant.research.public_beacon import (
    DRAND_CLIENT_INTEGRITY,
    DRAND_CLIENT_VERSION,
    FULL_ENTROPY_PROTOCOL,
    PINNED_QUICKNET,
    QUICKNET_GENESIS_TIME,
    QUICKNET_PERIOD_SECONDS,
    QUICKNET_RELAYS,
    VerifiedFullEntropy,
    build_execution_closure,
    build_seal_manifest,
    derive_full_master_seed,
    first_quicknet_round_at_or_after,
    full_trial_seed_digest,
    quicknet_round_timestamp,
    sealed_round_for_retry,
    select_future_quicknet_round,
    validate_seal_manifest,
    verified_full_entropy_from_receipt,
)
from ragwarrant.research.seed_schedule import build_seed_schedule_manifest
from ragwarrant.research.simulator import load_config


CONFIG = Path("configs/research/false_promotion_benchmark_v1.yaml")
SUBJECT_COMMIT = "ab" * 20
FREEZE_DIGEST = "cd" * 32
HISTORICAL_ROUND = 1
HISTORICAL_SIGNATURE = (
    "b55e7cb2d5c613ee0b2e28d6750aabbb78c39dcc96bd9d38c2c2e12198df9557"
    "1de8e8e402a0cc48871c7089a2b3af4b"
)
HISTORICAL_RANDOMNESS = (
    "1466a6cd24e327188770752f6134001c64d6efcc590ccc26b721611ad96f165a"
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _seal() -> dict[str, object]:
    target_timestamp = quicknet_round_timestamp(HISTORICAL_ROUND)
    seal = build_seal_manifest(
        subject_commit=SUBJECT_COMMIT,
        benchmark_freeze_digest=FREEZE_DIGEST,
        workflow_start_timestamp=target_timestamp - 1800,
    )
    assert seal["drand"]["target_round"] == HISTORICAL_ROUND  # type: ignore[index]
    return seal


def _receipt(seal: dict[str, object]) -> dict[str, object]:
    drand = seal["drand"]
    target_round = int(drand["target_round"])  # type: ignore[index]
    target_timestamp = quicknet_round_timestamp(target_round)
    return {
        "schema_version": "1.0",
        "entropy_protocol": FULL_ENTROPY_PROTOCOL,
        "verification_status": "VERIFIED",
        "signature_verified": True,
        "subject_commit": SUBJECT_COMMIT,
        "benchmark_freeze_digest": FREEZE_DIGEST,
        "seal_sha256": hashlib.sha256(
            (_canonical_json(seal) + "\n").encode("utf-8")
        ).hexdigest(),
        "verifier": {
            "package": "drand-client",
            "version": DRAND_CLIENT_VERSION,
            "integrity": DRAND_CLIENT_INTEGRITY,
            "beacon_verification_disabled": False,
        },
        "drand": {
            **PINNED_QUICKNET.as_dict(),
            "round": target_round,
            "randomness": HISTORICAL_RANDOMNESS,
            "signature": HISTORICAL_SIGNATURE,
        },
        "relay_verifications": [
            {
                "relay_url": relay,
                "round": target_round,
                "response_sha256": hashlib.sha256(relay.encode("utf-8")).hexdigest(),
                "signature_verified": True,
            }
            for relay in QUICKNET_RELAYS
        ],
        "seal_publication": {
            "schema_version": "1.0",
            "subject_commit": SUBJECT_COMMIT,
            "seal_sha256": hashlib.sha256(
                (_canonical_json(seal) + "\n").encode("utf-8")
            ).hexdigest(),
            "seal_commit_sha": "12" * 20,
            "canonical_seal_branch": f"ragwarrant-full-seal-{SUBJECT_COMMIT}",
            "canonical_seal_ref": f"refs/heads/ragwarrant-full-seal-{SUBJECT_COMMIT}",
            "frozen_subject_ref": f"refs/heads/ragwarrant-full-subject-{SUBJECT_COMMIT}",
            "draft_pr_url": "https://github.com/RAGWarrant/ragwarrant-governance/pull/999",
            "github_created_at_utc": __import__("datetime")
            .datetime.fromtimestamp(target_timestamp - 1700, tz=__import__("datetime").timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "seal_workflow_run_id": 12345,
        },
    }


def _verified_entropy() -> VerifiedFullEntropy:
    seal = _seal()
    return verified_full_entropy_from_receipt(
        seal,
        _receipt(seal),
        current_timestamp=quicknet_round_timestamp(HISTORICAL_ROUND) + 1,
        expected_subject_commit=SUBJECT_COMMIT,
        expected_benchmark_freeze_digest=FREEZE_DIGEST,
    )


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


def test_round_timestamp_and_future_round_formula_are_exact() -> None:
    assert quicknet_round_timestamp(1) == QUICKNET_GENESIS_TIME
    assert quicknet_round_timestamp(2) == QUICKNET_GENESIS_TIME + 3
    assert first_quicknet_round_at_or_after(QUICKNET_GENESIS_TIME) == 1
    start = QUICKNET_GENESIS_TIME + 10_000
    round_number, scheduled = select_future_quicknet_round(start)
    assert scheduled == quicknet_round_timestamp(round_number)
    assert scheduled >= start + 1800
    assert quicknet_round_timestamp(round_number - 1) < start + 1800


def test_canonical_byte_serialization_is_stable() -> None:
    master = derive_full_master_seed(
        target_round=HISTORICAL_ROUND,
        verified_beacon_randomness=HISTORICAL_RANDOMNESS,
        benchmark_freeze_digest=FREEZE_DIGEST,
        focus2_freeze_commit_sha=SUBJECT_COMMIT,
    )
    assert master.hex() == "b06acdc71a499c6575aa6d76351b1286990c338ab51add713f5323cdac22b2c4"
    assert full_trial_seed_digest(
        master, "v2|FULL|all_unsafe_boundary|256|21"
    ) == "f03a943a4ab75f96c6d9988f7f2b3b6bc8882d575d30126a495417c3a03d9061"


def test_stage_a_and_stage_b_hash_canonical_seal_json() -> None:
    seal = _seal()
    pretty = json.dumps(seal, indent=2, sort_keys=True) + "\n"
    raw_hash = hashlib.sha256(pretty.encode("utf-8")).hexdigest()
    canonical_hash = hashlib.sha256(
        (_canonical_json(seal) + "\n").encode("utf-8")
    ).hexdigest()
    assert raw_hash != canonical_hash
    seal_workflow = Path(".github/workflows/research-full-seal.yml").read_text(
        encoding="utf-8"
    )
    execute_workflow = Path(".github/workflows/research-full-execute.yml").read_text(
        encoding="utf-8"
    )
    for workflow in (seal_workflow, execute_workflow):
        assert 'separators=(",",":")' in workflow
        assert "canonical.encode()" in workflow
    assert 'sha256sum "$seal"' not in execute_workflow


def test_same_verified_beacon_and_freeze_inputs_are_deterministic() -> None:
    kwargs = {
        "target_round": HISTORICAL_ROUND,
        "verified_beacon_randomness": HISTORICAL_RANDOMNESS,
        "benchmark_freeze_digest": FREEZE_DIGEST,
        "focus2_freeze_commit_sha": SUBJECT_COMMIT,
    }
    assert derive_full_master_seed(**kwargs) == derive_full_master_seed(**kwargs)


def test_different_rounds_change_master_seed() -> None:
    first = derive_full_master_seed(
        target_round=1000,
        verified_beacon_randomness=HISTORICAL_RANDOMNESS,
        benchmark_freeze_digest=FREEZE_DIGEST,
        focus2_freeze_commit_sha=SUBJECT_COMMIT,
    )
    second = derive_full_master_seed(
        target_round=1001,
        verified_beacon_randomness=HISTORICAL_RANDOMNESS,
        benchmark_freeze_digest=FREEZE_DIGEST,
        focus2_freeze_commit_sha=SUBJECT_COMMIT,
    )
    assert first != second


def test_different_frozen_commits_change_master_seed() -> None:
    first = derive_full_master_seed(
        target_round=1000,
        verified_beacon_randomness=HISTORICAL_RANDOMNESS,
        benchmark_freeze_digest=FREEZE_DIGEST,
        focus2_freeze_commit_sha=SUBJECT_COMMIT,
    )
    second = derive_full_master_seed(
        target_round=1000,
        verified_beacon_randomness=HISTORICAL_RANDOMNESS,
        benchmark_freeze_digest=FREEZE_DIGEST,
        focus2_freeze_commit_sha="ef" * 20,
    )
    assert first != second


def test_different_benchmark_digests_change_master_seed() -> None:
    first = derive_full_master_seed(
        target_round=1000,
        verified_beacon_randomness=HISTORICAL_RANDOMNESS,
        benchmark_freeze_digest=FREEZE_DIGEST,
        focus2_freeze_commit_sha=SUBJECT_COMMIT,
    )
    second = derive_full_master_seed(
        target_round=1000,
        verified_beacon_randomness=HISTORICAL_RANDOMNESS,
        benchmark_freeze_digest="ef" * 32,
        focus2_freeze_commit_sha=SUBJECT_COMMIT,
    )
    assert first != second


def test_raw_master_seed_is_not_exposed_in_public_provenance() -> None:
    entropy = _verified_entropy()
    master_hex = derive_full_master_seed(
        target_round=HISTORICAL_ROUND,
        verified_beacon_randomness=HISTORICAL_RANDOMNESS,
        benchmark_freeze_digest=FREEZE_DIGEST,
        focus2_freeze_commit_sha=SUBJECT_COMMIT,
    ).hex()
    public_text = json.dumps(entropy.public_provenance(), sort_keys=True)
    assert master_hex not in public_text
    assert master_hex not in repr(entropy)
    assert entropy.public_provenance()["full_master_seed_persisted"] is False


def test_full_cannot_execute_without_a_published_seal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(CONFIG)
    config["scenarios"] = config["scenarios"][:1]
    config["profiles"]["FULL"]["replicate_count"] = 1

    def forbidden(*_args, **_kwargs):
        raise AssertionError("FULL evidence generation started")

    monkeypatch.setattr(benchmark_module, "simulate_trial", forbidden)
    with pytest.raises(ValueError, match="published seal"):
        run_benchmark(config, "FULL")


def test_imported_private_entropy_token_cannot_authorize_local_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ragwarrant.research.public_beacon as public_beacon

    config = load_config(CONFIG)
    config["scenarios"] = config["scenarios"][:1]
    config["profiles"]["FULL"]["replicate_count"] = 1
    forged = VerifiedFullEntropy(
        b"\x00" * 32,
        {"subject_commit": SUBJECT_COMMIT, "seal_sha256": "00" * 32},
        _token=public_beacon._VERIFIED_ENTROPY_TOKEN,
    )
    with pytest.raises(AttributeError):
        forged._execution_attestation = {  # type: ignore[attr-defined]
            "github_oidc_execution_verified": True
        }
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(
        benchmark_module,
        "simulate_trial",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("local forged FULL reached evidence generation")
        ),
    )
    with pytest.raises(ValueError, match="frozen GitHub Actions workflow"):
        run_benchmark(config, "FULL", verified_full_entropy=forged)


def test_imported_private_entropy_token_cannot_authorize_direct_simulator_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ragwarrant.research.public_beacon as public_beacon
    from ragwarrant.research.simulator import generate_evidence, simulate_trial

    config = load_config(CONFIG)
    config["scenarios"] = config["scenarios"][:1]
    scenario = config["scenarios"][0]
    forged = VerifiedFullEntropy(
        b"\x00" * 32,
        {"subject_commit": SUBJECT_COMMIT, "seal_sha256": "00" * 32},
        _token=public_beacon._VERIFIED_ENTROPY_TOKEN,
    )
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(
        "ragwarrant.research.simulator.np.random.default_rng",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("local forged FULL reached evidence RNG")
        ),
    )
    with pytest.raises(ValueError, match="active frozen GitHub Actions"):
        generate_evidence(
            config, scenario, 64, 0, "confirmatory", "FULL", master_seed=forged
        )
    with pytest.raises(ValueError, match="active frozen GitHub Actions"):
        simulate_trial(config, scenario, 64, 0, "FULL", master_seed=forged)


def test_full_cannot_execute_before_sealed_round() -> None:
    seal = _seal()
    with pytest.raises(ValueError, match="before the sealed round"):
        verified_full_entropy_from_receipt(
            seal,
            _receipt(seal),
            current_timestamp=quicknet_round_timestamp(HISTORICAL_ROUND) - 1,
            expected_subject_commit=SUBJECT_COMMIT,
            expected_benchmark_freeze_digest=FREEZE_DIGEST,
        )


def test_full_cannot_execute_with_a_different_round() -> None:
    seal = _seal()
    receipt = _receipt(seal)
    receipt["drand"]["round"] = HISTORICAL_ROUND + 1  # type: ignore[index]
    with pytest.raises(ValueError, match="differs from the sealed round"):
        verified_full_entropy_from_receipt(
            seal,
            receipt,
            current_timestamp=quicknet_round_timestamp(HISTORICAL_ROUND) + 1,
            expected_subject_commit=SUBJECT_COMMIT,
            expected_benchmark_freeze_digest=FREEZE_DIGEST,
        )


def test_full_cannot_execute_with_unverified_beacon() -> None:
    seal = _seal()
    receipt = _receipt(seal)
    receipt["signature_verified"] = False
    with pytest.raises(ValueError, match="verified beacon signature"):
        verified_full_entropy_from_receipt(
            seal,
            receipt,
            current_timestamp=quicknet_round_timestamp(HISTORICAL_ROUND) + 1,
            expected_subject_commit=SUBJECT_COMMIT,
            expected_benchmark_freeze_digest=FREEZE_DIGEST,
        )


def test_self_asserted_verified_flags_cannot_replace_bls_verification() -> None:
    seal = _seal()
    receipt = _receipt(seal)
    signature = str(receipt["drand"]["signature"])  # type: ignore[index]
    tampered = f"{signature[:-1]}{'0' if signature[-1] != '0' else '1'}"
    receipt["drand"]["signature"] = tampered  # type: ignore[index]
    receipt["drand"]["randomness"] = hashlib.sha256(  # type: ignore[index]
        bytes.fromhex(tampered)
    ).hexdigest()
    with pytest.raises(ValueError, match="BLS signature verification failed"):
        verified_full_entropy_from_receipt(
            seal,
            receipt,
            current_timestamp=quicknet_round_timestamp(HISTORICAL_ROUND) + 1,
            expected_subject_commit=SUBJECT_COMMIT,
            expected_benchmark_freeze_digest=FREEZE_DIGEST,
        )


@pytest.mark.parametrize("field", ["chain_hash", "public_key"])
def test_incorrect_chain_hash_or_public_key_fails_closed(field: str) -> None:
    seal = _seal()
    seal["drand"][field] = "00"  # type: ignore[index]
    with pytest.raises(ValueError, match="does not match pinned Quicknet"):
        validate_seal_manifest(seal)


def test_second_seal_is_rejected_by_atomic_deterministic_workflow() -> None:
    workflow = Path(".github/workflows/research-full-seal.yml").read_text(
        encoding="utf-8"
    )
    assert "concurrency:" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "ragwarrant-full-seal-${subject}" in workflow
    assert "git ls-remote" in workflow
    assert "gh pr list" in workflow and "--state all" in workflow
    assert "seal_commit_sha" in workflow
    assert "headRefOid" in workflow
    assert "cmp --silent \"$seal\" \"$RUNNER_TEMP/existing-seal.json\"" in workflow
    assert "--force" not in workflow


def test_no_fallback_round_path_exists() -> None:
    seal = _seal()
    seal["no_fallback_round"] = False
    with pytest.raises(ValueError, match="prohibit fallback"):
        validate_seal_manifest(seal)
    verifier = Path(".github/drand-verifier/verify_quicknet.mjs").read_text(
        encoding="utf-8"
    )
    assert "fetchBeacon(client, targetRound)" in verifier
    assert "public/latest" not in verifier
    assert "fetchBeacon(client)" not in verifier
    assert "targetRound +" not in verifier and "targetRound -" not in verifier


def test_retry_uses_only_the_original_round() -> None:
    seal = _seal()
    assert sealed_round_for_retry(seal) == HISTORICAL_ROUND
    assert sealed_round_for_retry(seal, HISTORICAL_ROUND) == HISTORICAL_ROUND
    with pytest.raises(ValueError, match="original sealed round"):
        sealed_round_for_retry(seal, HISTORICAL_ROUND + 1)


def test_ci_and_local_do_not_invoke_drand() -> None:
    benchmark_source = Path("src/ragwarrant/research/benchmark.py").read_text(
        encoding="utf-8"
    )
    verifier_source = Path(".github/drand-verifier/verify_quicknet.mjs").read_text(
        encoding="utf-8"
    )
    assert "profile == \"FULL\"" in benchmark_source
    assert "fetchBeacon(client, targetRound)" in verifier_source
    ordinary_ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "verify_quicknet.mjs" not in ordinary_ci
    assert "--profile FULL" not in ordinary_ci


def test_schedule_enumeration_does_not_retrieve_beacon_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ragwarrant.research.public_beacon as public_beacon

    def forbidden(*_args, **_kwargs):
        raise AssertionError("schedule enumeration attempted beacon verification")

    monkeypatch.setattr(public_beacon, "verified_full_entropy_from_receipt", forbidden)
    manifest = build_seed_schedule_manifest(load_config(CONFIG))
    assert manifest["schedule_enumeration_generated_evidence"] is False
    assert manifest["full_target_round_selected"] is False


def test_full_is_absent_from_ordinary_ci() -> None:
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "run_false_promotion_benchmark.py" not in ci
    assert "research-full" not in ci
    assert "verify_quicknet.mjs" not in ci
    assert "--profile FULL" not in ci


def test_protocol_slice_does_not_modify_historical_evidence() -> None:
    before = _historical_digests()
    assert before
    _verified_entropy()
    build_seed_schedule_manifest(load_config(CONFIG))
    assert _historical_digests() == before


def test_negative_full_results_follow_same_publication_path() -> None:
    seal = _seal()
    common = {
        "schema_version": "1.0",
        "execution_status": "COMPLETED",
        "entropy_protocol": FULL_ENTROPY_PROTOCOL,
        "subject_commit": SUBJECT_COMMIT,
        "benchmark_freeze_digest": FREEZE_DIGEST,
        "seed_schedule_version": 2,
        "seal_sha256": hashlib.sha256(
            (_canonical_json(seal) + "\n").encode("utf-8")
        ).hexdigest(),
        "drand": {"round": HISTORICAL_ROUND},
        "full_master_seed_persisted": False,
        "scientific_results_publication_required": True,
        "output_hashes": {"benchmark_manifest.json": "00" * 32},
    }
    positive = build_execution_closure(
        seal,
        {**common, "scientific_direction": "positive"},
        workflow_conclusion="success",
        workflow_run_url="https://github.com/RAGWarrant/ragwarrant-governance/actions/runs/1",
        output_hashes_verified=True,
    )
    negative = build_execution_closure(
        seal,
        {**common, "scientific_direction": "negative"},
        workflow_conclusion="success",
        workflow_run_url="https://github.com/RAGWarrant/ragwarrant-governance/actions/runs/2",
        output_hashes_verified=True,
    )
    assert positive["closure_status"] == negative["closure_status"] == "COMPLETED"
    assert positive["publication_independent_of_scientific_direction"] is True


def test_official_verifier_is_exact_version_integrity_locked() -> None:
    lock = json.loads(
        Path(".github/drand-verifier/package-lock.json").read_text(encoding="utf-8")
    )
    package = lock["packages"]["node_modules/drand-client"]
    assert package["version"] == DRAND_CLIENT_VERSION
    assert package["integrity"] == DRAND_CLIENT_INTEGRITY
    verifier = Path(".github/drand-verifier/verify_quicknet.mjs").read_text(
        encoding="utf-8"
    )
    assert "disableBeaconVerification: false" in verifier
    assert len(QUICKNET_RELAYS) >= 2


def test_official_client_verifies_recorded_round_and_rejects_tampering() -> None:
    verifier_root = Path(".github/drand-verifier")
    if not (verifier_root / "node_modules/drand-client/package.json").is_file():
        pytest.skip("run npm ci in .github/drand-verifier to exercise the pinned client")
    valid = subprocess.run(
        ["node", "verify_historical_fixture.mjs", "historical_quicknet_round_1.json", "valid"],
        cwd=verifier_root,
        check=True,
        capture_output=True,
        text=True,
    )
    tampered = subprocess.run(
        ["node", "verify_historical_fixture.mjs", "historical_quicknet_round_1.json", "tampered"],
        cwd=verifier_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "signature verified" in valid.stdout
    assert "signature rejected" in tampered.stdout


def test_canonical_runner_invokes_verifier_and_accepts_no_receipt_argument() -> None:
    runner = Path("scripts/run_sealed_full_benchmark.py").read_text(encoding="utf-8")
    assert "_invoke_pinned_verifier" in runner
    assert '"node"' in runner
    assert "--verified-beacon-receipt" not in runner
    assert "--seal-publication" in runner


def test_execution_and_publication_permissions_are_separated() -> None:
    execution = Path(".github/workflows/research-full-execute.yml").read_text(
        encoding="utf-8"
    )
    assert "contents: read" in execution
    assert "publish-write-only" in execution
    assert "contents: write" in execution
    read_job, write_job = execution.split("  publish-write-only:", maxsplit=1)
    assert "contents: write" not in read_job
    assert "actions/checkout" not in write_job
    assert "scripts/" not in write_job
    closure_source = Path("src/ragwarrant/research/public_beacon.py").read_text(
        encoding="utf-8"
    )
    assert "ABORTED_OR_INCOMPLETE" in closure_source
    assert "build_full_publication_closure.py" in read_job


def test_workflows_pin_actions_and_execution_to_frozen_subject() -> None:
    workflows = [
        Path(".github/workflows/research-full-seal.yml"),
        Path(".github/workflows/research-full-closure.yml"),
        Path(".github/workflows/research-full-execute.yml"),
        Path(".github/workflows/research-full-reconciler.yml"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)
    assert "actions/checkout@v" not in text
    assert "actions/setup-python@v" not in text
    assert "actions/setup-node@v" not in text
    assert "actions/upload-artifact@v" not in text
    assert "actions/download-artifact@v" not in text
    execution = workflows[2].read_text(encoding="utf-8")
    assert 'test "$SUBJECT_COMMIT" = "$WORKFLOW_SHA"' in execution
    assert '--ref "$frozen_branch"' in workflows[3].read_text(encoding="utf-8")


def test_hard_cancellation_has_frozen_incomplete_closure_path() -> None:
    closure = Path(".github/workflows/research-full-closure.yml").read_text(
        encoding="utf-8"
    )
    reconciler = Path(".github/workflows/research-full-reconciler.yml").read_text(
        encoding="utf-8"
    )
    assert "ABORTED_OR_INCOMPLETE" in closure
    assert 'test "$WORKFLOW_SHA" = "$SUBJECT_COMMIT"' in closure
    assert "aborted_execution_run_id" in closure
    assert "research-full-closure.yml" in reconciler
    assert "seal_commit_sha=${seal_commit}" in reconciler


def test_completed_closure_requires_verified_output_hashes() -> None:
    seal = _seal()
    manifest = {
        "schema_version": "1.0",
        "execution_status": "COMPLETED",
        "entropy_protocol": FULL_ENTROPY_PROTOCOL,
        "subject_commit": SUBJECT_COMMIT,
        "benchmark_freeze_digest": FREEZE_DIGEST,
        "seed_schedule_version": 2,
        "seal_sha256": hashlib.sha256(
            (_canonical_json(seal) + "\n").encode("utf-8")
        ).hexdigest(),
        "drand": {"round": HISTORICAL_ROUND},
        "full_master_seed_persisted": False,
        "scientific_results_publication_required": True,
        "output_hashes": {"benchmark_manifest.json": "00" * 32},
    }
    closure = build_execution_closure(
        seal,
        manifest,
        workflow_conclusion="success",
        workflow_run_url="https://github.com/RAGWarrant/ragwarrant-governance/actions/runs/3",
        output_hashes_verified=False,
    )
    assert closure["closure_status"] == "ABORTED_OR_INCOMPLETE"
