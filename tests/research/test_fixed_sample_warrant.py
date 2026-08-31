from __future__ import annotations

import math

import pytest

from ragwarrant.research.fixed_sample_warrant import (
    BONFERRONI,
    HOLM,
    apply_multiplicity,
    bonferroni_adjust,
    bounded_paired_quality_p_value,
    exact_binomial_lower_tail,
    holm_step_down_adjust,
)


def test_exact_binomial_lower_tail_matches_hand_calculated_examples() -> None:
    assert exact_binomial_lower_tail(0, 10, 0.10) == pytest.approx(0.3486784401)
    assert exact_binomial_lower_tail(1, 10, 0.10) == pytest.approx(0.7360989291)
    assert exact_binomial_lower_tail(0, 100, 0.05) == pytest.approx(0.95**100)


def test_binary_lower_tail_has_the_certification_direction() -> None:
    zero_events = exact_binomial_lower_tail(0, 100, 0.10)
    one_event = exact_binomial_lower_tail(1, 100, 0.10)
    ten_events = exact_binomial_lower_tail(10, 100, 0.10)
    assert zero_events < one_event < ten_events


def test_exact_binomial_lower_tail_handles_degenerate_thresholds() -> None:
    assert exact_binomial_lower_tail(0, 10, 0.0) == 1.0
    assert exact_binomial_lower_tail(9, 10, 0.0) == 1.0
    assert exact_binomial_lower_tail(9, 10, 1.0) == 0.0
    assert exact_binomial_lower_tail(10, 10, 1.0) == 1.0


@pytest.mark.parametrize(
    ("event_count", "sample_count", "threshold", "message"),
    [
        (-1, 10, 0.1, "event_count"),
        (11, 10, 0.1, "event_count"),
        (0, 0, 0.1, "sample_count"),
        (0.5, 10, 0.1, "event_count"),
        (False, 10, 0.1, "event_count"),
        (0, 10, -0.1, "null_probability"),
        (0, 10, 1.1, "null_probability"),
        (0, 10, math.nan, "null_probability"),
        (0, 10, math.inf, "null_probability"),
    ],
)
def test_exact_binomial_lower_tail_fails_closed(
    event_count: object, sample_count: object, threshold: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        exact_binomial_lower_tail(event_count, sample_count, threshold)  # type: ignore[arg-type]


def test_bounded_quality_matches_approved_hoeffding_formula() -> None:
    deltas = (0.04, 0.06)
    expected = math.exp(-2.0 * 2 * (0.05 + 0.02) ** 2 / (0.25 - (-0.25)) ** 2)
    assert bounded_paired_quality_p_value(deltas, 0.02, -0.25, 0.25) == pytest.approx(
        expected
    )


def test_bounded_quality_returns_one_at_or_below_null_boundary() -> None:
    assert bounded_paired_quality_p_value((-0.02,), 0.02, -0.25, 0.25) == 1.0
    assert bounded_paired_quality_p_value((-0.03, -0.01), 0.02, -0.25, 0.25) == 1.0


def test_bounded_quality_becomes_more_significant_with_more_favorable_evidence() -> None:
    weak = bounded_paired_quality_p_value((0.0,) * 50, 0.02, -0.25, 0.25)
    strong = bounded_paired_quality_p_value((0.10,) * 50, 0.02, -0.25, 0.25)
    assert strong < weak


@pytest.mark.parametrize(
    ("deltas", "margin", "lower", "upper", "message"),
    [
        ((), 0.02, -0.25, 0.25, "non-empty"),
        ((math.nan,), 0.02, -0.25, 0.25, "finite"),
        ((math.inf,), 0.02, -0.25, 0.25, "finite"),
        ((0.30,), 0.02, -0.25, 0.25, "outside"),
        ((0.0,), -0.01, -0.25, 0.25, "nonnegative"),
        ((0.0,), 0.02, 0.25, -0.25, "strictly less"),
        ((0.0,), 0.02, 0.25, 0.25, "strictly less"),
        ((0.0,), 0.02, math.nan, 0.25, "finite"),
    ],
)
def test_bounded_quality_fails_closed(
    deltas: tuple[float, ...], margin: float, lower: float, upper: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        bounded_paired_quality_p_value(deltas, margin, lower, upper)


def test_bonferroni_uses_the_complete_family_and_adjusts_p_values() -> None:
    result = bonferroni_adjust({"h3": 0.50, "h1": 0.01, "h2": 0.03}, alpha=0.05)
    assert result.method == BONFERRONI
    assert result.family_size == 3
    assert result.ordered_hypothesis_ids == ("h1", "h2", "h3")
    assert result.rejected_hypothesis_ids == ("h1",)
    assert result.adjusted_p_value("h1") == pytest.approx(0.03)
    assert result.adjusted_p_value("h2") == pytest.approx(0.09)
    assert result.adjusted_p_value("h3") == 1.0
    assert result.rejection_threshold("h1") == pytest.approx(0.05 / 3)


def test_bonferroni_rejects_at_exact_threshold() -> None:
    result = bonferroni_adjust({"boundary": 0.025, "other": 0.9}, alpha=0.05)
    assert result.rejected_hypothesis_ids == ("boundary",)


def test_holm_step_down_adjustment_and_exact_threshold_convention() -> None:
    result = holm_step_down_adjust(
        {"third": 0.03, "first": 0.01, "second": 0.025}, alpha=0.05
    )
    assert result.method == HOLM
    assert result.ordered_hypothesis_ids == ("first", "second", "third")
    assert result.rejected_hypothesis_ids == ("first", "second", "third")
    assert result.adjusted_p_value("first") == pytest.approx(0.03)
    assert result.adjusted_p_value("second") == pytest.approx(0.05)
    assert result.adjusted_p_value("third") == pytest.approx(0.05)
    assert result.rejection_threshold("second") == pytest.approx(0.025)


def test_holm_stops_at_first_failure() -> None:
    result = holm_step_down_adjust(
        {"first": 0.02, "would-pass-later": 0.021, "last": 0.022}, alpha=0.05
    )
    assert result.rejected_hypothesis_ids == ()


def test_holm_ties_use_hypothesis_id_order_and_discrete_values_are_unchanged() -> None:
    result = holm_step_down_adjust(
        (("z-risk", 0.01), ("a-risk", 0.01), ("other", 0.8)), alpha=0.05
    )
    assert result.ordered_hypothesis_ids == ("a-risk", "z-risk", "other")
    assert dict(result.raw_p_values) == {"a-risk": 0.01, "other": 0.8, "z-risk": 0.01}


def test_holm_is_never_less_powerful_than_bonferroni_for_same_family() -> None:
    families = (
        {"a": 0.001, "b": 0.02, "c": 0.7},
        {"a": 0.0125, "b": 0.0125, "c": 0.0125, "d": 0.0125},
        {"a": 0.02, "b": 0.021, "c": 0.022},
        {"a": 0.0, "b": 0.016, "c": 0.5},
    )
    for family in families:
        bonferroni = bonferroni_adjust(family, alpha=0.05)
        holm = holm_step_down_adjust(family, alpha=0.05)
        assert set(bonferroni.rejected_hypothesis_ids) <= set(
            holm.rejected_hypothesis_ids
        )


@pytest.mark.parametrize("alpha", [0.0, 1.0, -0.1, math.nan, math.inf])
def test_multiplicity_rejects_invalid_alpha(alpha: float) -> None:
    with pytest.raises(ValueError, match="alpha"):
        bonferroni_adjust({"h": 0.1}, alpha)
    with pytest.raises(ValueError, match="alpha"):
        holm_step_down_adjust({"h": 0.1}, alpha)


@pytest.mark.parametrize(
    "family",
    [
        {},
        {"h": -0.1},
        {"h": 1.1},
        {"h": math.nan},
        {"h": math.inf},
        {"": 0.1},
        (("duplicate", 0.1), ("duplicate", 0.2)),
    ],
)
def test_multiplicity_rejects_malformed_families(family: object) -> None:
    with pytest.raises(ValueError):
        bonferroni_adjust(family, 0.05)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        holm_step_down_adjust(family, 0.05)  # type: ignore[arg-type]


def test_apply_multiplicity_dispatches_only_prespecified_methods() -> None:
    family = {"h": 0.01}
    assert apply_multiplicity(family, 0.05, BONFERRONI).method == BONFERRONI
    assert apply_multiplicity(family, 0.05, HOLM).method == HOLM
    with pytest.raises(ValueError, match="unknown multiplicity method"):
        apply_multiplicity(family, 0.05, "pick_after_looking")
