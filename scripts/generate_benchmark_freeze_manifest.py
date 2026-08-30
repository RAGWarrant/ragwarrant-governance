from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from ragwarrant.research.public_beacon import (
    FULL_CONFIRMATION_STATUS,
    FULL_ENTROPY_PROTOCOL,
    benchmark_freeze_digest,
)
from ragwarrant.research.simulator import load_config


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / ".local_data/research_review/BENCHMARK_FREEZE_MANIFEST.json"
)
FROZEN_PATHS = (
    ".github/drand-verifier/package-lock.json",
    ".github/drand-verifier/package.json",
    ".github/drand-verifier/historical_quicknet_round_1.json",
    ".github/drand-verifier/verify_historical_fixture.mjs",
    ".github/drand-verifier/verify_github_oidc.mjs",
    ".github/drand-verifier/verify_quicknet.mjs",
    ".github/drand-verifier/verify_receipt_signature.mjs",
    ".github/workflows/research-full-closure.yml",
    ".github/workflows/research-full-execute.yml",
    ".github/workflows/research-full-reconciler.yml",
    ".github/workflows/research-full-seal.yml",
    "configs/research/false_promotion_benchmark_v1.yaml",
    "docs/research/false_promotion_benchmark_full_entropy_drand_amendment.md",
    "docs/research/false_promotion_benchmark_protocol.md",
    "docs/research/false_promotion_benchmark_seed_schedule_v2_amendment.md",
    "docs/research/fixed_sample_promotion_warrant_design.md",
    "scripts/build_full_publication_closure.py",
    "scripts/generate_benchmark_freeze_manifest.py",
    "scripts/generate_seed_schedule_v2_manifest.py",
    "scripts/prepare_full_beacon_seal.py",
    "scripts/run_false_promotion_benchmark.py",
    "scripts/run_sealed_full_benchmark.py",
    "src/ragwarrant/research/benchmark.py",
    "src/ragwarrant/research/methods.py",
    "src/ragwarrant/research/public_beacon.py",
    "src/ragwarrant/research/reporting.py",
    "src/ragwarrant/research/seed_schedule.py",
    "src/ragwarrant/research/simulator.py",
    "src/ragwarrant/research/types.py",
    "tests/research/test_benchmark_controls.py",
    "tests/research/test_benchmark_reproducibility.py",
    "tests/research/test_method_contract.py",
    "tests/research/test_output_contract.py",
    "tests/research/test_public_beacon_entropy.py",
    "tests/research/test_seed_schedule_v2.py",
    "tests/research/test_simulator_truth.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hash the frozen Focus 1 benchmark and public-beacon protocol."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    args = parse_args()
    config = load_config(
        REPOSITORY_ROOT / "configs/research/false_promotion_benchmark_v1.yaml"
    )
    input_hashes = {}
    for relative in FROZEN_PATHS:
        path = REPOSITORY_ROOT / relative
        if not path.is_file():
            raise SystemExit(f"frozen input is missing: {relative}")
        input_hashes[relative] = _sha256(path)
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "benchmark_protocol_version": config["protocol_version"],
        "seed_schedule_version": config["seed_schedule_version"],
        "full_entropy_protocol": FULL_ENTROPY_PROTOCOL,
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
        "profile_sizes": {
            profile: int(value["replicate_count"])
            for profile, value in config["profiles"].items()
        },
        "input_hashes": input_hashes,
        "base_commit": _git("rev-parse", "HEAD"),
        "working_tree_dirty": bool(_git("status", "--porcelain")),
        "full_confirmation_status": FULL_CONFIRMATION_STATUS,
        "focus2_implementation_status": "DESIGN_ONLY_NOT_IMPLEMENTED",
        "full_confirmation_ready": False,
        "full_profile_executed": False,
        "full_results_inspected": False,
        "candidate_families_frozen_before_confirmatory_evidence": True,
        "deployable_methods_receive_population_truth": False,
    }
    manifest["benchmark_freeze_digest"] = benchmark_freeze_digest(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "focus1_freeze_manifest_written",
                "benchmark_freeze_digest": manifest["benchmark_freeze_digest"],
                "full_profile_executed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
