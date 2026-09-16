from datetime import UTC, date, datetime

from cross_asset.storage import DuckDBStore, latest_formal_observations_asof
from cross_asset.storage.acceptance_registry import upsert_data_acceptance

DECISION_TIME = datetime(2026, 9, 17, 1, tzinfo=UTC)
OBS_DATE = date(2026, 9, 16)
AVAILABLE_AT = datetime(2026, 9, 16, 21, tzinfo=UTC)


def _accept(store, usage_status):
    approved_at = datetime(2026, 9, 16, 20, tzinfo=UTC)
    upsert_data_acceptance(
        store,
        {
            "series_id": "US_EQ",
            "provider": "yahoo",
            "source_series_id": "^GSPC",
            "status": "PASS",
            "tech_gate": "PASS",
            "legal_gate": "PASS",
            "pit_gate": "PASS",
            "stability_gate": "PASS",
            "pit_grade": "B",
            "origin": "LIVE",
            "permission_scope": "formal-guard-test",
            "semantic_equivalence": True,
            "manifest_hash": f"manifest-{usage_status}",
            "reviewer": "reviewer",
            "approved_at": approved_at,
            "evidence_json": "{}",
            "updated_at": approved_at,
            "usage_status": usage_status,
        },
    )


def _observe(store, *, run_id, run_provider):
    store.start_run(
        run_provider,
        run_id,
        requested_series=1,
        started_at=AVAILABLE_AT,
    )
    store.insert_observations(
        [
            {
                "series_id": "US_EQ",
                "observation_date": OBS_DATE,
                "available_at": AVAILABLE_AT,
                "value": 7000.0,
                "source": "yahoo",
                "source_series_id": "^GSPC",
                "vintage_date": None,
                "ingested_at": AVAILABLE_AT,
                "quality": "ok",
                "raw_file": "monitoring-formal-guard-test",
            }
        ],
        run_id=run_id,
    )
    store.finish_run(
        run_id,
        "success",
        success_series=1,
        failed_series=0,
        rows_written=1,
    )


def test_matching_formal_registry_cannot_promote_monitoring_lineage():
    store = DuckDBStore(":memory:")
    try:
        _accept(store, "LIVE_VERIFIED")
        _accept(store, "RESEARCH_ADMISSIBLE")
        _observe(
            store,
            run_id="monitoring-yahoo-exact-formal-identity",
            run_provider="MONITORING:yahoo",
        )

        for usage_status in ("LIVE_VERIFIED", "RESEARCH_ADMISSIBLE"):
            formal = latest_formal_observations_asof(
                store.conn,
                DECISION_TIME,
                required_usage_status=usage_status,
                series_ids=["US_EQ"],
                market_data_cutoff=OBS_DATE,
            )
            assert formal.empty
    finally:
        store.close()


def test_non_monitoring_exact_approved_identity_remains_formal():
    store = DuckDBStore(":memory:")
    try:
        _accept(store, "LIVE_VERIFIED")
        _observe(
            store,
            run_id="formal-yahoo-exact-identity",
            run_provider="yahoo",
        )
        formal = latest_formal_observations_asof(
            store.conn,
            DECISION_TIME,
            required_usage_status="LIVE_VERIFIED",
            series_ids=["US_EQ"],
            market_data_cutoff=OBS_DATE,
        )
        assert len(formal) == 1
        assert formal.iloc[0]["source"] == "yahoo"
        assert formal.iloc[0]["source_series_id"] == "^GSPC"
    finally:
        store.close()
