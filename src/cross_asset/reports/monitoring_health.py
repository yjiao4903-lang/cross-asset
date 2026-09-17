"""Monitoring freshness/read-model layered on the existing data-health authority."""

from __future__ import annotations

from datetime import UTC, datetime

from cross_asset.engines.freshness import evaluate_series_freshness
from cross_asset.reports.data_health import data_health
from cross_asset.storage import latest_formal_observations_asof


def _rows(conn, sql, params=()):
    cursor = conn.execute(sql, params)
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def monitoring_data_health(
    conn,
    as_of=None,
    *,
    market_data_cutoff=None,
    calendar_config="config/calendars.yml",
    series_calendar_config="config/series_calendars.yml",
    series_ids=None,
):
    """Return monitoring health and formal availability as separate dimensions.

    The existing ``data_health`` read-model remains authoritative for generic
    operational status. Calendar freshness is layered on top through the
    existing fail-closed freshness engine; no weekday or elapsed-hour fallback
    is introduced here.
    """

    as_of = as_of or datetime.now(UTC).replace(tzinfo=None)
    cutoff = market_data_cutoff or as_of.date()
    base = {row["series_id"]: row for row in data_health(conn, as_of)}
    wanted = {str(value) for value in series_ids} if series_ids else set(base)
    result = []

    for sid in sorted(wanted):
        spec = base.get(sid)
        if spec is None:
            continue
        monitoring_rows = _rows(
            conn,
            """SELECT o.*
               FROM observations o
               JOIN ingestion_runs r ON r.run_id=o.run_id
               WHERE o.series_id=? AND o.available_at<=?
                 AND upper(r.provider) LIKE 'MONITORING:%'
               ORDER BY o.observation_date DESC,o.available_at DESC,o.ingested_at DESC""",
            (sid, as_of),
        )
        latest = monitoring_rows[0] if monitoring_rows else None
        event_rows = _rows(
            conn,
            """SELECT *
               FROM data_quality_events
               WHERE series_id=? AND detected_at<=?
                 AND event_type LIKE 'MONITORING_%'
               ORDER BY detected_at DESC
               LIMIT 1""",
            (sid, as_of),
        )
        latest_event = event_rows[0] if event_rows else None
        event_type = str((latest_event or {}).get("event_type") or "").upper()

        freshness = None
        if latest is not None:
            freshness = evaluate_series_freshness(
                sid,
                latest_observation_date=latest.get("observation_date"),
                market_data_cutoff=cutoff,
                calendar_config=calendar_config,
                series_calendar_config=series_calendar_config,
            )

        quality = str((latest or {}).get("quality") or "").lower()
        if event_type == "MONITORING_SCHEMA_ERROR":
            monitoring_status = "FAILED"
            monitoring_reason = "monitoring schema/identity validation failed"
        elif event_type == "MONITORING_FETCH_ERROR":
            monitoring_status = "FAILED"
            monitoring_reason = "monitoring provider fetch failed"
        elif event_type == "MONITORING_MISSING" and latest is None:
            monitoring_status = "MISSING"
            monitoring_reason = "monitoring provider returned no row"
        elif quality in {"failed", "unavailable"}:
            monitoring_status = "FAILED" if quality == "failed" else "UNAVAILABLE"
            monitoring_reason = f"monitoring row quality={quality}"
        elif latest is None:
            monitoring_status = "MISSING"
            monitoring_reason = "no monitoring observation"
        elif freshness is None:
            monitoring_status = "BLOCKED"
            monitoring_reason = "monitoring freshness unavailable"
        else:
            monitoring_status = freshness.status
            monitoring_reason = freshness.reason

        formal_available = False
        for usage_status in ("LIVE_VERIFIED", "RESEARCH_ADMISSIBLE"):
            formal = latest_formal_observations_asof(
                conn,
                as_of,
                required_usage_status=usage_status,
                series_ids=[sid],
                market_data_cutoff=cutoff,
            )
            if not formal.empty:
                formal_available = True
                break

        result.append(
            {
                "series_id": sid,
                "provider": latest.get("source") if latest else None,
                "source_series_id": latest.get("source_series_id") if latest else None,
                "frequency": spec.get("frequency"),
                "unit": spec.get("unit"),
                "currency": spec.get("currency"),
                "timezone": spec.get("timezone"),
                "freshness_expectation": {
                    "stale_after_hours": spec.get("stale_after_hours")
                },
                "last_observation_date": latest.get("observation_date") if latest else None,
                "available_at": latest.get("available_at") if latest else None,
                "raw_file": latest.get("raw_file") if latest else None,
                "monitoring_observation_rows": len(monitoring_rows),
                "monitoring_status": monitoring_status,
                "monitoring_reason": monitoring_reason,
                "monitoring_fresh": monitoring_status == "OK",
                "calendar": freshness.calendar if freshness else None,
                "calendar_lag_sessions": freshness.lag_sessions if freshness else None,
                "data_health_status": spec.get("status"),
                "formally_consumable": bool(spec.get("formally_consumable")),
                "formal_observation_available": formal_available,
                "formal_readiness": (
                    "FORMAL_OBSERVATION_AVAILABLE" if formal_available else "FORMAL_BLOCKED"
                ),
                "usage_separation": (
                    "MONITORING_AND_FORMAL_SEPARATE"
                    if formal_available and latest is not None
                    else "MONITORING_NOT_FORMAL"
                    if latest is not None
                    else "NO_MONITORING_DATA"
                ),
            }
        )
    return result


__all__ = ["monitoring_data_health"]
