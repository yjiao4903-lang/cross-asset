import json
from datetime import UTC, datetime

from cross_asset.reports.data_health import (
    critical_unhealthy,
    data_health,
    generate_data_health_report,
)
from cross_asset.storage import DuckDBStore


def _catalog(store, sid, critical=True, stale_after=None):
    store.query(
        "INSERT INTO series_catalog VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            sid,
            sid,
            "market",
            "test",
            "daily",
            "level",
            None,
            None,
            critical,
            "market",
            stale_after,
            True,
            datetime(2025, 1, 1, tzinfo=UTC).replace(tzinfo=None),
            datetime(2025, 1, 1, tzinfo=UTC).replace(tzinfo=None),
        ],
    )


def _observation(store, sid, quality="ok", value=1.0):
    store.query(
        "INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            sid,
            "2025-01-01",
            "2025-01-01 00:00:00",
            value,
            "fixture",
            sid,
            None,
            "2025-01-01 00:00:00",
            quality,
            None,
            "run",
        ],
    )


def test_data_health_status_matrix_and_critical():
    store = DuckDBStore()
    for sid in ("OK", "STALE", "CLOSED", "FAILED", "FALLBACK", "MISSING", "UNAVAILABLE"):
        _catalog(
            store,
            sid,
            critical=sid not in ("OK", "CLOSED"),
            stale_after=1 if sid == "STALE" else None,
        )
    _observation(store, "OK")
    _observation(store, "STALE")
    _observation(store, "CLOSED", "closed")
    _observation(store, "FAILED", "failed")
    _observation(store, "FALLBACK", "fallback")
    _observation(store, "UNAVAILABLE", "unavailable")
    rows = data_health(store.conn, datetime(2025, 1, 2, tzinfo=UTC).replace(tzinfo=None))
    statuses = {row["series_id"]: row["status"] for row in rows}
    assert statuses == {
        "OK": "OK",
        "STALE": "STALE",
        "CLOSED": "CLOSED",
        "FAILED": "FAILED",
        "FALLBACK": "FALLBACK",
        "MISSING": "MISSING",
        "UNAVAILABLE": "UNAVAILABLE",
    }
    assert {row["series_id"] for row in critical_unhealthy(rows)} == {
        "STALE",
        "FAILED",
        "FALLBACK",
        "MISSING",
        "UNAVAILABLE",
    }


def test_data_health_report_is_pit_scoped_and_json_markdown(tmp_path):
    store = DuckDBStore()
    _catalog(store, "PIT", critical=True)
    _observation(store, "PIT")
    store.query(
        "INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            "PIT",
            "2025-01-02",
            "2025-01-03 00:00:00",
            2.0,
            "fixture",
            "PIT",
            None,
            "2025-01-03 00:00:00",
            "ok",
            None,
            "run2",
        ],
    )
    md, js = generate_data_health_report(
        store.conn, datetime(2025, 1, 2, tzinfo=UTC).replace(tzinfo=None), output_dir=tmp_path, offline_fixture=True
    )
    with open(js, encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["mode"] == "offline_fixture"
    assert payload["series"][0]["available_at"] == "2025-01-01T00:00:00"
    with open(md, encoding="utf-8") as handle:
        text = handle.read()
    assert "PIT" in text and "OK" in text
