"""Issue #114 Scope G tests: deterministic demo fixtures with required semantics."""

import json
from pathlib import Path

import pytest

from cross_asset.decision_support.enums import (
    DataHealthStatus,
    EvidenceLane,
    InformationSetStatus,
    QuadrantLabel,
)
from cross_asset.decision_support.fixtures import (
    build_benign_snapshot,
    build_tightening_snapshot,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "decision_support"


@pytest.fixture(scope="module")
def benign():
    return build_benign_snapshot()


@pytest.fixture(scope="module")
def tightening():
    return build_tightening_snapshot()


def test_two_snapshots_represent_different_states(benign, tightening):
    assert benign.regime.quadrant_label != tightening.regime.quadrant_label
    assert (
        benign.regime.quadrant_label == QuadrantLabel.GOLDILOCKS
    ), "benign fixture should be a goldilocks-like environment"
    assert (
        tightening.regime.quadrant_label == QuadrantLabel.STAGFLATION_RISK
    ), "tightening fixture should carry stagflation risk"
    benign_stances = {v.asset: v.stance for v in benign.asset_views}
    tightening_stances = {v.asset: v.stance for v in tightening.asset_views}
    assert benign_stances != tightening_stances


def test_fixtures_are_deterministic():
    assert build_benign_snapshot().to_json() == build_benign_snapshot().to_json()
    assert build_tightening_snapshot().to_json() == build_tightening_snapshot().to_json()


def test_fixture_lane_is_monitoring_by_default(benign, tightening):
    assert benign.metadata.resolved_lane() is EvidenceLane.MONITORING
    assert tightening.metadata.resolved_lane() is EvidenceLane.MONITORING


def test_fixture_information_set_delta(benign, tightening):
    # Both fixtures updated this week, each with exactly one overdue component.
    assert (
        benign.weekly_change.information_set_delta.resolved_status()
        is InformationSetStatus.UPDATED
    )
    assert benign.weekly_change.information_set_delta.stale_factors == ["CN_MFG_PMI"]
    assert (
        tightening.weekly_change.information_set_delta.resolved_status()
        is InformationSetStatus.UPDATED
    )
    assert tightening.weekly_change.information_set_delta.stale_factors == ["US_ISM_PMI"]
    # Revisions are preserved as events, never collapsed.
    benign_events = {
        event.resolved_event_type().value
        for event in benign.weekly_change.information_set_delta.events
    }
    assert "REVISION" in benign_events
    assert "OVERDUE" in benign_events
    # Surprise metadata must declare its method.
    for event in benign.weekly_change.information_set_delta.events:
        if event.surprise is not None:
            assert event.surprise.resolved_method().value == "TREND_RELATIVE"


def test_fixture_macro_state_respects_no_release_no_movement(benign):
    deltas = {entry.factor_id: entry.delta for entry in benign.weekly_change.macro_state_delta.entries}
    # Inflation series had no releases this week: no synthetic drift.
    assert deltas["US_CORE_CPI_TREND"] == 0.0
    assert deltas["US_PPI_TREND"] == 0.0
    assert deltas["US_WAGE_PRESSURE"] == 0.0
    # Released factors moved.
    assert deltas["US_PAYROLLS_TREND"] > 0
    causes = {
        entry.factor_id: entry.resolved_cause().value
        for entry in benign.weekly_change.macro_state_delta.entries
    }
    assert causes["US_PAYROLLS_TREND"] == "NEW_INFORMATION"
    assert causes["US_CORE_CPI_TREND"] == "NO_NEW_INFORMATION"


def test_fixture_stance_changes_and_reason_tags(benign, tightening):
    benign_delta = benign.weekly_change.asset_view_delta
    assert any(entry.delta != 0 for entry in benign_delta.entries)
    for entry in benign_delta.entries:
        assert entry.reason_tags, "stance changes must carry reason tags"
    tightening_delta = tightening.weekly_change.asset_view_delta
    assert any(entry.delta < 0 for entry in tightening_delta.entries)
    assert any(entry.delta > 0 for entry in tightening_delta.entries)
    # CASH counter-trend stance must be tagged as such.
    cash = next(entry for entry in tightening_delta.entries if entry.asset == "CASH")
    assert "MARKET_COUNTER_TREND" in cash.reason_tags


def test_fixture_market_condition_units(benign):
    units = {move.instrument: move.resolved_unit().value for move in benign.weekly_change.market_condition_delta.moves}
    assert units["US10Y"] == "BPS"
    assert units["US_HY_OAS"] == "BPS"
    assert units["SPX"] == "PCT"
    assert units["GOLD"] == "PCT"
    assert units["VIX"] == "POINT"


def test_fixture_data_health_badges(benign, tightening):
    assert benign.data_health_summary.resolved_overall() is DataHealthStatus.PARTIAL
    assert "CN_MFG_PMI" in benign.data_health_summary.stale_components
    assert tightening.data_health_summary.resolved_overall() is DataHealthStatus.PARTIAL
    # Tightening carries an explicit gate blocker for the missing valuation overlay.
    assert any("GOLD_REAL_RATE_OVERLAY" in blocker for blocker in tightening.data_health_summary.blockers)
    # At least one asset view carries a non-OK data-health badge in each scenario.
    assert any(v.resolved_data_health() is not DataHealthStatus.OK for v in tightening.asset_views)


def test_fixture_counter_signals_present(tightening):
    gold = next(v for v in tightening.asset_views if v.asset == "GOLD")
    assert gold.counter_signals, "tightening fixture must expose counter-signals"


def test_fixture_executive_brief_shape(benign):
    brief = benign.executive_brief
    assert brief.what_changed and brief.why_it_matters
    assert len(brief.what_to_watch) >= 2


def test_golden_fixture_files_match_generation():
    """The committed JSON fixtures for #115 must equal regenerated output."""
    for name, builder in (
        ("snapshot_benign.json", build_benign_snapshot),
        ("snapshot_tightening.json", build_tightening_snapshot),
    ):
        path = FIXTURE_DIR / name
        assert path.exists(), f"missing committed fixture {path}"
        committed = path.read_text(encoding="utf-8")
        regenerated = builder().to_json()
        assert committed == regenerated, f"{name} does not match regenerated output"
        parsed = json.loads(committed)
        assert parsed["metadata"]["snapshot_version"] == "DashboardSnapshotV0"
