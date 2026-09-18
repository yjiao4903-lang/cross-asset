"""RT139 B5 — asset rules / gates attacks (seeds: #138 B5; re-derived)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from cross_asset.decision_support.producer import build_monitoring_snapshot
from redteam139._helpers import (
    WEEK1_CUTOFF,
    WEEK1_DECISION,
    WEEK2_CUTOFF,
    WEEK2_DECISION,
    direct_pack,
    mechanics_registry,
)

REG = mechanics_registry()


def _snap(cutoff, decision, run_id, cpi_end=None, previous=None, **pack_kwargs):
    pack = direct_pack(as_of=cutoff, decision=decision, run_id=run_id,
                       cpi_end=cpi_end or date(cutoff.year, cutoff.month, 1), **pack_kwargs)
    return build_monitoring_snapshot(pack, previous_snapshot=previous, registry=REG)


def _two_weeks():
    week1 = _snap(WEEK1_CUTOFF, WEEK1_DECISION, "wb-b5-w1", cpi_end=date(2026, 8, 1))
    week2 = _snap(WEEK2_CUTOFF, WEEK2_DECISION, "wb-b5-w2", previous=week1)
    return week1, week2


# --- RT139-B5-01: asset views exist with bounded stance and confidence ---
def test_b5_01_asset_views_wellformed():
    week1, _ = _two_weeks()
    for view in week1.asset_views:
        assert isinstance(view.stance, int)
        assert -2 <= view.stance <= 2
        assert 0.0 <= view.confidence <= 1.0


# --- RT139-B5-02: asset keys are stable across weeks ---
def test_b5_02_asset_keys_stable():
    week1, week2 = _two_weeks()
    assert [view.asset for view in week1.asset_views] == [view.asset for view in week2.asset_views]


# --- RT139-B5-03: prior_stance chains across weeks ---
def test_b5_03_prior_stance_chains():
    week1, week2 = _two_weeks()
    by_asset = {view.asset: view for view in week2.asset_views}
    for view in week1.asset_views:
        assert by_asset[view.asset].prior_stance == view.stance


# --- RT139-B5-04: same-week retry copies the prior asset delta (P2-08 doc) ---
def test_b5_04_same_week_retry_copies_delta_documented():
    week1, week2 = _two_weeks()
    retry_pack = direct_pack(as_of=WEEK2_CUTOFF,
                             decision=WEEK2_DECISION + timedelta(hours=2),
                             run_id="wb-b5-w2-retry")
    retry = build_monitoring_snapshot(retry_pack, previous_snapshot=week2, registry=REG)
    # Documented residual P2 (ADV-P2-08): the retry inherits the prior weekly
    # deltas wholesale — a retry is not a new economic week.
    assert (retry.weekly_change.asset_view_delta.model_dump()
            == week2.weekly_change.asset_view_delta.model_dump())


# --- RT139-B5-05: market confirmation may be UNKNOWN without market data ---
def test_b5_05_market_confirmation_explicit_when_unknown():
    week1, _ = _two_weeks()
    for view in week1.asset_views:
        assert view.market_confirmation is not None


# --- RT139-B5-06: counter signals and invalidators are lists/strings, never silent ---
def test_b5_06_counter_signals_and_invalidator_typed():
    week1, _ = _two_weeks()
    for view in week1.asset_views:
        assert isinstance(view.counter_signals, list)
        assert isinstance(view.invalidator, str) or view.invalidator is None


# --- RT139-B5-07: stance change in week 2 has reason tags ---
def test_b5_07_stance_change_has_reason_tags():
    week1, week2 = _two_weeks()
    for view in week2.asset_views:
        if view.stance != view.prior_stance:
            assert view.drivers or view.counter_signals


# --- RT139-B5-08: asset view delta entries are well-formed ---
def test_b5_08_asset_delta_entries_wellformed():
    week1, week2 = _two_weeks()
    for entry in week2.weekly_change.asset_view_delta.entries:
        assert entry.delta == entry.current_stance - entry.previous_stance


# --- RT139-B5-09: week1 asset delta is empty without a causal prior ---
def test_b5_09_first_week_asset_delta_empty():
    week1, _ = _two_weeks()
    assert week1.weekly_change.asset_view_delta.entries == []


# --- RT139-B5-10: gates cannot fabricate stances from missing factors ---
def test_b5_10_missing_factor_gates_do_not_fabricate():
    week1, _ = _two_weeks()
    # with only synthetic confirmation data, unknown macro inputs stay explicit
    for view in week1.asset_views:
        assert view.macro_bias is not None
