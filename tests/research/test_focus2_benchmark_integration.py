from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from ragwarrant.research import focus2_benchmark as focus2_module
from ragwarrant.research.benchmark import EVENT_FIELDS, run_benchmark
from ragwarrant.research.fixed_sample_warrant import FOCUS1_FREEZE_DIGEST
from ragwarrant.research.simulator import load_config


FOCUS1_CONFIG = Path("configs/research/false_promotion_benchmark_v1.yaml")
FOCUS2_CONFIG = Path("configs/research/fixed_sample_multi_risk_warrant_v1.yaml")
FREEZE_MANIFEST = Path(
    ".local_data/research_review/BENCHMARK_FREEZE_MANIFEST.json"
)


def _focus2_config() -> dict:
    loaded = yaml.safe_load(FOCUS2_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _tiny_config(*, replicate_count: int = 2) -> dict:
    config = load_config(FOCUS1_CONFIG)
    config["scenarios"] = [
        scenario
        for scenario in config["scenarios"]
        if scenario["scenario_id"] == "one_clearly_safe"
    ]
    config["scenarios"][0]["sample_sizes"] = [16, 24]
    config["profiles"]["CI"] = {
        "replicate_count": replicate_count,
        "bootstrap_resamples": 8,
    }
    config["trial_sample_limit"] = replicate_count
    return config


def _permit_tiny_config(
    monkeypatch: pytest.MonkeyPatch, config: dict
) -> None:
    monkeypatch.setattr(
        focus2_module,
        "_load_frozen_focus1_config",
        lambda: copy.deepcopy(config),
    )


def _frozen_hashes() -> dict[str, str]:
    manifest = json.loads(FREEZE_MANIFEST.read_text(encoding="utf-8"))
    return {
        relative_path: hashlib.sha256(Path(relative_path).read_bytes()).hexdigest()
        for relative_path in manifest["input_hashes"]
    }


def _without_focus2_trial_fields(row: dict[str, object]) -> dict[str, object]:
    result = dict(row)
    for field in (
        "multiplicity_method",
        "familywise_error_level",
        "family_hash",
        "hypothesis_count",
    ):
        result.pop(field)
    return result


def _without_focus2_aggregate_fields(row: dict[str, object]) -> dict[str, object]:
    result = dict(row)
    for field in (
        "multiplicity_method",
        "familywise_error_level",
        "family_hash",
        "hypothesis_count",
    ):
        result.pop(field)
    for event in EVENT_FIELDS:
        if event != "false_promotion":
            result.pop(f"{event}_rate_confidence_interval")
    return result


def test_focus2_is_deterministic_and_adds_prespecified_method_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _tiny_config()
    _permit_tiny_config(monkeypatch, config)

    first = focus2_module.run_focus2_benchmark(
        copy.deepcopy(config), _focus2_config(), "CI", master_seed=123
    )
    repeat = focus2_module.run_focus2_benchmark(
        copy.deepcopy(config), _focus2_config(), "CI", master_seed=123
    )

    assert first == repeat
    variants = {
        (row["method_id"], row["multiplicity_method"])
        for row in first["method_summary_rows"]
    }
    assert variants == {
        ("always_block", "not_applicable"),
        ("naive_point_estimate", "not_applicable"),
        ("corrected_paired_bootstrap_gate", "not_applicable"),
        ("oracle_safe_objective", "not_applicable"),
        ("fixed_sample_multi_risk_warrant_v1", "holm"),
        ("fixed_sample_multi_risk_warrant_v1", "bonferroni"),
    }
    assert set(first["warrant_artifacts"]) == {"holm", "bonferroni"}
    assert first["manifest"]["warrant_artifact_selection_rule"] == (
        "lexicographically first base scenario_id, smallest sample_size, "
        "trial_index 0; one artifact per prespecified multiplicity method"
    )
    assert first["manifest"]["warrant_artifact_identifiers"] == (
        "opaque method-facing policy IDs"
    )
    assert all(
        identity == "v2|CI|one_clearly_safe|16|0"
        for identity in first["manifest"][
            "warrant_artifact_evidence_trial_identity"
        ].values()
    )
    assert all(
        artifact["population_truth_accessed"] is False
        and artifact["full_profile_used"] is False
        for artifact in first["warrant_artifacts"].values()
    )


def test_existing_baseline_outputs_remain_equivalent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _tiny_config()
    _permit_tiny_config(monkeypatch, config)
    frozen = run_benchmark(copy.deepcopy(config), "CI", master_seed=91)
    focus2 = focus2_module.run_focus2_benchmark(
        copy.deepcopy(config), _focus2_config(), "CI", master_seed=91
    )

    baseline_ids = set(frozen["manifest"]["executed_method_ids"])
    focus2_trials = [
        _without_focus2_trial_fields(row)
        for row in focus2["trial_summary_sample_rows"]
        if row["method_id"] in baseline_ids
    ]
    focus2_aggregates = [
        _without_focus2_aggregate_fields(row)
        for row in focus2["method_summary_rows"]
        if row["method_id"] in baseline_ids
    ]
    assert focus2_trials == frozen["trial_summary_sample_rows"]
    assert focus2_aggregates == frozen["method_summary_rows"]


def test_simulator_called_once_and_family_frozen_before_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _tiny_config(replicate_count=2)
    _permit_tiny_config(monkeypatch, config)
    real_freeze = focus2_module.freeze_candidate_family
    real_simulate = focus2_module.simulate_trial
    events: list[str] = []

    def recording_freeze(**kwargs):
        events.append(f"freeze:{kwargs['multiplicity_method']}")
        return real_freeze(**kwargs)

    def recording_simulate(*args, **kwargs):
        assert events[:2] == ["freeze:holm", "freeze:bonferroni"]
        events.append("simulate")
        return real_simulate(*args, **kwargs)

    monkeypatch.setattr(focus2_module, "freeze_candidate_family", recording_freeze)
    monkeypatch.setattr(focus2_module, "simulate_trial", recording_simulate)

    result = focus2_module.run_focus2_benchmark(
        config, _focus2_config(), "CI", master_seed=41
    )

    assert events == [
        "freeze:holm",
        "freeze:bonferroni",
        "simulate",
        "simulate",
        "freeze:holm",
        "freeze:bonferroni",
        "simulate",
        "simulate",
    ]
    assert result["manifest"]["trial_count_total"] == 4
    assert result["manifest"][
        "candidate_families_frozen_before_confirmatory_evidence"
    ] is True


def test_exact_same_opaque_evidence_object_reaches_all_truth_isolated_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _tiny_config(replicate_count=1)
    _permit_tiny_config(monkeypatch, config)
    registry = focus2_module.method_registry()
    seen: list[tuple[str, int, str, tuple[str, ...], str]] = []

    class BaselineSpy:
        def __init__(self, method_id: str, delegate: object):
            self.method_id = method_id
            self.delegate = delegate

        def evaluate(self, evidence, policy, method_seed=0):
            seen.append(
                (
                    self.method_id,
                    id(evidence),
                    evidence.scenario_id,
                    evidence.policy_ids,
                    evidence.evidence_hash,
                )
            )
            return self.delegate.evaluate(evidence, policy, method_seed)

    for method_id in tuple(registry):
        registry[method_id] = BaselineSpy(method_id, registry[method_id])
    monkeypatch.setattr(focus2_module, "method_registry", lambda: registry)

    real_warrant = focus2_module.FixedSampleMultiRiskWarrant

    class WarrantSpy:
        def __init__(self, family):
            self.family = family
            self.delegate = real_warrant(family)

        def evaluate_warrant(self, evidence, policy):
            seen.append(
                (
                    f"warrant:{self.family.multiplicity_method}",
                    id(evidence),
                    evidence.scenario_id,
                    evidence.policy_ids,
                    evidence.evidence_hash,
                )
            )
            return self.delegate.evaluate_warrant(evidence, policy)

    monkeypatch.setattr(focus2_module, "FixedSampleMultiRiskWarrant", WarrantSpy)
    result = focus2_module.run_focus2_benchmark(
        config, _focus2_config(), "CI", master_seed=7
    )

    assert len(seen) == 10
    by_evidence_hash: dict[str, set[int]] = {}
    for item in seen:
        by_evidence_hash.setdefault(item[4], set()).add(item[1])
    assert len(by_evidence_hash) == 2
    assert all(len(object_ids) == 1 for object_ids in by_evidence_hash.values())
    assert all(item[2] == "scenario_opaque" for item in seen)
    assert all(
        policy_id.startswith("policy_")
        for item in seen
        for policy_id in item[3]
    )
    assert result["manifest"][
        "same_observed_evidence_object_shared_by_truth_isolated_methods"
    ] is True
    assert result["manifest"]["truth_access_method_ids"] == [
        "oracle_safe_objective"
    ]
    assert result["manifest"][
        "truth_isolated_method_accessed_population_truth"
    ] is False


@pytest.mark.parametrize("profile", ["FULL", "full", "UNKNOWN", ""])
def test_full_and_unknown_profiles_fail_before_simulation(
    monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    def forbidden_simulation(*args, **kwargs):
        raise AssertionError("profile rejection occurred after evidence generation")

    monkeypatch.setattr(focus2_module, "simulate_trial", forbidden_simulation)
    match = "FULL is prohibited" if profile == "FULL" else "unknown Focus 2 profile"
    with pytest.raises(ValueError, match=match):
        focus2_module.run_focus2_benchmark({}, {}, profile)


def test_freeze_digest_and_exact_config_guard_run_before_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(FOCUS1_CONFIG)
    config["master_seed"] += 1

    def forbidden_simulation(*args, **kwargs):
        raise AssertionError("freeze guard occurred after evidence generation")

    monkeypatch.setattr(focus2_module, "simulate_trial", forbidden_simulation)
    with pytest.raises(ValueError, match="differs from the frozen on-disk config"):
        focus2_module.run_focus2_benchmark(config, _focus2_config(), "CI")

    focus2_config = _focus2_config()
    focus2_config["focus1_benchmark_freeze_digest"] = "0" * 64
    with pytest.raises(ValueError, match="focus1_benchmark_freeze_digest"):
        focus2_module.run_focus2_benchmark(
            load_config(FOCUS1_CONFIG), focus2_config, "CI"
        )


def test_run_preserves_every_frozen_focus1_input_and_selects_no_drand_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _tiny_config(replicate_count=1)
    _permit_tiny_config(monkeypatch, config)
    before = _frozen_hashes()

    result = focus2_module.run_focus2_benchmark(
        config, _focus2_config(), "CI", master_seed=9
    )

    assert _frozen_hashes() == before
    assert result["manifest"]["focus1_benchmark_freeze_digest"] == FOCUS1_FREEZE_DIGEST
    assert result["manifest"]["full_profile_used"] is False
    assert result["manifest"]["full_evidence_generated"] is False
    assert result["manifest"]["full_results_inspected"] is False
    assert result["manifest"]["target_drand_round_selected"] is False
    assert all(
        row["multiplicity_method"]
        in {"not_applicable", "holm", "bonferroni"}
        for row in result["trial_summary_sample_rows"]
    )
    assert all(
        row["multiplicity_method"]
        in {"not_applicable", "holm", "bonferroni"}
        for row in result["method_summary_rows"]
    )


def test_seed_override_validation_fails_closed_before_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _tiny_config(replicate_count=1)
    _permit_tiny_config(monkeypatch, config)

    def forbidden_simulation(*args, **kwargs):
        raise AssertionError("invalid seed reached evidence generation")

    monkeypatch.setattr(focus2_module, "simulate_trial", forbidden_simulation)
    with pytest.raises(ValueError, match="nonnegative integer"):
        focus2_module.run_focus2_benchmark(
            config, _focus2_config(), "CI", master_seed=True
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("familywise_error_level", 0.5),
        ("quality_delta_bounds", [-0.10, 0.10]),
        ("selection_objective", "minimize_latency"),
        ("incumbent_policy_id", "different_incumbent"),
        ("multiplicity_methods", ["bonferroni", "holm"]),
    ],
)
def test_approved_focus2_config_is_hash_locked_before_sampling(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    config = _focus2_config()
    config[field] = value

    def forbidden_simulation(*args, **kwargs):
        raise AssertionError("modified Focus 2 config reached evidence generation")

    monkeypatch.setattr(focus2_module, "simulate_trial", forbidden_simulation)
    with pytest.raises(ValueError, match="approved v1 contract|prespecified"):
        focus2_module.run_focus2_benchmark(
            load_config(FOCUS1_CONFIG), config, "CI"
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("structural_family_mismatch_behavior", "drop_failed_hypotheses"),
        (
            "insufficient_prespecified_group_count_behavior",
            "omit_hypothesis",
        ),
    ],
)
def test_focus2_family_failure_contract_is_exact(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    config = _tiny_config(replicate_count=1)
    focus2_config = _focus2_config()
    focus2_config[field] = value

    def forbidden_simulation(*args, **kwargs):
        raise AssertionError("invalid family contract reached evidence generation")

    monkeypatch.setattr(focus2_module, "simulate_trial", forbidden_simulation)
    with pytest.raises(ValueError, match=field):
        focus2_module.run_focus2_benchmark(config, focus2_config, "CI")
