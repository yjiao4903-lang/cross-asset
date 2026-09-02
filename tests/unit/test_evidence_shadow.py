from datetime import UTC, datetime

from cross_asset.ingestion.evidence_shadow import (
    load_wind_engineering_frame,
    run_wind_evidence_shadow,
    run_wind_local_experiment,
)
from cross_asset.storage import init_db
from cross_asset.storage.experiment import explain_run


def _seed(store):
    rows = []
    for series, source, country, frequency in (
        ("CN_EQ_LARGE", "H00300", "China", "daily"),
        ("CN_EQ_SMALL", "H00852", "China", "daily"),
        ("CN_CPI", "M0000612", "China", "monthly"),
    ):
        for day, value in (("2025-01-01", 100.0), ("2025-02-01", 101.0)):
            rows.append(("hash", source, series, series, country, frequency, "index_points", "wind_manual", day, value, None, None, "PIT_BLOCKED", "MANUAL", "{}", "2025-03-01"))
    store.conn.executemany("INSERT INTO wind_evidence_staging VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)


def test_engineering_frame_is_cutoff_scoped_and_never_admissible(tmp_path):
    store = init_db(tmp_path / "test.duckdb")
    try:
        _seed(store)
        frame = load_wind_engineering_frame(
            store.conn, decision_time=datetime(2025, 2, 20, tzinfo=UTC)
        )
        assert set(frame["usage_status"]) == {"ENGINEERING_ONLY"}
        assert not frame["decision_eligible"].any()
        assert set(frame["observation_date"].astype(str)) == {"2025-01-01", "2025-02-01"}
        assert len(frame[frame["series_id"] == "CN_CPI"]) == 1
        assert store.conn.execute("select count(*) from observations").fetchone()[0] == 0
    finally:
        store.close()


def test_shadow_runs_features_without_allocation_or_observation_write(tmp_path):
    store = init_db(tmp_path / "test.duckdb")
    try:
        _seed(store)
        result = run_wind_evidence_shadow(
            store.conn, decision_time=datetime(2025, 12, 31, tzinfo=UTC)
        )
        assert result["status"] == "ENGINEERING_READY"
        assert result["no_trade"] is True
        assert result["decision_eligible"] is False
        assert result["formal_observations_written"] == 0
        assert "live_allocation" in result["blocked_from"]
        assert store.conn.execute("select count(*) from observations").fetchone()[0] == 0
    finally:
        store.close()


def test_local_experiment_allocates_without_orders_or_formal_write(tmp_path):
    store = init_db(tmp_path / "test.duckdb")
    try:
        _seed(store)
        result = run_wind_local_experiment(
            store.conn, decision_time=datetime(2025, 12, 31, tzinfo=UTC)
        )
        assert result["status"] == "LOCAL_EXPERIMENT_ACTIVE"
        assert result["no_broker_connection"] is True
        assert result["no_order_generation"] is True
        assert abs(sum(result["allocation"]["weights"].values()) - 1) < 1e-9
        assert store.conn.execute("select count(*) from observations").fetchone()[0] == 0
    finally:
        store.close()


def test_local_experiment_persistence_is_idempotent_and_explainable(tmp_path):
    store = init_db(tmp_path / "test.duckdb")
    try:
        _seed(store)
        when = datetime(2025, 12, 31, tzinfo=UTC)
        first = run_wind_local_experiment(
            store.conn,
            decision_time=when,
            store=store,
            persist=True,
            project_root=".",
        )
        second = run_wind_local_experiment(
            store.conn,
            decision_time=when,
            store=store,
            persist=True,
            project_root=".",
        )
        assert first["persistence"]["run_id"] == second["persistence"]["run_id"]
        assert first["persistence"]["reused"] is False
        assert second["persistence"]["reused"] is True
        explained = explain_run(store.conn, first["persistence"]["run_id"])
        assert explained["run"]["run_mode"] == "LOCAL_EXPERIMENT"
        assert "manifest_json" not in explained["snapshot"]
        assert explained["snapshot"]["manifest_entry_count"] > 0
        assert explained["allocation_results"]
        assert explained["factors"]
        assert explained["asset_scores"]
        expected_time = datetime(2025, 12, 31, tzinfo=UTC).replace(tzinfo=None)
        assert explained["factors"][0]["decision_time"] == expected_time
        assert explained["factors"][0]["data_cutoff"] == expected_time
        assert explained["asset_scores"][0]["decision_time"] == expected_time
        assert explained["asset_scores"][0]["data_cutoff"] == expected_time
        assert store.conn.execute("select count(*) from model_runs").fetchone()[0] == 1
        assert store.conn.execute("select count(*) from observations").fetchone()[0] == 0
    finally:
        store.close()
