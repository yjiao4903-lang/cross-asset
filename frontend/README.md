# Macro Workbench v1 — frontend (#115)

Personal macro decision cockpit rendering one versioned `DashboardSnapshotV0`
object. Dark, dense, 1440×900-first; Overview is a zero-scroll layout.

Stack (frozen by #112 UI freeze): React 19 + Vite + Tailwind CSS v4 +
Recharts + Lucide. No chart library beyond Recharts. No business/signal math
in React — the app renders one snapshot object.

## Run on Windows (user path)

From the repository root, double-click:

```text
START_MACRO_WORKBENCH.cmd
```

The Windows launcher checks Node/npm, installs dependencies only when needed,
builds `frontend/dist` only when missing/stale, serves it on
`http://127.0.0.1:8765`, waits for health, then opens the default browser.
Double-click `STOP_MACRO_WORKBENCH.cmd` to stop the launcher-owned server.
See `launcher/README.md` for troubleshooting and safety details.

## Frontend developer commands

For frontend development only:

```bat
cd frontend
npm ci
npm run dev
```

Production build:

```bat
npm run build
```

Unit / component tests:

```bat
npm run test
```

## Fixture mode (current state)

- The app renders the **authoritative #117 producer golden fixtures**
  (byte-equivalent copies in `src/snapshot/golden/`, sha256-pinned in
  `golden/manifest.json`, source commit `c64ae88d4851dc5ee1847a20e24a6cce00b5942f`):
  - **A — Benign** (`benign`)
  - **B — Tightening** (`tightening`, default)
- The UI consumes producer field shapes through a presentation-only adapter
  (`src/snapshot/adapt.js`): no economic/signal inference, no invented fields.
- Reconciliation mapping is documented in `src/snapshot/RECONCILIATION.md`;
  structural validation lives in `src/snapshot/schema.js` and runs against the
  raw producer payload on every load.

## Keyboard / interaction (V1)

- `1`–`5`: Overview / Weekly Pulse / Heatmap / Asset Lens / Data Health
- `r`: reload snapshot fixture
- click an asset row (Overview) or an asset chip (Asset Lens) to drill down
- click a heatmap cell to inspect cluster contributors

## Visual semantics (frozen)

- red / green: market and stance direction only
- amber: warning, low confidence, data-health problems (stale/missing/blocked)
- gray: unavailable / `NO_NEW_INFORMATION` (dashed border, never bearish)
- blue: fresh data / informational confidence
- A data-health failure never renders as a bearish signal; low-frequency
  `NO_NEW_INFORMATION` series never produce synthetic weekly movement.

## Layout map

1. **Overview** — status ribbon, four climate pills, regime quadrant +
   hysteresis, 8-asset stance board (60%), what-changed split into macro
   information vs genuine market moves + executive brief (40%). No scroll.
2. **Weekly Pulse** — releases/revisions, weekly market moves (PCT/BPS/POINT),
   cluster weekly-delta chart, cross-asset 1W/1M/3M + momentum matrix (producer
   V0 emits no YTD), stance/confidence changes, cause-tagged macro state delta.
3. **Heatmap** — factor families × region cells with state/direction/freshness,
   contributor drill-down.
4. **Asset Lens** — stance/prior, macro bias, confirmation gate, valuation,
   driver bars, stance history, invalidators, confidence/data-health.
5. **Data Health** — pipeline truth separated from signal: fresh/stale/
   missing/blocked counters, MONITORING vs FORMAL eligibility, unresolved
   contracts, provenance table with PIT timestamps.

Screenshots for review: `docs/screenshots/` (1440×900).
