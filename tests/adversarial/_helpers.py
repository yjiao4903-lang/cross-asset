"""Shared deterministic helpers for the WEEKEND-REDTEAM adversarial suite (#137).

Everything here is offline: no network, no Wind, no proprietary local files.
Synthetic observations are TEST-ONLY mechanics inputs and are never described
as real market evidence.
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
    MonitoringObservation,
    MonitoringObservationPack,
    MonitoringRunLineage,
    MonitoringSeries,
)
from cross_asset.operations.workbench_run import WorkbenchRun
from cross_asset.storage.catalog import sync_series_catalog
from cross_asset.storage.duckdb import DuckDBStore

AS_OF = date(2026, 9, 11)
DECISION = datetime(2026, 9, 12, 6, tzinfo=UTC)
CAPTURE = datetime(2026, 9, 12, 0, tzinfo=UTC)

BLOCKED_LANE = LaneBinding(route="SANCTIONED_FORMAL_QUERY", status="BLOCKED")
MONITORING_LANE = LaneBinding(route="TEST_ONLY_MONITORING", status="BOUND")


def mechanics_registry() -> FactorBindingRegistry:
    """TEST-ONLY registry for producer mechanics.

    Synthetic identities never enter the repository binding config; product
    BOUND truth is covered separately by the accepted governance tests.
    """

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


def series(
    series_id: str,
    dates,
    values,
    *,
    status: str = "FRESH",
    available_at_hour: int = 18,
) -> MonitoringSeries:
    return MonitoringSeries(
        series_id=series_id,
        status=status,
        observations=[
            MonitoringObservation(
                observation_date=stamp.date(),
                available_at=datetime.combine(
                    stamp.date(), datetime.min.time(), tzinfo=UTC
                )
                + timedelta(hours=available_at_hour),
                value=float(value),
                source_ref=f"adversarial-test-only:{series_id}",
            )
            for stamp, value in zip(dates, values, strict=True)
        ],
        provenance={"route": "adversarial-test-only", "series_id": series_id},
    )


def pack(
    *,
    omit: frozenset[str] = frozenset(),
    statuses: dict[str, str] | None = None,
    as_of: date = AS_OF,
    decision: datetime = DECISION,
    run_id: str = "wb-adv-001",
    source_mode: str = "LIVE",
    origin: str = "CANONICAL_MONITORING",
) -> MonitoringObservationPack:
    daily = pd.bdate_range(end=as_of, periods=90)
    monthly = pd.date_range(end=date(2026, 9, 1), periods=40, freq="MS")
    definitions = {
        "T_PAYROLL": (monthly, [130000 + i * 175 + (i % 4) * 25 for i in range(40)]),
        "T_CPI": (monthly, [250 + i * 0.55 + (i % 5) * 0.07 for i in range(40)]),
        "T_US_EQ": (daily, [5000 + i * 7 + (i % 4) * 2 for i in range(90)]),
    }
    resolved_statuses = statuses or {}
    return MonitoringObservationPack(
        origin=origin,
        as_of=as_of,
        lineage=MonitoringRunLineage(
            run_id=run_id,
            decision_time=decision,
            data_cutoff=as_of,
            source_mode=source_mode,
            config_identity="decision-support-v2:adversarial-test-only",
        ),
        series=[
            series(sid, dates, values, status=resolved_statuses.get(sid, "FRESH"))
            for sid, (dates, values) in definitions.items()
            if sid not in omit
        ],
    )


def governed_store(series_ids=("US_NONFARM_PAYROLLS", "US_CORE_CPI"), provider="fred"):
    """Monitoring store seeded with the accepted canonical series mappings."""

    store = DuckDBStore(":memory:")
    sync_series_catalog(store, series_ids=list(series_ids), provider=provider)
    return store


def month_rows(
    series_id: str,
    source_series_id: str,
    values,
    *,
    capture_time: datetime = CAPTURE,
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


def workbench_run(
    run_id: str = "wb-adv-monitoring",
    *,
    decision_time: datetime = DECISION,
    data_cutoff: date = AS_OF,
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


def write_monitoring_run(store, rows, *, run_id="monitoring-fred-adv", requested=None):
    """Persist rows under one MONITORING:fred ingestion run."""

    store.start_run("MONITORING:fred", run_id, requested_series=requested or 1)
    store.insert_observations(rows, run_id=run_id)
    store.finish_run(run_id, "success", success_series=requested or 1, failed_series=0)
    return run_id
