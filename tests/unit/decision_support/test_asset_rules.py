"""Issue #114 Scope F tests: asset gates deterministic, bounded, no zero-fill."""


from cross_asset.decision_support.asset_rules import (
    AssetRuleSpec,
    apply_confirmation_gate,
    apply_valuation_gate,
    build_asset_gate,
    compute_macro_bias,
    market_confirmation_state,
)
from cross_asset.decision_support.enums import MarketConfirmation


def _rule(**overrides) -> AssetRuleSpec:
    base: dict = {
        "asset": "US_EQ",
        "macro_weights": {"GROWTH_ACTIVITY": 1.0, "POLICY_LIQUIDITY": 0.5},
        "macro_scale": 1.0,
        "confirmation_source": "US_EQ_TREND_63D",
        "confirmation_bonus": 0.1,
        "counter_trend_cap": 1,
        "valuation_source": "",
        "invalidator": "test invalidator",
    }
    base.update(overrides)
    return AssetRuleSpec(**base)


def test_stance_bounded_in_extreme_inputs():
    rule = _rule(macro_weights={"GROWTH_ACTIVITY": 5.0}, macro_scale=0.5)
    result = build_asset_gate(
        rule,
        cyclical_scores={"GROWTH_ACTIVITY": 2.0},
        tactical_scores={"US_EQ_TREND_63D": 2.0},
        structural_scores={},
    )
    assert -2 <= result.macro_bias <= 2
    assert -2 <= result.stance <= 2
    assert result.macro_bias == 2
    negative = build_asset_gate(
        rule,
        cyclical_scores={"GROWTH_ACTIVITY": -2.0},
        tactical_scores={"US_EQ_TREND_63D": -2.0},
        structural_scores={},
    )
    assert negative.stance == -2


def test_confirmation_confirms_attenuates_and_caps():
    rule = _rule()
    confirmed = build_asset_gate(
        rule,
        cyclical_scores={"GROWTH_ACTIVITY": 1.0, "POLICY_LIQUIDITY": 0.5},
        tactical_scores={"US_EQ_TREND_63D": 0.8},
        structural_scores={},
    )
    assert confirmed.market_confirmation is MarketConfirmation.CONFIRMED
    assert confirmed.stance == confirmed.macro_bias == 1

    counter = build_asset_gate(
        rule,
        cyclical_scores={"GROWTH_ACTIVITY": 2.0, "POLICY_LIQUIDITY": 1.0},
        tactical_scores={"US_EQ_TREND_63D": -0.8},
        structural_scores={},
    )
    assert counter.market_confirmation is MarketConfirmation.COUNTER_TREND
    # Conviction is capped, sign never flipped.
    assert counter.stance == 1
    assert counter.macro_bias == 2

    divergent = build_asset_gate(
        rule,
        cyclical_scores={"GROWTH_ACTIVITY": 2.0, "POLICY_LIQUIDITY": 1.0},
        tactical_scores={"US_EQ_TREND_63D": 0.0},
        structural_scores={},
    )
    assert divergent.market_confirmation is MarketConfirmation.DIVERGENT
    # bias clips to +2, divergence attenuates one step to +1.
    assert divergent.stance == 1


def test_divergent_attenuates_one_step():
    stance, note = apply_confirmation_gate(2, MarketConfirmation.DIVERGENT, counter_trend_cap=1)
    assert stance == 1
    assert note == "market divergence attenuation applied"


def test_valuation_is_asymmetric_cap_cushion():
    # Expensive valuation caps a +2 long to +1 but never creates a short.
    capped, tag = apply_valuation_gate(2, -1.5, cap_threshold=-1.0, cushion_threshold=1.0)
    assert capped == 1 and "cap" in tag
    # Cheap valuation cushions a -2 short to -1 but never creates a long.
    cushioned, tag = apply_valuation_gate(-2, 1.5, cap_threshold=-1.0, cushion_threshold=1.0)
    assert cushioned == -1 and "cushion" in tag
    # Neutral valuation changes nothing.
    untouched, _ = apply_valuation_gate(2, 0.0, cap_threshold=-1.0, cushion_threshold=1.0)
    assert untouched == 2


def test_confirmation_helpers_direct():
    assert market_confirmation_state(1, 0.5) is MarketConfirmation.CONFIRMED
    assert market_confirmation_state(1, -0.5) is MarketConfirmation.COUNTER_TREND
    assert market_confirmation_state(0, 0.5) is MarketConfirmation.DIVERGENT
    assert market_confirmation_state(1, None) is MarketConfirmation.DIVERGENT
    capped, _ = apply_confirmation_gate(2, MarketConfirmation.COUNTER_TREND, counter_trend_cap=1)
    assert capped == 1
    assert apply_confirmation_gate(-2, MarketConfirmation.COUNTER_TREND, counter_trend_cap=1)[0] == -1


def test_missing_cluster_lowers_confidence_and_blocks_not_zero_fill():
    rule = _rule(macro_weights={"GROWTH_ACTIVITY": 1.0, "POLICY_LIQUIDITY": 0.5})
    result = build_asset_gate(
        rule,
        cyclical_scores={"GROWTH_ACTIVITY": 1.0, "POLICY_LIQUIDITY": None},
        tactical_scores={"US_EQ_TREND_63D": 0.5},
        structural_scores={},
    )
    # Policy contribution is excluded, not zero-filled into a silent sum.
    assert result.macro_bias == 1
    assert result.confidence < 1.0
    assert any(b.source == "POLICY_LIQUIDITY" for b in result.blockers)
    assert result.data_health.value == "PARTIAL"


def test_missing_confirmation_input_is_a_blocker():
    rule = _rule()
    result = build_asset_gate(
        rule,
        cyclical_scores={"GROWTH_ACTIVITY": 1.0, "POLICY_LIQUIDITY": 0.5},
        tactical_scores={},
        structural_scores={},
    )
    assert result.market_confirmation is MarketConfirmation.DIVERGENT
    assert any(b.source == "US_EQ_TREND_63D" for b in result.blockers)


def test_all_macro_missing_forces_explicit_neutral():
    rule = _rule()
    result = build_asset_gate(
        rule,
        cyclical_scores={"GROWTH_ACTIVITY": None, "POLICY_LIQUIDITY": None},
        tactical_scores={"US_EQ_TREND_63D": 0.5},
        structural_scores={},
    )
    assert result.stance == 0
    assert result.data_health.value == "MISSING"


def test_compute_macro_bias_weights_are_economic_not_fitted():
    rule = _rule(macro_weights={"GROWTH_ACTIVITY": 1.0, "POLICY_LIQUIDITY": 0.5})
    bias, confidence, contributions, blockers = compute_macro_bias(
        rule, {"GROWTH_ACTIVITY": 1.0, "POLICY_LIQUIDITY": -0.4}
    )
    assert bias == 1  # 1.0 - 0.2 = 0.8 -> rounds to 1
    assert confidence == 1.0
    assert ("POLICY_LIQUIDITY", -0.2) in [(f, round(c, 4)) for f, c in contributions]
    assert blockers == []
