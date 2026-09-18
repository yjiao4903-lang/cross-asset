# Real Runtime Windows Launcher V1 (Issue #134)

Windows 10/11 local launcher for the REAL-SNAPSHOT stack: backend snapshot API + built
frontend static server with an owned reverse proxy so browser `/api/...` requests reach the
snapshot API.

## User flow

1. Double-click `START_MACRO_WORKBENCH.cmd` (or run `launcher/launcher.ps1`).
2. The launcher:
   - locates a Python 3 interpreter (repo `.venv` first, then PATH);
   - runs `npm ci` only when `frontend/node_modules` is missing/stale;
   - runs `npm run build` only when `frontend/dist` is missing/stale;
   - starts the backend snapshot API (`snapshot_cli serve`) on `127.0.0.1:8008` and waits for `/api/health`;
   - starts `launcher/server.mjs` on `127.0.0.1:8765`, which serves `frontend/dist` and reverse-proxies `/api/*` to the backend;
   - waits for `/__health`, then opens the default browser.
3. Double-click `STOP_MACRO_WORKBENCH.cmd` to stop.

Only launcher-owned processes are ever terminated. Ownership is verified by process command
line (must reference `launcher/server.mjs` or `decision_support.snapshot_cli`).

## Addresses

- Frontend/UI + API proxy: `http://127.0.0.1:8765`
- Backend snapshot API (direct): `http://127.0.0.1:8008`
- `/api/health`, `/api/snapshot/latest`, `/api/snapshot/<id>`, `/api/factors`, `/api/assets/*`, `/api/data-health`

Both listeners bind to `127.0.0.1` only.

## Safety model

- Backend port and frontend port occupied by a non-launcher-owned process => the launcher
  fails closed and does NOT kill or replace the foreign process.
- Duplicate start: a named mutex and freshness checks prevent a second owned stack.
- Stop refuses to kill any PID it does not own.
- No administrator/elevation, no registry/firewall changes, no global `node`/`python` kill.

## Env overrides (automation/tests)

- `MACRO_WORKBENCH_NO_BROWSER=1` suppresses opening the browser.
- `CROSS_ASSET_PYTHON` points the launcher at a specific `python.exe`.

## Runtime artifacts / logs

- `launcher/.runtime/frontend-stdout.log`, `frontend-stderr.log`
- `launcher/.runtime/backend-stdout.log`, `backend-stderr.log`
- `launcher/.runtime/server.log`
- `launcher/logs/launcher.log`
- Launcher ownership metadata: `launcher/.runtime/servers.pid`
- Persisted snapshots live under `artifacts/dashboard_snapshots/` (default backend root).