"""Fixtures for the WEEKEND-REDTEAM adversarial suite (#137)."""

from __future__ import annotations

import shutil

import pytest

from cross_asset.storage.duckdb import DuckDBStore

from _helpers import governed_store as _governed_store


@pytest.fixture()
def monitoring_store():
    store = DuckDBStore(":memory:")
    try:
        yield store
    finally:
        store.close()


@pytest.fixture()
def governed_store():
    """Factory for monitoring stores seeded with accepted canonical mappings."""

    opened: list[DuckDBStore] = []

    def _build(series_ids=("US_NONFARM_PAYROLLS", "US_CORE_CPI"), provider="fred"):
        store = _governed_store(series_ids, provider)
        opened.append(store)
        return store

    try:
        yield _build
    finally:
        for store in opened:
            store.close()


@pytest.fixture()
def snapshot_root(tmp_path):
    root = tmp_path / "snapshots"
    shutil.rmtree(root, ignore_errors=True)
    return root


@pytest.fixture(autouse=True)
def _no_live_network(monkeypatch):
    """Core acceptance must never depend on an outbound provider call.

    Loopback stays available so the read-only snapshot API can be exercised.
    """

    import socket

    real_connect = socket.socket.connect
    allowed = {"127.0.0.1", "::1", "localhost"}

    def _guarded(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if str(host) not in allowed:
            raise AssertionError(
                f"adversarial suite must not reach the network: {host!r}"
            )
        return real_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", _guarded)
