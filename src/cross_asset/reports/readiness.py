"""Deterministic readiness summary for the first formal Marco -> Cross E2E."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

READINESS_PROFILE = "FIRST_REAL_MARCO_CROSS_E2E_V1"
FIRST_REAL_E2E_PROFILE = {
    "CN_EQ_LARGE": "wind",
    "HK_EQ": "wind",
    "US_EQ": "wind",
    "CN_BOND_10Y": "wind",
    "GOLD": "wind",
    "COPPER": "wind",
}
_REQUIRED_GATES = ("tech_gate", "legal_gate", "pit_gate", "stability_gate")


def _accepted_sources(store, series_id: str, provider: str) -> list[str]:
    gate_sql = " AND ".join(f"{gate}='PASS'" for gate in _REQUIRED_GATES)
    rows = store.conn.execute(
        f"""
        SELECT DISTINCT source_series_id
        FROM data_acceptance_registry
        WHERE series_id=?
          AND lower(provider)=lower(?)
          AND status='PASS'
          AND {gate_sql}
          AND source_series_id IS NOT NULL
          AND trim(source_series_id) <> ''
        ORDER BY source_series_id
        """,
        [series_id, provider],
    ).fetchall()
    return [str(row[0]) for row in rows]


def _series_readiness(store, series_id: str, provider: str) -> dict[str, object]:
    observation_rows = int(
        store.conn.execute(
            "SELECT COUNT(*) FROM observations WHERE series_id=?",
            [series_id],
        ).fetchone()[0]
    )
    accepted_sources = _accepted_sources(store, series_id, provider)
    acceptance_pass = bool(accepted_sources)

    accepted_observation_rows = 0
    date_min = None
    date_max = None
    if accepted_sources:
        placeholders = ",".join("?" for _ in accepted_sources)
        row = store.conn.execute(
            f"""
            SELECT COUNT(*), MIN(observation_date), MAX(observation_date)
            FROM observations
            WHERE series_id=?
              AND lower(source)=lower(?)
              AND source_series_id IN ({placeholders})
            """,
            [series_id, provider, *accepted_sources],
        ).fetchone()
        accepted_observation_rows = int(row[0])
        date_min = row[1].isoformat() if row[1] is not None else None
        date_max = row[2].isoformat() if row[2] is not None else None

    blockers: list[str] = []
    if not acceptance_pass:
        blockers.append("ACCEPTANCE_NOT_PASS")
    if accepted_observation_rows == 0:
        blockers.append("ACCEPTED_SOURCE_OBSERVATIONS_MISSING")

    return {
        "series_id": series_id,
        "required_provider": provider,
        "acceptance_pass": acceptance_pass,
        "accepted_source_series_ids": accepted_sources,
        "observation_rows": observation_rows,
        "accepted_observation_rows": accepted_observation_rows,
        "date_min": date_min,
        "date_max": date_max,
        "status": "READY" if not blockers else "BLOCKED",
        "blockers": blockers,
    }


def _write_payload(path: Path, title: str, payload: dict[str, object]) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    tmp = path / f".{title}.tmp"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path / f"{title}.json")
    tmp = path / f".{title}.md"
    tmp.write_text(f"# {title}\n\n```json\n{text}```\n", encoding="utf-8")
    tmp.replace(path / f"{title}.md")


def generate_readiness(store, output_dir="artifacts/readiness"):
    """Report first-real-E2E data readiness without overclaiming history/E2E completion."""
    observations = int(store.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0])
    accepted_pass = int(
        store.conn.execute(
            "SELECT COUNT(*) FROM data_acceptance_registry WHERE status='PASS'"
        ).fetchone()[0]
    )
    series = [
        _series_readiness(store, series_id, provider)
        for series_id, provider in FIRST_REAL_E2E_PROFILE.items()
    ]
    ready_series_count = sum(item["status"] == "READY" for item in series)
    ready = ready_series_count == len(FIRST_REAL_E2E_PROFILE)
    blockers = [
        {"series_id": item["series_id"], "code": code}
        for item in series
        for code in item["blockers"]
    ]

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "readiness_profile": READINESS_PROFILE,
        "status": "DATA_READY" if ready else "DATA_BLOCKED",
        "observations": observations,
        "accepted_pass": accepted_pass,
        "required_accepted_pass": len(FIRST_REAL_E2E_PROFILE),
        "required_series": list(FIRST_REAL_E2E_PROFILE),
        "required_series_count": len(FIRST_REAL_E2E_PROFILE),
        "ready_series_count": ready_series_count,
        "pit_admissible": ready,
        "series": series,
        "blockers": blockers,
        "scope_note": (
            "DATA_READY here means the six first-real-E2E series each have an exact PASS "
            "Wind acceptance provenance and at least one matching formal observation. It does "
            "not establish the 2014-to-latest complete-day backfill or a successful Marco-to-Cross E2E."
        ),
    }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    _write_payload(out, "DATA_READY", payload)

    history_payload = {
        **payload,
        "status": "HISTORY_BLOCKED",
        "history_completeness_established": False,
        "history_reason": (
            "P0-B 2014-to-latest complete-day history coverage is a separate gate and is not "
            "established by data-readiness."
        ),
    }
    _write_payload(out, "HISTORY_READY", history_payload)
    return payload
