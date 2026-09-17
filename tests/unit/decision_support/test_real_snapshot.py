from __future__ import annotations

import json
import threading
from datetime import UTC, date, datetime, timedelta
from http.client import HTTPConnection

import pandas as pd
import pytest

from cross_asset.decision_support.producer import (
    MonitoringObservation,
    MonitoringObservationPack,
    MonitoringRunLineage,
    MonitoringSeries,
    build_monitoring_snapshot,
)
from cross_asset.decision_support.serving import SnapshotReadService, SnapshotStore, make_server

AS_OF = date(2026, 9, 11)
DECISION = datetime(2026, 9, 12, 6, tzinfo=UTC)


def _series(series_id: str, dates, values, *, status: str = "FRESH") -> MonitoringSeries:
    return MonitoringSeries(
        series_id=series_id,
        status=status,
        observations=[
            MonitoringObservation(
                observation_date=stamp.date(),
                available_at=datetime.combine(stamp.date(), datetime.min.time(), tzinfo=UTC)
                + timedelta(hours=18),
                value=float(value),
                source_ref=f"canonical:{series_id}",
            )
            for stamp, value in zip(dates, values, strict=True)
        ],
        provenance={"route": "test-canonical-monitoring-pack", "series_id": series_id},
    )


def _pack(*, omit: set[str] | None = None, source_mode: str = "LIVE") -> MonitoringObservationPack:
    omit = omit or set()
    daily = pd.bdate_range(end=AS_OF, periods=90)
    weekly = pd.date_range(end=AS_OF, periods=40, freq="W-FRI")
    monthly = pd.date_range(end=date(2026, 9, 1), periods=40, freq="MS")

    definitions = {
        "US_NONFARM_PAYROLLS": (monthly, [130000 + i * 175 + (i % 4) * 25 for i in range(40)]),
        "US_CPI_CORE": (monthly, [250 + i * 0.55 + (i % 5) * 0.07 for i in range(40)]),
        "US_TSY_10Y": (daily, [3.5 + i * 0.004 + (i % 9) * 0.006 for i in range(90)]),
        "US_TSY_2Y": (daily, [3.8 + i * 0.002 + (i % 7) * 0.004 for i in range(90)]),
        "US_REAL_10Y": (daily, [1.5 + i * 0.002 + (i % 8) * 0.003 for i in range(90)]),
        "US_NFCI": (weekly, [-0.1 - i * 0.003 + (i % 5) * 0.002 for i in range(40)]),
        "USD_BROAD_INDEX": (daily, [100 + i * 0.03 + (i % 6) * 0.02 for i in range(90)]),
        "US_EQ": (daily, [5000 + i * 7 + (i % 4) * 2 for i in range(90)]),
        "CN_EQ_LARGE": (daily, [3500 + i * 3 + (i % 5) * 2 for i in range(90)]),
        "GOLD": (daily, [2900 + i * 4 + (i % 7) * 3 for i in range(90)]),
        "COPPER": (daily, [4.0 + i * 0.006 + (i % 5) * 0.003 for i in range(90)]),
    }
    series = [
        _series(series_id, dates, values)
        for series_id, (dates, values) in definitions.items()
        if series_id not in omit
    ]
    return MonitoringObservationPack(
        as_of=AS_OF,
        lineage=MonitoringRunLineage(
            run_id="wb-real-monitoring-001",
            decision_time=DECISION,
            data_cutoff=AS_OF,
            source_mode=source_mode,
            config_identity="decision-support-v2:test",
        ),
        series=series,
    )


def test_non_fixture_monitoring_pack_produces_valid_snapshot_and_truthful_lane_statuses():
    snapshot = build_monitoring_snapshot(_pack())

    assert snapshot.metadata.lane.value == "MONITORING"
    assert snapshot.metadata.run_id == "wb-real-monitoring-001"
    assert snapshot.details["origin"] == "CANONICAL_MONITORING"
    assert snapshot.details["binding_counts"]["monitoring_bound"] == 10
    assert snapshot.details["binding_counts"]["formal_blocked"] == 10
    payroll = next(
        item for item in snapshot.details["factor_bindings"] if item["factor_id"] == "US_PAYROLLS_TREND"
    )
    assert payroll["monitoring"]["status"] == "BOUND"
    assert payroll["formal"]["status"] == "BLOCKED"
    assert payroll["canonical_series_ids"] == ["US_NONFARM_PAYROLLS"]
    assert snapshot.macro_climate.score is not None
    assert snapshot.regime.coverage < 1.0
    assert snapshot.to_json() == build_monitoring_snapshot(_pack()).to_json()


def test_missing_bound_factor_stays_missing_and_lowers_coverage():
    snapshot = build_monitoring_snapshot(_pack(omit={"US_EQ"}))

    state = snapshot.details["factor_statuses"]["US_EQ_TREND_63D"]
    assert state["missing"] is True
    market = next(
        cluster
        for cluster in snapshot.clusters
        if cluster.family == "MARKET_CONFIRMATION" and cluster.horizon.value == "TACTICAL"
    )
    assert "US_EQ_TREND_63D" in market.missing_factors
    assert market.coverage < 1.0
    assert "US_EQ_TREND_63D" in snapshot.data_health_summary.missing_components


def test_non_live_or_non_monitoring_origin_cannot_enter_real_producer():
    with pytest.raises(ValueError, match="REQUIRES_LIVE"):
        build_monitoring_snapshot(_pack(source_mode="FIXTURE"))

    pack = _pack().model_copy(update={"origin": "FIXTURE"})
    with pytest.raises(ValueError, match="REJECTS_FIXTURE"):
        build_monitoring_snapshot(pack)


def test_no_new_low_frequency_information_creates_no_synthetic_macro_movement():
    first = build_monitoring_snapshot(_pack())
    later_lineage = _pack().lineage.model_copy(
        update={
            "run_id": "wb-real-monitoring-002",
            "decision_time": DECISION + timedelta(days=7),
            "data_cutoff": AS_OF + timedelta(days=7),
        }
    )
    second_pack = _pack().model_copy(
        update={"as_of": AS_OF + timedelta(days=7), "lineage": later_lineage}
    )
    second = build_monitoring_snapshot(second_pack, previous_snapshot=first)

    assert second.weekly_change.information_set_delta.status.value == "NO_NEW_INFORMATION"
    assert all(entry.delta == 0.0 for entry in second.weekly_change.macro_state_delta.entries)


def test_snapshot_store_and_read_service_surface_latest_by_id_factors_asset_and_health(tmp_path):
    snapshot = build_monitoring_snapshot(_pack())
    store = SnapshotStore(tmp_path)
    path = store.persist(snapshot)
    service = SnapshotReadService(store)

    assert path.exists()
    assert service.latest()["metadata"]["snapshot_id"] == snapshot.metadata.snapshot_id
    assert service.by_id(snapshot.metadata.snapshot_id)["metadata"]["run_id"] == "wb-real-monitoring-001"
    factors = service.factors()["factors"]
    assert next(item for item in factors if item["factor_id"] == "US_10Y_REAL_YIELD")["formal"]["status"] == "BLOCKED"
    assert service.asset("US_EQ")["asset_view"]["asset"] == "US_EQ"
    assert service.data_health()["binding_counts"]["monitoring_bound"] == 10
    assert service.health()["status"] == "OK"


def test_http_api_serves_latest_snapshot_without_mutation_routes(tmp_path):
    snapshot = build_monitoring_snapshot(_pack())
    store = SnapshotStore(tmp_path)
    store.persist(snapshot)
    server = make_server(store, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        connection.request("GET", "/api/snapshot/latest")
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["metadata"]["snapshot_id"] == snapshot.metadata.snapshot_id
        connection.request("GET", "/api/health")
        health_response = connection.getresponse()
        health = json.loads(health_response.read())
        assert health_response.status == 200
        assert health["snapshot_version"] == "DashboardSnapshotV0"
        connection.request("GET", "/api/not-a-route")
        missing = connection.getresponse()
        missing.read()
        assert missing.status == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
