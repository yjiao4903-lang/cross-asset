from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from cross_asset.decision_support.binding import (
    FactorBinding,
    FactorBindingRegistry,
    FactorTransform,
    LaneBinding,
)
from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db
from cross_asset.decision_support.producer import (
    MonitoringSnapshotBlocked,
    build_monitoring_snapshot,
    score_monitoring_factors,
)
from cross_asset.operations.workbench_run import WorkbenchRun
from cross_asset.storage.catalog import sync_series_catalog
from cross_asset.storage.duckdb import DuckDBStore


def _us_eq_registry() -> FactorBindingRegistry:
    return FactorBindingRegistry(
        version=99,
        contract="TEST_CURRENT_GOVERNED_BINDING",
        bindings=[
            FactorBinding(
                factor_id="US_EQ_TREND_63D",
                canonical_series_ids=["US_EQ"],
                transform=FactorTransform(type="TREND_63D"),
                monitoring=LaneBinding(
                    route="CANONICAL_MONITORING_OBSERVATIONS",
                    status="BOUND",
                ),
                formal=LaneBinding(route="SANCTIONED_FORMAL_QUERY", status="BLOCKED"),
            )
        ],
    )


def test_merged_monitoring_db_builds_pack_and_factor_without_hand_authored_json():
    store = DuckDBStore(":memory:")
    try:
        sync_series_catalog(store, series_ids=["US_EQ"], provider="yahoo")
        ingestion_run_id = "monitoring-yahoo-integration"
        store.start_run("MONITORING:yahoo", ingestion_run_id, requested_series=1)
        days = pd.bdate_range(end=date(2026, 9, 11), periods=90)
        rows = []
        for index, stamp in enumerate(days):
            obs_date = stamp.date()
            rows.append(
                {
                    "series_id": "US_EQ",
                    "observation_date": obs_date,
                    "available_at": datetime.combine(
                        obs_date, datetime.min.time(), tzinfo=UTC
                    )
                    + timedelta(hours=18),
                    "value": 5000.0 + index * 5.0,
                    "source": "yahoo",
                    "source_series_id": "^GSPC",
                    "ingested_at": datetime(2026, 9, 12, 0, tzinfo=UTC),
                    "quality": "ok",
                }
            )
        store.insert_observations(rows, run_id=ingestion_run_id)
        store.finish_run(
            ingestion_run_id,
            "success",
            success_series=1,
            failed_series=0,
            rows_written=len(rows),
        )

        workbench = WorkbenchRun(
            run_id="wb-monitoring-integration",
            run_kind="shadow",
            source_mode="LIVE",
            status="SUCCESS",
            model_version="workbench_v0.1",
            config_identity="decision-support-v2:test",
            data_cutoff="2026-09-11",
            decision_time="2026-09-12T06:00:00+00:00",
        )
        registry = _us_eq_registry()
        pack = build_monitoring_pack_from_db(store, workbench, registry=registry)

        assert pack.lineage.run_id == workbench.run_id
        assert pack.lineage.source_mode == "LIVE"
        assert pack.origin == "CANONICAL_MONITORING"
        assert [series.series_id for series in pack.series] == ["US_EQ"]
        assert pack.series[0].status == "FRESH"
        assert ingestion_run_id in pack.series[0].provenance["ingestion_run_ids"]
        assert pack.series[0].provenance["formal_admission_granted"] is False

        scores, _ = score_monitoring_factors(pack, registry=registry)
        assert scores["US_EQ_TREND_63D"].missing is False
        assert scores["US_EQ_TREND_63D"].score is not None

        # Until #129 supplies governed growth + inflation raw identities, the
        # same real DB path must fail closed rather than manufacture a regime.
        with pytest.raises(MonitoringSnapshotBlocked, match="regime axes unavailable"):
            build_monitoring_snapshot(pack, registry=registry)
    finally:
        store.close()
