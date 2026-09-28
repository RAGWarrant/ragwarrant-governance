from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from scripts.run_stratified_joint_power_study import load_config

from ragwarrant.research import stratified_joint_power as stratified
from ragwarrant.research.fixed_sample_warrant import HOLM, freeze_candidate_family
from ragwarrant.research.fixed_sample_warrant_v2 import (
    PRESPECIFIED_V2_VARIANTS,
    VARIANT_B_ID,
    FixedSampleMultiRiskWarrantV2,
)
from ragwarrant.research.simulator import sha256_json
from ragwarrant.research.stratified_joint_power import (
    BLOCKED_INSUFFICIENT_GROUP_EVIDENCE,
    CandidateSamples,
    SamplingContract,
    StratifiedEvidence,
    deterministic_seed,
    evaluate_stratified_iut_holm,
    minimum_screened_units,
    normalize_group_label,
    recruitment_cost_plan,
    simulate_joint_power,
    stable_hash,
)
from ragwarrant.research.types import EvidenceRow, ObservedEvidence, PolicyConfig


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/research/stratified_joint_warrant_power_v1.yaml"
FOCUS1_DIGEST = "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
PRESERVED_PLANNER_HASHES = {
    "configs/research/evidence_budget_planner_v1.yaml": "04b69b20601d7e1fdc1fbed8dea41384765813ed718b582d953374a1cb11f461",
    "src/ragwarrant/research/evidence_budget_planner.py": "a8d50bef9eda1fb90b40b8a3edc6bc5d2301d213fdbae3df8215c87806c24ab5",
    # Review-only test adapters are excluded from the scientific inventory;
    # the planner configuration and implementation remain byte-bound here.
}


def _policy() -> PolicyConfig:
    return PolicyConfig(
        quality_noninferiority_margin=0.02,
        group_quality_noninferiority_margin=0.03,
        max_safety_violation_probability=0.05,
        max_execution_failure_probability=0.03,
        max_insufficient_evidence_probability=0.10,
        cost_weight=1.0,
        latency_weight=0.0,
        confidence_level=0.95,
        bootstrap_resamples=0,
        enabled_risks=("overall_quality", "group_quality", "safety_violation_probability", "execution_failure_probability", "insufficient_evidence_probability"),
        enabled_group_risks=("safety_violation_probability",),
        group_ids=("majority", "minority"),
    )


def _family(
    core_n: int = 8,
    candidates: tuple[str, ...] = ("a", "b"),
    selection_objective: str = "minimize_cost",
):
    return freeze_candidate_family(
        candidate_policy_ids=candidates,
        incumbent_policy_id="incumbent",
        confirmatory_unit_count=core_n,
        policy=_policy(),
        quality_delta_bounds=(-0.25, 0.25),
        familywise_error_level=0.05,
        multiplicity_method=HOLM,
        selection_objective=selection_objective,
    )


def _candidate(policy_id: str, core_n: int = 8, topup_n: int = 0) -> CandidateSamples:
    labels = tuple("majority" if index % 2 == 0 else "minority" for index in range(core_n))
    zeros = tuple(0 for _ in range(core_n))
    topup_zeros = tuple(0 for _ in range(topup_n))
    return CandidateSamples(
        policy_id=policy_id,
        core_group_ids=labels,
        core_quality_delta=tuple(0.20 for _ in range(core_n)),
        core_binary=(("execution_failure_probability", zeros), ("insufficient_evidence_probability", zeros), ("safety_violation_probability", zeros)),
        topup_quality_delta=(("majority", topup_zeros), ("minority", topup_zeros)),
        topup_binary=(("majority", (("safety_violation_probability", topup_zeros),)), ("minority", (("safety_violation_probability", topup_zeros),))),
        mean_cost=1.0 if policy_id == "a" else 2.0,
        mean_latency=1.0,
    )


def _evidence(core_n: int = 8, topup_n: int = 0) -> StratifiedEvidence:
    return StratifiedEvidence(
        evidence_id="test",
        core_unit_ids=tuple(f"core-{index}" for index in range(core_n)),
        topup_unit_ids=(("majority", tuple(f"m-{index}" for index in range(topup_n))), ("minority", tuple(f"n-{index}" for index in range(topup_n)))),
        candidates=(_candidate("a", core_n, topup_n), _candidate("b", core_n, topup_n)),
    )


def test_focus1_and_prior_planner_files_are_unchanged() -> None:
    loaded = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert loaded["focus1_digest"] == FOCUS1_DIGEST
    for relative, expected in PRESERVED_PLANNER_HASHES.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


def test_group_assignment_is_deterministic_and_fails_closed() -> None:
    groups = ("majority", "minority")
    assert normalize_group_label("minority", groups) == "minority"
    assert normalize_group_label("minority", groups) == "minority"
    for value in (None, "", "unknown", ["majority"], ("majority", "minority")):
        with pytest.raises(ValueError):
            normalize_group_label(value, groups)


def test_sampling_contract_cannot_authorize_collection() -> None:
    fields = dict(
        target_population_id="planning",
        sampling_frame_id="frame",
        unit_definition="independent event",
        group_ids=("majority", "minority"),
        group_prevalence=(("majority", 0.9), ("minority", 0.1)),
        core_mechanism="IID_PROBABILITY_SAMPLE",
        topup_mechanism="OUTCOME_BLIND_RANDOM_WITHIN_GROUP",
        replacement=False,
        max_elapsed_days=14,
        screening_cap=1000,
        recruitment_deadline_days=14,
        candidate_family_hash="hash",
        incumbent_version="inc",
        model_version="model",
        evaluator_version="eval",
    )
    contract = SamplingContract(**fields)
    assert not contract.execution_authorized
    with pytest.raises(ValueError, match="cannot authorize"):
        SamplingContract(**fields, execution_authorized=True)


def test_duplicate_units_and_core_topup_overlap_fail_closed() -> None:
    family = _family()
    duplicate_core = StratifiedEvidence("x", ("same",) * 8, (("majority", ()), ("minority", ())), (_candidate("a"), _candidate("b")))
    with pytest.raises(ValueError, match="duplicate core"):
        duplicate_core.validate(family)
    overlap = StratifiedEvidence("x", tuple(f"core-{i}" for i in range(8)), (("majority", ("core-0",)), ("minority", ())), (_candidate("a", topup_n=0), _candidate("b", topup_n=0)))
    with pytest.raises(ValueError, match="duplicate unit"):
        overlap.validate(family)


def test_core_group_assignment_is_shared_across_every_candidate() -> None:
    first = _candidate("a")
    second = _candidate("b")
    inconsistent = CandidateSamples(
        second.policy_id,
        tuple(reversed(second.core_group_ids)),
        second.core_quality_delta,
        second.core_binary,
        second.topup_quality_delta,
        second.topup_binary,
        second.mean_cost,
        second.mean_latency,
    )
    evidence = StratifiedEvidence(
        "x",
        tuple(f"c-{index}" for index in range(8)),
        (("majority", ()), ("minority", ())),
        (first, inconsistent),
    )
    result = evaluate_stratified_iut_holm(
        evidence, _family(), _policy(), {"majority": 4, "minority": 4}
    )
    assert "immutable and shared" in (result.invalid_reason or "")


def test_core_counts_toward_quota_and_topups_do_not_enter_overall_tests() -> None:
    family = _family(core_n=8)
    result = evaluate_stratified_iut_holm(_evidence(core_n=8, topup_n=4), family, _policy(), {"majority": 8, "minority": 8})
    assert result.invalid_reason is None
    counts = dict(result.evidence_scope_counts)
    assert counts["a::overall_quality::__overall__"] == 8
    assert counts["a::group_quality::majority"] == 8
    assert counts["a::group_quality::minority"] == 8
    assert counts["a::safety_violation_probability::__overall__"] == 8
    assert counts["a::safety_violation_probability::minority"] == 8


def test_quota_shortfall_and_outcome_dependent_recruitment_block() -> None:
    family = _family()
    short = evaluate_stratified_iut_holm(_evidence(), family, _policy(), {"majority": 5, "minority": 5})
    assert short.invalid_reason == BLOCKED_INSUFFICIENT_GROUP_EVIDENCE
    evidence = _evidence()
    bad = StratifiedEvidence(evidence.evidence_id, evidence.core_unit_ids, evidence.topup_unit_ids, evidence.candidates, recruitment_basis="OBSERVED_SAFETY")
    result = evaluate_stratified_iut_holm(bad, family, _policy(), {"majority": 4, "minority": 4})
    assert "outcomes" in (result.invalid_reason or "")


def test_surplus_topups_and_topups_after_core_quota_are_rejected() -> None:
    family = _family()
    surplus = evaluate_stratified_iut_holm(
        _evidence(topup_n=1), family, _policy(), {"majority": 4, "minority": 4}
    )
    assert "quota shortfall exactly" in (surplus.invalid_reason or "")
    exact = evaluate_stratified_iut_holm(
        _evidence(topup_n=0), family, _policy(), {"majority": 4, "minority": 4}
    )
    assert exact.invalid_reason is None


def test_all_candidates_and_mandatory_components_remain_in_holm_family() -> None:
    result = evaluate_stratified_iut_holm(_evidence(), _family(), _policy(), {"majority": 4, "minority": 4})
    assert len(result.candidate_p_values) == 2
    assert len(result.component_p_values) == 16
    assert {item[0] for item in result.candidate_p_values} == {"a", "b"}


def test_core_only_adapter_is_equivalent_to_preserved_v2_iut_holm() -> None:
    core_n = 8
    family = _family(core_n=core_n)
    stratified = _evidence(core_n=core_n)
    scoped = evaluate_stratified_iut_holm(
        stratified, family, _policy(), {"majority": 4, "minority": 4}
    )
    rows = []
    for candidate in stratified.candidates:
        binary = dict(candidate.core_binary)
        for index, group_id in enumerate(candidate.core_group_ids):
            rows.append(
                EvidenceRow(
                    example_id=f"confirmatory-{index:06d}",
                    group_id=group_id,
                    policy_id=candidate.policy_id,
                    incumbent_quality=0.5,
                    candidate_quality=0.5 + candidate.core_quality_delta[index],
                    quality_delta=candidate.core_quality_delta[index],
                    safety_violation=binary["safety_violation_probability"][index],
                    execution_failure=binary["execution_failure_probability"][index],
                    insufficient_evidence=binary["insufficient_evidence_probability"][index],
                    cost=candidate.mean_cost,
                    latency=candidate.mean_latency,
                )
            )
    rows = tuple(sorted(rows, key=lambda item: (item.example_id, item.policy_id)))
    observed = ObservedEvidence(
        scenario_id="core-only-equivalence",
        phase="confirmatory",
        trial_index=0,
        sample_size=core_n,
        rows=rows,
        evidence_hash=sha256_json([row.as_dict() for row in rows]),
    )
    specification = next(
        item for item in PRESPECIFIED_V2_VARIANTS if item.variant_id == VARIANT_B_ID
    )
    preserved = FixedSampleMultiRiskWarrantV2(family, specification).evaluate_warrant(
        observed, _policy()
    )
    assert dict(scoped.candidate_p_values) == pytest.approx(
        {item.policy_id: item.candidate_iut_p_value for item in preserved.candidate_tests}
    )
    assert scoped.certified_policy_ids == preserved.certified_policy_ids


def test_stratified_selection_honors_the_frozen_operational_objective() -> None:
    core_n = 256
    first = _candidate("a", core_n=core_n)
    second_base = _candidate("b", core_n=core_n)
    second = CandidateSamples(
        second_base.policy_id,
        second_base.core_group_ids,
        second_base.core_quality_delta,
        second_base.core_binary,
        second_base.topup_quality_delta,
        second_base.topup_binary,
        2.0,
        0.5,
    )
    evidence = StratifiedEvidence(
        "selection-objective",
        tuple(f"core-{index}" for index in range(core_n)),
        (("majority", ()), ("minority", ())),
        (first, second),
    )
    quotas = {"majority": 128, "minority": 128}
    by_cost = evaluate_stratified_iut_holm(
        evidence,
        _family(core_n=core_n, selection_objective="minimize_cost"),
        _policy(),
        quotas,
    )
    by_latency = evaluate_stratified_iut_holm(
        evidence,
        _family(core_n=core_n, selection_objective="minimize_latency"),
        _policy(),
        quotas,
    )
    assert by_cost.certified_policy_ids == ("a", "b")
    assert by_cost.selected_policy_id == "a"
    assert by_latency.selected_policy_id == "b"


def test_stratified_selection_uses_lexical_policy_id_for_operational_ties() -> None:
    core_n = 256
    evidence = StratifiedEvidence(
        "selection-tie",
        tuple(f"core-{index}" for index in range(core_n)),
        (("majority", ()), ("minority", ())),
        (_candidate("a", core_n=core_n), _candidate("b", core_n=core_n)),
    )
    for objective in ("minimize_cost", "minimize_latency"):
        result = evaluate_stratified_iut_holm(
            evidence,
            _family(core_n=core_n, selection_objective=objective),
            _policy(),
            {"majority": 128, "minority": 128},
        )
        assert result.selected_policy_id == "a"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mean_cost", float("nan")),
        ("mean_cost", float("inf")),
        ("mean_cost", 0.0),
        ("mean_latency", float("nan")),
        ("mean_latency", -1.0),
    ],
)
def test_stratified_evidence_rejects_invalid_operational_metrics(
    field: str, value: float
) -> None:
    candidate = replace(_candidate("a"), **{field: value})
    evidence = StratifiedEvidence(
        "invalid-operational-metric",
        tuple(f"core-{index}" for index in range(8)),
        (("majority", ()), ("minority", ())),
        (candidate, _candidate("b")),
    )
    with pytest.raises(ValueError, match=field):
        evidence.validate(_family())


def test_missing_mandatory_binary_evidence_fails_closed() -> None:
    candidate = _candidate("a")
    bad = CandidateSamples(candidate.policy_id, candidate.core_group_ids, candidate.core_quality_delta, candidate.core_binary[:-1], candidate.topup_quality_delta, candidate.topup_binary, candidate.mean_cost, candidate.mean_latency)
    evidence = StratifiedEvidence("x", tuple(f"c-{i}" for i in range(8)), (("majority", ()), ("minority", ())), (bad, _candidate("b")))
    result = evaluate_stratified_iut_holm(evidence, _family(), _policy(), {"majority": 4, "minority": 4})
    assert "incomplete" in (result.invalid_reason or "")


def test_screening_cost_and_prevalence_sensitivity() -> None:
    args = dict(core_n=1383, group_quotas={"majority": 826, "minority": 826}, eligibility_rate=0.95, usable_rate=0.98, duplicate_rate=0.01, acquisition_probability=0.95, screening_cap=50000, unit_costs={"group_screen": 0.02, "eligibility_screen": 0.02, "full_evaluation": 1.0, "manual_review": 0.05, "data_acquisition": 0.05})
    common = recruitment_cost_plan(prevalence={"majority": 0.9, "minority": 0.1}, **args)
    rare = recruitment_cost_plan(prevalence={"majority": 0.95, "minority": 0.05}, **args)
    assert common["expected_evaluated_units"] == pytest.approx(2070.7)
    assert rare["expected_screened_units"] > common["expected_screened_units"]
    assert common["total_acquisition_cost"] > common["expected_evaluated_units"]
    conservative = common[
        "conservative_high_probability_screened_units_by_group_no_core_credit"
    ]
    assert conservative["minority"] > conservative["majority"]
    assert common["conservative_simultaneous_high_probability_screened_units"] == (
        common["conservative_core_screened_units"]
        + conservative["majority"]
        + conservative["minority"]
    )
    assert common["union_bound_per_requirement_probability"] > 0.95


def test_high_probability_screening_is_exact_and_cap_aware() -> None:
    assert minimum_screened_units(1, 0.5, 0.75, 10) == 2
    assert minimum_screened_units(5, 0.01, 0.95, 5) is None


def test_joint_power_simulation_is_deterministic_and_separates_metrics() -> None:
    family = _family(core_n=32, candidates=("a", "b", "c", "d"))
    kwargs = dict(family=family, policy=_policy(), core_n=32, group_quotas={"majority": 16, "minority": 16}, group_prevalence={"majority": 0.9, "minority": 0.1}, safe_policy_ids=("a",), binary_alternatives={"safety_violation_probability": 0.025, "execution_failure_probability": 0.015, "insufficient_evidence_probability": 0.05}, quality_slack=0.10, dependence_level="medium", replicates=4, master_seed=44)
    first = simulate_joint_power(**kwargs)
    second = simulate_joint_power(**kwargs)
    assert first == second
    assert first["candidate_results"][0]["monte_carlo_joint_power"] <= 1.0
    assert "union_bound_joint_lower_bound" in first["candidate_results"][0]
    assert "independence_approximation" in first["candidate_results"][0]
    assert first["planning_simulator_used_prespecified_truth"]
    assert not first["warrant_method_accessed_population_truth"]
    assert not first["confirmatory_evidence_collected"]


def test_dependence_namespaces_change_seeds_and_unknown_levels_fail() -> None:
    assert deterministic_seed(1, "low") != deterministic_seed(1, "high")
    with pytest.raises(ValueError, match="unknown dependence"):
        simulate_joint_power(family=_family(), policy=_policy(), core_n=8, group_quotas={"majority": 4, "minority": 4}, group_prevalence={"majority": 0.9, "minority": 0.1}, safe_policy_ids=("a",), binary_alternatives={"safety_violation_probability": 0.025, "execution_failure_probability": 0.015, "insufficient_evidence_probability": 0.05}, quality_slack=0.1, dependence_level="favorable", replicates=1, master_seed=1)


def test_joint_power_planning_requires_exactly_two_groups() -> None:
    policy = replace(_policy(), group_ids=("only",))
    family = freeze_candidate_family(
        candidate_policy_ids=("a", "b"),
        incumbent_policy_id="incumbent",
        confirmatory_unit_count=8,
        policy=policy,
        quality_delta_bounds=(-0.25, 0.25),
        familywise_error_level=0.05,
        multiplicity_method=HOLM,
        selection_objective="minimize_cost",
    )
    with pytest.raises(ValueError, match="exactly two"):
        simulate_joint_power(
            family=family,
            policy=policy,
            core_n=8,
            group_quotas={"only": 8},
            group_prevalence={"only": 1.0},
            safe_policy_ids=("a",),
            binary_alternatives={
                "safety_violation_probability": 0.025,
                "execution_failure_probability": 0.015,
                "insufficient_evidence_probability": 0.05,
            },
            quality_slack=0.1,
            dependence_level="low",
            replicates=1,
            master_seed=1,
        )


def test_joint_power_planning_rejects_quality_outside_frozen_support() -> None:
    with pytest.raises(ValueError, match="quality delta exceeds frozen support"):
        simulate_joint_power(
            family=_family(),
            policy=_policy(),
            core_n=8,
            group_quotas={"majority": 4, "minority": 4},
            group_prevalence={"majority": 0.9, "minority": 0.1},
            safe_policy_ids=("a",),
            binary_alternatives={
                "safety_violation_probability": 0.025,
                "execution_failure_probability": 0.015,
                "insufficient_evidence_probability": 0.05,
            },
            quality_slack=0.50,
            dependence_level="low",
            replicates=1,
            master_seed=1,
        )


def test_quality_support_is_validated_before_random_evidence_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_sampling(*args, **kwargs):
        raise AssertionError("quality sampling occurred before support validation")

    monkeypatch.setattr(stratified, "_mixed_signs", unexpected_sampling)
    with pytest.raises(ValueError, match="quality delta exceeds frozen support"):
        simulate_joint_power(
            family=_family(),
            policy=_policy(),
            core_n=8,
            group_quotas={"majority": 4, "minority": 4},
            group_prevalence={"majority": 0.9, "minority": 0.1},
            safe_policy_ids=("a",),
            binary_alternatives={
                "safety_violation_probability": 0.025,
                "execution_failure_probability": 0.015,
                "insufficient_evidence_probability": 0.05,
            },
            # Group mean 0.22 is inside [-0.25, 0.25], but its configured
            # +0.05 support endpoint is not. The plan must fail for every seed.
            quality_slack=0.25,
            dependence_level="low",
            replicates=1,
            master_seed=1,
        )


def test_no_full_or_drand_selection_and_planning_digest_is_stable() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert config["full_executed"] is False
    assert config["drand_round_selected"] is False
    assert config["evidence_collected"] is False
    assert config["execution_authorized"] is False
    assert stable_hash(config) == stable_hash(yaml.safe_load(CONFIG.read_text(encoding="utf-8")))


def test_frozen_scientific_and_dependence_inputs_fail_closed_on_mutation(tmp_path: Path) -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    mutations = [
        ("threshold", lambda value: value["warrant"]["binary_thresholds"].__setitem__("safety_violation_probability", 0.90)),
        ("margin", lambda value: value["warrant"].__setitem__("overall_quality_margin", 0.20)),
        ("support", lambda value: value["warrant"].__setitem__("quality_support", [-1.0, 1.0])),
        ("risk", lambda value: value["warrant"].__setitem__("enabled_risks", value["warrant"]["enabled_risks"][:-1])),
        ("dependence", lambda value: value["dependence"]["levels"].__setitem__("high", 0.1)),
        ("design", lambda value: value["designs"][1].__setitem__("core_n", 999)),
    ]
    for label, mutate in mutations:
        candidate = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        mutate(candidate)
        path = tmp_path / f"{label}.yaml"
        path.write_text(yaml.safe_dump(candidate, sort_keys=False), encoding="utf-8")
        with pytest.raises(ValueError, match="frozen contract"):
            load_config(path)
