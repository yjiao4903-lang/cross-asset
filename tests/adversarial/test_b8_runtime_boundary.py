"""B8 — runtime / launcher / static-server boundary attacks.

#134/#136 own the Windows launcher and native process semantics. This window has
no native Windows launcher proof, so process-ownership scenarios are recorded as
NOT_EXERCISED rather than asserted.
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path

from adversarial._helpers import (
    mechanics_registry,
    pack,
)
from cross_asset.decision_support.producer import build_monitoring_snapshot
from cross_asset.decision_support.serving import SnapshotStore, make_server


def _snapshot():
    return build_monitoring_snapshot(pack(), registry=mechanics_registry())


# --- B8-01: loopback-only default binding ---------------------------------------


def test_adv_b8_01_api_defaults_to_loopback_and_is_not_publicly_exposed():
    import inspect

    from cross_asset.decision_support import serving

    signature = inspect.signature(serving.make_server)
    assert signature.parameters["host"].default == "127.0.0.1"
    cli = inspect.getsource(serving.main)
    assert 'default="127.0.0.1"' in cli
    assert "0.0.0.0" not in cli


def test_adv_b8_02_snapshot_cli_serve_also_defaults_to_loopback():
    source = Path("src/cross_asset/decision_support/snapshot_cli.py").read_text(
        encoding="utf-8"
    )
    assert 'serve.add_argument("--host", default="127.0.0.1")' in source
    assert "0.0.0.0" not in source


# --- B8-03: no new web framework dependency ------------------------------------


def test_adv_b8_03_no_web_framework_is_introduced():
    project = Path("pyproject.toml").read_text(encoding="utf-8").lower()
    for framework in ("fastapi", "flask", "uvicorn", "starlette", "django"):
        assert framework not in project
    serving = Path("src/cross_asset/decision_support/serving.py").read_text(
        encoding="utf-8"
    )
    assert "http.server" in serving


# --- B8-04: graceful shutdown ---------------------------------------------------


def test_adv_b8_04_server_shuts_down_cleanly(snapshot_root):
    snapshot_root.mkdir(parents=True, exist_ok=True)
    SnapshotStore(snapshot_root).persist(_snapshot())
    server = make_server(SnapshotStore(snapshot_root), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    connection.request("GET", "/api/health")
    response = connection.getresponse()
    response.read()
    assert response.status == 200
    connection.close()
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    assert not thread.is_alive()


# --- B8-05: concurrent reads on the threaded server -----------------------------


def test_adv_b8_05_concurrent_reads_are_consistent(snapshot_root):
    snapshot_root.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot()
    SnapshotStore(snapshot_root).persist(snapshot)
    server = make_server(SnapshotStore(snapshot_root), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results: list[str] = []
    errors: list[BaseException] = []

    def reader():
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            try:
                connection.request("GET", "/api/snapshot/latest")
                response = connection.getresponse()
                payload = json.loads(response.read())
                results.append(payload["metadata"]["snapshot_id"])
            finally:
                connection.close()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    try:
        workers = [threading.Thread(target=reader) for _ in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert errors == []
    assert results == [snapshot.metadata.snapshot_id] * 8


# --- B8-06: no shell/process ownership assumptions in the Python runtime --------


def test_adv_b8_06_python_runtime_spawns_no_child_processes():
    for name in ("serving.py", "snapshot_cli.py", "producer.py"):
        source = Path(f"src/cross_asset/decision_support/{name}").read_text(
            encoding="utf-8"
        )
        assert "subprocess" not in source
        assert "os.system" not in source


# --- B8-07: launcher/native process evidence is external ------------------------


def test_adv_b8_07_native_windows_process_semantics_are_not_exercised_here():
    """NOT_EXERCISED: #134/#136 own native Windows process ownership.

    This window can only prove portable HTTP behaviour; asserting native
    process semantics from here would overstate the evidence.
    """

    launcher = Path("launcher")
    assert not launcher.exists(), "launcher belongs to PR #136 and is not on main"
    assert not Path("START_MACRO_WORKBENCH.cmd").exists()


# --- B8-08: the API never writes to the store -----------------------------------


def test_adv_b8_08_read_api_never_mutates_the_store(snapshot_root):
    snapshot_root.mkdir(parents=True, exist_ok=True)
    store = SnapshotStore(snapshot_root)
    store.persist(_snapshot())
    before = sorted(
        (path.name, path.stat().st_mtime_ns, path.read_bytes())
        for path in snapshot_root.iterdir()
    )
    server = make_server(store, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for route in ("/api/snapshot/latest", "/api/factors", "/api/data-health", "/api/health"):
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            try:
                connection.request("GET", route)
                response = connection.getresponse()
                response.read()
            finally:
                connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    after = sorted(
        (path.name, path.stat().st_mtime_ns, path.read_bytes())
        for path in snapshot_root.iterdir()
    )
    assert before == after
