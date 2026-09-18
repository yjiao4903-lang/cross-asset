"""Command-line entry point for REAL-SNAPSHOT-V1 producer and read-only API."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from cross_asset.operations.workbench_run import load_run
from cross_asset.storage.duckdb import DuckDBStore

from .decision_history import economic_week_id
from .monitoring_adapter import build_monitoring_pack_from_db
from .producer import MonitoringObservationPack, build_monitoring_snapshot
from .serving import SnapshotStore, make_server
from .snapshot import DashboardSnapshotV0


def _previous_snapshot_for(
    store: SnapshotStore,
    decision_time: datetime,
    *,
    data_cutoff,
) -> DashboardSnapshotV0 | None:
    """Return canonical earlier economic week; never look ahead on backfill/retry."""

    return store.prior_for(
        decision_time=decision_time,
        current_week_id=economic_week_id(data_cutoff),
    )


def _pack_from_args(args: argparse.Namespace) -> MonitoringObservationPack:
    if args.input:
        # Explicit diagnostic/test path. Normal runtime is DB/read-model driven.
        return MonitoringObservationPack.model_validate_json(
            Path(args.input).read_text(encoding="utf-8")
        )
    if not args.db or not args.run_id:
        raise ValueError("normal build requires --db and --run-id")
    run = load_run(args.run_id, args.runs_root)
    store = DuckDBStore(args.db)
    try:
        return build_monitoring_pack_from_db(store, run)
    finally:
        store.close()


def _build(args: argparse.Namespace) -> int:
    pack = _pack_from_args(args)
    store = SnapshotStore(args.root)
    previous = _previous_snapshot_for(
        store,
        pack.lineage.decision_time,
        data_cutoff=pack.lineage.data_cutoff,
    )
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
    source = build.add_mutually_exclusive_group(required=True)
    source.add_argument("--db", help="merged #127 DuckDB monitoring store (normal runtime)")
    source.add_argument(
        "--input",
        help="explicit diagnostic/test MonitoringObservationPack JSON; not normal runtime",
    )
    build.add_argument("--run-id", help="accepted #106 WorkbenchRun id (required with --db)")
    build.add_argument("--runs-root", default="artifacts/workbench")
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
