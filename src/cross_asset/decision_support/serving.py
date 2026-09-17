"""Minimal read-only DashboardSnapshot API for REAL-SNAPSHOT-V1.

No new web framework is introduced: the repository has no FastAPI/Flask
runtime dependency, so the standard-library HTTP server is the smallest
FastAPI-equivalent surface consistent with current dependencies.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .binding import load_factor_bindings
from .snapshot import SNAPSHOT_VERSION, DashboardSnapshotV0
from .taxonomy import load_taxonomy


class SnapshotStore:
    def __init__(self, root: str | Path = "artifacts/dashboard_snapshots") -> None:
        self.root = Path(root)

    def _path(self, snapshot_id: str) -> Path:
        if not snapshot_id or snapshot_id != Path(snapshot_id).name:
            raise ValueError("invalid_snapshot_id")
        return self.root / f"{snapshot_id}.json"

    def persist(self, snapshot: DashboardSnapshotV0) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        raw = snapshot.to_json(indent=2) + "\n"
        target = self._path(snapshot.metadata.snapshot_id)
        temp = target.with_suffix(".json.tmp")
        temp.write_text(raw, encoding="utf-8")
        temp.replace(target)
        latest = self.root / "latest.json"
        latest_temp = self.root / "latest.json.tmp"
        latest_temp.write_text(raw, encoding="utf-8")
        latest_temp.replace(latest)
        return target

    def load_latest(self) -> DashboardSnapshotV0:
        path = self.root / "latest.json"
        if not path.exists():
            raise FileNotFoundError("latest_snapshot_not_found")
        return DashboardSnapshotV0.from_json(path.read_text(encoding="utf-8"))

    def load(self, snapshot_id: str) -> DashboardSnapshotV0:
        path = self._path(snapshot_id)
        if not path.exists():
            raise FileNotFoundError(f"snapshot_not_found:{snapshot_id}")
        return DashboardSnapshotV0.from_json(path.read_text(encoding="utf-8"))


class SnapshotReadService:
    """Pure route payloads, shared by HTTP serving and tests."""

    def __init__(self, store: SnapshotStore) -> None:
        self.store = store
        self.taxonomy = load_taxonomy()
        self.bindings = load_factor_bindings(taxonomy=self.taxonomy)

    def latest(self) -> dict:
        return self.store.load_latest().model_dump(mode="json")

    def by_id(self, snapshot_id: str) -> dict:
        return self.store.load(snapshot_id).model_dump(mode="json")

    def factors(self) -> dict:
        return {
            "contract": "REAL-SNAPSHOT-V1",
            "binding_registry_version": self.bindings.version,
            "factors": self.bindings.records(self.taxonomy),
        }

    def asset(self, asset: str) -> dict:
        snapshot = self.store.load_latest()
        for view in snapshot.asset_views:
            if str(view.asset) == asset or getattr(view.asset, "value", None) == asset:
                return {
                    "snapshot_id": snapshot.metadata.snapshot_id,
                    "as_of": snapshot.metadata.as_of.isoformat(),
                    "asset_view": view.model_dump(mode="json"),
                }
        raise KeyError(f"asset_not_found:{asset}")

    def data_health(self) -> dict:
        snapshot = self.store.load_latest()
        return {
            "snapshot_id": snapshot.metadata.snapshot_id,
            "as_of": snapshot.metadata.as_of.isoformat(),
            "data_health_summary": snapshot.data_health_summary.model_dump(mode="json"),
            "binding_counts": snapshot.details.get("binding_counts", {}),
        }

    def health(self) -> dict:
        try:
            latest = self.store.load_latest()
        except FileNotFoundError:
            return {
                "status": "DEGRADED",
                "snapshot_version": SNAPSHOT_VERSION,
                "latest_snapshot_id": None,
            }
        return {
            "status": "OK",
            "snapshot_version": SNAPSHOT_VERSION,
            "latest_snapshot_id": latest.metadata.snapshot_id,
            "model_version": latest.metadata.model_version,
        }


class _Handler(BaseHTTPRequestHandler):
    service: SnapshotReadService

    def log_message(self, format: str, *args) -> None:
        return

    def _json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/api/snapshot/latest":
                payload = self.service.latest()
            elif path.startswith("/api/snapshot/"):
                payload = self.service.by_id(path.removeprefix("/api/snapshot/"))
            elif path == "/api/factors":
                payload = self.service.factors()
            elif path.startswith("/api/assets/"):
                payload = self.service.asset(path.removeprefix("/api/assets/"))
            elif path == "/api/data-health":
                payload = self.service.data_health()
            elif path in {"/api/health", "/api/version"}:
                payload = self.service.health()
            else:
                self._json(404, {"error": "route_not_found"})
                return
        except FileNotFoundError as exc:
            self._json(404, {"error": str(exc)})
            return
        except (KeyError, ValueError) as exc:
            self._json(404, {"error": str(exc)})
            return
        self._json(200, payload)


def make_server(
    store: SnapshotStore,
    *,
    host: str = "127.0.0.1",
    port: int = 8008,
) -> ThreadingHTTPServer:
    service = SnapshotReadService(store)

    class BoundHandler(_Handler):
        pass

    BoundHandler.service = service
    return ThreadingHTTPServer((host, port), BoundHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve REAL-SNAPSHOT-V1 read-only API")
    parser.add_argument("--root", default="artifacts/dashboard_snapshots")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8008)
    args = parser.parse_args()
    server = make_server(SnapshotStore(args.root), host=args.host, port=args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()


__all__ = ["SnapshotReadService", "SnapshotStore", "make_server"]
