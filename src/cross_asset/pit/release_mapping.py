"""Offline, non-admitting mapping of ALFRED date-level vintages to candidates."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo


def release_date_eod(release_date: str | date, timezone: str = "America/New_York") -> datetime:
    """Return conservative local end-of-day converted to UTC; not release proof."""
    day = date.fromisoformat(str(release_date)) if not isinstance(release_date, date) else release_date
    local = datetime.combine(day, time.max, tzinfo=ZoneInfo(timezone))
    return local.astimezone(UTC)


def map_alfred_rows(rows: list[dict], *, timezone: str = "America/New_York", decision_time: datetime | None = None) -> dict:
    """Map realtime_start dates to explicit *candidates* without admitting data."""
    if decision_time is not None and decision_time.tzinfo is None:
        raise ValueError("decision_time_must_be_timezone_aware")
    mapped, unmatched = [], 0
    for row in rows:
        vintage = row.get("realtime_start")
        if not vintage:
            unmatched += 1
            continue
        candidate = release_date_eod(vintage, timezone)
        mapped.append({"observation_date": row.get("date"), "vintage_date": vintage, "candidate_available_at": candidate.isoformat(), "eligible_next_decision": bool(decision_time and candidate <= decision_time), "admitted": False})
    return {"matched": len(mapped), "unmatched": unmatched, "rows": mapped}


def dry_run_alfred(raw_root: str | Path = "data/raw/fred", decision_time: datetime | None = None) -> dict:
    results = {}
    for path in sorted(Path(raw_root).glob("alfred_*_output_type_4/**/*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        source = path.parts[-4] if len(path.parts) >= 4 else path.stem
        code = source.removeprefix("alfred_").removesuffix("_output_type_4")
        rows = payload.get("observations", [])
        results[code] = {"raw_path": str(path).replace("\\", "/"), "policy": "release_date_eod", "pit_grade_candidate": "C", "evidence_status": "CANDIDATE_ONLY", **map_alfred_rows(rows, decision_time=decision_time)}
    for code in ("CPIAUCSL", "PCEPILFE", "UNRATE", "ICSA", "INDPRO", "DGS10", "DFII10", "EFFR"):
        results.setdefault(code, {"raw_path": None, "policy": "release_date_eod", "pit_grade_candidate": "C", "evidence_status": "UNMATCHED_NO_ALFRED_RAW", "matched": 0, "unmatched": 0, "rows": []})
    return {"status": "DRY_RUN_ONLY", "enabled": False, "observations_written": False, "registry_written": False, "series": results}
