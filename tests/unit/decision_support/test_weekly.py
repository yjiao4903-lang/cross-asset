"""Issue #114 Scope C tests: four-surface weekly change semantics."""

from datetime import date

import pytest

from cross_asset.decision_support.enums import (
    CauseTag,
    InformationSetStatus,
    MarketDeltaUnit,
    MarketMetricClass,
    ReleaseEventType,
)
from cross_asset.decision_support.weekly import (
    ReleaseEvent,
    SyntheticMovementError,
    build_information_set_delta,
    build_macro_state_delta,
    build_market_move,
)

# ---------------------------------------------------------------------------
# information_set_delta
# ---------------------------------------------------------------------------


def test_information_set_statuses_are_distinct_states():
    # NO_NEW_INFORMATION is its own explicit state: it is neither a neutral
    # score nor a missing component, and MISSING-style staleness has its own
    # OVERDUE_STALE state.
    statuses = {s.value for s in InformationSetStatus}
    assert {
        InformationSetStatus.UPDATED.value,
        InformationSetStatus.NO_NEW_INFORMATION.value,
        InformationSetStatus.OVERDUE_STALE.value,
    } == statuses
    assert "NEUTRAL" not in statuses
    assert "MISSING" not in statuses


def test_no_events_yields_no_new_information():
    delta = build_information_set_delta([], expected_releases={}, as_of=date(2026, 9, 4))
    assert delta.resolved_status() is InformationSetStatus.NO_NEW_INFORMATION
    assert delta.events == []


def test_revision_preserved_as_event():
    events = [
        ReleaseEvent(
            factor_id="US_CORE_CPI_TREND",
            series_id="FIXTURE_CPI",
            event_type=ReleaseEventType.REVISION,
            observation_date=date(2026, 8, 12),
        )
    ]
    delta = build_information_set_delta(events, expected_releases={}, as_of=date(2026, 9, 4))
    assert delta.resolved_status() is InformationSetStatus.UPDATED
    assert delta.events[0].resolved_event_type() is ReleaseEventType.REVISION


def test_overdue_stale_when_expected_release_missed():
    delta = build_information_set_delta(
        [],
        expected_releases={"CN_MFG_PMI": date(2026, 8, 31)},
        as_of=date(2026, 9, 4),
    )
    assert delta.resolved_status() is InformationSetStatus.OVERDUE_STALE
    assert delta.stale_factors == ["CN_MFG_PMI"]


def test_overdue_factor_does_not_mask_updated_status():
    events = [
        ReleaseEvent(
            factor_id="US_PAYROLLS_TREND",
            event_type=ReleaseEventType.NEW_OBSERVATION,
            observation_date=date(2026, 9, 4),
        )
    ]
    delta = build_information_set_delta(
        events,
        expected_releases={"CN_MFG_PMI": date(2026, 8, 31)},
        as_of=date(2026, 9, 4),
    )
    assert delta.resolved_status() is InformationSetStatus.UPDATED
    assert delta.stale_factors == ["CN_MFG_PMI"]


# ---------------------------------------------------------------------------
# macro_state_delta
# ---------------------------------------------------------------------------


def test_no_new_information_produces_zero_macro_movement():
    delta = build_macro_state_delta(
        {"a": 0.5, "b": -0.25},
        {"a": 0.5, "b": -0.25},
        information_status=InformationSetStatus.NO_NEW_INFORMATION,
    )
    assert all(entry.delta == 0.0 for entry in delta.entries)
    assert delta.changed_factors() == []


def test_synthetic_weekly_drift_is_rejected():
    with pytest.raises(SyntheticMovementError, match="synthetic movement"):
        build_macro_state_delta(
            {"a": 0.5},
            {"a": 0.6},
            information_status=InformationSetStatus.NO_NEW_INFORMATION,
        )


def test_movement_requires_an_observed_release():
    with pytest.raises(SyntheticMovementError, match="without an observed release"):
        build_macro_state_delta(
            {"a": 0.5},
            {"a": 0.6},
            information_status=InformationSetStatus.UPDATED,
            changed_by_release={"other"},
        )


def test_release_caused_movement_is_tagged():
    delta = build_macro_state_delta(
        {"a": 0.5, "b": 0.2},
        {"a": 0.6, "b": 0.2},
        information_status=InformationSetStatus.UPDATED,
        changed_by_release={"a"},
    )
    by_id = {entry.factor_id: entry for entry in delta.entries}
    assert by_id["a"].delta == pytest.approx(0.1)
    assert by_id["a"].resolved_cause() is CauseTag.NEW_INFORMATION
    assert by_id["b"].resolved_cause() is CauseTag.NO_NEW_INFORMATION


# ---------------------------------------------------------------------------
# market_condition_delta unit semantics
# ---------------------------------------------------------------------------


def test_price_fx_commodity_use_percent_change():
    move = build_market_move("SPX", MarketMetricClass.PRICE, 6450.0, 6528.0)
    assert move.resolved_unit() is MarketDeltaUnit.PCT
    assert move.weekly_change == pytest.approx(1.209302, abs=1e-5)
    fx = build_market_move("USD_CNY", MarketMetricClass.FX, 7.13, 7.11)
    assert fx.resolved_unit() is MarketDeltaUnit.PCT
    commodity = build_market_move("GOLD", MarketMetricClass.COMMODITY, 3480.0, 3532.0)
    assert commodity.resolved_unit() is MarketDeltaUnit.PCT


def test_yield_and_spread_use_bps_not_percent():
    yield_move = build_market_move("US10Y", MarketMetricClass.YIELD, 4.27, 4.36)
    assert yield_move.resolved_unit() is MarketDeltaUnit.BPS
    assert yield_move.weekly_change == pytest.approx(9.0)
    spread = build_market_move("US_HY_OAS", MarketMetricClass.SPREAD, 2.77, 2.98)
    assert spread.resolved_unit() is MarketDeltaUnit.BPS
    assert spread.weekly_change == pytest.approx(21.0)


def test_volatility_uses_configured_style():
    point = build_market_move("VIX", MarketMetricClass.VOLATILITY, 14.0, 17.2)
    assert point.resolved_unit() is MarketDeltaUnit.POINT
    assert point.weekly_change == pytest.approx(3.2)
    pct_style = build_market_move(
        "VIX", MarketMetricClass.VOLATILITY, 14.0, 17.2, volatility_style="PERCENTILE"
    )
    assert pct_style.resolved_unit() is MarketDeltaUnit.PERCENTILE


def test_percent_change_with_zero_prior_fails_closed():
    with pytest.raises(ValueError, match="zero prior"):
        build_market_move("SPX", MarketMetricClass.PRICE, 0.0, 10.0)
