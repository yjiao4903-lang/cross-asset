from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from cross_asset.decision_support.binding import (
    FactorBinding,
    FactorBindingRegistry,
    FactorTransform,
    LaneBinding,
)
from cross_asset.decision_support.enums import (
    AxisDirection,
    HorizonClass,
    InflationState,
    QuadrantLabel,
    ReleaseEventType,
)
from cross_asset.decision_support.horizon import HorizonAggregate
from cross_asset.decision_support.producer import (
    MonitoringObservation,
    MonitoringObservationPack,
    MonitoringRunLineage,
    MonitoringSeries,
    _build_regime,
    build_monitoring_snapshot,
)
from cross_asset.decision_support.regime import RegimeEngine
from cross_asset.decision_support.taxonomy import load_taxonomy
from cross_asset.decision_support.weekly import ReleaseEvent


def _aggregates(growth: float, inflation: float):
    return {
        ("GROWTH_ACTIVITY", HorizonClass.CYCLICAL): HorizonAggregate(
            horizon=HorizonClass.CYCLICAL,
            score=growth,
            confidence=1.0,
            coverage=1.0,
            contributors=["US_PAYROLLS_TREND"],
        ),
        ("INFLATION_COST", HorizonClass.CYCLICAL): HorizonAggregate(
            horizon=HorizonClass.CYCLICAL,
            score=inflation,
            confidence=1.0,
            coverage=1.0,
            contributors=["US_CORE_CPI_TREND"],
        ),
    }


def _persisted(history):
    return SimpleNamespace(
        details={"regime_input_history": history},
        metadata=SimpleNamespace(as_of=date(2026, 9, 7)),
    )


def _step(week_id: str, growth: float, inflation: float, previous=None):
    return _build_regime(
        _aggregates(growth, inflation),
        previous,
        load_taxonomy(),
        economic_week_id=week_id,
    )


def test_continuous_in_memory_sequence_equals_restart_persisted_history_replay():
    taxonomy = load_taxonomy()
    engine = RegimeEngine(
        axis_threshold=taxonomy.regime.axis_threshold,
        min_dwell_weeks=taxonomy.regime.min_dwell_weeks,
        lens_disagreement_threshold=taxonomy.regime.lens_disagreement_threshold,
    )
    continuous = None
    for growth, inflation in [(1.0, -1.0), (1.0, 1.0), (1.0, 1.0), (1.0, 1.0)]:
        continuous = engine.update(
            growth_score=growth,
            growth_direction=AxisDirection.FLAT,
            inflation_score=inflation,
            inflation_direction=AxisDirection.FLAT,
            inflation_state=InflationState.HIGH if inflation > 0 else InflationState.LOW,
            prior=continuous,
            confidence=1.0,
            coverage=1.0,
        )

    previous = None
    history = None
    for week_id, growth, inflation in [
        ("2026-08-24", 1.0, -1.0),
        ("2026-08-31", 1.0, 1.0),
        ("2026-09-07", 1.0, 1.0),
        ("2026-09-14", 1.0, 1.0),
    ]:
        replayed, history = _step(week_id, growth, inflation, previous)
        previous = _persisted(history)

    assert continuous is not None
    assert replayed.model_dump() == continuous.model_dump()


def test_three_retries_in_same_economic_week_do_not_satisfy_min_dwell_three():
    baseline, history = _step("2026-08-31", 1.0, -1.0)
    assert baseline.resolved_quadrant() is QuadrantLabel.GOLDILOCKS
    previous = _persisted(history)

    for _ in range(3):
        state, history = _step("2026-09-07", 1.0, 1.0, previous)
        previous = _persisted(history)
        assert state.resolved_quadrant() is QuadrantLabel.GOLDILOCKS
        assert state.transition_flag is False
        assert [item["economic_week_id"] for item in history] == [
            "2026-08-31",
            "2026-09-07",
        ]


def test_three_distinct_candidate_weeks_trigger_dwell_transition_normally():
    _, history = _step("2026-08-24", 1.0, -1.0)
    previous = _persisted(history)

    states = []
    for week_id in ["2026-08-31", "2026-09-07", "2026-09-14"]:
        state, history = _step(week_id, 1.0, 1.0, previous)
        states.append(state)
        previous = _persisted(history)

    assert states[0].resolved_quadrant() is QuadrantLabel.GOLDILOCKS
    assert states[1].resolved_quadrant() is QuadrantLabel.GOLDILOCKS
    assert states[2].resolved_quadrant() is QuadrantLabel.REFLATION
    assert states[2].transition_flag is True
    assert states[2].dwell_weeks == 1


def _registry() -> FactorBindingRegistry:
    blocked = LaneBinding(route="SANCTIONED_FORMAL_QUERY", status="BLOCKED")
    monitoring = LaneBinding(route="TEST_ONLY_MONITORING", status="BOUND")
    return FactorBindingRegistry(
        version=999,
        contract="TEST_ONLY_F04",
        bindings=[
            FactorBinding(
                factor_id="US_PAYROLLS_TREND",
                canonical_series_ids=["TEST_PAYROLL"],
                transform=FactorTransform(
                    type="PAYROLL_3M6M_SMOOTHED_MOMENTUM",
                    min_history=12,
                ),
                monitoring=monitoring,
                formal=blocked,
            ),
            FactorBinding(
                factor_id="US_CORE_CPI_TREND",
                canonical_series_ids=["TEST_CORE_CPI"],
                transform=FactorTransform(
                    type="CORE_CPI_3M6M_ANNUALIZED_TREND",
                    min_history=12,
                ),
                monitoring=monitoring,
                formal=blocked,
            ),
        ],
    )


def _series(series_id: str, values: list[float], decision_time: datetime) -> MonitoringSeries:
    dates = pd.date_range(end=date(2026, 9, 1), periods=len(values), freq="MS")
    return MonitoringSeries(
        series_id=series_id,
        observations=[
            MonitoringObservation(
                observation_date=stamp.date(),
                available_at=decision_time - timedelta(hours=1),
                value=float(value),
                source_ref=f"test:{series_id}",
            )
            for stamp, value in zip(dates, values, strict=True)
        ],
    )


def _pack(
    *,
    run_id: str,
    decision_time: datetime,
    data_cutoff: date,
    release_events: list[ReleaseEvent] | None = None,
) -> MonitoringObservationPack:
    payroll = [130000 + i * 175 + (i % 4) * 25 for i in range(40)]
    core_cpi = [250 + i * 0.55 + (i % 5) * 0.07 for i in range(40)]
    return MonitoringObservationPack(
        as_of=data_cutoff,
        lineage=MonitoringRunLineage(
            run_id=run_id,
            decision_time=decision_time,
            data_cutoff=data_cutoff,
            source_mode="LIVE",
            config_identity="f04-test",
        ),
        series=[
            _series("TEST_PAYROLL", payroll, decision_time),
            _series("TEST_CORE_CPI", core_cpi, decision_time),
        ],
        release_events=release_events or [],
    )


def test_same_week_replacement_preserves_weekly_information_semantics_without_new_macro_move():
    registry = _registry()
    first_decision = datetime(2026, 9, 8, 6, tzinfo=UTC)
    release = ReleaseEvent(
        factor_id="US_PAYROLLS_TREND",
        series_id="TEST_PAYROLL",
        event_type=ReleaseEventType.NEW_OBSERVATION,
        observation_date=date(2026, 9, 1),
    )
    first = build_monitoring_snapshot(
        _pack(
            run_id="week-retry-1",
            decision_time=first_decision,
            data_cutoff=date(2026, 9, 8),
            release_events=[release],
        ),
        registry=registry,
    )
    retry = build_monitoring_snapshot(
        _pack(
            run_id="week-retry-2",
            decision_time=first_decision + timedelta(days=1),
            data_cutoff=date(2026, 9, 9),
            release_events=[],
        ),
        previous_snapshot=first,
        registry=registry,
    )

    assert first.details["economic_week_id"] == retry.details["economic_week_id"]
    assert len(retry.details["regime_input_history"]) == 1
    assert retry.regime.dwell_weeks == first.regime.dwell_weeks == 1
    assert (
        retry.weekly_change.information_set_delta.model_dump()
        == first.weekly_change.information_set_delta.model_dump()
    )
    assert retry.weekly_change.information_set_delta.status.value == "UPDATED"
    assert (
        retry.weekly_change.macro_state_delta.model_dump()
        == first.weekly_change.macro_state_delta.model_dump()
    )


def test_future_previous_snapshot_is_rejected_fail_closed():
    registry = _registry()
    decision = datetime(2026, 9, 8, 6, tzinfo=UTC)
    future = build_monitoring_snapshot(
        _pack(
            run_id="future",
            decision_time=decision + timedelta(days=7),
            data_cutoff=date(2026, 9, 15),
        ),
        registry=registry,
    )

    with pytest.raises(ValueError, match="previous_snapshot_must_precede"):
        build_monitoring_snapshot(
            _pack(
                run_id="backfill",
                decision_time=decision,
                data_cutoff=date(2026, 9, 8),
            ),
            previous_snapshot=future,
            registry=registry,
        )
