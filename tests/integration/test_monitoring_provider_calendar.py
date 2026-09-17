from datetime import UTC, date, datetime

from cross_asset.domain.models import DataRequest, Observation
from cross_asset.ingestion.monitoring import MonitoringRunner
from cross_asset.ingestion.raw_archive import ImmutableRawArchive
from cross_asset.reports.monitoring_health import monitoring_data_health
from cross_asset.storage import DuckDBStore, latest_formal_observations_asof


class _FakeYahooMonitoring:
    name = "yahoo"
    last_error = None

    def __init__(self, *, source_series_id="^GSPC", quality="ok"):
        self.source_series_id = source_series_id
        self.quality = quality

    def fetch(self, request):
        return [
            Observation(
                series_id="US_EQ",
                observation_date=date(2026, 9, 16),
                available_at=datetime(2026, 9, 16, 21, tzinfo=UTC),
                value=7000.0,
                source="yahoo",
                source_series_id=self.source_series_id,
                frequency="daily",
                unit="price",
                quality=self.quality,
                metadata={"origin": "MONITORING", "usage_lane": "MONITORING_ONLY"},
            )
        ]


def _naive_utc(hour):
    return datetime(2026, 9, 17, hour, tzinfo=UTC).replace(tzinfo=None)


def _calendar_files(tmp_path, *, max_lag=0):
    calendars = tmp_path / "calendars.yml"
    calendars.write_text(
        "calendars:\n"
        "  TEST:\n"
        "    calendar_id: TEST\n"
        "    capability_status: VERIFIED\n"
        "    timezone: UTC\n"
        "    source: test\n"
        "    source_version: '1'\n"
        "    version: '1'\n"
        "    covered_years: [2026]\n"
        "    open_time: '00:00'\n"
        "    close_time: '23:59'\n"
        "    regular_close: '23:59'\n"
        "    holidays: []\n"
        "    early_closes: {}\n"
        "    verified: true\n"
        "    evidence: [test]\n"
        "    reviewer: test\n"
        "    approved_at: '2026-01-01T00:00:00+00:00'\n",
        encoding="utf-8",
    )
    mapping = tmp_path / "series_calendars.yml"
    mapping.write_text(
        "series_calendars:\n"
        f"  US_EQ: {{calendar: TEST, max_lag_sessions: {max_lag}}}\n",
        encoding="utf-8",
    )
    return calendars, mapping


def test_monitoring_pipeline_persists_operational_row_but_not_formal(tmp_path):
    store = DuckDBStore(":memory:")
    try:
        runner = MonitoringRunner(
            store,
            _FakeYahooMonitoring(),
            raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        )
        result = runner.run(
            DataRequest(series_ids=["US_EQ"]),
            run_id="monitoring-yahoo-test",
        )

        assert result["lane"] == "MONITORING"
        assert result["status"] == "success"
        assert result["rows_written"] == 1
        assert result["formal_admission_attempted"] is False
        assert store.conn.execute(
            "SELECT count(*) FROM data_acceptance_registry"
        ).fetchone()[0] == 0

        stored = store.conn.execute(
            """SELECT source,source_series_id,raw_file,run_id
               FROM observations WHERE series_id='US_EQ'"""
        ).fetchone()
        assert stored[0:2] == ("yahoo", "^GSPC")
        assert stored[2]
        assert stored[3] == "monitoring-yahoo-test"
        run_provider = store.conn.execute(
            "SELECT provider FROM ingestion_runs WHERE run_id='monitoring-yahoo-test'"
        ).fetchone()[0]
        assert run_provider == "MONITORING:yahoo"

        attempts = store.conn.execute(
            "SELECT status FROM provider_attempts WHERE series_id='US_EQ'"
        ).fetchall()
        assert attempts == [("SUCCESS",)]
        events = store.conn.execute(
            "SELECT event_type FROM data_quality_events WHERE series_id='US_EQ'"
        ).fetchall()
        assert events == [("MONITORING_OK",)]

        decision_time = _naive_utc(1)
        for usage_status in ("LIVE_VERIFIED", "RESEARCH_ADMISSIBLE"):
            formal = latest_formal_observations_asof(
                store.conn,
                decision_time,
                required_usage_status=usage_status,
                series_ids=["US_EQ"],
                market_data_cutoff=date(2026, 9, 16),
            )
            assert formal.empty

        calendars, mapping = _calendar_files(tmp_path)
        health = monitoring_data_health(
            store.conn,
            decision_time,
            market_data_cutoff=date(2026, 9, 16),
            calendar_config=calendars,
            series_calendar_config=mapping,
            series_ids=["US_EQ"],
        )[0]
        assert health["monitoring_status"] == "OK"
        assert health["monitoring_fresh"] is True
        assert health["formal_readiness"] == "FORMAL_BLOCKED"
        assert health["formal_observation_available"] is False
        assert health["usage_separation"] == "MONITORING_NOT_FORMAL"
    finally:
        store.close()


def test_monitoring_default_calendar_contract_reuses_upstream_mapping():
    store = DuckDBStore(":memory:")
    try:
        MonitoringRunner(store, _FakeYahooMonitoring()).run(
            DataRequest(series_ids=["US_EQ"]),
            run_id="monitoring-yahoo-calendar-upstream",
        )
        health = monitoring_data_health(
            store.conn,
            _naive_utc(1),
            market_data_cutoff=date(2026, 9, 16),
            series_ids=["US_EQ"],
        )[0]
        assert health["monitoring_status"] == "OK"
        assert health["monitoring_reason"] == "fresh_within_calendar_lag"
        assert health["calendar"] == "XNYS"
        assert health["calendar_lag_sessions"] == 0
        assert health["formal_readiness"] == "FORMAL_BLOCKED"
        assert health["formal_observation_available"] is False
        assert health["usage_separation"] == "MONITORING_NOT_FORMAL"
    finally:
        store.close()


def test_monitoring_freshness_reuses_session_calendar_and_can_be_stale(tmp_path):
    store = DuckDBStore(":memory:")
    try:
        MonitoringRunner(store, _FakeYahooMonitoring()).run(
            DataRequest(series_ids=["US_EQ"]),
            run_id="monitoring-yahoo-stale",
        )
        calendars, mapping = _calendar_files(tmp_path, max_lag=0)
        health = monitoring_data_health(
            store.conn,
            _naive_utc(23),
            market_data_cutoff=date(2026, 9, 17),
            calendar_config=calendars,
            series_calendar_config=mapping,
            series_ids=["US_EQ"],
        )[0]
        assert health["monitoring_status"] == "STALE"
        assert health["calendar_lag_sessions"] == 1
        assert health["formal_readiness"] == "FORMAL_BLOCKED"
    finally:
        store.close()


def test_failed_monitoring_quality_cannot_appear_healthy(tmp_path):
    store = DuckDBStore(":memory:")
    try:
        MonitoringRunner(store, _FakeYahooMonitoring(quality="failed")).run(
            DataRequest(series_ids=["US_EQ"]),
            run_id="monitoring-yahoo-failed-quality",
        )
        calendars, mapping = _calendar_files(tmp_path)
        health = monitoring_data_health(
            store.conn,
            _naive_utc(1),
            market_data_cutoff=date(2026, 9, 16),
            calendar_config=calendars,
            series_calendar_config=mapping,
            series_ids=["US_EQ"],
        )[0]
        assert health["monitoring_status"] == "FAILED"
        assert health["monitoring_fresh"] is False
        assert health["formal_readiness"] == "FORMAL_BLOCKED"
    finally:
        store.close()


def test_monitoring_identity_mismatch_fails_before_raw_or_canonical_persistence(tmp_path):
    store = DuckDBStore(":memory:")
    raw_root = tmp_path / "raw"
    try:
        result = MonitoringRunner(
            store,
            _FakeYahooMonitoring(source_series_id="SPY"),
            raw_archive=ImmutableRawArchive(raw_root),
        ).run(
            DataRequest(series_ids=["US_EQ"]),
            run_id="monitoring-yahoo-bad-identity",
        )

        assert result["status"] == "failed"
        assert result["rows_written"] == 0
        assert result["errors"]["US_EQ"] == [
            "monitoring_source_series_id_mismatch:SPY"
        ]
        assert store.conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 0
        assert not raw_root.exists()
        attempt = store.conn.execute(
            "SELECT status,schema_error FROM provider_attempts WHERE series_id='US_EQ'"
        ).fetchone()
        assert attempt[0] == "SCHEMA_ERROR"
        assert "monitoring_source_series_id_mismatch:SPY" in attempt[1]
        event = store.conn.execute(
            "SELECT event_type FROM data_quality_events WHERE series_id='US_EQ'"
        ).fetchone()[0]
        assert event == "MONITORING_SCHEMA_ERROR"
    finally:
        store.close()
