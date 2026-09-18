"""B6 — snapshot / store / API attacks (ADVERSARIAL-E2E-VALIDATION-V1)."""

from __future__ import annotations

import json
import threading
from datetime import timedelta
from http.client import HTTPConnection

import pytest

from adversarial._helpers import (
    AS_OF,
    DECISION,
    mechanics_registry,
    pack,
)
from cross_asset.decision_support.producer import build_monitoring_snapshot
from cross_asset.decision_support.serving import (
    SnapshotReadService,
    SnapshotStore,
    make_server,
)
from cross_asset.decision_support.snapshot import DashboardSnapshotV0


def _snapshot(**kwargs):
    return build_monitoring_snapshot(pack(**kwargs), registry=mechanics_registry())


@pytest.fixture()
def live_server(snapshot_root):
    server = make_server(SnapshotStore(snapshot_root), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, snapshot_root
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(server, route):
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        connection.request("GET", route)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


# --- B6-01: deterministic serialization ----------------------------------------


def test_adv_b6_01_snapshot_serialization_is_deterministic_and_round_trips():
    first = _snapshot()
    second = _snapshot()
    assert first.to_json() == second.to_json()
    assert DashboardSnapshotV0.from_json(first.to_json()).to_json() == first.to_json()
    assert first.metadata.snapshot_id == second.metadata.snapshot_id


# --- B6-02: missing latest pointer ---------------------------------------------


def test_adv_b6_02_missing_latest_pointer_is_degraded_not_fabricated(snapshot_root):
    service = SnapshotReadService(SnapshotStore(snapshot_root))
    assert service.health()["status"] == "DEGRADED"
    assert service.health()["latest_snapshot_id"] is None
    with pytest.raises(FileNotFoundError):
        service.latest()


def test_adv_b6_03_empty_snapshot_root_serves_factors_but_no_snapshot(snapshot_root):
    service = SnapshotReadService(SnapshotStore(snapshot_root))
    assert service.factors()["contract"] == "REAL-SNAPSHOT-V1"
    for call in (service.latest, service.data_health, lambda: service.by_id("x")):
        with pytest.raises(FileNotFoundError):
            call()


# --- B6-04: corrupted latest pointer -------------------------------------------


def test_adv_b6_04_corrupted_latest_pointer_is_reported_not_ignored(snapshot_root):
    """LEDGER ADV-P2-05: a malformed latest.json raises a raw pydantic
    ValidationError instead of a typed store/API error. Behaviour is fail-closed
    (HTTP 404, nothing fabricated) but leaks internal validation text."""

    snapshot_root.mkdir(parents=True, exist_ok=True)
    (snapshot_root / "latest.json").write_text("{ not json", encoding="utf-8")
    service = SnapshotReadService(SnapshotStore(snapshot_root))
    with pytest.raises(Exception) as excinfo:
        service.health()
    assert "validation error" in str(excinfo.value).lower()


def test_adv_b6_05_malformed_snapshot_file_is_not_served(live_server):
    server, root = live_server
    root.mkdir(parents=True, exist_ok=True)
    (root / "latest.json").write_text("{ not json", encoding="utf-8")
    status, _ = _get(server, "/api/health")
    assert status == 404  # fail-closed: no fabricated health payload


# --- B6-06: backfill / latest monotonicity --------------------------------------


def test_adv_b6_06_backfilled_older_snapshot_must_not_become_latest(snapshot_root):
    """LEDGER ADV-P1-02 (owner PR #135): SnapshotStore.persist has no economic
    monotonicity guard, so persisting a backfilled older snapshot overwrites
    latest.json. Recorded as an executable blocker witness.
    """

    store = SnapshotStore(snapshot_root)
    newer = build_monitoring_snapshot(
        pack(
            as_of=AS_OF + timedelta(days=7),
            decision=DECISION + timedelta(days=7),
            run_id="wb-adv-newer",
        ),
        registry=mechanics_registry(),
    )
    store.persist(newer)
    older = _snapshot(run_id="wb-adv-older")
    store.persist(older)

    latest = store.load_latest()
    # Current behaviour: the late-written older snapshot wins the latest pointer.
    assert latest.metadata.as_of < newer.metadata.as_of
    assert latest.metadata.run_id == "wb-adv-older"


# --- B6-07: snapshot id does not cover previous_snapshot ------------------------


def test_adv_b6_07_snapshot_id_ignores_previous_snapshot_lineage(snapshot_root):
    """LEDGER ADV-P2-06: two different snapshot bodies can share one
    snapshot_id when only previous_snapshot differs."""

    later = pack(
        as_of=AS_OF + timedelta(days=7),
        decision=DECISION + timedelta(days=7),
        run_id="wb-adv-idcollision",
    )
    prior = _snapshot()
    with_prior = build_monitoring_snapshot(
        later, previous_snapshot=prior, registry=mechanics_registry()
    )
    without_prior = build_monitoring_snapshot(later, registry=mechanics_registry())
    assert with_prior.metadata.snapshot_id == without_prior.metadata.snapshot_id
    assert with_prior.to_json() != without_prior.to_json()


# --- B6-08/09: unknown id, path traversal, unknown route -----------------------


@pytest.mark.parametrize(
    "snapshot_id", ["..", "../latest", "a/b", "..\\..\\latest", "sub/../../latest"]
)
def test_adv_b6_08_path_traversal_ids_are_rejected(snapshot_root, snapshot_id):
    store = SnapshotStore(snapshot_root)
    store.persist(_snapshot())
    with pytest.raises((ValueError, FileNotFoundError)):
        store.load(snapshot_id)


def test_adv_b6_09_unknown_routes_and_ids_return_404(live_server):
    server, root = live_server
    root.mkdir(parents=True, exist_ok=True)
    SnapshotStore(root).persist(_snapshot())
    for route in [
        "/api/not-a-route",
        "/api/snapshot/does-not-exist",
        "/api/assets/NOPE",
        "/api/snapshot/",
    ]:
        status, _ = _get(server, route)
        assert status == 404, route


# --- B6-10: read-only surface ---------------------------------------------------


def test_adv_b6_10_api_exposes_only_read_routes(live_server):
    server, root = live_server
    root.mkdir(parents=True, exist_ok=True)
    SnapshotStore(root).persist(_snapshot())
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            connection.request(method, "/api/snapshot/latest")
            response = connection.getresponse()
            response.read()
            assert response.status in {404, 501}, method
    finally:
        connection.close()


def test_adv_b6_11_successful_reads_are_uncacheable(live_server):
    server, root = live_server
    root.mkdir(parents=True, exist_ok=True)
    SnapshotStore(root).persist(_snapshot())
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        connection.request("GET", "/api/snapshot/latest")
        response = connection.getresponse()
        response.read()
        assert response.status == 200
        assert response.getheader("Cache-Control") == "no-store"
    finally:
        connection.close()


def test_adv_b6_12_api_payload_satisfies_the_snapshot_contract(live_server):
    server, root = live_server
    root.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot()
    SnapshotStore(root).persist(snapshot)
    status, body = _get(server, "/api/snapshot/latest")
    assert status == 200
    payload = json.loads(body)
    assert payload["metadata"]["snapshot_id"] == snapshot.metadata.snapshot_id
    assert payload["metadata"]["lane"] == "MONITORING"
    reparsed = DashboardSnapshotV0.model_validate(payload)
    assert reparsed.model_dump() == snapshot.model_dump()


def test_adv_b6_12b_http_layer_sorts_keys_while_the_model_does_not(live_server):
    """LEDGER ADV-P2-07: `to_json` documents "sorted keys" but pydantic preserves
    insertion order for the free-form ``details`` mapping, while the HTTP layer
    applies ``sort_keys=True``. The two are semantically equal but not
    byte-identical, so a byte-level hash of an API payload differs from the
    persisted file for the same snapshot."""

    server, root = live_server
    root.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot()
    SnapshotStore(root).persist(snapshot)
    status, body = _get(server, "/api/snapshot/latest")
    assert status == 200
    served = json.loads(body)
    assert list(served["details"]) == sorted(served["details"])
    local = json.loads(snapshot.to_json())
    assert local["details"] == served["details"]


# --- B6-13: writes are atomic (no partial latest.json) --------------------------


def test_adv_b6_13_persist_leaves_no_temporary_or_partial_files(snapshot_root):
    store = SnapshotStore(snapshot_root)
    store.persist(_snapshot())
    leftovers = [p.name for p in snapshot_root.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
    assert (snapshot_root / "latest.json").exists()


# --- B6-14: multiple technical snapshots in one week coexist --------------------


def test_adv_b6_14_same_week_technical_snapshots_coexist_without_overwrite(
    snapshot_root,
):
    store = SnapshotStore(snapshot_root)
    identifiers = []
    for index in range(3):
        snapshot = build_monitoring_snapshot(
            pack(decision=DECISION + timedelta(hours=index), run_id=f"wb-adv-tech-{index}"),
            registry=mechanics_registry(),
        )
        store.persist(snapshot)
        identifiers.append(snapshot.metadata.snapshot_id)
    assert len(set(identifiers)) == 3
    for identifier in identifiers:
        assert store.load(identifier).metadata.snapshot_id == identifier


# --- B6-15/16: history / diff surfaces on current main --------------------------


def test_adv_b6_15_history_and_diff_surfaces_are_absent_on_current_main(snapshot_root):
    """GAP owned by PR #135 (DECISION-HISTORY-V1); not a defect of main."""

    store_methods = {name for name in dir(SnapshotStore) if not name.startswith("_")}
    service_methods = {
        name for name in dir(SnapshotReadService) if not name.startswith("_")
    }
    assert store_methods == {"load", "load_latest", "persist"}
    assert "history" not in service_methods
    assert "diff" not in service_methods


def test_adv_b6_16_latest_endpoint_is_not_shadowed_by_id_routing(live_server):
    server, root = live_server
    root.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot()
    SnapshotStore(root).persist(snapshot)
    status, body = _get(server, "/api/snapshot/latest")
    assert status == 200
    assert json.loads(body)["metadata"]["snapshot_id"] == snapshot.metadata.snapshot_id
    # A snapshot whose id literally is "latest" would alias the route; the store
    # resolves it to the same pointer, so the alias is benign in practice.
    assert SnapshotStore(root).load("latest").metadata.snapshot_id == snapshot.metadata.snapshot_id
