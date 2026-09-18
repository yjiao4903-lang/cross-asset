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
from cross_asset.storage.catalog import expected_source_identities

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
                   source_series_id,raw_file,run_id,ingested_at,r.provider AS run_provider
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


def _identity_violations(conn, rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Re-check persisted row identity against the governed enabled mappings.

    The accepted monitoring ingestion path (``MonitoringRunner._validate_rows``)
    already rejects a run whose rows carry a provider or provider-symbol identity
    that does not belong to the governed mapping. The read model is a separate
    boundary: rows can be persisted directly, or by another window, so the
    adapter must not treat a mis-identified row as evidence for the canonical
    series it is filed under. Provider/source identity mismatch is never a
    comparable series, so violations fail closed per series instead of being
    silently consumed.
    """

    violations: dict[str, list[str]] = {}
    expected_cache: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        series_id = str(row.get("series_id") or "")
        run_provider = str(row.get("run_provider") or "")
        lane, _, provider = run_provider.partition(":")
        provider = provider.strip().lower()
        reasons: list[str] = []
        if lane.strip().upper() != "MONITORING" or not provider:
            reasons.append("monitoring_run_provider_unresolved")
        else:
            observed_source = str(row.get("source") or "").strip().lower()
            if observed_source != provider:
                reasons.append(
                    f"monitoring_source_mismatch:{observed_source or 'missing'}"
                )
            cache_key = (provider, series_id)
            if cache_key not in expected_cache:
                expected_cache[cache_key] = set(
                    expected_source_identities(conn, provider, [series_id]).get(series_id) or set()
                )
            allowed = expected_cache[cache_key]
            observed_symbol = str(row.get("source_series_id") or "")
            if not allowed:
                reasons.append("monitoring_source_mapping_missing")
            elif observed_symbol not in allowed:
                reasons.append(
                    f"monitoring_source_series_id_mismatch:{observed_symbol or 'missing'}"
                )
        if reasons:
            violations.setdefault(series_id, []).extend(reasons)
    return {key: sorted(set(value)) for key, value in violations.items()}


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
    identity_violations = _identity_violations(store.conn, db_rows)
    by_series: dict[str, list[dict[str, Any]]] = {series_id: [] for series_id in series_ids}
    for row in db_rows:
        by_series.setdefault(str(row["series_id"]), []).append(row)

    series: list[MonitoringSeries] = []
    for series_id in series_ids:
        raw_rows = by_series.get(series_id, [])
        identity_blockers = identity_violations.get(series_id, [])
        # Mis-identified rows are never usable evidence for this canonical series;
        # the series is represented as BLOCKED, mirroring MONITORING_SCHEMA_ERROR.
        rows = [] if identity_blockers else raw_rows
        health_row = health.get(series_id, {})
        freshness_unverified = _freshness_unverified(health_row, rows)
        status = "BLOCKED" if identity_blockers else _pack_status(health_row, rows)
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
        ingestion_run_ids = sorted({str(row["run_id"]) for row in raw_rows if row.get("run_id")})
        source_refs = sorted(
            {
                f"{row.get('source') or 'unknown'}:{row.get('source_series_id') or 'unknown'}"
                for row in raw_rows
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
                    "identity_verified": not identity_blockers,
                    "identity_blockers": identity_blockers,
                    "identity_blocked_rows": len(raw_rows) if identity_blockers else 0,
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
