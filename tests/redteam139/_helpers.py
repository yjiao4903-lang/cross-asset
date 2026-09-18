"""Deterministic, offline helpers for the #139 adversarial closure suite.

Everything here runs on task-scoped scratch state (in-memory DuckDB, temp
snapshot dirs) built strictly through accepted code paths. No Wind, no network,
no proprietary local files. Synthetic observations are TEST-ONLY mechanics
inputs and are never described as real market evidence.

Seeds derive from the #138 evidence matrix; every case is re-derived against
current main rather than copied blindly (#139 Phase 0 rule).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from cross_asset.decision_support.binding import (
    FactorBinding,
    FactorBindingRegistry,
    FactorTransform,
    LaneBinding,
)
from cross_asset.decision_support.producer import (
    MonitoringMarketMove,
    MonitoringObservation,
    MonitoringObservationPack,
    MonitoringRunLineage,
    MonitoringSeries,
)
from cross_asset.operations.workbench_run import WorkbenchRun
from cross_asset.storage.catalog import sync_series_catalog
from cross_asset.storage.duckdb import DuckDBStore

# Economic calendar used across the multi-week closure scenarios.
WEEK1_CUTOFF = date(2026, 9, 4)
WEEK1_DECISION = datetime(2026, 9, 5, 6, tzinfo=UTC)
WEEK2_CUTOFF = date(2026, 9, 11)
WEEK2_DECISION = datetime(2026, 9, 12, 6, tzinfo=UTC)
WEEK3_CUTOFF = date(2026, 9, 18)
WEEK3_DECISION = datetime(2026, 9, 19, 6, tzinfo=UTC)

BLOCKED_LANE = LaneBinding(route="SANCTIONED_FORMAL_QUERY", status="BLOCKED")
MONITORING_LANE = LaneBinding(route="TEST_ONLY_MONITORING", status="BOUND")


def mechanics_registry() -> FactorBindingRegistry:
    """TEST-ONLY registry for producer mechanics (never enters repo config)."""

    return FactorBindingRegistry(
        version=999,
        contract="TEST_ONLY_ADVERSARIAL_MECHANICS",
        bindings=[
            FactorBinding(
                factor_id="US_PAYROLLS_TREND",
                canonical_series_ids=["T_PAYROLL"],
                transform=FactorTransform(
                    type="PAYROLL_3M6M_SMOOTHED_MOMENTUM", min_history=12
                ),
                monitoring=MONITORING_LANE,
                formal=BLOCKED_LANE,
            ),
            FactorBinding(
                factor_id="US_CORE_CPI_TREND",
                canonical_series_ids=["T_CPI"],
                transform=FactorTransform(
                    type="CORE_CPI_3M6M_ANNUALIZED_TREND", min_history=12
                ),
                monitoring=MONITORING_LANE,
                formal=BLOCKED_LANE,
            ),
            FactorBinding(
                factor_id="US_EQ_TREND_63D",
                canonical_series_ids=["T_US_EQ"],
                transform=FactorTransform(type="TREND_63D"),
                monitoring=MONITORING_LANE,
                formal=BLOCKED_LANE,
            ),
        ],
    )


def payroll_values(months: int) -> list[float]:
    return [145000 + i * 145 + (i % 5) * 18 + (i // 12) * 23 for i in range(months)]


def cpi_values(months: int) -> list[float]:
    cpi = [270.0]
    rates = [0.0018, 0.0022, 0.0027, 0.0031, 0.0025, 0.0020]
    for index in range(1, months):
        cpi.append(cpi[-1] * (1.0 + rates[index % 6]))
    return cpi


def month_rows(
    series_id: str,
    source_series_id: str,
    values,
    *,
    capture_time: datetime,
    source: str = "fred",
    end: date = date(2026, 9, 1),
) -> list[dict]:
    months = pd.date_range(end=end, periods=len(values), freq="MS")
    return [
        {
            "series_id": series_id,
            "observation_date": stamp.date(),
            "available_at": capture_time,
            "value": float(value),
            "source": source,
            "source_series_id": source_series_id,
            "ingested_at": capture_time,
            "quality": "ok",
        }
        for stamp, value in zip(months, values, strict=True)
    ]


def write_monitoring_run(store, rows, *, run_id, requested=None):
    """Persist rows under one MONITORING:fred ingestion run (accepted path)."""

    store.start_run("MONITORING:fred", run_id, requested_series=requested or 1)
    store.insert_observations(rows, run_id=run_id)
    store.finish_run(run_id, "success", success_series=requested or 1, failed_series=0)
    return run_id


def workbench_run(
    run_id: str,
    *,
    decision_time: datetime = WEEK2_DECISION,
    data_cutoff: date = WEEK2_CUTOFF,
    source_mode: str = "LIVE",
) -> WorkbenchRun:
    return WorkbenchRun(
        run_id=run_id,
        run_kind="shadow",
        source_mode=source_mode,
        status="SUCCESS",
        model_version="workbench_v0.1",
        config_identity="decision-support-v2:adversarial-test-only",
        data_cutoff=data_cutoff.isoformat(),
        decision_time=decision_time.isoformat(),
    )


def governed_store(series_ids=("US_NONFARM_PAYROLLS", "US_CORE_CPI"), provider="fred"):
    """Scratch monitoring store seeded with accepted canonical mappings."""

    store = DuckDBStore(":memory:")
    sync_series_catalog(store, series_ids=list(series_ids), provider=provider)
    return store


def capture_pack(store, *, cutoff: date, decision: datetime, capture: datetime, run_id: str,
                 cpi_end: date | None = None, extra_rows=None):
    """Insert a monitoring capture and build the pack through the DB adapter."""

    end_month = cpi_end if cpi_end is not None else date(cutoff.year, cutoff.month, 1)
    months = len(pd.date_range(end=date(2025, 8, 1), periods=60, freq="MS"))
    _ = months
    n = 48 if end_month.month == 8 else 49
    rows = month_rows("US_NONFARM_PAYROLLS", "PAYEMS", payroll_values(n),
                      capture_time=capture, end=end_month)
    rows += month_rows("US_CORE_CPI", "CPILFESL", cpi_values(n),
                       capture_time=capture, end=end_month)
    if extra_rows:
        rows = rows + extra_rows
    write_monitoring_run(store, rows, run_id=run_id, requested=2)
    from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db

    return build_monitoring_pack_from_db(store, workbench_run(run_id, decision_time=decision, data_cutoff=cutoff))


def direct_pack(*, as_of: date, decision: datetime, run_id: str,
                cpi_end: date = date(2026, 9, 1),
                omit: frozenset[str] = frozenset(),
                statuses: dict[str, str] | None = None,
                market_moves: list[MonitoringMarketMove] | None = None) -> MonitoringObservationPack:
    """Hand-built diagnostic pack (bypasses the DB adapter)."""

    daily = pd.bdate_range(end=as_of, periods=90)
    monthly = pd.date_range(end=cpi_end, periods=40, freq="MS")
    definitions = {
        "T_PAYROLL": (monthly, [130000 + i * 175 + (i % 4) * 25 for i in range(40)]),
        "T_CPI": (monthly, [250 + i * 0.55 + (i % 5) * 0.07 for i in range(40)]),
        "T_US_EQ": (daily, [5000 + i * 7 + (i % 4) * 2 for i in range(90)]),
    }
    resolved = statuses or {}
    series = []
    for sid, (dates, values) in definitions.items():
        if sid in omit:
            continue
        series.append(
            MonitoringSeries(
                series_id=sid,
                status=resolved.get(sid, "FRESH"),
                observations=[
                    MonitoringObservation(
                        observation_date=stamp.date(),
                        available_at=datetime.combine(stamp.date(), datetime.min.time(), tzinfo=UTC)
                        + timedelta(hours=18),
                        value=float(value),
                        source_ref=f"adversarial-test-only:{sid}",
                    )
                    for stamp, value in zip(dates, values, strict=True)
                ],
                provenance={"route": "adversarial-test-only", "series_id": sid},
            )
        )
    return MonitoringObservationPack(
        origin="CANONICAL_MONITORING",
        as_of=as_of,
        lineage=MonitoringRunLineage(
            run_id=run_id,
            decision_time=decision,
            data_cutoff=as_of,
            source_mode="LIVE",
            config_identity="decision-support-v2:adversarial-test-only",
        ),
        series=series,
        market_moves=market_moves or [],
    )
