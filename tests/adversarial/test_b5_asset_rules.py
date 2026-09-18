"""B5 — asset-rule / confirmation / valuation attacks (ADVERSARIAL-E2E-VALIDATION-V1)."""

from __future__ import annotations

import pytest

from cross_asset.decision_support.asset_rules import (
    UNKNOWN_CONFIRMATION_DISCOUNT,
    apply_confirmation_gate,
    apply_valuation_gate,
    build_asset_gate,
    compute_macro_bias,
    market_confirmation_state,
)
from cross_asset.decision_support.enums import DataHealthStatus, MarketConfirmation
from cross_asset.decision_support.taxonomy import load_taxonomy

from _helpers import mechanics_registry, pack

from cross_asset.decision_support.producer import build_monitoring_snapshot

from cross_asset.decision_support.snapshot import AssetViewV0


def _rule(asset: str):
    return load_taxonomy().asset_rule(asset)


# --- B5-01: macro basis missing -> explicit neutral, never a guess --------------


def test_adv_b5_01_missing_macro_basis_yields_explicit_neutral_stance():
    rule = _rule("US_EQ")
    result = build_asset_gate(
        rule,
        cyclical_scores={family: None for family in rule.macro_weights},
        tactical_scores={},
        structural_scores={},
    )
    assert result.macro_declared == len(rule.macro_weights)
    assert result.macro_available == 0
    assert result.macro_missing == len(rule.macro_weights)
    assert result.macro_bias == 0
    assert result.stance == 0
    assert result.data_health is DataHealthStatus.MISSING
    assert result.market_confirmation is MarketConfirmation.UNKNOWN
    assert "macro basis unavailable" in result.valuation_tag


def test_adv_b5_02_partial_macro_basis_excludes_missing_and_lowers_confidence():
    rule = _rule("US_EQ")
    scores = {family: None for family in rule.macro_weights}
    available_family = next(iter(rule.macro_weights))
    scores[available_family] = 1.0
    basis = compute_macro_bias(rule, scores)
    assert basis.available == 1
    assert basis.missing == len(rule.macro_weights) - 1
    assert pytest.approx(basis.confidence_factor) == 1 / len(rule.macro_weights)
    assert all(blocker.source != available_family for blocker in basis.blockers)


# --- B5-03/04: confirmation semantics -------------------------------------------


@pytest.mark.parametrize(
    "bias,confirmation,expected",
    [
        (1, None, MarketConfirmation.UNKNOWN),
        (1, 0.0, MarketConfirmation.DIVERGENT),
        (0, 0.5, MarketConfirmation.DIVERGENT),
        (1, 0.5, MarketConfirmation.CONFIRMED),
        (1, -0.5, MarketConfirmation.COUNTER_TREND),
        (-1, -0.5, MarketConfirmation.CONFIRMED),
    ],
)
def test_adv_b5_03_confirmation_state_matrix(bias, confirmation, expected):
    assert market_confirmation_state(bias, confirmation) is expected


def test_adv_b5_04_unobservable_confirmation_is_unknown_not_divergent():
    rule = _rule("US_EQ")
    result = build_asset_gate(
        rule,
        cyclical_scores={family: 0.5 for family in rule.macro_weights},
        tactical_scores={rule.confirmation_source: None},
        structural_scores={},
    )
    assert result.market_confirmation is MarketConfirmation.UNKNOWN
    blockers = [blocker.source for blocker in result.blockers]
    assert rule.confirmation_source in blockers
    # No stance gate is applied for an unobserved input, only a discount.
    assert result.stance == result.macro_bias
    assert any("UNKNOWN" in note for note in result.counter_signals)


def test_adv_b5_05_confirmation_conflict_caps_but_never_flips_the_sign():
    for stance in (-2, -1, 1, 2):
        capped, _ = apply_confirmation_gate(
            stance, MarketConfirmation.COUNTER_TREND, counter_trend_cap=1
        )
        assert abs(capped) <= 1
        if stance > 0:
            assert capped > 0
        else:
            assert capped < 0


def test_adv_b5_06_divergent_attenuates_one_step_toward_neutral():
    assert apply_confirmation_gate(2, MarketConfirmation.DIVERGENT, counter_trend_cap=1)[0] == 1
    assert apply_confirmation_gate(-2, MarketConfirmation.DIVERGENT, counter_trend_cap=1)[0] == -1
    assert apply_confirmation_gate(0, MarketConfirmation.DIVERGENT, counter_trend_cap=1)[0] == 0


# --- B5-07/08: valuation cap/cushion edges --------------------------------------


@pytest.mark.parametrize(
    "stance,valuation,expected",
    [
        (2, -1.0, 1),
        (2, -0.999999, 2),
        (-2, 1.0, -1),
        (-2, 0.999999, -2),
        (2, None, 2),
        (-2, None, -2),
        (0, -2.0, 0),
    ],
)
def test_adv_b5_07_valuation_cap_and_cushion_edges(stance, valuation, expected):
    result, _ = apply_valuation_gate(
        stance, valuation, cap_threshold=-1.0, cushion_threshold=1.0
    )
    assert result == expected


def test_adv_b5_08_cheap_valuation_never_upgrades_a_short_stance():
    result, _ = apply_valuation_gate(
        -2, 2.0, cap_threshold=-1.0, cushion_threshold=1.0
    )
    assert result == -1
    # A cheap valuation must not create a long from a short.
    assert result <= 0


# --- B5-09: counter-signals reflect genuine disagreement -----------------------


def test_adv_b5_09_counter_signals_are_emitted_for_opposing_contributions():
    rule = _rule("US_EQ")
    scores = {family: 1.0 for family in rule.macro_weights}
    negative_family = next(
        family for family, weight in rule.macro_weights.items() if weight < 0
    )
    scores[negative_family] = 2.0
    result = build_asset_gate(
        rule,
        cyclical_scores=scores,
        tactical_scores={rule.confirmation_source: 1.0},
        structural_scores={},
    )
    assert result.stance > 0
    assert any(
        signal.startswith(negative_family) for signal in result.counter_signals
    )


# --- B5-10: missing factor must not become bearish ------------------------------


def test_adv_b5_10_missing_confirmation_factor_does_not_turn_an_asset_bearish():
    snapshot = build_monitoring_snapshot(
        pack(omit=frozenset({"T_US_EQ"})), registry=mechanics_registry()
    )
    view = next(item for item in snapshot.asset_views if item.asset.value == "US_EQ")
    assert view.market_confirmation is MarketConfirmation.UNKNOWN
    assert view.stance >= 0, "an unavailable confirmation input must not create a short"
    assert view.data_health is not DataHealthStatus.OK
    assert next(
        state
        for state in snapshot.details["factor_statuses"].values()
        if state["missing"]
    )["missing"] is True


# --- B5-11: market confirmation is not macro authority --------------------------


def test_adv_b5_11_confirmation_only_factor_never_sets_macro_bias():
    rule = _rule("US_EQ")
    result = build_asset_gate(
        rule,
        cyclical_scores={family: None for family in rule.macro_weights},
        tactical_scores={rule.confirmation_source: 2.0},
        structural_scores={},
    )
    assert result.macro_bias == 0
    assert result.stance == 0
    assert result.data_health is DataHealthStatus.MISSING


# --- B5-12: driven-by-market confirmation is tagged, not silently economic ------


def test_adv_b5_12_confirmed_state_is_attributed_to_the_confirmation_source():
    rule = _rule("US_EQ")
    result = build_asset_gate(
        rule,
        cyclical_scores={family: 1.0 for family in rule.macro_weights},
        tactical_scores={rule.confirmation_source: 1.0},
        structural_scores={},
    )
    assert result.market_confirmation is MarketConfirmation.CONFIRMED
    assert f"market_confirmed:{rule.confirmation_source}" in result.drivers
    assert result.confidence >= result.macro_available / result.macro_declared


# --- B5-13: stance bounds are always respected ----------------------------------


def test_adv_b5_13_all_asset_stances_stay_inside_bounds():
    taxonomy = load_taxonomy()
    snapshot = build_monitoring_snapshot(pack(), registry=mechanics_registry())
    assert len(snapshot.asset_views) == len(taxonomy.asset_rules)
    for view in snapshot.asset_views:
        assert -2 <= view.stance <= 2
        assert -2 <= view.macro_bias <= 2
        assert -2 <= view.prior_stance <= 2
        assert isinstance(view, AssetViewV0)
        assert view.invalidator, "every V0 asset rule must publish an invalidator"


# --- B5-14: unknown confirmation discount is named, not implicit ----------------


def test_adv_b5_14_unknown_confirmation_discount_is_the_named_constant():
    rule = _rule("US_EQ")
    scores = {family: 1.0 for family in rule.macro_weights}
    unknown = build_asset_gate(
        rule,
        cyclical_scores=scores,
        tactical_scores={rule.confirmation_source: None},
        structural_scores={},
    )
    confirmed = build_asset_gate(
        rule,
        cyclical_scores=scores,
        tactical_scores={rule.confirmation_source: 1.0},
        structural_scores={},
    )
    assert unknown.confidence < confirmed.confidence
    assert UNKNOWN_CONFIRMATION_DISCOUNT == 0.7
