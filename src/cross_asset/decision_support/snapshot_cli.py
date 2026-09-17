"""Command-line entry point for REAL-SNAPSHOT-V1 producer and read-only API."""

from __future__ import annotations

import argparse
from pathlib import Path

from .producer import MonitoringObservationPack, build_monitoring_snapshot
from .serving import SnapshotStore, make_server


def _build(args: argparse.Namespace) -> int:
    pack = MonitoringObservationPack.model_validate_json(
        Path(args.input).read_text(encoding="utf-8")
    )
    store = SnapshotStore(args.root)
    previous = None
    try:
        candidate = store.load_latest()
        if candidate.metadata.snapshot_id != f"pending:{pack.lineage.run_id}":
            previous = candidate
    except FileNotFoundError:
        pass
    snapshot = build_monitoring_snapshot(pack, previous_snapshot=previous)
    path = store.persist(snapshot)
    print(
        f"snapshot_id={snapshot.metadata.snapshot_id} lane={snapshot.metadata.lane} "
        f"run_id={snapshot.metadata.run_id} path={path}"
    )
    return 0


def _serve(args: argparse.Namespace) -> int:
    server = make_server(SnapshotStore(args.root), host=args.host, port=args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="REAL-SNAPSHOT-V1 operations")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build/persist a MONITORING DashboardSnapshotV0")
    build.add_argument("--input", required=True, help="canonical MonitoringObservationPack JSON")
    build.add_argument("--root", default="artifacts/dashboard_snapshots")
    build.set_defaults(handler=_build)

    serve = sub.add_parser("serve", help="serve the read-only snapshot API")
    serve.add_argument("--root", default="artifacts/dashboard_snapshots")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8008)
    serve.set_defaults(handler=_serve)

    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
