from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path

import pytest

from scripts import run_evidence_budget_study as study_cli
from ragwarrant.research.evidence_budget_planner import (
    CERTIFICATION_BUDGET_FEASIBLE,
    CERTIFICATION_BUDGET_MARGINAL,
    CERTIFICATION_BUDGET_UNDERPOWERED,
    CERTIFICATION_STRUCTURALLY_INFEASIBLE,
    FOCUS1_FREEZE_DIGEST,
    binomial_cdf,
    binary_planning_power,
    effective_planning_alpha,
    empirical_bernstein_radius,
    empirical_bernstein_test,
    expected_group_topup_count,
    exact_binary_rejection_region,
    expected_total_for_group_count,
    group_count_sufficiency_probability,
    high_probability_total_for_group_count,
    hoeffding_minimum_certifying_mean,
    hoeffding_planning_power_lower_bound,
    load_planner_config,
    minimum_binary_sample_count,
    minimum_binary_structural_count,
    minimum_empirical_bernstein_crossing_count,
    minimum_hoeffding_sample_count_for_power,
    plan_evidence_budget,
    planning_family_size,
    stable_config_hash,
    study_rows,
    validate_planner_config,
    validate_stratified_quotas,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs/research/evidence_budget_planner_v1.yaml"
PRESERVED_SHA256 = {
    "configs/research/fixed_sample_multi_risk_warrant_v2.yaml": "9ea78712a5ab0cee58982cec0cd2d69bc363d2c3c084d9507e54416dc18d1238",
    "configs/research/fixed_sample_multi_risk_warrant_v2_iut_holm.yaml": "b396bff282fb80ee2c9258caec1342862417b3dc92d3c30f208d9009267a1566",
    "docs/research/fixed_sample_multi_risk_warrant_v2.md": "d170214f03ef8da86c1a7a1354ef645b8ef28538ba0b9cd747dec5a3a37b931f",
    "docs/research/fixed_sample_multi_risk_warrant_v2_iut_holm.md": "a3e9fc385836c4d273f66129dc9dd0c09c3ecf246e05e33122b91faa1d0697ca",
    "scripts/run_fixed_sample_warrant_v2_benchmark.py": "4581c2ac43bb7704e8f521bca1fa34a1a75b7a16bbdb24fb9d79a35f7e0e1d80",
    "scripts/run_focus2_power_feasibility_audit.py": "c43ae625e65bdf6c93417c5e9409554cd2a601257ce324d6ba206d1fd5387635",
    "src/ragwarrant/research/fixed_sample_warrant_v2.py": "9c3cbea2f0645cae46d7b3ad434b3953371a72bc9d7498bbaf1473dec40d842b",
    "src/ragwarrant/research/focus2_power_diagnostics.py": "7c702c249b7bf646da6230970462b25e3b6abdce78c380536ba0fc5c68edd4b8",
    "src/ragwarrant/research/focus2_v2_benchmark.py": "339b9df2276945547ddd3533818d366757d665a970ca8aa5904c2e1abfacc2dd",
    "src/ragwarrant/research/focus2_v2_reporting.py": "87c34660ce9ba0dfc37b008d44c5aecc3f846bd6219cb209cf56d02ec1e5e2ce",
    "tests/research/test_fixed_sample_warrant_v2.py": "54d8d4ab3f7e0a82af5f07edfa6da040541519cdb57a410e6e09f84f743f5210",
    "tests/research/test_focus2_power_feasibility.py": "bc696685c3f1b960d1b586056a8526126eea500056958da791c62fb07d6ca446",
    "tests/research/test_focus2_v2_benchmark_integration.py": "66af1fb74c36acdc35468a8de6dcae0da6959dcfc628ac08d76d1c03a07829ba",
    "configs/research/false_promotion_benchmark_v1.yaml": "4469bb06123796cb71103c2ec0b105e444167fe2b7e538193288ba22d916920a",
    "docs/research/false_promotion_benchmark_protocol.md": "6d661b06d49f31d40ac21a5cc0516e9f61c6e084514c1ac1838b36f6693686ad",
    "docs/research/false_promotion_benchmark_seed_schedule_v2_amendment.md": "9ffcb40dae4e8740e6f944d817e3f9a384d3ce53c4c2c3fa154bc91895447628",
    "docs/research/false_promotion_benchmark_full_entropy_drand_amendment.md": "14618686523a420f840b810e3107d177c6299fb1eb9e4a35d01bf4d3b68c577f",
    "src/ragwarrant/research/seed_schedule.py": "1083c32e750b87f3b4876b6685d9cf25a97d0b765181af03f3a2ac60c4411aba",
    "src/ragwarrant/research/public_beacon.py": "ee17e10f8747b931da09c0745b1d2b6eeb547e4ce4622efba6a581e01e41c2a3",
}


@pytest.fixture(scope="module")
def config() -> dict[str, object]:
    return load_planner_config(CONFIG_PATH)


@pytest.fixture(scope="module")
def result(config: dict[str, object]) -> dict[str, object]:
    return plan_evidence_budget(config)


def test_exact_binomial_rejection_region_matches_hand_case() -> None:
    # X~Binomial(2, 0.5): P(X<=0)=0.25 and P(X<=1)=0.75.
    plan = exact_binary_rejection_region(2, 0.5, 0.30)
    assert plan.rejection_max_events == 0
    assert plan.zero_event_p_value == pytest.approx(0.25)
    assert binary_planning_power(plan, 0.25) == pytest.approx(0.75**2)
    assert exact_binary_rejection_region(1, 0.5, 0.30).rejection_max_events is None


def test_zero_event_structural_threshold_and_monotonicity() -> None:
    minimum = minimum_binary_structural_count(0.03, 0.05, 1000)
    assert minimum == 99
    assert exact_binary_rejection_region(98, 0.03, 0.05).rejection_max_events is None
    assert exact_binary_rejection_region(99, 0.03, 0.05).rejection_max_events == 0
    assert all(
        exact_binary_rejection_region(n, 0.03, 0.05).structurally_certifiable
        for n in range(99, 120)
    )


def test_binary_target_ordering_without_false_adjacent_monotonicity_claim() -> None:
    required = [
        minimum_binary_sample_count(0.05, 0.01, 0.025, target, 5000)
        for target in (0.5, 0.8, 0.9)
    ]
    assert all(value is not None for value in required)
    assert required == sorted(required)
    plan = exact_binary_rejection_region(250, 0.05, 0.01)
    assert binary_planning_power(plan, 0.01) >= binary_planning_power(plan, 0.025)


def test_invalid_binary_planning_alternative_fails_closed() -> None:
    plan = exact_binary_rejection_region(256, 0.05, 0.01)
    with pytest.raises(ValueError, match="p_alt < threshold"):
        binary_planning_power(plan, 0.05)
    with pytest.raises(ValueError, match="p_alt < threshold"):
        minimum_binary_sample_count(0.05, 0.01, 0.06, 0.8, 1000)


def test_quality_crossing_and_power_lower_bound_are_distinct() -> None:
    expected_mean = -0.02 + 0.5 * math.sqrt(math.log(1 / 0.05) / (2 * 64))
    assert hoeffding_minimum_certifying_mean(
        64, 0.02, -0.25, 0.25, 0.05
    ) == pytest.approx(expected_mean)
    power = hoeffding_planning_power_lower_bound(256, 0.5, 0.05, 0.10)
    assert 0.0 < power < 1.0
    minimum = minimum_hoeffding_sample_count_for_power(0.5, 0.05, 0.10, 0.8)
    assert hoeffding_planning_power_lower_bound(minimum, 0.5, 0.05, 0.10) >= 0.8
    if minimum > 1:
        assert hoeffding_planning_power_lower_bound(minimum - 1, 0.5, 0.05, 0.10) < 0.8


def test_empirical_bernstein_exact_constants_zero_variance_and_strict_boundary() -> None:
    expected = 7.0 * math.log(40.0) / (3.0 * 63.0)
    assert empirical_bernstein_radius(64, 0.0, 0.05) == pytest.approx(expected)
    values = [0.1] * 64
    passing_threshold = 0.1 + expected + 1e-12
    assert empirical_bernstein_test(values, passing_threshold, 0.05).certifies
    assert not empirical_bernstein_test(values, 0.1 + expected, 0.05).certifies
    with pytest.raises(ValueError, match="n >= 2"):
        empirical_bernstein_radius(1, 0.0, 0.05)


def test_empirical_bernstein_crossing_is_sensitivity_not_power() -> None:
    zero_variance = minimum_empirical_bernstein_crossing_count(
        0.5, 0.10, 0.0, 0.01, 5000
    )
    high_variance = minimum_empirical_bernstein_crossing_count(
        0.5, 0.10, 0.25, 0.01, 5000
    )
    assert zero_variance is not None and high_variance is not None
    assert zero_variance < high_variance


def test_subgroup_expected_and_exact_high_probability_counts() -> None:
    assert expected_total_for_group_count(24, 0.10) == 240
    assert group_count_sufficiency_probability(24, 24, 1.0) == 1.0
    minimum = high_probability_total_for_group_count(24, 0.10, 0.95, 5000)
    assert minimum is not None
    assert group_count_sufficiency_probability(minimum, 24, 0.10) >= 0.95
    assert group_count_sufficiency_probability(minimum - 1, 24, 0.10) < 0.95


def test_zero_tiny_prevalence_and_impossible_subgroup_requirements() -> None:
    assert expected_total_for_group_count(1, 0.0) is None
    assert high_probability_total_for_group_count(1, 0.0, 0.95, 1000) is None
    assert high_probability_total_for_group_count(10, 1e-9, 0.95, 1000) is None
    assert group_count_sufficiency_probability(9, 10, 0.5) == 0.0
    assert expected_total_for_group_count(0, 0.0) == 0
    assert expected_group_topup_count(2, 1, 0.5) == pytest.approx(0.25)
    assert expected_group_topup_count(2, 2, 0.5) == pytest.approx(1.0)


def test_group_contract_and_guaranteed_minimum_bind_the_quota(
    config: dict[str, object],
) -> None:
    changed = copy.deepcopy(config)
    changed["protected_groups"][1]["guaranteed_minimum_count"] = 500
    planned = plan_evidence_budget(changed)
    for target in changed["planning_power_targets"]:
        assert planned["target_designs"][str(float(target))]["required_n_by_group"]["minority"] >= 500
    invalid = copy.deepcopy(config)
    invalid["group_structure"] = "OVERLAPPING_GROUPS"
    with pytest.raises(ValueError, match="CATEGORICAL_PARTITION"):
        validate_planner_config(invalid)


def test_natural_sampling_design_meets_simultaneous_group_acquisition_target(
    config: dict[str, object], result: dict[str, object]
) -> None:
    required_groups = {item["group_id"] for item in config["protected_groups"]}
    for design in result["target_designs"].values():
        assert set(design["acquisition"]) == required_groups
        total_n = design["natural_sampling_required_total_n"]
        total_failure_bound = math.fsum(
            1.0
            - group_count_sufficiency_probability(
                total_n,
                item["required_group_n"],
                item["target_population_prevalence"],
            )
            for item in design["acquisition"].values()
        )
        assert total_failure_bound <= 1.0 - config["target_acquisition_probability"] + 1e-12


def test_stratified_quota_validation_preserves_all_groups() -> None:
    validate_stratified_quotas(500, {"majority": 100, "minority": 100}, ("majority", "minority"))
    with pytest.raises(ValueError, match="every required group"):
        validate_stratified_quotas(500, {"majority": 100}, ("majority", "minority"))
    with pytest.raises(ValueError, match="positive integer"):
        validate_stratified_quotas(500, {"majority": 100, "minority": 0}, ("majority", "minority"))


def test_family_size_contains_all_candidates_risks_and_groups(config: dict[str, object]) -> None:
    assert planning_family_size(config) == 24
    assert effective_planning_alpha(config) == pytest.approx(0.05 / 24)
    flat = copy.deepcopy(config)
    flat["hypothesis_organization"] = "FLAT_FAMILY"
    # 4 overall components + 2 group-quality + 2 group-safety per candidate.
    assert planning_family_size(flat) == 24 * 8


def test_planner_is_deterministic_and_does_not_report_joint_power(
    config: dict[str, object], result: dict[str, object]
) -> None:
    repeated = plan_evidence_budget(copy.deepcopy(config))
    assert stable_config_hash(config) == stable_config_hash(copy.deepcopy(config))
    assert result == repeated
    assert result["population_truth_accessed"] is False
    assert result["confirmatory_outcomes_accessed"] is False
    assert result["joint_candidate_power_calculated"] is False
    assert result["empirical_bernstein_planning_power_calculated"] is False
    assert result["full_evidence_generated"] is False
    assert result["drand_round_selected"] is False


def test_budget_statuses_are_closed_and_no_budget_is_required_to_win(
    result: dict[str, object],
) -> None:
    allowed = {
        CERTIFICATION_BUDGET_FEASIBLE,
        CERTIFICATION_BUDGET_MARGINAL,
        CERTIFICATION_BUDGET_UNDERPOWERED,
        CERTIFICATION_STRUCTURALLY_INFEASIBLE,
    }
    rows = result["budget_matrix"]
    assert rows
    assert {row["status"] for row in rows} <= allowed


def test_invalid_config_truth_fields_and_frozen_contract_changes_fail(
    config: dict[str, object],
) -> None:
    truth = copy.deepcopy(config)
    truth["population_truth"] = {"candidate": "safe"}
    with pytest.raises(ValueError, match="truth/outcome"):
        validate_planner_config(truth)
    changed = copy.deepcopy(config)
    changed["binary_risks"]["safety_violation_probability"]["threshold"] = 0.06
    with pytest.raises(ValueError, match="frozen contract"):
        validate_planner_config(changed)

    missing_risk = copy.deepcopy(config)
    missing_risk["enabled_risks"].remove("group_quality")
    with pytest.raises(ValueError, match="every mandatory frozen risk"):
        validate_planner_config(missing_risk)
    missing_group = copy.deepcopy(config)
    missing_group["protected_groups"] = [
        {
            "group_id": "majority",
            "target_population_prevalence": 1.0,
            "guaranteed_minimum_count": 0,
        }
    ]
    with pytest.raises(ValueError, match="mandatory frozen group plan"):
        validate_planner_config(missing_group)


def test_frozen_focus1_and_prior_v2_hashes_are_unchanged() -> None:
    assert FOCUS1_FREEZE_DIGEST == "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
    for relative, expected in PRESERVED_SHA256.items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert actual == expected


def test_module_has_no_simulator_beacon_or_evidence_generation_imports() -> None:
    source = (ROOT / "src/ragwarrant/research/evidence_budget_planner.py").read_text(
        encoding="utf-8"
    )
    assert "simulate_trial" not in source
    assert "public_beacon" not in source
    assert "requests" not in source
    assert "urllib" not in source
    assert "import drand" not in source.lower()
    assert "drand_round_selected" in source


def test_runner_writes_only_planning_outputs_and_refuses_full(
    tmp_path: Path,
    config: dict[str, object],
) -> None:
    assert study_cli.main(["--config", str(CONFIG_PATH), "--output-dir", str(tmp_path)]) == 0
    assert {path.name for path in tmp_path.iterdir()} == {
        "EVIDENCE_BUDGET_STUDY.csv",
        "EVIDENCE_BUDGET_STUDY.md",
        "SUBGROUP_EVIDENCE_PLAN.md",
    }
    rows = study_rows(config, plan_evidence_budget(config))
    assert rows and all("budget_status" in row for row in rows)
    with pytest.raises(SystemExit, match="FULL evidence generation is prohibited"):
        study_cli.main(["--execute-full"])
