"""Read-only DashboardSnapshot API with DECISION-HISTORY-V1 continuity."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .binding import load_factor_bindings
from .decision_history import (
    asset_stance_history,
    canonical_by_week,
    canonical_prior,
    history_payload,
    snapshot_economic_week_id,
    structured_diff,
    technical_history_payload,
)
from .snapshot import SNAPSHOT_VERSION, DashboardSnapshotV0
from .taxonomy import load_taxonomy


class SnapshotStore:
    """File-backed immutable technical snapshots plus canonical economic history."""

    def __init__(self, root: str | Path = "artifacts/dashboard_snapshots") -> None:
        self.root = Path(root)

    def _path(self, snapshot_id: str) -> Path:
        if not snapshot_id or snapshot_id != Path(snapshot_id).name:
            raise ValueError("invalid_snapshot_id")
        return self.root / f"{snapshot_id}.json"

    def _write_latest(self, snapshot: DashboardSnapshotV0) -> None:
        raw = snapshot.to_json(indent=2) + "\n"
        latest = self.root / "latest.json"
        latest_temp = self.root / "latest.json.tmp"
        latest_temp.write_text(raw, encoding="utf-8")
        latest_temp.replace(latest)

    def persist(self, snapshot: DashboardSnapshotV0) -> Path:
        """Persist technical snapshot and refresh canonical economic current.

        Late backfills never displace the true later economic current. Same-week
        retries may replace that week's canonical representative when their
        decision_time is later, while the superseded technical file remains.
        """

        self.root.mkdir(parents=True, exist_ok=True)
        raw = snapshot.to_json(indent=2) + "\n"
        target = self._path(snapshot.metadata.snapshot_id)
        temp = target.with_suffix(".json.tmp")
        temp.write_text(raw, encoding="utf-8")
        temp.replace(target)
        canonical = canonical_by_week(self.list_snapshots())
        if canonical:
            self._write_latest(canonical[-1])
        return target

    def list_snapshots(self) -> list[DashboardSnapshotV0]:
        if not self.root.exists():
            return []
        snapshots: list[DashboardSnapshotV0] = []
        for path in sorted(self.root.glob("*.json")):
            if path.name == "latest.json":
                continue
            snapshots.append(DashboardSnapshotV0.from_json(path.read_text(encoding="utf-8")))
        return sorted(
            snapshots,
            key=lambda snapshot: (
                snapshot_economic_week_id(snapshot),
                snapshot.metadata.decision_time,
                snapshot.metadata.snapshot_id,
            ),
        )

    def list_canonical(self) -> list[DashboardSnapshotV0]:
        return canonical_by_week(self.list_snapshots())

    def load_latest(self) -> DashboardSnapshotV0:
        path = self.root / "latest.json"
        if path.exists():
            return DashboardSnapshotV0.from_json(path.read_text(encoding="utf-8"))
        canonical = self.list_canonical()
        if not canonical:
            raise FileNotFoundError("latest_snapshot_not_found")
        return canonical[-1]

    def load(self, snapshot_id: str) -> DashboardSnapshotV0:
        path = self._path(snapshot_id)
        if not path.exists():
            raise FileNotFoundError(f"snapshot_not_found:{snapshot_id}")
        return DashboardSnapshotV0.from_json(path.read_text(encoding="utf-8"))

    def prior_for(self, *, decision_time: datetime, current_week_id: str) -> DashboardSnapshotV0 | None:
        return canonical_prior(
            self.list_snapshots(),
            decision_time=decision_time,
            current_week_id=current_week_id,
        )


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

    def snapshots(
        self,
        *,
        view: str = "canonical",
        start_week: str | None = None,
        end_week: str | None = None,
        limit: int | None = None,
    ) -> dict:
        snapshots = self.store.list_snapshots()
        if view == "technical":
            return technical_history_payload(snapshots)
        if view != "canonical":
            raise ValueError(f"unsupported_history_view:{view}")
        return history_payload(
            snapshots,
            start_week=start_week,
            end_week=end_week,
            limit=limit,
        )

    def asset_history(self, asset: str) -> dict:
        return asset_stance_history(self.store.list_snapshots(), asset)

    def diff(self, snapshot_id: str, prior_id: str) -> dict:
        return structured_diff(self.store.load(snapshot_id), self.store.load(prior_id))

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
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if path == "/api/snapshot/latest":
                payload = self.service.latest()
            elif path == "/api/snapshots":
                limit_raw = query.get("limit", [None])[0]
                payload = self.service.snapshots(
                    view=query.get("view", ["canonical"])[0],
                    start_week=query.get("start_week", [None])[0],
                    end_week=query.get("end_week", [None])[0],
                    limit=int(limit_raw) if limit_raw is not None else None,
                )
            elif path.startswith("/api/history/assets/"):
                payload = self.service.asset_history(path.removeprefix("/api/history/assets/"))
            elif path.startswith("/api/snapshot/") and "/diff/" in path:
                remainder = path.removeprefix("/api/snapshot/")
                snapshot_id, prior_id = remainder.split("/diff/", 1)
                payload = self.service.diff(snapshot_id, prior_id)
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
