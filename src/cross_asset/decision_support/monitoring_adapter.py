"""Merged #127 MONITORING DB/read-model -> REAL-SNAPSHOT-V1 adapter.

The adapter is provider-neutral. It consumes canonical observations already
persisted by the monitoring lane and reuses the accepted #106 WorkbenchRun as
snapshot lineage. It never grants FORMAL/OOS eligibility.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from cross_asset.operations.workbench_run import WorkbenchRun
from cross_asset.reports.monitoring_health import monitoring_data_health
from cross_asset.storage._time import utc_naive

from .binding import FactorBindingRegistry, load_factor_bindings
from .producer import (
    MonitoringObservation,
    MonitoringObservationPack,
    MonitoringRunLineage,
    MonitoringSeries,
)

_HEALTH_TO_PACK = {
    "OK": "FRESH",
    "STALE": "STALE",
    "MISSING": "MISSING",
    "BLOCKED": "BLOCKED",
    "FAILED": "BLOCKED",
    "UNAVAILABLE": "BLOCKED",
}
# #129 explicitly permits captured publication-frequency macro history to remain
# MONITORING evidence when publication freshness is not yet governed. Keep this
# exception narrow: only missing publication/calendar authority is represented as
# partial/stale evidence. Provider/schema/identity failures stay BLOCKED.
_MONITORING_FRESHNESS_UNVERIFIED_REASONS = {
    "calendar_mapping_missing",
}


def _parse_decision_time(value: str | None) -> datetime:
    if not value:
        raise ValueError("workbench_run_decision_time_required")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("workbench_run_decision_time_invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_cutoff(value: str | None) -> date:
    if not value:
        raise ValueError("workbench_run_data_cutoff_required")
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValueError("workbench_run_data_cutoff_invalid") from exc


def _rows(conn, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, params)
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _monitoring_rows(conn, series_ids: list[str], decision_time: datetime, cutoff: date):
    if not series_ids:
        return []
    placeholders = ",".join("?" for _ in series_ids)
    return _rows(
        conn,
        f"""SELECT series_id,observation_date,available_at,value,source,
                   source_series_id,raw_file,run_id,ingested_at
            FROM observations o
            JOIN ingestion_runs r USING(run_id)
            WHERE o.series_id IN ({placeholders})
              AND o.available_at<=?
              AND o.observation_date<=?
              AND upper(r.provider) LIKE 'MONITORING:%'
            QUALIFY row_number() OVER (
                PARTITION BY o.series_id,o.observation_date
                ORDER BY o.available_at DESC,o.ingested_at DESC,o.run_id DESC
            )=1
            ORDER BY o.series_id,o.observation_date,o.available_at""",
        [*series_ids, utc_naive(decision_time), cutoff],
    )


def _freshness_unverified(health_row: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    monitoring_status = str(health_row.get("monitoring_status") or "MISSING").upper()
    reason = str(health_row.get("monitoring_reason") or "").strip().lower()
    return bool(
        rows
        and monitoring_status == "BLOCKED"
        and reason in _MONITORING_FRESHNESS_UNVERIFIED_REASONS
    )


def _pack_status(health_row: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    if _freshness_unverified(health_row, rows):
        # Reuse the accepted producer's STALE semantics so the evidence remains
        # usable only with reduced confidence and PARTIAL health. Raw read-model
        # status/reason remain in provenance as BLOCKED/UNVERIFIED.
        return "STALE"
    monitoring_status = str(health_row.get("monitoring_status") or "MISSING").upper()
    return _HEALTH_TO_PACK.get(monitoring_status, "BLOCKED")


def build_monitoring_pack_from_db(
    store,
    workbench_run: WorkbenchRun,
    *,
    registry: FactorBindingRegistry | None = None,
    calendar_config: str = "config/calendars.yml",
    series_calendar_config: str = "config/series_calendars.yml",
) -> MonitoringObservationPack:
    """Build a canonical observation pack directly from merged #127/#129 authorities."""

    workbench_run.validate()
    if workbench_run.source_mode != "LIVE":
        raise ValueError("monitoring_snapshot_requires_live_workbench_run")
    decision_time = _parse_decision_time(workbench_run.decision_time)
    db_as_of = utc_naive(decision_time)
    cutoff = _parse_cutoff(workbench_run.data_cutoff)
    registry = registry or load_factor_bindings()
    bound = [
        binding
        for binding in registry.bindings
        if binding.monitoring.status == "BOUND"
    ]
    series_ids = sorted(
        {series_id for binding in bound for series_id in binding.canonical_series_ids}
    )

    health_rows = monitoring_data_health(
        store.conn,
        as_of=db_as_of,
        market_data_cutoff=cutoff,
        calendar_config=calendar_config,
        series_calendar_config=series_calendar_config,
        series_ids=series_ids,
    )
    health = {str(row["series_id"]): row for row in health_rows}
    db_rows = _monitoring_rows(store.conn, series_ids, decision_time, cutoff)
    by_series: dict[str, list[dict[str, Any]]] = {series_id: [] for series_id in series_ids}
    for row in db_rows:
        by_series.setdefault(str(row["series_id"]), []).append(row)

    series: list[MonitoringSeries] = []
    for series_id in series_ids:
        rows = by_series.get(series_id, [])
        health_row = health.get(series_id, {})
        freshness_unverified = _freshness_unverified(health_row, rows)
        status = _pack_status(health_row, rows)
        observations = [
            MonitoringObservation(
                observation_date=row["observation_date"],
                available_at=row["available_at"].replace(tzinfo=UTC)
                if row["available_at"].tzinfo is None
                else row["available_at"].astimezone(UTC),
                value=float(row["value"]),
                source_ref=(
                    f"{row.get('source') or 'unknown'}:"
                    f"{row.get('source_series_id') or 'unknown'}:"
                    f"{row.get('run_id') or 'unknown'}"
                ),
            )
            for row in rows
        ]
        ingestion_run_ids = sorted({str(row["run_id"]) for row in rows if row.get("run_id")})
        source_refs = sorted(
            {
                f"{row.get('source') or 'unknown'}:{row.get('source_series_id') or 'unknown'}"
                for row in rows
            }
        )
        monitoring_reason = health_row.get("monitoring_reason")
        series.append(
            MonitoringSeries(
                series_id=series_id,
                status=status,
                observations=observations,
                provenance={
                    "origin": "MONITORING_DB",
                    "ingestion_run_ids": ingestion_run_ids,
                    "source_refs": source_refs,
                    "monitoring_status": health_row.get("monitoring_status"),
                    "monitoring_reason": monitoring_reason,
                    "freshness_verified": not freshness_unverified,
                    "freshness_limitation": monitoring_reason if freshness_unverified else None,
                    "calendar": health_row.get("calendar"),
                    "calendar_lag_sessions": health_row.get("calendar_lag_sessions"),
                    "formal_readiness": health_row.get("formal_readiness"),
                    "formal_admission_granted": False,
                },
            )
        )

    return MonitoringObservationPack(
        as_of=cutoff,
        lineage=MonitoringRunLineage(
            run_id=workbench_run.run_id,
            decision_time=decision_time,
            data_cutoff=cutoff,
            source_mode=workbench_run.source_mode,
            config_identity=workbench_run.config_identity,
        ),
        series=series,
    )


__all__ = ["build_monitoring_pack_from_db"]
