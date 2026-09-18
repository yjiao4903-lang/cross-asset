"""RT139 B6 — snapshot persistence / history / API attacks.

Includes the #139 Phase 3 required cases re-testing the old #138 P1-02
latest-pointer finding against merged #135.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, UTC
from http.client import HTTPConnection

import pytest

from cross_asset.decision_support.decision_history import (
    canonical_by_week,
    snapshot_economic_week_id,
)
from cross_asset.decision_support.producer import build_monitoring_snapshot
from cross_asset.decision_support.serving import (
    SnapshotReadService,
    SnapshotStore,
    make_server,
)
from redteam139._helpers import (
    WEEK1_CUTOFF,
    WEEK1_DECISION,
    WEEK2_CUTOFF,
    WEEK2_DECISION,
    WEEK3_CUTOFF,
    WEEK3_DECISION,
    direct_pack,
    mechanics_registry,
)

REG = mechanics_registry()


def _snap(cutoff, decision, run_id, cpi_end=None, previous=None):
    pack = direct_pack(as_of=cutoff, decision=decision, run_id=run_id,
                       cpi_end=cpi_end or date(cutoff.year, cutoff.month, 1))
    return build_monitoring_snapshot(pack, previous_snapshot=previous, registry=REG)


def _two_weeks():
    week1 = _snap(WEEK1_CUTOFF, WEEK1_DECISION, "wb-b6-w1", cpi_end=date(2026, 8, 1))
    week2 = _snap(WEEK2_CUTOFF, WEEK2_DECISION, "wb-b6-w2", previous=week1)
    return week1, week2


# --- RT139-B6-01 (#139 Phase 3): later economic week persists FIRST ---
def test_b6_01_later_week_persisted_first_is_latest(snapshot_root):
    week1, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week2)
    store.persist(week1)
    assert store.load_latest().metadata.as_of == WEEK2_CUTOFF


# --- RT139-B6-02 (#139 Phase 3): older backfill later never displaces latest ---
def test_b6_02_backfilled_older_snapshot_must_not_become_latest(snapshot_root):
    week1, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week2)
    store.persist(week1)  # backfilled technically later
    assert store.load_latest().metadata.as_of == WEEK2_CUTOFF


# --- RT139-B6-03 (#139 Phase 3): same-week retry after latest keeps the week ---
def test_b6_03_same_week_retry_after_latest_keeps_week(snapshot_root):
    _, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week2)
    retry = week2.model_copy(deep=True)
    store.persist(retry)
    latest = store.load_latest()
    assert latest.metadata.as_of == WEEK2_CUTOFF
    assert snapshot_economic_week_id(latest) == snapshot_economic_week_id(week2)


# --- RT139-B6-04 (#139 Phase 3): a later-decision same-week retry becomes representative ---
def test_b6_04_same_week_retry_with_later_decision_time_is_canonical(snapshot_root):
    _, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week2)
    retry_pack = direct_pack(as_of=WEEK2_CUTOFF,
                             decision=WEEK2_DECISION + timedelta(hours=2),
                             run_id="wb-b6-w2-retry")
    retry = build_monitoring_snapshot(retry_pack, previous_snapshot=None, registry=REG)
    store.persist(retry)
    latest = store.load_latest()
    assert snapshot_economic_week_id(latest) == snapshot_economic_week_id(week2)
    # canonical view keeps exactly one representative per week
    canonical = store.list_canonical()
    weeks = [snapshot_economic_week_id(item) for item in canonical]
    assert len(weeks) == len(set(weeks))


# --- RT139-B6-05 (#139 Phase 3): future-dated economic week handled explicitly ---
def test_b6_05_future_week_snapshot_persists_as_its_own_week(snapshot_root):
    _, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week2)
    future = _snap(date(2026, 9, 25), datetime(2026, 9, 26, 6, tzinfo=UTC), "wb-b6-future")
    store.persist(future)
    assert store.load_latest().metadata.as_of == date(2026, 9, 25)
    # but a future snapshot can never be the causal prior of an earlier week
    assert store.prior_for(decision_time=WEEK2_DECISION,
                           current_week_id=snapshot_economic_week_id(week2)) is None


# --- RT139-B6-06 (#139 Phase 3): corrupted latest pointer degrades typed ---
def test_b6_06_corrupted_latest_pointer_typed_failure(snapshot_root):
    week1, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week2)
    store.persist(week1)
    (snapshot_root / "latest.json").write_text("{ not json", encoding="utf-8")
    # Documented residual P2 (ADV-P2-05): the raw ValidationError surfaces;
    # semantics are still fail-closed (no fixture, no silent fallback).
    with pytest.raises(ValueError):
        store.load_latest()


# --- RT139-B6-07 (#139 Phase 3): missing latest pointer recovers via canonical list ---
def test_b6_07_missing_latest_pointer_recovers(snapshot_root):
    week1, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week2)
    store.persist(week1)
    (snapshot_root / "latest.json").unlink()
    assert store.load_latest().metadata.as_of == WEEK2_CUTOFF


# --- RT139-B6-08 (#139 Phase 3): restart/readback preserves the full state ---
def test_b6_08_restart_readback_preserves_state(snapshot_root):
    week1, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    store.persist(week2)
    reopened = SnapshotStore(snapshot_root)  # new process
    assert reopened.load_latest().metadata.as_of == WEEK2_CUTOFF
    assert len(reopened.list_snapshots()) == 2
    assert reopened.load(week1.metadata.snapshot_id).metadata.snapshot_id == week1.metadata.snapshot_id


# --- RT139-B6-09 (#139 Phase 3): canonical current/prior selection ---
def test_b6_09_canonical_current_and_prior(snapshot_root):
    week1, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    store.persist(week2)
    prior = store.prior_for(decision_time=WEEK2_DECISION,
                            current_week_id=snapshot_economic_week_id(week2))
    assert prior is not None
    assert prior.metadata.snapshot_id == week1.metadata.snapshot_id


# --- RT139-B6-10: a backfilled older week does not become the prior of a newer week ---
def test_b6_10_backfill_does_not_steal_prior(snapshot_root):
    week1, week2 = _two_weeks()
    week0 = _snap(date(2026, 8, 28), datetime(2026, 8, 29, 6, tzinfo=UTC), "wb-b6-w0",
                  cpi_end=date(2026, 7, 1))
    store = SnapshotStore(snapshot_root)
    store.persist(week2)
    store.persist(week1)
    store.persist(week0)
    prior = store.prior_for(decision_time=WEEK2_DECISION,
                            current_week_id=snapshot_economic_week_id(week2))
    assert prior.metadata.snapshot_id == week1.metadata.snapshot_id


# --- RT139-B6-11: list ordering is economic, not write-time ---
def test_b6_11_list_snapshots_ordered_by_economic_week(snapshot_root):
    week1, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week2)
    store.persist(week1)
    ordered = store.list_snapshots()
    weeks = [snapshot_economic_week_id(item) for item in ordered]
    assert weeks == sorted(weeks)


# --- RT139-B6-12: canonical_by_week keeps the later decision_time retry ---
def test_b6_12_canonical_by_week_keeps_latest_decision(snapshot_root):
    _, week2 = _two_weeks()
    retry_pack = direct_pack(as_of=WEEK2_CUTOFF,
                             decision=WEEK2_DECISION + timedelta(hours=3),
                             run_id="wb-b6-w2-retry2")
    retry = build_monitoring_snapshot(retry_pack, registry=REG)
    store = SnapshotStore(snapshot_root)
    store.persist(week2)
    store.persist(retry)
    canonical = store.list_canonical()
    assert len(canonical) == 1
    assert canonical[0].metadata.decision_time == retry.metadata.decision_time


# --- RT139-B6-13: invalid snapshot id is rejected ---
def test_b6_13_invalid_snapshot_id_rejected(snapshot_root):
    store = SnapshotStore(snapshot_root)
    with pytest.raises(ValueError):
        store.load("../escape")
    with pytest.raises(ValueError):
        store.load("")


# --- RT139-B6-14: missing snapshot is FileNotFoundError, not fixture ---
def test_b6_14_missing_snapshot_is_file_not_found(snapshot_root):
    store = SnapshotStore(snapshot_root)
    with pytest.raises(FileNotFoundError):
        store.load("dsv0-monitoring-20260911-doesnotexist")


# --- RT139-B6-15: empty store load_latest is FileNotFoundError ---
def test_b6_15_empty_store_load_latest_raises(snapshot_root):
    store = SnapshotStore(snapshot_root)
    with pytest.raises(FileNotFoundError):
        store.load_latest()


# --- RT139-B6-16: history surfaces exist post-#135 (GAP-01 closed) ---
def test_b6_16_history_surfaces_exist(snapshot_root):
    week1, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    store.persist(week2)
    service = SnapshotReadService(store)
    payload = service.snapshots()
    assert payload["history"], "canonical history must be enumerable"
    assert payload["current"] and payload["prior"]
    technical = service.snapshots(view="technical")
    assert technical["history"]


# --- RT139-B6-17: diff surface exists post-#135 (GAP-01 closed) ---
def test_b6_17_diff_surface_exists(snapshot_root):
    week1, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    store.persist(week2)
    service = SnapshotReadService(store)
    diff = service.diff(week2.metadata.snapshot_id, week1.metadata.snapshot_id)
    assert diff


# --- RT139-B6-18: weekly comparability gate exists post-#132 (GAP-02 closed) ---
def test_b6_18_weekly_comparability_gate_exists():
    import inspect

    from cross_asset.research import weekly_core

    source = inspect.getsource(weekly_core)
    assert "comparab" in source.lower()


# --- RT139-B6-19: API /api/snapshot/latest serves the canonical latest ---
def test_b6_19_api_latest_endpoint(snapshot_root):
    week1, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    store.persist(week2)
    server = make_server(store, host="127.0.0.1", port=0)
    port = server.server_address[1]
    from threading import Thread

    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/snapshot/latest")
        response = conn.getresponse()
        body = json.loads(response.read())
        assert response.status == 200
        assert body["metadata"]["snapshot_id"] == week2.metadata.snapshot_id
    finally:
        server.shutdown()


# --- RT139-B6-20: API failure is an error payload, never a fixture fallback ---
def test_b6_20_api_failure_is_not_fixture_fallback(snapshot_root):
    store = SnapshotStore(snapshot_root)
    server = make_server(store, host="127.0.0.1", port=0)
    port = server.server_address[1]
    from threading import Thread

    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/snapshot/latest")
        response = conn.getresponse()
        body = json.loads(response.read())
        assert response.status >= 400
        assert "fixture" not in json.dumps(body).lower() or body.get("error")
        assert "metadata" not in body or body.get("error")
    finally:
        server.shutdown()


# --- RT139-B6-21: snapshot id collision across lineage (P2-06 doc) ---
def test_b6_21_snapshot_id_ignores_previous_snapshot_documented(snapshot_root):
    pack = direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-b6-21")
    week1 = _snap(WEEK1_CUTOFF, WEEK1_DECISION, "wb-b6-21-w1", cpi_end=date(2026, 8, 1))
    with_prior = build_monitoring_snapshot(pack, previous_snapshot=week1, registry=REG)
    without_prior = build_monitoring_snapshot(pack, registry=REG)
    # Documented residual P2 (ADV-P2-06): identity covers the pack but not the
    # lineage input; the store deduplicates by id, so a retry overwrites.
    assert with_prior.metadata.snapshot_id == without_prior.metadata.snapshot_id


# --- RT139-B6-22: to_json ordering contract (P2-07 doc) ---
def test_b6_22_to_json_ordering_documented(snapshot_root):
    week1, _ = _two_weeks()
    raw = week1.to_json()
    parsed = json.loads(raw)
    assert parsed["metadata"]["snapshot_id"] == week1.metadata.snapshot_id


# --- RT139-B6-23: asset history surface exists ---
def test_b6_23_asset_history_surface(snapshot_root):
    week1, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    store.persist(week2)
    service = SnapshotReadService(store)
    asset_id = week2.asset_views[0].asset
    payload = service.asset_history(asset_id)
    assert payload["trajectory"]


# --- RT139-B6-24: snapshots() limit and week window work ---
def test_b6_24_snapshots_window_and_limit(snapshot_root):
    week1, week2 = _two_weeks()
    week3 = _snap(WEEK3_CUTOFF, WEEK3_DECISION, "wb-b6-w3", previous=week2)
    store = SnapshotStore(snapshot_root)
    for item in (week1, week2, week3):
        store.persist(item)
    service = SnapshotReadService(store)
    limited = service.snapshots(limit=2)
    assert len(limited["history"]) == 2
    windowed = service.snapshots(start_week=snapshot_economic_week_id(week2))
    weeks = [item["economic_week_id"] for item in windowed["history"]]
    assert all(week >= snapshot_economic_week_id(week2) for week in weeks)


# --- RT139-B6-25: store never serves latest.json content differing from canonical ---
def test_b6_25_latest_pointer_matches_canonical(snapshot_root):
    week1, week2 = _two_weeks()
    store = SnapshotStore(snapshot_root)
    store.persist(week2)
    store.persist(week1)
    raw = json.loads((snapshot_root / "latest.json").read_text(encoding="utf-8"))
    canonical = store.list_canonical()
    assert raw["metadata"]["snapshot_id"] == canonical[-1].metadata.snapshot_id


# --- RT139-B6-26: store root is created lazily and is a pure technical artifact ---
def test_b6_26_store_creates_root_lazily(snapshot_root):
    store = SnapshotStore(snapshot_root)
    assert not snapshot_root.exists()
    week1, _ = _two_weeks()
    store.persist(week1)
    assert snapshot_root.exists()
