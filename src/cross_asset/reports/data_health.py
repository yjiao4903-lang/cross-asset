"""Auditable data-health query and report helpers (no provider calls)."""

import json
from datetime import UTC, datetime
from pathlib import Path

from cross_asset.storage import approved_observations_asof

STATUSES = {"OK", "CLOSED", "STALE", "MISSING", "FAILED", "FALLBACK", "UNAVAILABLE"}


def _approved_observation_count(conn, series_id: str, as_of) -> int:
    """Approved-provenance rows via the shared formal query (either usage scope)."""

    total = 0
    for usage_status in ("LIVE_VERIFIED", "RESEARCH_ADMISSIBLE"):
        total += len(
            approved_observations_asof(
                conn,
                as_of,
                required_usage_status=usage_status,
                series_id=series_id,
            ).fetchall()
        )
    return total

def provider_reliability(conn, series_id, as_of=None, window_days=30):
    """Aggregate attempts; absent history returns None fields, never synthetic zeroes."""
    as_of=as_of or datetime.now(UTC).replace(tzinfo=None)
    rows=_rows(conn,"SELECT * FROM provider_attempts WHERE series_id=? AND started_at<=?",(series_id,as_of))
    rows=[r for r in rows if (as_of-r['started_at']).total_seconds() <= window_days*86400]
    ok=[r for r in rows if str(r.get('status','')).upper() in ('SUCCESS','OK')]
    lat=sorted(float(r['latency_ms']) for r in ok if r.get('latency_ms') is not None)
    median=(lat[len(lat)//2] if len(lat)%2 else (lat[len(lat)//2-1]+lat[len(lat)//2])/2) if lat else None
    return {'success_rate_30d':len(ok)/len(rows) if rows else None,'median_latency_ms_30d':median,
            'failure_count_30d':sum(str(r.get('status','')).upper() in ('FAILED','ERROR','SCHEMA_ERROR') for r in rows) if rows else None,
            'fallback_count_30d':sum(bool(r.get('fallback')) for r in rows) if rows else None,
            'last_success':max((r.get('finished_at') for r in ok),default=None),
            'last_schema_error':max((r.get('schema_error') for r in rows if r.get('schema_error')),default=None),
            'reliability_status':'OK' if rows else 'UNAVAILABLE'}


def _rows(conn, sql, params=()):
    cur = conn.execute(sql, params)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def data_health(conn, as_of=None):
    as_of = as_of or datetime.now(UTC).replace(tzinfo=None)
    catalog = _rows(conn, "SELECT * FROM series_catalog WHERE active = TRUE ORDER BY series_id")
    result = []
    for spec in catalog:
        sid = spec["series_id"]
        rows = _rows(
            conn,
            "SELECT * FROM observations WHERE series_id=? AND available_at<=? ORDER BY observation_date DESC, available_at DESC",
            (sid, as_of),
        )
        latest = rows[0] if rows else None
        age = None
        status = "MISSING"
        reason = "no released observation"
        events = _rows(
            conn,
            "SELECT * FROM data_quality_events WHERE series_id=? AND (detected_at<=? OR detected_at IS NULL) ORDER BY detected_at DESC",
            (sid, as_of),
        )
        mappings = _rows(conn, "SELECT provider, priority FROM source_mapping WHERE series_id=? AND enabled=TRUE ORDER BY priority", (sid,))
        attempts = [a for a in _rows(conn, "SELECT * FROM provider_attempts WHERE series_id=? AND started_at<=?", (sid, as_of)) if (as_of - a['started_at']).total_seconds() <= 30*86400]
        successes=[a for a in attempts if str(a.get('status','')).upper() in ('SUCCESS','OK')]
        failures=[a for a in attempts if str(a.get('status','')).upper() in ('FAILED','ERROR','SCHEMA_ERROR')]
        latencies=sorted(float(a['latency_ms']) for a in successes if a.get('latency_ms') is not None)
        reliability={
            'success_rate_30d': len(successes)/len(attempts) if attempts else None,
            'median_latency_ms_30d': (latencies[len(latencies)//2] if latencies and len(latencies)%2 else ((latencies[len(latencies)//2-1]+latencies[len(latencies)//2])/2 if latencies else None)),
            'failure_count_30d': len(failures) if attempts else None,
            'fallback_count_30d': sum(bool(a.get('fallback')) for a in attempts) if attempts else None,
            'last_success': max((a.get('finished_at') for a in successes), default=None),
            'last_schema_error': max((a.get('schema_error') for a in attempts if a.get('schema_error')), default=None),
            'reliability_status': 'OK' if attempts else 'UNAVAILABLE',
        }
        q = (latest or {}).get("quality")
        event_types = {str(e.get("event_type", "")).upper() for e in events}
        if q in ("unavailable", "UNAVAILABLE"):
            status = "UNAVAILABLE"
            reason = "series unavailable"
        elif "FETCH_ERROR" in event_types or q in ("failed", "FAILED"):
            status = "FAILED"
            reason = "fetch or quality failure"
        elif "SOURCE_SWITCH" in event_types or q in ("fallback", "FALLBACK"):
            status = "FALLBACK"
            reason = "backup/fallback source active"
        elif q in ("closed", "CLOSED"):
            status = "CLOSED"
            reason = "market/data source closed"
        elif latest:
            threshold = spec.get("stale_after_hours")
            age = (
                (as_of - latest["available_at"]).total_seconds() / 3600
                if latest.get("available_at")
                else None
            )
            if threshold is not None and age is not None and age > float(threshold):
                status = "STALE"
                reason = "latest observation exceeds freshness threshold"
            else:
                status = "OK"
                reason = "fresh released observation"
        out = {
            **spec,
            "last_observation_date": latest.get("observation_date") if latest else None,
            "available_at": latest.get("available_at") if latest else None,
            "age_hours": age if latest else None,
            "source": latest.get("source") if latest else None,
            "quality": q,
            "status": status,
            "reason": reason,
            "approved_observation_rows": _approved_observation_count(conn, sid, as_of),
            "formally_consumable": False,
            "critical_unhealthy": bool(spec.get("critical")) and status not in ("OK", "CLOSED"),
            "primary_source": mappings[0]['provider'] if mappings else None,
            "active_source": latest.get('source') if latest else None,
        }
        # Raw observations without an approved provenance identity are never
        # formally consumable, whatever their row quality looks like.
        out["formally_consumable"] = out["approved_observation_rows"] > 0 and status in ("OK", "CLOSED")
        if out["approved_observation_rows"] == 0 and latest is not None:
            out["reason"] = (out["reason"] + "; no approved provenance identity").lstrip("; ")
        out.update(reliability)
        result.append(out)
    return result


def critical_unhealthy(rows):
    return [r for r in rows if r.get("critical") and r.get("status") not in ("OK", "CLOSED")]


def _jsonable(x):
    if isinstance(x, datetime):
        return x.isoformat()
    return str(x) if hasattr(x, "isoformat") else x


def generate_data_health_report(
    conn, as_of=None, output_dir="artifacts/reports", offline_fixture=False
):
    rows = data_health(conn, as_of)
    as_of = as_of or datetime.now(UTC).replace(tzinfo=None)
    payload = {
        "as_of": as_of,
        "mode": "offline_fixture" if offline_fixture else "database",
        "critical_unhealthy": critical_unhealthy(rows),
        "series": rows,
    }
    payload = json.loads(json.dumps(payload, default=_jsonable))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = as_of.strftime("%Y-%m-%d")
    jp = out / f"data_health_{stamp}.json"
    mp = out / f"data_health_{stamp}.md"
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# Data Health\n\nAs of: {payload['as_of']}",
        f"Mode: {payload['mode']}",
        "",
        "| Series | Primary | Active | Available At | Age (h) | Status | Success 30d | Median latency ms | Critical |",
        "|---|---|---|---|---:|---|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['series_id']} | {r.get('primary_source') or '-'} | {r.get('active_source') or '-'} | {r.get('available_at') or '-'} | {r.get('age_hours') if r.get('age_hours') is not None else '-'} | {r['status']} | {r.get('success_rate_30d') if r.get('success_rate_30d') is not None else '-'} | {r.get('median_latency_ms_30d') if r.get('median_latency_ms_30d') is not None else '-'} | {'YES' if r['critical_unhealthy'] else 'no'} |"
        )
    if payload["critical_unhealthy"]:
        lines += [
            "",
            "## Critical unhealthy",
            *[
                f"- {r['series_id']}: {r['status']} ({r['reason']})"
                for r in payload["critical_unhealthy"]
            ],
        ]
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(mp), str(jp)


get_data_health = data_health
build_data_health_report = generate_data_health_report
