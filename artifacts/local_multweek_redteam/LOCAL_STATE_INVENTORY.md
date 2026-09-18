# LOCAL STATE INVENTORY — MULTIWEEK-MONITORING-CLOSURE-REDTEAM-V1

- Owner lane: `LOCAL-DEV-A` (#139)
- Authoritative main at capture: `036b58450226e2b4c2e88401ca246aa2b3fe6024`
- Captured: 2026-09-18 (local workstation)

## Census result

**No authoritative populated cross-asset database exists on this workstation.**

| Location | What it is | Verdict |
|---|---|---|
| `_redteam137/data/db/cross_asset.duckdb` (798,720 bytes, sha256 `77edb5c2…34d`) | #137 window's scratch clone DB, full schema, **0 rows** in `observations` / `ingestion_runs` / `series_catalog` | EMPTY_SCHEMA_ONLY; left untouched |
| `_redteam137/artifacts/workbench/runs/` (37 files) | daily WorkbenchRun records, all `DATA_BLOCKED` / `FROZEN` (`pipeline_data_blocked`) | historical evidence of the blocked formal lane; no monitoring snapshot state |
| `_rt_tmp/**`, `_audit_scratch/**` (`*.duckdb`) | pytest-scoped scratch DBs from prior windows | not authoritative; left untouched |
| any `dashboard_snapshots/` root | — | none found; no persisted real snapshot history exists locally |

## Mutation policy applied

- **No fault injection into any pre-existing DB.** All adversarial, closure and soak work ran on
  task-scoped scratch DuckDB stores (`:memory:` or per-iteration temp dirs) created strictly through
  accepted code paths:
  `sync_series_catalog → store.start_run/insert_observations/finish_run → WorkbenchRun →
  build_monitoring_pack_from_db → build_monitoring_snapshot → SnapshotStore`.
- Snapshot stores are temp directories created per test/soak iteration and deleted afterwards.
- The #137-era DB and artifacts were only read (read-only connection, SHA-256 recorded above).

## Environment note

- No Wind / WindPy / proprietary local files; those lanes stay `NOT_EXERCISED` in the matrix.
  Missing Wind is explicitly not a blocker for this task.
- Baseline suite on the task venv: `tests/unit` 535 passed. `tests/integration` initially reported
  228 collection errors that trace to pytest's Windows temp-root permission (`PermissionError` on
  `pytest-of-user`), not product code; with `--basetemp` pointed at a local scratch dir the suite is
  re-run as part of final evidence.
