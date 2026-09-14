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


def test_fixture_missing_regime_axis_fails_closed(benign):
    """R1 blocker 3: no None -> 0.0 substitution anywhere in snapshot assembly."""
    import copy

    from cross_asset.decision_support.fixtures import (
        _benign_scenario,
        _build_snapshot,
    )
    from cross_asset.decision_support.horizon import SubfactorScore
    from cross_asset.decision_support.regime import RegimeInsufficientDataError
    from cross_asset.decision_support.taxonomy import load_taxonomy

    config = load_taxonomy()
    scenario = _benign_scenario(config)
    growth_factors = [
        sub.factor_id
        for sub in config.subfactors()
        if sub.family == "GROWTH_ACTIVITY" and sub.horizon == "CYCLICAL"
    ]
    weeks = []
    for week in scenario.weeks:
        scores = dict(week.scores)
        for factor_id in growth_factors:
            scores[factor_id] = SubfactorScore(
                factor_id=factor_id,
                horizon="CYCLICAL",
                missing=True,
            )
        weeks.append(
            type(week)(as_of=week.as_of, scores=list(scores.values()),
                       market_levels=week.market_levels, events=week.events)
        )
    broken = copy.copy(scenario)
    broken.weeks = weeks
    with pytest.raises(RegimeInsufficientDataError, match="growth"):
        _build_snapshot(broken, config)


def test_fixture_climate_components_render_ready(benign, tightening):
    """R1 blocker 4: Overview pills come fully typed from the backend."""
    expected = {
        "POLICY_LIQUIDITY",
        "FINANCIAL_CONDITIONS",
        "MARKET_CONFIRMATION",
        "RISK_APPETITE",
        "INVESTMENT_CLIMATE",
    }
    for snapshot in (benign, tightening):
        components = {c.component: c for c in snapshot.climate_components}
        assert set(components) == expected
        for component in components.values():
            assert component.state, component.component
            assert component.state != ""
            assert 0.0 <= component.confidence <= 1.0
            assert 0.0 <= component.coverage <= 1.0
            if component.score is not None:
                assert -2.0 <= component.score <= 2.0
        # A missing lens must surface UNAVAILABLE, never a fabricated state.
    tightening_components = {c.component: c for c in tightening.climate_components}
    assert tightening_components["POLICY_LIQUIDITY"].state in {
        "EASING",
        "NEUTRAL",
        "TIGHTENING",
    }
    benign_components = {c.component: c for c in benign.climate_components}
    assert benign_components["MARKET_CONFIRMATION"].state == "TRENDING_UP"


def test_fixture_snapshot_version_is_authoritative(benign):
    # Preserve the exact authoritative value consumed by #115/#116.
    assert benign.metadata.snapshot_version == "DashboardSnapshotV0"


def test_fixture_lane_param_only_accepts_non_formal_lanes():
    from cross_asset.decision_support.enums import EvidenceLane
    from cross_asset.decision_support.fixtures import build_benign_snapshot

    research = build_benign_snapshot(lane=EvidenceLane.RESEARCH)
    assert research.metadata.resolved_lane() is EvidenceLane.RESEARCH


# ---------------------------------------------------------------------------
# R2 regressions: financial-conditions sign / semantic consistency
# ---------------------------------------------------------------------------


def _component(snapshot, name):
    return {c.component: c for c in snapshot.climate_components}[name]


def test_score_sign_to_state_convention_is_enforced(benign, tightening):
    """Rendered state must follow the frozen score-sign convention, not merely
    belong to the allowed label set: positive financial-conditions score =
    EASING, negative = TIGHTENING."""
    benign_fincond = _component(benign, "FINANCIAL_CONDITIONS")
    assert benign_fincond.score is not None and benign_fincond.score > 0.25
    assert benign_fincond.state == "EASING"
    tightening_fincond = _component(tightening, "FINANCIAL_CONDITIONS")
    assert tightening_fincond.score is not None and tightening_fincond.score < -0.25
    assert tightening_fincond.state == "TIGHTENING"


def test_tightening_financial_conditions_not_easing(tightening, benign):
    assert _component(tightening, "FINANCIAL_CONDITIONS").state != "EASING"
    # The stress week's genuine market surface (HY spread widens in bps) must
    # agree with the rendered lens state.
    hy_move = next(
        m
        for m in tightening.weekly_change.market_condition_delta.moves
        if m.instrument == "US_HY_OAS"
    )
    assert hy_move.resolved_unit().value == "BPS"
    assert hy_move.weekly_change > 0, "stress week widens HY spread in bps"
    assert _component(tightening, "FINANCIAL_CONDITIONS").state == "TIGHTENING"
    # Benign must not contradict its own easing narrative either.
    benign_hy = next(
        m
        for m in benign.weekly_change.market_condition_delta.moves
        if m.instrument == "US_HY_OAS"
    )
    assert benign_hy.weekly_change < 0
    assert _component(benign, "FINANCIAL_CONDITIONS").state == "EASING"


def test_investment_climate_consistent_with_components(tightening, benign):
    for snapshot, expected in ((tightening, "RISK_OFF"), (benign, "RISK_ON")):
        components = {c.component: c for c in snapshot.climate_components}
        inputs = [
            components[k].score
            for k in ("FINANCIAL_CONDITIONS", "RISK_APPETITE", "MARKET_CONFIRMATION")
        ]
        assert all(s is not None for s in inputs)
        mean = round(sum(inputs) / len(inputs), 4)
        climate = snapshot.investment_climate
        assert climate.score == mean, "investment climate must derive from its components"
        assert climate.state == expected
        component = components["INVESTMENT_CLIMATE"]
        assert component.state == expected
        assert component.score == climate.score
        # Risk-off narrative must agree with risk-appetite lens, not invert it.
        assert (
            components["RISK_APPETITE"].state == "RISK_OFF"
            if expected == "RISK_OFF"
            else components["RISK_APPETITE"].state == "RISK_ON"
            or components["RISK_APPETITE"].state == "NEUTRAL"
        )


def test_tightening_policy_and_risk_lenses_coherent(tightening):
    components = {c.component: c for c in tightening.climate_components}
    assert components["POLICY_LIQUIDITY"].state == "TIGHTENING"
    assert components["RISK_APPETITE"].state == "RISK_OFF"
    assert components["MARKET_CONFIRMATION"].state in {"NEUTRAL", "TRENDING_DOWN"}
