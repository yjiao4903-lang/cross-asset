from datetime import UTC, date, datetime, timedelta

from cross_asset.domain.models import DataRequest, Observation
from cross_asset.ingestion.monitoring import MonitoringRunner
from cross_asset.providers.monitoring import FREDMonitoringProvider
from cross_asset.reports.monitoring_health import monitoring_data_health
from cross_asset.storage import DuckDBStore, latest_formal_observations_asof
from cross_asset.storage.acceptance_registry import upsert_data_acceptance

SERIES_IDS = [
    "US_NONFARM_PAYROLLS",
    "US_CORE_CPI",
    "US_GOV_2Y",
    "US_REAL_10Y",
]
SOURCE_IDS = {
    "US_NONFARM_PAYROLLS": "PAYEMS",
    "US_CORE_CPI": "CPILFESL",
    "US_GOV_2Y": "DGS2",
    "US_REAL_10Y": "DFII10",
}


def _fake_public_csv(self, request):
    series = {}
    for sid in request.series_ids:
        code = request.source_series_ids[sid]
        payload = (
            f"observation_date,{code}\n"
            f"2020-01-01,100.0\n"
            f"2026-08-01,101.0\n"
        ).encode()
        self.raw_archive.write("fred", f"public_csv_{code}", payload, extension="csv")
        series[sid] = {"source_series_id": code, "row_count": 2}
    return {"status": "PARTIAL", "source_mode": "FRED_PUBLIC_GRAPH_CSV", "series": series}


def _accept_exact_fred_identity(store, usage_status):
    now = datetime.now(UTC)
    upsert_data_acceptance(
        store,
        {
            "series_id": "US_NONFARM_PAYROLLS",
            "provider": "fred",
            "source_series_id": "PAYEMS",
            "status": "PASS",
            "tech_gate": "PASS",
            "legal_gate": "PASS",
            "pit_gate": "PASS",
            "stability_gate": "PASS",
            "pit_grade": "B",
            "origin": "LIVE",
            "permission_scope": "monitoring-source-expansion-test",
            "semantic_equivalence": True,
            "manifest_hash": f"fred-payems-{usage_status}",
            "reviewer": "reviewer",
            "approved_at": now,
            "evidence_json": "{}",
            "updated_at": now,
            "usage_status": usage_status,
        },
    )


def test_fred_monitoring_pipeline_persists_history_but_never_promotes_formal(monkeypatch):
    monkeypatch.setattr(
        "cross_asset.providers.monitoring.FREDProvider.fetch_public_csv_sample",
        _fake_public_csv,
    )
    store = DuckDBStore(":memory:")
    try:
        result = MonitoringRunner(store, FREDMonitoringProvider()).run(
            DataRequest(series_ids=SERIES_IDS),
            run_id="monitoring-fred-exact-us-macro",
        )
        assert result["lane"] == "MONITORING"
        assert result["status"] == "success"
        assert result["rows_written"] == 8
        assert result["series_catalog_rows"] == 4
        assert result["source_mapping_rows"] == 4
        assert result["formal_admission_attempted"] is False
        assert store.conn.execute(
            "SELECT count(*) FROM data_acceptance_registry"
        ).fetchone()[0] == 0

        identities = store.conn.execute(
            """SELECT series_id,source_series_id,count(*)
               FROM observations
               GROUP BY series_id,source_series_id
               ORDER BY series_id"""
        ).fetchall()
        assert identities == [
            ("US_CORE_CPI", "CPILFESL", 2),
            ("US_GOV_2Y", "DGS2", 2),
            ("US_NONFARM_PAYROLLS", "PAYEMS", 2),
            ("US_REAL_10Y", "DFII10", 2),
        ]
        assert store.conn.execute(
            "SELECT provider FROM ingestion_runs WHERE run_id='monitoring-fred-exact-us-macro'"
        ).fetchone()[0] == "MONITORING:fred"

        _accept_exact_fred_identity(store, "LIVE_VERIFIED")
        _accept_exact_fred_identity(store, "RESEARCH_ADMISSIBLE")
        decision_time = datetime.now(UTC) + timedelta(minutes=1)
        for usage_status in ("LIVE_VERIFIED", "RESEARCH_ADMISSIBLE"):
            formal = latest_formal_observations_asof(
                store.conn,
                decision_time,
                required_usage_status=usage_status,
                series_ids=["US_NONFARM_PAYROLLS"],
                market_data_cutoff=date(2026, 8, 1),
            )
            assert formal.empty

        health = monitoring_data_health(
            store.conn,
            decision_time.replace(tzinfo=None),
            market_data_cutoff=date(2026, 8, 1),
            series_ids=["US_NONFARM_PAYROLLS"],
        )[0]
        assert health["monitoring_status"] == "BLOCKED"
        assert health["monitoring_reason"] == "calendar_mapping_missing"
        assert health["formal_readiness"] == "FORMAL_BLOCKED"
        assert health["usage_separation"] == "MONITORING_NOT_FORMAL"
    finally:
        store.close()


class _WrongFredIdentity:
    name = "fred"
    last_error = None

    def fetch(self, request):
        return [
            Observation(
                series_id="US_NONFARM_PAYROLLS",
                observation_date=date(2026, 8, 1),
                available_at=datetime.now(UTC),
                value=100.0,
                source="fred",
                source_series_id="ICSA",
                frequency="monthly",
                unit="thousands_persons",
                metadata={
                    "origin": "MONITORING",
                    "usage_lane": "MONITORING_ONLY",
                },
            )
        ]


def test_fred_monitoring_wrong_source_identity_is_rejected_before_persistence():
    store = DuckDBStore(":memory:")
    try:
        result = MonitoringRunner(store, _WrongFredIdentity()).run(
            DataRequest(series_ids=["US_NONFARM_PAYROLLS"]),
            run_id="monitoring-fred-wrong-payroll-identity",
        )
        assert result["status"] == "failed"
        assert result["rows_written"] == 0
        assert result["errors"]["US_NONFARM_PAYROLLS"] == [
            "monitoring_source_series_id_mismatch:ICSA"
        ]
        assert store.conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 0
        event = store.conn.execute(
            "SELECT event_type FROM data_quality_events WHERE series_id='US_NONFARM_PAYROLLS'"
        ).fetchone()[0]
        assert event == "MONITORING_SCHEMA_ERROR"
    finally:
        store.close()
