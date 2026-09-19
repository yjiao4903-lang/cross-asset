# HANDOFF — LOCAL-DEV-B / WINDOWS-REAL-SNAPSHOT-SOAK-UAT-V2 (#140)

**Marker:** `HANDOFF_COMPLETE: LOCAL-B-WINDOWS-REAL-SNAPSHOT-SOAK-UAT-V2`
**Generated:** 2026-09-19 (UTC+8 native Windows session)
**Lane:** LOCAL-DEV-B — launcher/runtime-only scope; no Decision Kernel/economics/history/weekly/formal-admission changes.

## 1. Git / PR facts

| item | value |
|---|---|
| Authoritative main at start of completion | `8149f1cbe7d724e94d670ea7dc7af916e307d853` |
| Authoritative main at PR open | `8149f1cbe7d724e94d670ea7dc7af916e307d853` (unchanged) |
| Merge-base of branch vs main | `8149f1cbe7d724e94d670ea7dc7af916e307d853` |
| Branch | `local-dev-b/windows-real-snapshot-soak-uat-v2` |
| Prior branch head (fresh-read input) | `afa1ebc991464c0382f4a53ec503a2bf5c0d0c5f` |
| Completion commit (contains this handoff) | `07e709d486f6f29e0dc7735bfad34746a6df5247` |
| ahead / behind vs `8149f1c` | 10 ahead / 0 behind (afa1ebc 8 commits + merge `3af1464` of main + completion commit) |
| PR | #142 (`main` <- `local-dev-b/windows-real-snapshot-soak-uat-v2`), no executor merge |
| Stale evidence | #134 / PR #136 used as historical evidence only; never merged/rebased |

Diff scope vs main: `START/STOP_MACRO_WORKBENCH.cmd`, `launcher/**`, `launcher/tests/**` (launcher/runtime-only), plus two frontend material-usability fixes on the real-snapshot path (see B3/B4) and `.gitignore` entry for the user-space Node runtime. No `src/cross_asset/**` changes.

## 2. Provider connectivity (Phase 2)

Driver: `launcher/tests/provider_connectivity_v2.py` (DNS → TCP v4/v6 → TLS → HTTPS trust-env/no-proxy → repository provider path).

| provider | classification | repo-path rows | latest observation |
|---|---|---|---|
| FRED (`DFII10`) | **LIVE_REACHABLE** | 28 | 2026-09-17 |
| Yahoo (`^GSPC`) | **LIVE_REACHABLE** | 2514 | 2026-09-18 |

The #136-era FRED timeout did not reproduce: DNS OK (TLSv1.3), public HTTPS OK, repository provider path returns real rows. `NETWORK_BLOCKED` / `PROVIDER_BLOCKED` / `CODE_PATH_DEFECT` did not apply to either provider.

## 3. Real snapshot chain (Phases 3+6) — PASS (partial source coverage, gate not lowered)

Full genuine non-fixture chain executed on native Windows:

```
public provider (FRED + Yahoo)
  -> MonitoringRunner (ingestion runs monitoring-fred/yahoo-windows-uat-v2-*)
  -> local DuckDB (4387 real observation rows; FRED 1873 + Yahoo 2514)
  -> LIVE WorkbenchRun (source_mode=LIVE, origin=MONITORING, formal_gate=false)
  -> snapshot_cli build --db + --run-id
  -> real DashboardSnapshot dsv0-monitoring-20260919-8258e11a5b5065b8
  -> SnapshotStore (artifacts/windows_uat_v2/dashboard_snapshots)
  -> snapshot API (/api/health, /api/snapshot/latest, /api/snapshots)
  -> built frontend/static reverse proxy (launcher server.mjs, 127.0.0.1:8765 -> 127.0.0.1:8008)
  -> Windows browser (interactive in-app browser + headless Edge DOM readback)
  -> STOP -> full restart -> identical persisted snapshot/history
```

Identity / boundary assertions:

- API and browser display the **same `snapshot_id`** (`dsv0-monitoring-20260919-8258e11a5b5065b8`, `data-testid="snapshot-id"`).
- Provenance remains **MONITORING** end-to-end (ingestion runs, workbench run, snapshot lane); acceptance registry rows = 0; every `series_provenance` entry has `formal_admission_granted=false`.
- No demo/golden fallback anywhere (frontend DOM checked; `DEMO / GOLDEN` badge absent in normal mode).
- Data health is truthful: PARTIAL — 23 missing / 3 stale / 25 blocked components; unavailable inputs reported as UNKNOWN/missing, never zero-filled.
- Stop/restart persistence proof: same snapshot_id, same run_id, `technical_snapshot_count=1`, `canonical_week_count=1` after full restart — **restart creates no new run and no new economic_week**.
- The only open source gap: bound series `CN_EQ_LARGE`, `COPPER`, `GOLD` have no accepted public-provider source on this lane → status `REAL_SNAPSHOT_PERSISTED_PARTIAL` (not a provider availability failure; FRED/Yahoo classified LIVE_REACHABLE).

## 4. Native soak / fault matrix (Phase 5) — SOAK_PASS 18/18

Driver: `launcher/tests/windows_soak_uat_v2.ps1` (rewritten — the committed copy was a corrupted binary blob). Evidence: `SOAK_MATRIX.{json,md}`, `PROCESS_OWNERSHIP_MATRIX.{json,md}`.

All PASS: clean start; warm start; duplicate start (single stack reused, pids unchanged); API-only crash (proxy answers 502, actionable) + recovery; frontend-only crash + recovery; full restart; stale PID metadata (recycled deterministically); foreign frontend port (exit 13, occupant survives); foreign backend port (exit 14, occupant survives); corrupted runtime metadata (stop refuses with 43, no unverified kill); missing runtime metadata (stop refuses with 41); restored-metadata recovery; browser reopen (headless Edge DOM: real run_id found, no demo badge, no unavailable state); final snapshot/history readback; unrelated Python/Node sentinel survival across every scenario.

Ownership invariants verified: STOP/START own only command-line-verified launcher processes recorded in `servers.pid`; localhost-only; no admin/elevation; no registry/firewall mutation; no global Node/Python kill.

## 5. Fixed defects on this branch (launcher/runtime scope only)

- `launcher/tests/windows_soak_uat_v2.ps1`: committed blob was corrupted (~18.7KB binary garbage) — rewritten and executed.
- `launcher/tests/real_snapshot_uat_v2.py`: Windows DuckDB single-writer lock — parent connection closed before the snapshot_cli subprocess.
- `frontend/src/pages/OverviewPage.jsx`: render crash on real snapshot with empty drivers array — truthful placeholder.
- `frontend/src/App.jsx`: header displays producer-owned `metadata.snapshot_id` + overflow fix.
- Harness wait semantics in both PowerShell drivers (`HasExited` polling; pipeline EOF / descendant-tree waits hang otherwise).

## 6. Environment (Phase 1)

Windows 10.0.26200 x64; Python 3.12.10 (repo `.venv`); Node v24.21.0 / npm 11.19.0 (user-space `tools/node`, no admin); frontend `dist` built from source; ports 8765/8008 free at census; per-user registry proxy 127.0.0.1:17891 present but bypassed for loopback and not used for provider semantics. Evidence: `ENVIRONMENT.{json,md}`.

## 7. Remaining blockers

- `B7` (open, routed): CN_EQ_LARGE / COPPER / GOLD real-source coverage — needs WEB-CONTROL/LOCAL-A decision on accepted sources; does not block this completion.
- No runtime, ownership, or formal-boundary blockers open. `BLOCKER_LEDGER.{json,md}` has the full register.

## 8. CI / tests (final)

- Directly relevant native drivers executed on this machine: provider ladder PASS, real snapshot UAT, soak matrix 18/18 PASS, environment census.
- `ruff check src tests`: PASS. Frontend `vitest`: 55 passed; production build PASS (frontend.yml PASS on PR #142).
- `pytest -q` locally (Windows): 910 passed / 1 skipped / 1 failed.
- PR #142 CI: **frontend PASS**; ci.yml ubuntu-latest and windows-latest each fail exactly one test — `test_executor_does_not_fall_back_to_older_ok_vintage_when_latest_is_stale`. Verified **pre-existing on pristine main `8149f1c`** (fails identically in a clean main worktree; this branch has zero `src/`+`tests/` diff). Calendar/time-sensitive formal-consumption regression owned by main — routed to WEB-CONTROL/LOCAL-A, out of LOCAL-B scope.
- No executor merge; WEB-CONTROL owns acceptance and merge ordering.
