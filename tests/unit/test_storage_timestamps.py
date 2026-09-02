from datetime import UTC, date, datetime, timedelta, timezone

from cross_asset.storage import init_db


def test_insert_observations_normalizes_available_at_to_utc_naive():
    store = init_db(":memory:")
    try:
        local_midnight = datetime(2026, 1, 3, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        store.insert_observations(
            [
                {
                    "series_id": "S",
                    "observation_date": date(2026, 1, 2),
                    "available_at": local_midnight,
                    "value": 1.0,
                    "source": "fixture",
                    "source_series_id": "S",
                    "vintage_date": None,
                    "ingested_at": local_midnight,
                    "quality": "ok",
                    "raw_file": "fixture",
                }
            ],
            run_id="timestamp-fixture",
        )
        returned = store.conn.execute(
            "SELECT available_at, ingested_at FROM observations"
        ).fetchone()
        expected = datetime(2026, 1, 2, 16, tzinfo=UTC).replace(tzinfo=None)
        assert returned == (expected, expected)
    finally:
        store.close()
