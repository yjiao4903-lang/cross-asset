from __future__ import annotations

import json
import threading
from datetime import UTC, date, datetime
from http.client import HTTPConnection

from cross_asset.decision_support.decision_history import structured_diff
from cross_asset.decision_support.serving import SnapshotReadService, SnapshotStore, make_server
from cross_asset.decision_support.snapshot import DashboardSnapshotV0


def _snapshot(
    snapshot_id: str,
    *,
    week: str,
    decision_time: str,
    run_id: str,
    stance: int = 0,
    confidence: float = 0.6,
    factor_score: float = 0.2,
    regime: str = "GOLDILOCKS",
    missing: list[str] | None = None,
) -> DashboardSnapshotV0:
    missing = missing or []
    as_of = date.fromisoformat(week)
    dt = datetime.fromisoformat(decision_time).astimezone(UTC)
    return DashboardSnapshotV0.model_validate(
        {
            "metadata": {
                "snapshot_id": snapshot_id,
                "as_of": as_of,
                "decision_time": dt,
                "lane": "MONITORING",
                "run_id": run_id,
                "model_version": "decision-support-v2-real-snapshot-v1",
            },
            "macro_climate": {
                "state": "TEST",
                "score": factor_score,
                "confidence": confidence,
                "coverage": 1.0,
            },
            "investment_climate": {"state": "TEST"},
            "climate_components": [],
            "clusters": [
                {
                    "cluster_id": "GROWTH_ACTIVITY@CYCLICAL",
                    "family": "GROWTH_ACTIVITY",
                    "horizon": "CYCLICAL",
                    "score": factor_score,
                    "confidence": confidence,
                    "coverage": 1.0,
                    "missing_factors": missing,
                }
            ],
            "weekly_change": {
                "information_set_delta": {"status": "NO_NEW_INFORMATION"},
                "macro_state_delta": {"entries": []},
                "market_condition_delta": {"moves": []},
                "asset_view_delta": {"entries": []},
            },
            "regime": {
                "quadrant_label": regime,
                "growth_state": "EXPANDING",
                "growth_direction": "FLAT",
                "inflation_state": "LOW",
                "inflation_direction": "FLAT",
                "dwell_weeks": 2,
                "confidence": confidence,
                "coverage": 1.0,
            },
            "asset_views": [
                {
                    "asset": "US_EQ",
                    "macro_bias": stance,
                    "market_confirmation": "CONFIRMED",
                    "stance": stance,
                    "prior_stance": stance,
                    "confidence": confidence,
                    "drivers": ["GROWTH_ACTIVITY"],
                    "counter_signals": [],
                    "invalidator": "test invalidator",
                    "data_health": "OK",
                }
            ],
            "cross_asset_pulse": {"entries": []},
            "executive_brief": {},
            "data_health_summary": {
                "overall": "PARTIAL" if missing else "OK",
                "missing_components": missing,
            },
            "details": {
                "producer": "REAL-SNAPSHOT-V1",
                "economic_week_id": week,
                "data_cutoff": week,
                "config_identity": "decision-support-v2:test",
                "taxonomy_version": 2,
                "binding_registry_version": 3,
                "subfactor_scores_current": {"US_PAYROLLS_TREND": factor_score},
                "factor_statuses": {
                    "US_PAYROLLS_TREND": {
                        "monitoring": "BOUND",
                        "formal": "BLOCKED",
                        "missing": False,
                        "stale": False,
                        "confidence": confidence,
                    }
                },
                "series_provenance": {"US_NONFARM_PAYROLLS": {"source": "FRED:PAYEMS"}},
                "workbench_lineage": {
                    "run_id": run_id,
                    "decision_time": dt.isoformat(),
                    "data_cutoff": week,
                    "source_mode": "LIVE",
                    "config_identity": "decision-support-v2:test",
                },
            },
        }
    )


def test_multiweek_history_restart_same_week_canonical_and_late_backfill(tmp_path):
    store = SnapshotStore(tmp_path)
    week1 = _snapshot(
        "s-w1",
        week="2026-08-31",
        decision_time="2026-09-04T06:00:00+00:00",
        run_id="r-w1",
        stance=0,
    )
    week3 = _snapshot(
        "s-w3",
        week="2026-09-14",
        decision_time="2026-09-18T06:00:00+00:00",
        run_id="r-w3",
        stance=1,
        factor_score=0.8,
    )
    retry1 = _snapshot(
        "s-w2-a",
        week="2026-09-07",
        decision_time="2026-09-10T06:00:00+00:00",
        run_id="r-w2-a",
        stance=0,
        factor_score=0.4,
    )
    retry2 = _snapshot(
        "s-w2-b",
        week="2026-09-07",
        decision_time="2026-09-11T06:00:00+00:00",
        run_id="r-w2-b",
        stance=0,
        factor_score=0.4,
    )
    retry3 = _snapshot(
        "s-w2-c",
        week="2026-09-07",
        decision_time="2026-09-11T06:00:00+00:00",
        run_id="r-w2-c",
        stance=0,
        factor_score=0.4,
    )

    # Persist true current first, then a late-created backfill and same-week retries.
    for snapshot in [week1, week3, retry1, retry2, retry3]:
        store.persist(snapshot)

    assert store.load_latest().metadata.snapshot_id == "s-w3"
    assert [s.metadata.snapshot_id for s in store.list_canonical()] == [
        "s-w1",
        "s-w2-c",
        "s-w3",
    ]
    assert len(store.list_snapshots()) == 5

    # New process/restart sees exactly the same technical and canonical history.
    restarted = SnapshotStore(tmp_path)
    service = SnapshotReadService(restarted)
    history = service.snapshots()
    assert [entry["economic_week_id"] for entry in history["history"]] == [
        "2026-08-31",
        "2026-09-07",
        "2026-09-14",
    ]
    assert history["current"]["snapshot_id"] == "s-w3"
    assert history["prior"]["snapshot_id"] == "s-w2-c"
    w2 = next(entry for entry in history["history"] if entry["economic_week_id"] == "2026-09-07")
    assert w2["superseded_snapshot_ids"] == ["s-w2-a", "s-w2-b"]
    assert history["technical_snapshot_count"] == 5
    assert history["canonical_week_count"] == 3
    assert history["ytd"]["status"] == "DEFERRED"


def test_causal_prior_for_backfill_never_reads_future_snapshot(tmp_path):
    store = SnapshotStore(tmp_path)
    for snapshot in [
        _snapshot("w1", week="2026-08-31", decision_time="2026-09-04T06:00:00+00:00", run_id="r1"),
        _snapshot("w2", week="2026-09-07", decision_time="2026-09-11T06:00:00+00:00", run_id="r2"),
        _snapshot("w3", week="2026-09-14", decision_time="2026-09-18T06:00:00+00:00", run_id="r3"),
    ]:
        store.persist(snapshot)

    prior = store.prior_for(
        decision_time=datetime(2026, 9, 12, 6, tzinfo=UTC),
        current_week_id="2026-09-07",
    )
    assert prior is not None
    assert prior.metadata.snapshot_id == "w1"


def test_asset_stance_history_is_producer_owned_and_auditable(tmp_path):
    store = SnapshotStore(tmp_path)
    store.persist(_snapshot("w1", week="2026-08-31", decision_time="2026-09-04T06:00:00+00:00", run_id="r1", stance=0))
    store.persist(_snapshot("w2", week="2026-09-07", decision_time="2026-09-11T06:00:00+00:00", run_id="r2", stance=1, confidence=0.8))

    payload = SnapshotReadService(store).asset_history("US_EQ")
    assert [(point["snapshot_id"], point["economic_week_id"], point["stance"]) for point in payload["trajectory"]] == [
        ("w1", "2026-08-31", 0),
        ("w2", "2026-09-07", 1),
    ]
    assert payload["trajectory"][1]["drivers"] == ["GROWTH_ACTIVITY"]
    assert payload["ytd"]["status"] == "DEFERRED"


def test_structured_diff_reports_real_state_changes_but_same_week_rebuild_does_not_invent_them():
    prior = _snapshot("w1", week="2026-08-31", decision_time="2026-09-04T06:00:00+00:00", run_id="r1", stance=0, factor_score=0.2)
    current = _snapshot("w2", week="2026-09-07", decision_time="2026-09-11T06:00:00+00:00", run_id="r2", stance=1, factor_score=0.9, regime="REFLATION", missing=["X"])
    changed = structured_diff(current, prior)
    assert changed["has_state_changes"] is True
    assert "US_PAYROLLS_TREND" in changed["changes"]["factor_states"]
    assert "GROWTH_ACTIVITY@CYCLICAL" in changed["changes"]["clusters"]
    assert changed["changes"]["regime"] is not None
    assert "US_EQ" in changed["changes"]["asset_views"]
    assert changed["changes"]["data_health"] is not None
    assert changed["evidence"]["current_run_id"] == "r2"

    retry_a = _snapshot("retry-a", week="2026-09-07", decision_time="2026-09-10T06:00:00+00:00", run_id="ra", stance=1, factor_score=0.9)
    retry_b = _snapshot("retry-b", week="2026-09-07", decision_time="2026-09-11T06:00:00+00:00", run_id="rb", stance=1, factor_score=0.9)
    same_week = structured_diff(retry_b, retry_a)
    assert same_week["same_economic_week"] is True
    assert same_week["has_state_changes"] is False
    assert all(value in ({}, None) for value in same_week["changes"].values())


def test_history_api_preserves_latest_by_id_and_exposes_history_diff_and_asset(tmp_path):
    store = SnapshotStore(tmp_path)
    first = _snapshot("w1", week="2026-08-31", decision_time="2026-09-04T06:00:00+00:00", run_id="r1", stance=0)
    second = _snapshot("w2", week="2026-09-07", decision_time="2026-09-11T06:00:00+00:00", run_id="r2", stance=1, factor_score=0.6)
    store.persist(first)
    store.persist(second)
    server = make_server(store, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        connection.request("GET", "/api/snapshot/latest")
        latest = json.loads(connection.getresponse().read())
        assert latest["metadata"]["snapshot_id"] == "w2"

        connection.request("GET", "/api/snapshot/w1")
        by_id = json.loads(connection.getresponse().read())
        assert by_id["metadata"]["snapshot_id"] == "w1"

        connection.request("GET", "/api/snapshots?view=canonical&limit=2")
        history = json.loads(connection.getresponse().read())
        assert [row["snapshot_id"] for row in history["history"]] == ["w1", "w2"]

        connection.request("GET", "/api/history/assets/US_EQ")
        stance = json.loads(connection.getresponse().read())
        assert [row["stance"] for row in stance["trajectory"]] == [0, 1]

        connection.request("GET", "/api/snapshot/w2/diff/w1")
        diff = json.loads(connection.getresponse().read())
        assert diff["has_state_changes"] is True
        assert diff["ytd"]["status"] == "DEFERRED"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
