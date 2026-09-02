from datetime import UTC, date, datetime, timedelta, timezone

from cross_asset.storage import init_db
from cross_asset.storage.provenance import ProvenanceStore


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


def test_ingestion_run_timestamps_normalize_explicit_utc_plus_eight_values():
    store = init_db(":memory:")
    try:
        local_midnight = datetime(2026, 1, 3, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        store.start_run("fixture", "run", started_at=local_midnight)
        store.finish_run("run", "success", finished_at=local_midnight)
        returned = store.conn.execute(
            "SELECT started_at, finished_at FROM ingestion_runs WHERE run_id='run'"
        ).fetchone()
        expected = datetime(2026, 1, 2, 16, tzinfo=UTC).replace(tzinfo=None)
        assert returned == (expected, expected)
    finally:
        store.close()


def test_provenance_snapshot_and_model_run_normalize_pit_timestamps():
    store = init_db(":memory:")
    try:
        local_midnight = datetime(2026, 1, 3, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        provenance = ProvenanceStore(store.conn)
        snapshot_id = provenance.create_snapshot(
            [{"series_id": "S", "available_at": local_midnight}],
            data_cutoff=local_midnight,
            config_hash_value="config",
        )
        provenance.start_model_run(
            "fixture", local_midnight, "v1", "config", "code", snapshot_id, local_midnight,
            run_id="model-run",
        )
        expected = datetime(2026, 1, 2, 16, tzinfo=UTC).replace(tzinfo=None)
        assert store.conn.execute(
            "SELECT max_available_at, data_cutoff FROM data_snapshots WHERE snapshot_id=?",
            [snapshot_id],
        ).fetchone() == (expected, expected)
        assert store.conn.execute(
            "SELECT decision_time, data_cutoff FROM model_runs WHERE run_id='model-run'"
        ).fetchone() == (expected, expected)
    finally:
        store.close()
