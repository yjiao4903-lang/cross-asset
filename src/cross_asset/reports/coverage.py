"""Read-only point-in-time coverage report."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from cross_asset.operations.calendar import MarketCalendar


def _sessions(calendar, start, end):
    values, day = [], start
    while day <= end:
        if calendar.is_session(day):
            values.append(day)
        day += timedelta(days=1)
    return values


def generate_coverage_report(conn, as_of=None, output=None, calendar_config="config/calendars.yml", mapping_config="config/series_calendars.yml"):
    cutoff = datetime.fromisoformat(as_of).replace(tzinfo=None) if as_of else None
    params = [cutoff] if cutoff else []
    where = "WHERE available_at <= ?" if cutoff else ""
    rows = conn.execute(f"SELECT series_id, MIN(observation_date), MAX(observation_date), COUNT(*), COUNT(DISTINCT observation_date) FROM observations {where} GROUP BY series_id ORDER BY series_id", params).fetchall()
    catalog = {r[0]: r for r in conn.execute("SELECT series_id, frequency FROM series_catalog").fetchall()}
    mappings = {}
    for row in conn.execute("SELECT series_id, provider, source_series_id FROM source_mapping WHERE enabled=TRUE ORDER BY priority").fetchall():
        mappings.setdefault(row[0], row[1:])
    registry = {r[0]: r for r in conn.execute("SELECT series_id,status,pit_grade,origin FROM data_acceptance_registry").fetchall()}
    try:
        mapping = yaml.safe_load(Path(mapping_config).read_text(encoding="utf-8")).get("series_calendars", {})
    except (OSError, AttributeError, yaml.YAMLError):
        mapping = {}
    report, warnings = [], []
    observed_ids = {row[0] for row in rows}
    for sid, start, end, count, distinct in rows:
        reg = registry.get(sid, (None, "UNKNOWN", None, "UNAVAILABLE"))
        cal_name, cal_status, missing_pct, max_gap = mapping.get(sid), "UNKNOWN", None, None
        if cal_name:
            cal = MarketCalendar(cal_name, calendar_config)
            cal_status = cal.session_status(end)
            if cal.capability_status == "VERIFIED" and start and end:
                sessions = _sessions(cal, start, end)
                expected = len(sessions)
                missing_pct = round((expected - distinct) / expected * 100, 6) if expected else 0.0
                observed = {item[0] for item in conn.execute(f"SELECT DISTINCT observation_date FROM observations {where} AND series_id=?", params + [sid]).fetchall()}
                max_run = run = 0
                for session in sessions:
                    run = run + 1 if session not in observed else 0
                    max_run = max(max_run, run)
                max_gap = max_run
            else:
                warnings.append(f"{sid}: calendar not verified")
        else:
            warnings.append(f"{sid}: calendar mapping missing")
        report.append({"series": sid, "start": str(start), "end": str(end), "n_obs": count, "n_dates": distinct, "missing_pct": missing_pct, "max_gap_sessions": max_gap, "pit_grade": reg[2], "provider": mappings.get(sid, ("UNKNOWN",))[0], "origin": reg[3], "acceptance_status": reg[1], "calendar_status": cal_status, "usable_from": str(start), "warnings": sorted(set(warnings))})
    for sid in sorted(set(catalog) - observed_ids):
        reg = registry.get(sid, (None, "UNKNOWN", None, "UNAVAILABLE"))
        report.append({"series": sid, "start": None, "end": None, "n_obs": 0, "n_dates": 0, "missing_pct": None, "max_gap_sessions": None, "pit_grade": reg[2], "provider": mappings.get(sid, ("UNKNOWN",))[0], "origin": reg[3], "acceptance_status": reg[1], "calendar_status": "UNKNOWN", "usable_from": None, "warnings": [f"{sid}: no observations"]})
    has_data = any(row["n_obs"] for row in report)
    status = "EMPTY" if not report or not has_data else ("PARTIAL" if any(row["acceptance_status"] != "PASS" or row["calendar_status"] == "UNKNOWN" for row in report) else "PASS")
    payload = {"as_of": as_of, "status": status, "time_basis": "observations with available_at <= as_of; UTC comparison", "warnings": sorted(set(warnings)), "series": sorted(report, key=lambda row: row["series"])}
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        return path, payload
    return payload
