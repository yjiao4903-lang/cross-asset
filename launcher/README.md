# Macro Workbench Windows Launcher V1

Windows 10/11 local launcher for the Macro Workbench frontend.

## Start

Double-click:

```text
START_MACRO_WORKBENCH.cmd
```

The launcher checks Node.js/npm, installs frontend dependencies with `npm ci` only when needed, rebuilds `frontend/dist` only when missing or stale, starts a localhost-only static server, waits for `/__health`, then opens the default browser.

## Stop

Double-click:

```text
STOP_MACRO_WORKBENCH.cmd
```

Stop only targets the PID recorded by the launcher and verifies that the process command line belongs to `launcher/server.mjs`. It never kills all `node.exe` processes.

## Prerequisite

Node.js with npm must already be installed and available on `PATH`. The launcher does not download Node.js, change `PATH`, request administrator privileges, or modify the registry/firewall.

## Default address

```text
http://127.0.0.1:8765
```

The server binds only to `127.0.0.1` and serves only `frontend/dist`.

## Build freshness

A build runs when `frontend/dist/index.html` is missing or when any of these are newer than it:

- `frontend/src/**`
- `frontend/index.html`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/vite.config.*`

Otherwise the existing production build is reused.

## Common errors

- **Node/npm not found:** install Node.js, then launch again. No automatic download is attempted.
- **`npm ci` failed:** inspect `launcher/logs/launcher.log`; the server is not started.
- **Build failed:** inspect `launcher/logs/launcher.log`; an old build is not served as if startup succeeded.
- **Port 8765 in use:** if `/__health` is not the Macro Workbench health response, the launcher refuses to kill or replace the other application.
- **Stale PID:** stale launcher metadata is removed automatically when its PID is dead or no longer belongs to `launcher/server.mjs`.
- **Browser did not open:** if the health check passed, open `http://127.0.0.1:8765` manually.

## Test/CI mode

Set:

```text
MACRO_WORKBENCH_NO_BROWSER=1
```

to suppress browser launch in automated tests. Normal user launches open the default browser after health succeeds.

V1 launches the frontend only. The launcher keeps a clear extension point for a future `backend start -> backend health -> frontend start -> frontend health -> browser` sequence.
