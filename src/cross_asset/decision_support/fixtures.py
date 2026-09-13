"""Deterministic demo snapshots for Issue #114 Scope G.

Two self-contained scenarios built from fixed fixture data through the real
engine paths (horizon aggregation, weekly deltas, regime, asset gates):

- ``build_benign_snapshot``      — goldilocks-like cyclical environment with
  mixed tactical confirmation;
- ``build_tightening_snapshot``  — slowing/stagflation-risk environment with
  counter-signals.

Both include ``NO_NEW_INFORMATION`` semantics, one overdue/stale component,
stance changes and data-health badges, and are fully deterministic. All
fixtures run on the ``MONITORING`` lane; they can never be labelled
``FORMAL_OOS`` without explicit external evidence.
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

from .asset_rules import AssetGateResult, build_asset_gate
from .climate import (
    derive_climate_components,
    derive_investment_climate,
    derive_macro_climate,
)
from .enums import (
    AssetTarget,
    AxisDirection,
    DataHealthStatus,
    EvidenceLane,
    HorizonClass,
    InflationState,
    InformationSetStatus,
    MarketMetricClass,
)
from .horizon import (
    HorizonAggregate,
    SubfactorScore,
    aggregate_cluster_horizon,
    aggregate_context,
)
from .regime import RegimeEngine
from .snapshot import (
    AssetViewV0,
    ClusterView,
    CrossAssetPulse,
    DashboardSnapshotV0,
    DataHealthSummary,
    ExecutiveBrief,
    PulseEntry,
    SnapshotMetadata,
    WeeklyChange,
)
from .taxonomy import DecisionSupportConfig, load_taxonomy
from .weekly import (
    AssetStanceChange,
    AssetViewDelta,
    ReleaseEvent,
    build_information_set_delta,
    build_macro_state_delta,
    build_market_condition_delta,
    build_market_move,
)

MODEL_VERSION = "decision-support-v2-core-v0"
AS_OF = date(2026, 9, 4)
DECISION_TIME = datetime(2026, 9, 5, 6, 0, 0, tzinfo=UTC)

_INFLATION_HIGH = 0.4
_INFLATION_LOW = -0.4


def _score(factor_id: str, horizon: str, value: float, confidence: float = 0.9) -> SubfactorScore:
    return SubfactorScore(
        factor_id=factor_id,
        horizon=horizon,
        score=value,
        confidence=confidence,
        coverage=1.0,
    )


def _missing(factor_id: str, horizon: str, stale: bool = True) -> SubfactorScore:
    return SubfactorScore(
        factor_id=factor_id,
        horizon=horizon,
        score=None,
        confidence=0.0,
        coverage=0.0,
        missing=True,
        stale=stale,
    )


def _inflation_state(score: float | None) -> InflationState:
    if score is None:
        return InflationState.MODERATE
    if score >= _INFLATION_HIGH:
        return InflationState.HIGH
    if score <= _INFLATION_LOW:
        return InflationState.LOW
    return InflationState.MODERATE


def _direction(delta: float | None) -> AxisDirection:
    if delta is None or abs(delta) <= 0.05:
        return AxisDirection.FLAT
    return AxisDirection.RISING if delta > 0 else AxisDirection.FALLING


class _Week:
    """One weekly observation of scored subfactors plus market levels."""

    def __init__(
        self,
        as_of: date,
        scores: list[SubfactorScore],
        market_levels: dict[str, float],
        events: list[ReleaseEvent] | None = None,
    ) -> None:
        self.as_of = as_of
        self.scores = {s.factor_id: s for s in scores}
        self.market_levels = market_levels
        self.events = events or []


class _Scenario:
    def __init__(
        self,
        *,
        slug: str,
        weeks: list[_Week],
        market_spec: dict[str, tuple[str, list[float]]],
        pulse: list[PulseEntry],
        expected_releases: dict[str, date],
        changed_by_release: set[str],
        brief: ExecutiveBrief,
        climate_summaries: dict[str, str],
    ) -> None:
        self.slug = slug
        self.weeks = weeks
        self.market_spec = market_spec
        self.pulse = pulse
        self.expected_releases = expected_releases
        self.changed_by_release = changed_by_release
        self.brief = brief
        self.climate_summaries = climate_summaries


# --------------------------------------------------------------------------
# Benign / goldilocks-like scenario
# --------------------------------------------------------------------------

_BENIGN_CYCLICAL = {
    "US_PAYROLLS_TREND": [0.3, 0.6],
    "US_ISM_PMI": [0.3, 0.45],
    "CN_MFG_PMI": [0.2, None],  # overdue: no September release arrived
    "US_CORE_CPI_TREND": [-0.3, -0.3],
    "US_PPI_TREND": [-0.2, -0.2],
    "US_WAGE_PRESSURE": [0.1, 0.1],
    "FED_POLICY_STANCE": [0.7, 0.7],
    "US_YIELD_CURVE_10Y2Y": [0.3, 0.3],
    "CN_CREDIT_IMPULSE": [-0.4, -0.35],
    "CN_M1_M2_GAP": [-0.5, -0.45],
    "CN_NEW_LOANS_TREND": [-0.3, -0.3],
    "US_FIN_COND_TREND": [0.2, 0.4],
}
_BENIGN_TACTICAL = {
    "BREAKEVEN_5Y5Y": [0.1, 0.15],
    "CN_DR007": [-0.2, -0.25],
    "US_HY_SPREAD": [-0.1, 0.2],
    "US_10Y_REAL_YIELD": [-0.4, -0.35],
    "USD_BROAD_MOMENTUM": [-0.2, -0.3],
    "US_EQ_TREND_63D": [0.7, 0.9],
    "CN_EQ_TREND_63D": [0.2, 0.4],
    "CN_BOND_TREND_63D": [0.3, 0.25],
    "GOLD_TREND_63D": [0.4, 0.6],
    "COPPER_TREND_63D": [0.3, 0.6],
    "VIX_LEVEL": [-0.2, -0.4],
    "CFTC_RISK_POSITIONING": [0.1, 0.1],
}
_BENIGN_STRUCTURAL = {
    "US_EQ_ERP_PROXY": [-0.8, -0.8],
    "CN_EQ_VALUATION": [0.9, 1.1],
    "GOLD_REAL_RATE_OVERLAY": [-0.5, -0.5],
}
_BENIGN_MARKET_SPEC: dict[str, tuple[str, list[float]]] = {
    "SPX": (MarketMetricClass.PRICE.value, [6450.0, 6528.0]),
    "CSI300": (MarketMetricClass.PRICE.value, [4230.0, 4255.0]),
    "HSI": (MarketMetricClass.PRICE.value, [24800.0, 24998.0]),
    "GOLD": (MarketMetricClass.COMMODITY.value, [3480.0, 3532.0]),
    "COPPER": (MarketMetricClass.COMMODITY.value, [4.52, 4.61]),
    "USD_CNY": (MarketMetricClass.FX.value, [7.13, 7.11]),
    "US10Y": (MarketMetricClass.YIELD.value, [4.23, 4.27]),
    "CN10Y": (MarketMetricClass.YIELD.value, [1.78, 1.76]),
    "US_HY_OAS": (MarketMetricClass.SPREAD.value, [2.85, 2.77]),
    "VIX": (MarketMetricClass.VOLATILITY.value, [14.8, 14.0]),
}


def _benign_weeks(config: DecisionSupportConfig) -> list[_Week]:
    prior_as_of = date(2026, 8, 28)
    weeks: list[_Week] = []
    for week_index in range(2):
        as_of = prior_as_of if week_index == 0 else AS_OF
        scores: list[SubfactorScore] = []
        for spec in config.subfactors():
            series = (
                _BENIGN_CYCLICAL
                | _BENIGN_TACTICAL
                | _BENIGN_STRUCTURAL
            ).get(spec.factor_id)
            if series is None:
                continue
            value = series[week_index]
            if value is None:
                scores.append(_missing(spec.factor_id, HorizonClass(spec.horizon).value))
            else:
                scores.append(
                    _score(spec.factor_id, HorizonClass(spec.horizon).value, value, confidence=0.85)
                )
        events: list[ReleaseEvent] = []
        market_levels = {
            instrument: values[min(week_index, len(values) - 1)]
            for instrument, (_, values) in _BENIGN_MARKET_SPEC.items()
        }
        if week_index == 1:
            events = [
                ReleaseEvent(
                    factor_id="US_PAYROLLS_TREND",
                    series_id="FIXTURE_PAYEMS",
                    event_type="NEW_OBSERVATION",
                    observation_date=as_of,
                    note="fixture August payroll release",
                    surprise={"method": "TREND_RELATIVE", "value": 0.2, "baseline": "3m trend"},
                ),
                ReleaseEvent(
                    factor_id="US_ISM_PMI",
                    series_id="FIXTURE_ISM",
                    event_type="REVISION",
                    observation_date=date(2026, 8, 3),
                    note="fixture July ISM revision upward",
                ),
                ReleaseEvent(
                    factor_id="CN_CREDIT_IMPULSE",
                    series_id="FIXTURE_TSF",
                    event_type="NEW_OBSERVATION",
                    observation_date=date(2026, 9, 1),
                    note="fixture August aggregate financing",
                ),
                ReleaseEvent(
                    factor_id="CN_M1_M2_GAP",
                    series_id="FIXTURE_M1M2",
                    event_type="NEW_OBSERVATION",
                    observation_date=date(2026, 9, 1),
                    note="fixture August money supply",
                ),
                ReleaseEvent(
                    factor_id="US_FIN_COND_TREND",
                    series_id="FIXTURE_NFCI",
                    event_type="NEW_OBSERVATION",
                    observation_date=date(2026, 9, 4),
                    note="fixture weekly financial conditions update",
                ),
                ReleaseEvent(
                    factor_id="CN_MFG_PMI",
                    series_id="FIXTURE_CN_PMI",
                    event_type="OVERDUE",
                    observation_date=None,
                    note="expected 2026-08-31 release not arrived; stale, not zero",
                ),
            ]
        weeks.append(_Week(as_of=as_of, scores=scores, market_levels=market_levels, events=events))
    return weeks


_BENIGN_PULSE = [
    PulseEntry(asset=AssetTarget.US_EQ.value, ret_1w=1.21, ret_1m=2.4, ret_3m=5.1, momentum_label="IMPROVING"),
    PulseEntry(asset=AssetTarget.CN_EQ.value, ret_1w=0.59, ret_1m=1.2, ret_3m=-1.8, momentum_label="MIXED"),
    PulseEntry(asset=AssetTarget.HK_EQ.value, ret_1w=0.8, ret_1m=1.9, ret_3m=3.2, momentum_label="MIXED"),
    PulseEntry(asset=AssetTarget.CN_BOND.value, ret_1w=0.06, ret_1m=0.2, ret_3m=0.7, momentum_label="STABLE"),
    PulseEntry(asset=AssetTarget.GOLD.value, ret_1w=1.49, ret_1m=3.1, ret_3m=8.4, momentum_label="IMPROVING"),
    PulseEntry(asset=AssetTarget.COPPER.value, ret_1w=1.99, ret_1m=4.0, ret_3m=6.5, momentum_label="IMPROVING"),
    PulseEntry(asset=AssetTarget.USD_CNY.value, ret_1w=-0.28, ret_1m=-0.6, ret_3m=-1.1, momentum_label="CNY FIRMING"),
    PulseEntry(asset=AssetTarget.CASH.value, ret_1w=0.0, ret_1m=0.1, ret_3m=0.4, momentum_label="FLAT"),
]

_BENIGN_BRIEF = ExecutiveBrief(
    what_changed=(
        "US growth signals improved on the August payroll release and an upward ISM "
        "revision; China credit data ticked up but the China PMI release is overdue. "
        "Inflation series had no new information this week."
    ),
    why_it_matters=(
        "A goldilocks-leaning cyclical mix with easing financial conditions supports "
        "pro-cyclical asset views, but the improvement is not yet confirmed by China "
        "domestic data."
    ),
    what_to_watch=[
        "overdue China PMI release and whether it confirms the growth improvement",
        "whether US equity trend confirmation persists without stretch of valuation",
        "China credit impulse follow-through into new loans",
    ],
)


def _benign_scenario(config: DecisionSupportConfig) -> _Scenario:
    return _Scenario(
        slug="benign",
        weeks=_benign_weeks(config),
        market_spec=_BENIGN_MARKET_SPEC,
        pulse=_BENIGN_PULSE,
        expected_releases={"CN_MFG_PMI": date(2026, 8, 31)},
        changed_by_release={
            "US_PAYROLLS_TREND",
            "US_ISM_PMI",
            "CN_CREDIT_IMPULSE",
            "CN_M1_M2_GAP",
            "US_FIN_COND_TREND",
        },
        brief=_BENIGN_BRIEF,
        climate_summaries={
            "macro": "goldilocks-leaning: growth improving, inflation moderate and driftless this week",
            "investment": "risk-on tilt with mixed tactical confirmation; financial conditions easing",
        },
    )


# --------------------------------------------------------------------------
# Tightening / stagflation-risk scenario
# --------------------------------------------------------------------------

_TIGHTENING_CYCLICAL = {
    "US_PAYROLLS_TREND": [0.4, -0.3, -0.3, -0.4],
    "US_ISM_PMI": [0.3, -0.3, -0.3, None],  # overdue in the final week
    "US_CORE_CPI_TREND": [0.3, 0.4, 0.45, 0.6],
    "US_PPI_TREND": [0.2, 0.3, 0.35, 0.4],
    "US_WAGE_PRESSURE": [0.3, 0.35, 0.4, 0.4],
    "FED_POLICY_STANCE": [0.0, -0.2, -0.3, -0.4],
    "US_YIELD_CURVE_10Y2Y": [0.0, -0.1, -0.2, -0.2],
    "CN_CREDIT_IMPULSE": [-0.3, -0.4, -0.4, -0.5],
    "CN_M1_M2_GAP": [-0.3, -0.4, -0.5, -0.6],
    "CN_NEW_LOANS_TREND": [-0.2, -0.3, -0.3, -0.3],
    "US_FIN_COND_TREND": [0.0, -0.3, -0.4, -0.4],
}
_TIGHTENING_TACTICAL = {
    "BREAKEVEN_5Y5Y": [0.2, 0.3, 0.4, 0.5],
    "CN_DR007": [-0.1, 0.0, 0.1, 0.3],
    "US_HY_SPREAD": [-0.2, 0.2, 0.5, 0.8],
    "US_10Y_REAL_YIELD": [-0.3, -0.4, -0.5, -0.6],
    "USD_BROAD_MOMENTUM": [0.1, 0.3, 0.5, 0.7],
    "US_EQ_TREND_63D": [0.5, 0.2, -0.2, -0.5],
    "CN_EQ_TREND_63D": [0.3, 0.1, -0.1, -0.4],
    "CN_BOND_TREND_63D": [0.2, 0.2, 0.2, 0.2],
    "GOLD_TREND_63D": [0.1, 0.2, 0.2, 0.3],
    "COPPER_TREND_63D": [0.3, 0.1, -0.2, -0.6],
    "VIX_LEVEL": [-0.2, -0.5, -0.7, -0.9],
    "CFTC_RISK_POSITIONING": [0.1, 0.0, -0.2, -0.3],
}
_TIGHTENING_STRUCTURAL = {
    "US_EQ_ERP_PROXY": [-1.0, -1.1, -1.2, -1.2],
    "CN_EQ_VALUATION": [1.0, 1.1, 1.2, 1.2],
    "GOLD_REAL_RATE_OVERLAY": [None, None, None, None],  # overlay unavailable in this scenario
}
_TIGHTENING_MARKET_SPEC: dict[str, tuple[str, list[float]]] = {
    "SPX": (MarketMetricClass.PRICE.value, [6528.0, 6395.0]),
    "CSI300": (MarketMetricClass.PRICE.value, [4255.0, 4165.0]),
    "HSI": (MarketMetricClass.PRICE.value, [24998.0, 24450.0]),
    "GOLD": (MarketMetricClass.COMMODITY.value, [3532.0, 3560.0]),
    "COPPER": (MarketMetricClass.COMMODITY.value, [4.61, 4.49]),
    "USD_CNY": (MarketMetricClass.FX.value, [7.11, 7.16]),
    "US10Y": (MarketMetricClass.YIELD.value, [4.27, 4.36]),
    "CN10Y": (MarketMetricClass.YIELD.value, [1.76, 1.72]),
    "US_HY_OAS": (MarketMetricClass.SPREAD.value, [2.77, 2.98]),
    "VIX": (MarketMetricClass.VOLATILITY.value, [14.0, 17.2]),
}


def _tightening_weeks(config: DecisionSupportConfig) -> list[_Week]:
    week_ends = [date(2026, 8, 14), date(2026, 8, 21), date(2026, 8, 28), AS_OF]
    all_series = _TIGHTENING_CYCLICAL | _TIGHTENING_TACTICAL | _TIGHTENING_STRUCTURAL
    weeks: list[_Week] = []
    for week_index, as_of in enumerate(week_ends):
        scores: list[SubfactorScore] = []
        for spec in config.subfactors():
            series = all_series.get(spec.factor_id)
            if series is None:
                continue
            value = series[week_index]
            if value is None:
                scores.append(_missing(spec.factor_id, HorizonClass(spec.horizon).value))
            else:
                scores.append(
                    _score(spec.factor_id, HorizonClass(spec.horizon).value, value, confidence=0.85)
                )
        events: list[ReleaseEvent] = []
        market_levels = {
            instrument: values[min(week_index, len(values) - 1)]
            for instrument, (_, values) in _TIGHTENING_MARKET_SPEC.items()
        }
        if week_index == 3:
            events = [
                ReleaseEvent(
                    factor_id="US_CORE_CPI_TREND",
                    series_id="FIXTURE_CPILFESL",
                    event_type="NEW_OBSERVATION",
                    observation_date=as_of,
                    note="fixture August core CPI re-acceleration",
                    surprise={"method": "TREND_RELATIVE", "value": 0.4, "baseline": "6m trend"},
                ),
                ReleaseEvent(
                    factor_id="US_PAYROLLS_TREND",
                    series_id="FIXTURE_PAYEMS",
                    event_type="REVISION",
                    observation_date=as_of,
                    note="fixture payroll benchmark revision downward",
                ),
                ReleaseEvent(
                    factor_id="US_PPI_TREND",
                    series_id="FIXTURE_PPI",
                    event_type="NEW_OBSERVATION",
                    observation_date=as_of,
                    note="fixture August PPI",
                ),
                ReleaseEvent(
                    factor_id="CN_CREDIT_IMPULSE",
                    series_id="FIXTURE_TSF",
                    event_type="NEW_OBSERVATION",
                    observation_date=date(2026, 9, 1),
                    note="fixture August aggregate financing, softer",
                ),
                ReleaseEvent(
                    factor_id="CN_M1_M2_GAP",
                    series_id="FIXTURE_M1M2",
                    event_type="NEW_OBSERVATION",
                    observation_date=date(2026, 9, 1),
                    note="fixture August money supply, weaker activation",
                ),
                ReleaseEvent(
                    factor_id="FED_POLICY_STANCE",
                    series_id="FIXTURE_FOMC",
                    event_type="NEW_OBSERVATION",
                    observation_date=date(2026, 9, 2),
                    note="fixture FOMC decision: hawkish hold",
                ),
                ReleaseEvent(
                    factor_id="US_ISM_PMI",
                    series_id="FIXTURE_ISM",
                    event_type="OVERDUE",
                    observation_date=None,
                    note="expected 2026-09-01 release not arrived; stale, not zero",
                ),
            ]
        weeks.append(_Week(as_of=as_of, scores=scores, market_levels=market_levels, events=events))
    return weeks


_TIGHTENING_PULSE = [
    PulseEntry(asset=AssetTarget.US_EQ.value, ret_1w=-2.04, ret_1m=-3.8, ret_3m=1.2, momentum_label="DETERIORATING"),
    PulseEntry(asset=AssetTarget.CN_EQ.value, ret_1w=-2.11, ret_1m=-2.9, ret_3m=-4.5, momentum_label="DETERIORATING"),
    PulseEntry(asset=AssetTarget.HK_EQ.value, ret_1w=-2.19, ret_1m=-3.3, ret_3m=-2.1, momentum_label="DETERIORATING"),
    PulseEntry(asset=AssetTarget.CN_BOND.value, ret_1w=0.11, ret_1m=0.3, ret_3m=0.9, momentum_label="STABLE"),
    PulseEntry(asset=AssetTarget.GOLD.value, ret_1w=0.79, ret_1m=2.2, ret_3m=7.0, momentum_label="RESILIENT"),
    PulseEntry(asset=AssetTarget.COPPER.value, ret_1w=-2.6, ret_1m=-4.8, ret_3m=-3.2, momentum_label="DETERIORATING"),
    PulseEntry(asset=AssetTarget.USD_CNY.value, ret_1w=0.7, ret_1m=1.4, ret_3m=2.3, momentum_label="USD FIRMING"),
    PulseEntry(asset=AssetTarget.CASH.value, ret_1w=0.0, ret_1m=0.1, ret_3m=0.4, momentum_label="DEFENSIVE"),
]

_TIGHTENING_BRIEF = ExecutiveBrief(
    what_changed=(
        "Core CPI re-accelerated on the August release while payroll revisions cut the "
        "growth picture; credit spreads widened and volatility jumped. The ISM release "
        "is overdue and the gold real-rate overlay is unavailable."
    ),
    why_it_matters=(
        "Growth deteriorating with inflation rising is a stagflation-risk mix: it "
        "caps pro-cyclical conviction, favors defensive stances and puts a premium on "
        "invalidator discipline rather than trend chasing."
    ),
    what_to_watch=[
        "overdue ISM release: confirmation or pushback on the growth deterioration",
        "whether HY spread widening persists beyond +20bps/week",
        "core CPI trend: two more accelerating prints would harden the stagflation quadrant",
    ],
)


def _tightening_scenario(config: DecisionSupportConfig) -> _Scenario:
    return _Scenario(
        slug="tightening",
        weeks=_tightening_weeks(config),
        market_spec=_TIGHTENING_MARKET_SPEC,
        pulse=_TIGHTENING_PULSE,
        expected_releases={"US_ISM_PMI": date(2026, 9, 1)},
        changed_by_release={
            "US_PAYROLLS_TREND",
            "US_CORE_CPI_TREND",
            "US_PPI_TREND",
            "FED_POLICY_STANCE",
            "CN_CREDIT_IMPULSE",
            "CN_M1_M2_GAP",
        },
        brief=_TIGHTENING_BRIEF,
        climate_summaries={
            "macro": "stagflation-risk: growth deteriorating while inflation re-accelerates",
            "investment": "risk-off tilt; financial conditions tightening, volatility elevated",
        },
    )


# --------------------------------------------------------------------------
# Snapshot assembly
# --------------------------------------------------------------------------


def _family_aggregates(
    week: _Week,
    config: DecisionSupportConfig,
) -> dict[tuple[str, HorizonClass], HorizonAggregate]:
    aggregates: dict[tuple[str, HorizonClass], HorizonAggregate] = {}
    for family in config.families:
        by_horizon: dict[HorizonClass, list[SubfactorScore]] = {}
        for spec in family.subfactors:
            score = week.scores.get(spec.factor_id)
            if score is None:
                score = _missing(spec.factor_id, HorizonClass(spec.horizon).value)
            by_horizon.setdefault(spec.resolved_horizon(), []).append(score)
        for horizon, scores in by_horizon.items():
            if horizon is HorizonClass.STRUCTURAL_CONTEXT:
                aggregates[(family.family_id, horizon)] = aggregate_context(scores)
            else:
                aggregates[(family.family_id, horizon)] = aggregate_cluster_horizon(
                    scores, horizon=horizon
                )
    return aggregates


def _cluster_views(
    current: dict[tuple[str, HorizonClass], HorizonAggregate],
    previous: dict[tuple[str, HorizonClass], HorizonAggregate],
) -> list[ClusterView]:
    views: list[ClusterView] = []
    for (family, horizon), aggregate in sorted(current.items()):
        prev = previous.get((family, horizon))
        delta = (
            round(aggregate.score - prev.score, 4)
            if aggregate.score is not None and prev is not None and prev.score is not None
            else None
        )
        views.append(
            ClusterView(
                cluster_id=f"{family}@{horizon.value}",
                family=family,
                horizon=horizon,
                score=aggregate.score,
                weekly_delta=delta,
                direction=_direction(delta),
                confidence=aggregate.confidence,
                coverage=aggregate.coverage,
                top_positive=[],
                top_negative=[],
                missing_factors=aggregate.missing,
                stale_factors=aggregate.stale,
                freshness_status=(
                    DataHealthStatus.PARTIAL
                    if aggregate.missing or aggregate.stale
                    else DataHealthStatus.OK
                ),
            )
        )
    return views


def _asset_gates(
    week: _Week,
    aggregates: Mapping[tuple[str, HorizonClass], HorizonAggregate],
    config: DecisionSupportConfig,
) -> dict[str, AssetGateResult]:
    cyclical_scores = {
        family: aggregate.score
        for (family, horizon), aggregate in aggregates.items()
        if horizon is HorizonClass.CYCLICAL
    }
    tactical = {
        factor_id: score.effective_score()
        for factor_id, score in week.scores.items()
        if score.resolved_horizon() is HorizonClass.TACTICAL and not score.missing
    }
    structural = {
        factor_id: score.effective_score()
        for factor_id, score in week.scores.items()
        if score.resolved_horizon() is HorizonClass.STRUCTURAL_CONTEXT and not score.missing
    }
    return {
        rule.asset: build_asset_gate(
            rule,
            cyclical_scores=cyclical_scores,
            tactical_scores=tactical,
            structural_scores=structural,
        )
        for rule in config.asset_rules
    }


def _asset_views(
    gates: Mapping[str, AssetGateResult],
    prior_gates: Mapping[str, AssetGateResult],
    config: DecisionSupportConfig,
) -> list[AssetViewV0]:
    views: list[AssetViewV0] = []
    for rule in config.asset_rules:
        gate = gates[rule.asset]
        prior = prior_gates[rule.asset]
        views.append(
            AssetViewV0(
                asset=gate.asset,
                macro_bias=gate.macro_bias,
                market_confirmation=gate.market_confirmation.value,
                valuation_tag=gate.valuation_tag,
                stance=gate.stance,
                prior_stance=prior.stance,
                confidence=gate.confidence,
                drivers=gate.drivers,
                counter_signals=gate.counter_signals,
                invalidator=rule.invalidator,
                data_health=gate.data_health.value,
            )
        )
    return views


def _asset_view_delta(
    gates: Mapping[str, AssetGateResult],
    prior_gates: Mapping[str, AssetGateResult],
    macro_delta_factors: list[str],
    config: DecisionSupportConfig,
) -> AssetViewDelta:
    factor_to_family = {
        sub.factor_id: sub.family for sub in config.subfactors()
    }
    updated_families = sorted(
        {factor_to_family[factor_id] for factor_id in macro_delta_factors}
    )
    entries: list[AssetStanceChange] = []
    for rule in config.asset_rules:
        gate = gates[rule.asset]
        prior = prior_gates[rule.asset]
        delta = gate.stance - prior.stance
        confidence_delta = round(gate.confidence - prior.confidence, 4)
        if delta == 0 and abs(confidence_delta) < 0.01:
            continue
        tags: list[str] = []
        if delta > 0:
            tags.append("STANCE_UP")
        elif delta < 0:
            tags.append("STANCE_DOWN")
        tags.extend(f"{family}_UPDATED" for family in updated_families)
        tags.append(f"MARKET_{gate.market_confirmation.value}")
        entries.append(
            AssetStanceChange(
                asset=gate.asset,
                previous_stance=prior.stance,
                current_stance=gate.stance,
                delta=delta,
                reason_tags=tags,
                confidence_delta=confidence_delta,
            )
        )
    return AssetViewDelta(entries=entries)


def _market_condition_delta(scenario: _Scenario, config: DecisionSupportConfig):
    moves = []
    for instrument, (metric_class, values) in scenario.market_spec.items():
        prior, current = values[-2], values[-1]
        moves.append(
            build_market_move(
                instrument,
                metric_class,
                prior,
                current,
                volatility_style=config.market_delta.volatility_style,
            )
        )
    return build_market_condition_delta(moves)


def _build_snapshot(
    scenario: _Scenario,
    config: DecisionSupportConfig,
    *,
    lane: EvidenceLane | str = EvidenceLane.MONITORING,
) -> DashboardSnapshotV0:
    resolved_lane = EvidenceLane(lane)
    if resolved_lane is EvidenceLane.FORMAL_OOS:
        raise ValueError(
            "FIXTURE_MONITORING_ONLY: synthetic/demo fixture builders can never "
            "emit FORMAL_OOS; formal snapshots only come from the future "
            "sanctioned production path (no evidence-string escape exists)"
        )
    current_week = scenario.weeks[-1]
    prior_week = scenario.weeks[-2]
    current_aggregates = _family_aggregates(current_week, config)
    prior_aggregates = _family_aggregates(prior_week, config)

    clusters = _cluster_views(current_aggregates, prior_aggregates)

    # --- regime over the full weekly sequence (hysteresis is sequential) ---
    engine = RegimeEngine(
        axis_threshold=config.regime.axis_threshold,
        min_dwell_weeks=config.regime.min_dwell_weeks,
        lens_disagreement_threshold=config.regime.lens_disagreement_threshold,
    )
    regime_state = None
    prior_growth_score: float | None = None
    prior_inflation_score: float | None = None
    for week in scenario.weeks:
        aggregates = _family_aggregates(week, config)
        growth = aggregates[("GROWTH_ACTIVITY", HorizonClass.CYCLICAL)]
        inflation = aggregates[("INFLATION_COST", HorizonClass.CYCLICAL)]
        growth_delta = (
            None
            if prior_growth_score is None or growth.score is None
            else round(growth.score - prior_growth_score, 4)
        )
        inflation_delta = (
            None
            if prior_inflation_score is None or inflation.score is None
            else round(inflation.score - prior_inflation_score, 4)
        )
        regime_state = engine.update(
            growth_score=growth.score,
            growth_direction=_direction(growth_delta),
            inflation_score=inflation.score,
            inflation_direction=_direction(inflation_delta),
            inflation_state=_inflation_state(inflation.score),
            prior=regime_state,
            confidence=round(min(growth.confidence, inflation.confidence), 4),
            coverage=round(min(growth.coverage, inflation.coverage), 4),
        )
        prior_growth_score = growth.score
        prior_inflation_score = inflation.score
    assert regime_state is not None

    growth_current = current_aggregates[("GROWTH_ACTIVITY", HorizonClass.CYCLICAL)]
    inflation_current = current_aggregates[("INFLATION_COST", HorizonClass.CYCLICAL)]
    growth_prior = prior_aggregates[("GROWTH_ACTIVITY", HorizonClass.CYCLICAL)]
    inflation_prior = prior_aggregates[("INFLATION_COST", HorizonClass.CYCLICAL)]
    growth_delta = (
        round(growth_current.score - growth_prior.score, 4)
        if growth_current.score is not None and growth_prior.score is not None
        else None
    )
    inflation_delta = (
        round(inflation_current.score - inflation_prior.score, 4)
        if inflation_current.score is not None and inflation_prior.score is not None
        else None
    )
    macro_climate = derive_macro_climate(
        growth_current,
        inflation_current,
        growth_weekly_delta=growth_delta,
        inflation_weekly_delta=inflation_delta,
        summary=scenario.climate_summaries["macro"],
    )
    investment_climate = derive_investment_climate(
        current_aggregates[("FINANCIAL_CONDITIONS", HorizonClass.TACTICAL)],
        current_aggregates[("RISK_APPETITE", HorizonClass.TACTICAL)],
        current_aggregates[("MARKET_CONFIRMATION", HorizonClass.TACTICAL)],
        weekly_delta=None,
        summary=scenario.climate_summaries["investment"],
    )

    # --- weekly change surfaces ---
    info_delta = build_information_set_delta(
        current_week.events,
        expected_releases=scenario.expected_releases,
        as_of=current_week.as_of,
    )
    cyclical_ids = [
        spec.factor_id
        for spec in config.subfactors()
        if spec.resolved_horizon() is HorizonClass.CYCLICAL
    ]
    previous_scores = {
        fid: prior_week.scores[fid].effective_score()
        for fid in cyclical_ids
        if fid in prior_week.scores and not prior_week.scores[fid].missing
    }
    current_scores = {
        fid: current_week.scores[fid].effective_score()
        for fid in cyclical_ids
        if fid in current_week.scores and not current_week.scores[fid].missing
    }
    macro_delta = build_macro_state_delta(
        previous_scores,
        current_scores,
        information_status=info_delta.resolved_status(),
        changed_by_release=scenario.changed_by_release,
    )
    market_delta = _market_condition_delta(scenario, config)

    gates = _asset_gates(current_week, current_aggregates, config)
    prior_gates = _asset_gates(prior_week, prior_aggregates, config)
    views = _asset_views(gates, prior_gates, config)
    view_delta = _asset_view_delta(
        gates,
        prior_gates,
        macro_delta.changed_factors(),
        config,
    )

    data_health = _data_health_summary(clusters, info_delta, gates)

    details = _details(
        scenario,
        config,
        current_week,
        info_delta,
        gates,
    )

    return DashboardSnapshotV0(
        metadata=SnapshotMetadata(
            snapshot_id=f"dsv0-monitoring-{scenario.slug}-{AS_OF.isoformat().replace('-', '')}",
            as_of=AS_OF,
            decision_time=DECISION_TIME,
            lane=resolved_lane.value,
            run_id=f"fixture-run-{scenario.slug}-{AS_OF.isoformat().replace('-', '')}",
            model_version=MODEL_VERSION,
        ),
        macro_climate=macro_climate,
        investment_climate=investment_climate,
        climate_components=derive_climate_components(
            current_aggregates,
            prior_aggregates,
            investment_climate,
        ),
        clusters=clusters,
        weekly_change=WeeklyChange(
            information_set_delta=info_delta,
            macro_state_delta=macro_delta,
            market_condition_delta=market_delta,
            asset_view_delta=view_delta,
        ),
        regime=regime_state,
        asset_views=views,
        cross_asset_pulse=CrossAssetPulse(
            entries=scenario.pulse,
            summary=scenario.climate_summaries["investment"],
        ),
        executive_brief=scenario.brief,
        data_health_summary=data_health,
        details=details,
    )


def _data_health_summary(
    clusters: list[ClusterView],
    info_delta: Any,
    gates: Mapping[str, AssetGateResult],
) -> DataHealthSummary:
    stale: set[str] = set()
    missing: set[str] = set()
    blockers: list[str] = []
    for cluster in clusters:
        stale.update(cluster.stale_factors)
        missing.update(cluster.missing_factors)
    stale.update(info_delta.stale_factors)
    for rule_asset, gate in sorted(gates.items()):
        for blocker in gate.blockers:
            blockers.append(f"{rule_asset}: {blocker.source} — {blocker.reason}")
    overall = (
        DataHealthStatus.PARTIAL if stale or missing or blockers else DataHealthStatus.OK
    )
    return DataHealthSummary(
        overall=overall,
        stale_components=sorted(stale),
        missing_components=sorted(missing),
        blockers=blockers,
    )


def _details(
    scenario: _Scenario,
    config: DecisionSupportConfig,
    current_week: _Week,
    info_delta: Any,
    gates: Mapping[str, AssetGateResult],
) -> dict[str, Any]:
    factor_to_family = {sub.factor_id: sub.family for sub in config.subfactors()}
    changed = {
        factor_id: factor_to_family.get(factor_id, "UNKNOWN")
        for factor_id in scenario.changed_by_release
    }
    family_status: dict[str, str] = {}
    for family in config.families:
        family_factors = {sub.factor_id for sub in family.subfactors}
        if family_factors & set(changed):
            family_status[family.family_id] = InformationSetStatus.UPDATED.value
        elif family_factors & set(info_delta.stale_factors):
            family_status[family.family_id] = InformationSetStatus.OVERDUE_STALE.value
        else:
            family_status[family.family_id] = (
                InformationSetStatus.NO_NEW_INFORMATION.value
            )
    return {
        "lineage_note": "fixture lineage; real source binding comes later",
        "taxonomy_version": config.version,
        "parameter_status": config.parameter_status,
        "family_information_status": family_status,
        "released_factors": sorted(changed),
        "subfactor_scores_current": {
            factor_id: (None if score.missing else score.score)
            for factor_id, score in sorted(current_week.scores.items())
        },
        "gate_blockers": {
            asset: [
                {"source": blocker.source, "reason": blocker.reason}
                for blocker in gate.blockers
            ]
            for asset, gate in sorted(gates.items())
            if gate.blockers
        },
    }


def build_benign_snapshot(
    config_path: str | None = None,
    **kwargs: Any,
) -> DashboardSnapshotV0:
    config = load_taxonomy(config_path) if config_path else load_taxonomy()
    return _build_snapshot(_benign_scenario(config), config, **kwargs)


def build_tightening_snapshot(
    config_path: str | None = None,
    **kwargs: Any,
) -> DashboardSnapshotV0:
    config = load_taxonomy(config_path) if config_path else load_taxonomy()
    return _build_snapshot(_tightening_scenario(config), config, **kwargs)
