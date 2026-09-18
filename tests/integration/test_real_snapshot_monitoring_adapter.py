from __future__ import annotations

import json
import threading
from datetime import UTC, date, datetime
from http.client import HTTPConnection

import pandas as pd

from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db
from cross_asset.decision_support.producer import (
    build_monitoring_snapshot,
    score_monitoring_factors,
)
from cross_asset.decision_support.serving import SnapshotStore, make_server
from cross_asset.operations.workbench_run import WorkbenchRun
from cross_asset.storage.catalog import sync_series_catalog
from cross_asset.storage.duckdb import DuckDBStore


def _monthly_rows(
    series_id: str,
    source_series_id: str,
    values: list[float],
    *,
    capture_time: datetime,
) -> list[dict]:
    months = pd.date_range(end=date(2026, 9, 1), periods=len(values), freq="MS")
    return [
        {
            "series_id": series_id,
            "observation_date": stamp.date(),
            # #129 monitoring history is capture-time/non-PIT. Every historical
            # row is known no earlier than this monitoring capture.
            "available_at": capture_time,
            "value": float(value),
            "source": "fred",
            "source_series_id": source_series_id,
            "ingested_at": capture_time,
            "quality": "ok",
        }
        for stamp, value in zip(months, values, strict=True)
    ]


def test_merged_monitoring_db_to_factor_snapshot_and_http_api(tmp_path):
    store = DuckDBStore(":memory:")
    capture_time = datetime(2026, 9, 12, 0, tzinfo=UTC)
    decision_time = datetime(2026, 9, 12, 6, tzinfo=UTC)
    try:
        # Consume the accepted #129 canonical identities, not provider-code aliases.
        sync_series_catalog(
            store,
            series_ids=["US_NONFARM_PAYROLLS", "US_CORE_CPI"],
            provider="fred",
        )
        ingestion_run_id = "monitoring-fred-real-snapshot-integration"
        store.start_run("MONITORING:fred", ingestion_run_id, requested_series=2)

        payroll_levels = [
            145000
            + index * 145
            + (index % 5) * 18
            + (index // 12) * 23
            for index in range(48)
        ]
        cpi_levels: list[float] = [270.0]
        monthly_rates = [0.0018, 0.0022, 0.0027, 0.0031, 0.0025, 0.0020]
        for index in range(1, 48):
            cpi_levels.append(cpi_levels[-1] * (1.0 + monthly_rates[index % 6]))

        rows = _monthly_rows(
            "US_NONFARM_PAYROLLS",
            "PAYEMS",
            payroll_levels,
            capture_time=capture_time,
        )
        rows += _monthly_rows(
            "US_CORE_CPI",
            "CPILFESL",
            cpi_levels,
            capture_time=capture_time,
        )
        store.insert_observations(rows, run_id=ingestion_run_id)
        store.finish_run(
            ingestion_run_id,
            "success",
            success_series=2,
            failed_series=0,
            rows_written=len(rows),
        )

        workbench = WorkbenchRun(
            run_id="wb-monitoring-real-regime-001",
            run_kind="shadow",
            source_mode="LIVE",
            status="SUCCESS",
            model_version="workbench_v0.1",
            config_identity="decision-support-v2:real-integration",
            data_cutoff="2026-09-11",
            decision_time=decision_time.isoformat(),
        )
        pack = build_monitoring_pack_from_db(store, workbench)
        by_series = {item.series_id: item for item in pack.series}

        assert pack.origin == "CANONICAL_MONITORING"
        assert pack.lineage.run_id == workbench.run_id
        assert pack.lineage.decision_time == decision_time
        assert pack.lineage.source_mode == "LIVE"

        payroll = by_series["US_NONFARM_PAYROLLS"]
        core_cpi = by_series["US_CORE_CPI"]
        # Publication freshness is intentionally not fabricated. #127 remains
        # BLOCKED at read-model level; #124 consumes the captured history as
        # reduced-confidence/stale monitoring evidence per the accepted #129 contract.
        assert payroll.status == "STALE"
        assert core_cpi.status == "STALE"
        assert payroll.provenance["monitoring_status"] == "BLOCKED"
        assert core_cpi.provenance["monitoring_status"] == "BLOCKED"
        assert payroll.provenance["monitoring_reason"] == "calendar_mapping_missing"
        assert core_cpi.provenance["monitoring_reason"] == "calendar_mapping_missing"
        assert payroll.provenance["freshness_verified"] is False
        assert core_cpi.provenance["freshness_verified"] is False
        assert "fred:PAYEMS" in payroll.provenance["source_refs"]
        assert "fred:CPILFESL" in core_cpi.provenance["source_refs"]
        assert payroll.provenance["formal_admission_granted"] is False
        assert core_cpi.provenance["formal_admission_granted"] is False

        scores, statuses = score_monitoring_factors(pack)
        assert scores["US_PAYROLLS_TREND"].missing is False
        assert scores["US_CORE_CPI_TREND"].missing is False
        assert scores["US_PAYROLLS_TREND"].score is not None
        assert scores["US_CORE_CPI_TREND"].score is not None
        assert scores["US_PAYROLLS_TREND"].confidence == 0.5
        assert scores["US_CORE_CPI_TREND"].confidence == 0.5
        assert statuses["US_PAYROLLS_TREND"]["stale"] is True
        assert statuses["US_CORE_CPI_TREND"]["stale"] is True
        assert statuses["USD_BROAD_MOMENTUM"]["monitoring"] == "UNBOUND"
        assert statuses["US_YIELD_CURVE_10Y2Y"]["monitoring"] == "UNBOUND"

        snapshot = build_monitoring_snapshot(pack)
        assert snapshot.metadata.run_id == workbench.run_id
        assert snapshot.metadata.lane.value == "MONITORING"
        assert snapshot.macro_climate.score is not None
        assert snapshot.regime is not None
        assert snapshot.details["binding_counts"]["monitoring_bound"] == 7
        assert snapshot.details["binding_counts"]["formal_blocked"] == 7
        assert snapshot.data_health_summary.overall.value == "PARTIAL"
        assert snapshot.details["series_provenance"]["US_NONFARM_PAYROLLS"][
            "formal_admission_granted"
        ] is False

        snapshot_store = SnapshotStore(tmp_path / "snapshots")
        snapshot_store.persist(snapshot)
        server = make_server(snapshot_store, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            connection.request("GET", "/api/snapshot/latest")
            response = connection.getresponse()
            payload = json.loads(response.read())
            assert response.status == 200
            assert payload["metadata"]["snapshot_id"] == snapshot.metadata.snapshot_id
            assert payload["metadata"]["run_id"] == workbench.run_id
            assert payload["details"]["binding_counts"]["monitoring_bound"] == 7
            assert payload["details"]["series_provenance"]["US_CORE_CPI"][
                "freshness_verified"
            ] is False
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    finally:
        store.close()
