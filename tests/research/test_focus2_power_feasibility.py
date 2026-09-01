from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pytest

from scripts import run_focus2_power_feasibility_audit as audit_cli
import ragwarrant.research.fixed_sample_warrant as v1
import ragwarrant.research.fixed_sample_warrant_v2 as prior_v2
from ragwarrant.research.fixed_sample_warrant import HOLM, freeze_candidate_family
from ragwarrant.research.focus2_power_diagnostics import (
    COMPARISON_SPECIFICATION,
    FOCUS1_CONFIG_PATH,
    METHOD_ID,
    FixedSampleMultiRiskWarrantV2IUTHolm,
    binary_best_case_feasibility,
    build_power_feasibility_rows,
    hoeffding_required_gap,
    load_overlay_config,
    maurer_pontil_theorem4_radius,
    summarize_feasibility_cells,
)
from ragwarrant.research.simulator import load_config, sha256_json
from ragwarrant.research.types import EvidenceRow, ObservedEvidence, PolicyConfig


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FROZEN_FOCUS1_DIGEST = (
    "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
)
FROZEN_V1_SOURCE_SHA256 = (
    "87e88342354346d0dceb29f45946e846b68f6b1fbaa42a946d5a53822ef4e8ad"
)


def _policy(
    enabled_risks: tuple[str, ...],
    *,
    group_ids: tuple[str, ...] = ("g1",),
) -> PolicyConfig:
    return PolicyConfig(
        quality_noninferiority_margin=0.02,
        group_quality_noninferiority_margin=0.03,
        max_safety_violation_probability=0.05,
        max_execution_failure_probability=0.03,
        max_insufficient_evidence_probability=0.10,
        cost_weight=1.0,
        latency_weight=0.1,
        confidence_level=0.95,
        bootstrap_resamples=64,
        enabled_risks=enabled_risks,
        enabled_group_risks=(),
        group_ids=group_ids,
    )


def _evidence(
    deltas: dict[str, float],
    *,
    sample_size: int = 256,
    observed_groups: tuple[str, ...] = ("g1",),
) -> ObservedEvidence:
    rows = tuple(
        EvidenceRow(
            example_id=f"confirmatory-{index:06d}",
            group_id=observed_groups[index % len(observed_groups)],
            policy_id=policy_id,
            incumbent_quality=0.7,
            candidate_quality=0.7 + delta,
            quality_delta=delta,
            safety_violation=0,
            execution_failure=0,
            insufficient_evidence=0,
            cost=1.0,
            latency=1.0,
        )
        for policy_id, delta in sorted(deltas.items())
        for index in range(sample_size)
    )
    ordered = tuple(sorted(rows, key=lambda row: (row.example_id, row.policy_id)))
    return ObservedEvidence(
        scenario_id=f"constructed__n{sample_size}",
        phase="confirmatory",
        trial_index=0,
        sample_size=sample_size,
        rows=ordered,
        evidence_hash=sha256_json([row.as_dict() for row in ordered]),
    )


def _family(evidence: ObservedEvidence, policy: PolicyConfig) -> v1.FrozenCandidateFamily:
    return freeze_candidate_family(
        candidate_policy_ids=evidence.policy_ids,
        incumbent_policy_id="incumbent",
        confirmatory_unit_count=evidence.sample_size,
        policy=policy,
        quality_delta_bounds=(-0.25, 0.25),
        familywise_error_level=0.05,
        multiplicity_method=HOLM,
        selection_objective="minimize_cost",
    )


def test_named_comparison_is_exact_candidate_max_p_iut_holm() -> None:
    assert METHOD_ID == "FIXED_SAMPLE_MULTI_RISK_WARRANT_V2_IUT_HOLM"
    assert COMPARISON_SPECIFICATION.multiplicity_scope == prior_v2.CANDIDATE_IUT
    assert COMPARISON_SPECIFICATION.multiplicity_method == HOLM
    assert COMPARISON_SPECIFICATION.quality_test == prior_v2.PAIRED_HOEFFDING
    assert prior_v2.candidate_iut_p_value((0.001, 0.2, 0.04)) == 0.2


def test_named_adapter_matches_existing_iut_hoeffding_ablation() -> None:
    policy = _policy(("overall_quality", "execution_failure_probability"))
    evidence = _evidence({"a": 0.20, "b": 0.01})
    family = _family(evidence, policy)
    existing_spec = next(
        item
        for item in prior_v2.PRESPECIFIED_V2_VARIANTS
        if item.variant_id == prior_v2.VARIANT_B_ID
    )
    existing = prior_v2.FixedSampleMultiRiskWarrantV2(
        family, existing_spec
    ).evaluate_warrant(evidence, policy)
    named = FixedSampleMultiRiskWarrantV2IUTHolm(family).evaluate_warrant(
        evidence, policy
    )
    assert named.component_tests == existing.component_tests
    assert named.candidate_tests == existing.candidate_tests
    assert named.certified_policy_ids == existing.certified_policy_ids
    assert named.selected_policy_id == existing.selected_policy_id
    assert named.decision == existing.decision


def test_one_nonsignificant_component_prevents_joint_certification() -> None:
    policy = _policy(("overall_quality", "execution_failure_probability"))
    evidence = _evidence({"candidate": 0.20}, sample_size=64)
    warrant = FixedSampleMultiRiskWarrantV2IUTHolm(
        _family(evidence, policy)
    ).evaluate_warrant(evidence, policy)
    candidate = warrant.candidate_tests[0]
    assert candidate.candidate_iut_p_value == max(
        item.raw_p_value for item in warrant.component_tests
    )
    assert candidate.candidate_iut_p_value == pytest.approx(0.97**64)
    assert not candidate.rejected
    assert warrant.certified_policy_ids == ()


def test_binary_best_case_feasibility_and_boundaries_are_exact() -> None:
    n64 = binary_best_case_feasibility(0.03, 64, 0.05)
    assert n64.minimum_attainable_p_value == pytest.approx(0.97**64)
    assert n64.minimum_attainable_p_value == pytest.approx(
        v1.exact_binomial_lower_tail(0, 64, 0.03)
    )
    assert n64.minimum_sample_count == 99
    assert not n64.attainable
    assert binary_best_case_feasibility(0.03, 99, 0.05).attainable
    zero = binary_best_case_feasibility(0.0, 1000, 0.05)
    assert zero.minimum_attainable_p_value == 1.0
    assert zero.minimum_sample_count is None
    one = binary_best_case_feasibility(1.0, 1, 0.05)
    assert one.minimum_attainable_p_value == 0.0
    assert one.minimum_sample_count == 1


def test_hoeffding_crossing_is_algebraic_not_a_power_claim() -> None:
    expected = 0.5 * math.sqrt(math.log(20.0) / (2.0 * 64))
    assert hoeffding_required_gap(64, 0.5, 0.05) == pytest.approx(expected)
    assert math.isinf(hoeffding_required_gap(0, 0.5, 0.05))


def test_holm_uses_complete_candidate_family_and_deterministic_ties() -> None:
    result = v1.holm_step_down_adjust(
        {"candidate_b": 0.01, "candidate_a": 0.01, "candidate_c": 0.9}, 0.05
    )
    assert result.family_size == 3
    assert result.ordered_hypothesis_ids == (
        "candidate_a",
        "candidate_b",
        "candidate_c",
    )
    assert result.rejected_hypothesis_ids == ("candidate_a", "candidate_b")


def test_missing_group_evidence_is_retained_and_blocks_certification() -> None:
    policy = _policy(("group_quality",), group_ids=("g1", "g2"))
    evidence = _evidence(
        {"candidate": 0.20}, sample_size=256, observed_groups=("g1",)
    )
    warrant = FixedSampleMultiRiskWarrantV2IUTHolm(
        _family(evidence, policy)
    ).evaluate_warrant(evidence, policy)
    missing = next(item for item in warrant.component_tests if item.group_id == "g2")
    assert missing.sample_count == 0
    assert missing.raw_p_value == 1.0
    assert missing.failure_reason == "missing_group_evidence"
    assert not warrant.candidate_tests[0].rejected


def test_maurer_pontil_radius_is_diagnostic_only_and_handles_small_n() -> None:
    expected = math.sqrt(2.0 * 0.01 * math.log(40.0) / 64.0) + (
        7.0 * math.log(40.0) / (3.0 * 63.0)
    )
    assert maurer_pontil_theorem4_radius(64, 0.01, 0.05) == pytest.approx(expected)
    assert math.isinf(maurer_pontil_theorem4_radius(1, 0.01, 0.05))


@pytest.fixture(scope="module")
def audit_rows() -> list[dict[str, object]]:
    return build_power_feasibility_rows(
        load_config(FOCUS1_CONFIG_PATH),
        load_overlay_config(),
        verify_retained_outputs=False,
    )


def test_bounded_audit_uses_only_matched_ci_local_evidence(
    audit_rows: list[dict[str, object]],
) -> None:
    assert audit_rows
    assert {row["profile"] for row in audit_rows} == {"CI", "LOCAL"}
    assert {row["trial_index"] for row in audit_rows} == {0, 1}
    assert all(
        str(row["evidence_trial_identity"]).startswith(
            f"v2|{row['profile']}|"
        )
        for row in audit_rows
    )
    hashes: dict[str, set[str]] = {}
    for row in audit_rows:
        hashes.setdefault(str(row["evidence_trial_identity"]), set()).add(
            str(row["evidence_hash"])
        )
    assert all(len(values) == 1 for values in hashes.values())
    assert all(row["method_received_population_truth"] is False for row in audit_rows)
    assert all(
        row["existing_complete_developmental_profile_v1_holm_any_certification"]
        is False
        and row[
            "existing_complete_developmental_profile_v2_iut_holm_any_certification"
        ]
        is False
        for row in audit_rows
    )


def test_n64_cells_are_budget_impossible_without_multiplicity(
    audit_rows: list[dict[str, object]],
) -> None:
    summaries = summarize_feasibility_cells(audit_rows)
    n64 = [row for row in summaries if int(row["sample_size"]) == 64]
    assert n64
    assert all(
        row["structural_feasibility"]
        == "B_IMPOSSIBLE_UNADJUSTED_AT_RETAINED_ACTUAL_COUNTS"
        for row in n64
        if row["safe_candidate_exists"]
    )


def test_mixed_candidate_feasibility_is_not_mislabeled_all_possible() -> None:
    base = {
        "profile": "CI",
        "scenario_id": "mixed__n10",
        "scenario_family": "CONSTRUCTED",
        "sample_size": 10,
        "candidate_count": 2,
        "trial_index": 0,
        "group_id": None,
        "risk_id": "execution_failure_probability",
        "actual_observation_count": 10,
        "candidate_truly_safe": True,
        "dominant_gate": True,
        "v2_candidate_certified": False,
        "existing_complete_developmental_profile_v1_holm_any_certification": False,
        "existing_complete_developmental_profile_v2_iut_holm_any_certification": False,
    }
    rows = [
        {**base, "policy_id": "impossible", "algebraically_possible_unadjusted": False},
        {**base, "policy_id": "possible", "algebraically_possible_unadjusted": True},
    ]
    summary = summarize_feasibility_cells(rows)[0]
    assert summary["empirical_result"] == "A_NO_CERTIFICATIONS_OBSERVED"
    assert (
        summary["structural_feasibility"]
        == "MIXED_B_C_FEASIBILITY_ACROSS_CANDIDATE_TRIALS"
    )
    assert summary["classification"] == "MIXED_STRUCTURAL_FEASIBILITY_OBSERVED_POWER_LOW"


def test_no_safe_candidate_cell_does_not_claim_power() -> None:
    base = {
        "profile": "CI",
        "scenario_id": "all_unsafe__n10",
        "scenario_family": "ALL_UNSAFE_BOUNDARY",
        "sample_size": 10,
        "candidate_count": 1,
        "trial_index": 0,
        "policy_id": "unsafe",
        "candidate_truly_safe": False,
        "group_id": None,
        "risk_id": "execution_failure_probability",
        "actual_observation_count": 10,
        "dominant_gate": True,
        "v2_candidate_certified": False,
        "algebraically_possible_unadjusted": True,
        "existing_complete_developmental_profile_v1_holm_any_certification": False,
        "existing_complete_developmental_profile_v2_iut_holm_any_certification": False,
    }
    summary = summarize_feasibility_cells([base])[0]
    assert summary["classification"] == (
        "POWER_NOT_APPLICABLE_NO_SAFE_CANDIDATE_CORRECT_BLOCK_OBSERVED"
    )


def test_v1_hashes_focus1_and_prohibited_profiles_remain_fixed() -> None:
    assert FROZEN_FOCUS1_DIGEST == (
        "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
    )
    source = REPOSITORY_ROOT / "src/ragwarrant/research/fixed_sample_warrant.py"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == FROZEN_V1_SOURCE_SHA256
    overlay = load_overlay_config()
    assert overlay["full_profile_permitted"] is False
    assert overlay["target_drand_round_selected"] is False
    assert "FULL" not in overlay["development_profiles"]


def test_audit_cli_refuses_full_without_running_evidence() -> None:
    with pytest.raises(SystemExit, match="FULL is prohibited"):
        audit_cli.main(["--profile", "FULL"])
