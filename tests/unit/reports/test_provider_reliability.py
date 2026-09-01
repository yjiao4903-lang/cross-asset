from datetime import UTC, datetime

from cross_asset.reports.data_health import provider_reliability
from cross_asset.storage.duckdb import DuckDBStore


def _dt(*args):
    return datetime(*args, tzinfo=UTC).replace(tzinfo=None)


def test_provider_reliability_30d_and_empty_history():
    store = DuckDBStore()
    empty = provider_reliability(store.conn, "S", _dt(2025, 2, 1))
    assert empty["reliability_status"] == "UNAVAILABLE"
    assert empty["success_rate_30d"] is None

    for attempt in [
        {"attempt_id": "1", "provider": "fixture", "series_id": "S", "started_at": _dt(2025, 1, 20), "finished_at": _dt(2025, 1, 20, 0, 0, 1), "status": "SUCCESS", "latency_ms": 10},
        {"attempt_id": "2", "provider": "fixture", "series_id": "S", "started_at": _dt(2025, 1, 21), "finished_at": _dt(2025, 1, 21, 0, 0, 2), "status": "FAILED", "latency_ms": 30, "schema_error": "bad schema", "fallback": True},
        {"attempt_id": "3", "provider": "fixture", "series_id": "S", "started_at": _dt(2024, 12, 1), "finished_at": _dt(2024, 12, 1), "status": "SUCCESS", "latency_ms": 1},
    ]:
        store.record_provider_attempt(attempt)
    result = provider_reliability(store.conn, "S", _dt(2025, 2, 1))
    assert result["success_rate_30d"] == 0.5
    assert result["median_latency_ms_30d"] == 10
    assert result["failure_count_30d"] == 1
    assert result["fallback_count_30d"] == 1
    assert result["last_schema_error"] == "bad schema"
