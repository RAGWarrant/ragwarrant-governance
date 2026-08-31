"""Portable Focus 1 freeze adapter for clean-checkout research tests.

This narrow adapter reconstructs the accepted Focus 1 freeze manifest from a
checkpoint-derived, immutable 36-path hash inventory. It does not implement the
later packaging-provenance amendment, materialization verification, or path
registry APIs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


FOCUS1_CHECKPOINT_COMMIT = "124836bcc2fba48373d7bd08f0087b23f2e41620"
FOCUS1_DIGEST = "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
FOCUS1_AUTHORITY_VERIFIED = "FOCUS1_AUTHORITY_VERIFIED"
FOCUS1_AUTHORITY_PATH_SET_MISMATCH = "FOCUS1_AUTHORITY_PATH_SET_MISMATCH"
FOCUS1_AUTHORITY_BLOB_MISMATCH = "FOCUS1_AUTHORITY_BLOB_MISMATCH"
FOCUS1_AUTHORITY_DIGEST_MISMATCH = "FOCUS1_AUTHORITY_DIGEST_MISMATCH"

FOCUS1_CHECKPOINT_INPUT_SHA256: Mapping[str, str] = {
    ".github/drand-verifier/package-lock.json": "956b72022cf6f01d30be2c31a077e02200dc741f5730818e8608f31ee86fe80e",
    ".github/drand-verifier/package.json": "f0b0cc73ba14fa249f97c60b83a9fcccb6099c0c69c925c18421cbada942f2d9",
    ".github/drand-verifier/historical_quicknet_round_1.json": "67cd42b915a87e08070004e110985b2b46fc215b85dcc2a4fbeb9d7fe3a5e85c",
    ".github/drand-verifier/verify_historical_fixture.mjs": "850c4091586ed6a2dd2c50caaa653e118b6ef3656a0f2a82f93744beca1bab6d",
    ".github/drand-verifier/verify_github_oidc.mjs": "e836c609f0fe2a114ae8e723301739d7eff645b0a695528bb2ec67e05beecc57",
    ".github/drand-verifier/verify_quicknet.mjs": "230bc859ebf17b80351f4e755153cda22e0c7321ff40c4869d5898e36f567ff3",
    ".github/drand-verifier/verify_receipt_signature.mjs": "13c89b8bd8dd2eb12d5eedb8945aa90db13599dff2b5b90b9c049dbe705e1bf3",
    ".github/workflows/research-full-closure.yml": "a0ffdcec1c5b173469b7c54439330406c8336f618e4420a1a4d1b3d544ea56e6",
    ".github/workflows/research-full-execute.yml": "d3e30030cd910425bb9eee2b0eb90d70442cec7d0897dd36c5ee2a3fb1691a89",
    ".github/workflows/research-full-reconciler.yml": "9ee392238f4ec1a5a8835a08c457d685aeb8f86253d7adb0c1edf21d554bd130",
    ".github/workflows/research-full-seal.yml": "94b4df4a32839318487506f16b0cb2c226261d29844c2a0a8f203907f187206a",
    "configs/research/false_promotion_benchmark_v1.yaml": "4469bb06123796cb71103c2ec0b105e444167fe2b7e538193288ba22d916920a",
    "docs/research/false_promotion_benchmark_full_entropy_drand_amendment.md": "14618686523a420f840b810e3107d177c6299fb1eb9e4a35d01bf4d3b68c577f",
    "docs/research/false_promotion_benchmark_protocol.md": "6d661b06d49f31d40ac21a5cc0516e9f61c6e084514c1ac1838b36f6693686ad",
    "docs/research/false_promotion_benchmark_seed_schedule_v2_amendment.md": "9ffcb40dae4e8740e6f944d817e3f9a384d3ce53c4c2c3fa154bc91895447628",
    "docs/research/fixed_sample_promotion_warrant_design.md": "c11d0c530462d1f86d104c7250d8f1884ff6d8831a2594b6c0173fa950af93c3",
    "scripts/build_full_publication_closure.py": "47c367acb451bdb0b5811be9d170a80f284a1d2b07ae5c8ee2396efef4bcd3e2",
    "scripts/generate_benchmark_freeze_manifest.py": "f6c4d5cc7a886daba43760b97b540f078d5eb113f8ba02c4baa4fe7918bf9105",
    "scripts/generate_seed_schedule_v2_manifest.py": "f0f09638bac4f6d2c04384fae71db0187393234fa554512d25aecd0bb7ec63f4",
    "scripts/prepare_full_beacon_seal.py": "0d0f626dc59033295d2e2c74e212b098be5b28e7bbad27c35c3c560373c97f6d",
    "scripts/run_false_promotion_benchmark.py": "763fa4d52e7019afa323394eeff5e0b6e22b9f480df763aa55a96e8f1f560471",
    "scripts/run_sealed_full_benchmark.py": "bdff85b39009338b4c916afdd2260ecc8549645da5a29be56c8ef598874ffe47",
    "src/ragwarrant/research/benchmark.py": "b5d2f6e293812109da0467415c26c99f68c78e6032e35a17169bd51e369d70b0",
    "src/ragwarrant/research/methods.py": "fa92da3f06e6faefd77f0c84b07c66dbf1a6024edced86735ced8ea1250b77c1",
    "src/ragwarrant/research/public_beacon.py": "ee17e10f8747b931da09c0745b1d2b6eeb547e4ce4622efba6a581e01e41c2a3",
    "src/ragwarrant/research/reporting.py": "56bec0ef53012f6ebd35387f5e2717659153b354b228cf9f034076215be2203f",
    "src/ragwarrant/research/seed_schedule.py": "1083c32e750b87f3b4876b6685d9cf25a97d0b765181af03f3a2ac60c4411aba",
    "src/ragwarrant/research/simulator.py": "39a4e7ffee0670d57dd58f7c49126a3e9834f7672c05adec3a4a5063bc8f852d",
    "src/ragwarrant/research/types.py": "2cd9e4285aa978a029562d2545f49bc48893199c2595a15e8307e59f06443c2e",
    "tests/research/test_benchmark_controls.py": "db9e58304fbfc46541ba0276d25a82f385824aa3a5f2fe6f1adb7e6c08d3c7d4",
    "tests/research/test_benchmark_reproducibility.py": "8b37dd4e9b6b64857f5363e9525239fd1af679ae0972dd0f7920243a78ec54e3",
    "tests/research/test_method_contract.py": "314182deec71c5cd3b0f6d4467720ccf2bae98c0d8745e7741bcc67aecab9a3d",
    "tests/research/test_output_contract.py": "0e331305c7e695e76279dc3757588150f4aff26d9fefc890f19c78e8c404d6ac",
    "tests/research/test_public_beacon_entropy.py": "b12134ca00aed52aaf19e6b0ef0151a8792c02bf18063355ecd0dcd214010e66",
    "tests/research/test_seed_schedule_v2.py": "af5232bae9ab8a81d5b946afe28b3bbce2d497dab5b72ba609b6686f5ff3638e",
    "tests/research/test_simulator_truth.py": "920fcd653e551f3c86be012ce9abf4b11b9160ef1142df133dcee8eaea4f8665",
}


def _manifest(input_hashes: Mapping[str, str]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "benchmark_protocol_version": "false_promotion_benchmark_v1",
        "seed_schedule_version": 2,
        "full_entropy_protocol": "DRAND_QUICKNET_FUTURE_ROUND_V1",
        "protocol_version": "focus1_freeze_review_v1",
        "scenario_version": "false_promotion_benchmark_v1_scenarios",
        "method_interface_version": "promotion_method_evaluate_method_decision_v1",
        "estimands": [
            "P(at least one unsafe candidate is promoted in a trial)",
            "P(at least one unsafe candidate is certified in a trial)",
            "P(false block in a trial)",
            "P(correct promotion in a trial)",
            "P(correct no-safe-candidate block in a trial)",
            "operational regret conditional on safe selection",
        ],
        "candidate_truth_definition": (
            "Every enabled overall-quality, protected-group-quality, safety-violation, "
            "execution-failure, and insufficient-evidence threshold passes under exact "
            "configured population parameters. Cost and latency are operational objectives."
        ),
        "event_definitions": {
            "false_promotion": "A deployable method selects a candidate that is not truly promotion-safe.",
            "false_certification": "A certified set contains at least one candidate that is not truly promotion-safe.",
            "false_block": "At least one truly safe candidate exists and the method promotes none.",
            "operational_regret": "Selected safe candidate objective minus the optimal truly safe candidate objective.",
        },
        "estimator_definitions": {
            "event_rate": "event count divided by fixed Monte Carlo trial count within each scenario/sample-size/method cell",
            "monte_carlo_interval": "two-sided 95% Wilson binomial interval for Monte Carlo event-rate uncertainty",
            "mean_certified_set_size": "arithmetic mean over method-trials in one cell",
            "mean_operational_regret": "arithmetic mean conditional on safe selections with defined regret",
        },
        "enabled_risk_definitions": [
            "overall_quality_delta_vs_incumbent",
            "quality_delta_by_group",
            "safety_violation_probability",
            "execution_failure_probability",
            "insufficient_evidence_probability",
        ],
        "input_hashes": dict(input_hashes),
    }


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_focus1_portable_authority(repository_root: Path) -> dict[str, Any]:
    """Verify candidate bytes against the accepted checkpoint-derived inventory."""

    root = Path(repository_root).resolve(strict=True)
    expected_manifest = _manifest(FOCUS1_CHECKPOINT_INPUT_SHA256)
    expected_digest = _digest(expected_manifest)
    if expected_digest != FOCUS1_DIGEST:
        raise ValueError(FOCUS1_AUTHORITY_DIGEST_MISMATCH)

    observed: dict[str, str] = {}
    for relative_path, expected_hash in FOCUS1_CHECKPOINT_INPUT_SHA256.items():
        path = root / relative_path
        if not path.is_file():
            raise ValueError(f"{FOCUS1_AUTHORITY_PATH_SET_MISMATCH}: {relative_path}")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"{FOCUS1_AUTHORITY_BLOB_MISMATCH}: {relative_path}")
        observed[relative_path] = actual_hash

    observed_digest = _digest(_manifest(observed))
    if observed_digest != FOCUS1_DIGEST:
        raise ValueError(FOCUS1_AUTHORITY_DIGEST_MISMATCH)
    authoritative_manifest = dict(expected_manifest)
    authoritative_manifest["benchmark_freeze_digest"] = expected_digest
    return {
        "status": FOCUS1_AUTHORITY_VERIFIED,
        "authority_source": "CHECKPOINT_DERIVED_ACCEPTED_INVENTORY",
        "checkpoint_commit": FOCUS1_CHECKPOINT_COMMIT,
        "frozen_path_count": len(FOCUS1_CHECKPOINT_INPUT_SHA256),
        "expected_digest": expected_digest,
        "observed_digest": observed_digest,
        "manifest": authoritative_manifest,
    }
