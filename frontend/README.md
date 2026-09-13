# Macro Workbench v1 — frontend (#115)

Personal macro decision cockpit rendering one versioned `DashboardSnapshotV0`
object. Dark, dense, 1440×900-first; Overview is a zero-scroll layout.

Stack (frozen by #112 UI freeze): React 19 + Vite + Tailwind CSS v4 +
Recharts + Lucide. No chart library beyond Recharts. No business/signal math
in React — the app renders one snapshot object.

## Run on Windows (local)

```bat
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in a desktop browser at 1440×900.

Production build + preview:

```bat
npm run build
npm run preview
```

Unit / component tests:

```bat
npm run test
```

## Fixture mode (current state)

- No #114 backend fixture has landed on `main` yet, so the app runs in
  **fixture mode only**: `src/snapshot/fixtures/` holds two deterministic
  hand-built scenarios:
  - **A — Benign / Mixed Confirmation** (`benign`)
  - **B — Deteriorating / Stagflation Risk** (`stress`, default)
- Switch scenarios with the selector in the header; `r` reloads the fixture
  deterministically. These fixtures are synthetic — no live data, no DB access.
- Reconciliation contract with #114 is documented in
  `src/snapshot/RECONCILIATION.md`; structural validation lives in
  `src/snapshot/schema.js` and runs on every snapshot load.

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
2. **Weekly Pulse** — releases/revisions, weekly market moves, cluster deltas,
   cross-asset 1W/1M/3M/YTD matrix, stance/confidence changes.
3. **Heatmap** — factor families × region cells with state/direction/freshness,
   contributor drill-down.
4. **Asset Lens** — stance/prior, macro bias, confirmation gate, valuation,
   driver bars, stance history, invalidators, confidence/data-health.
5. **Data Health** — pipeline truth separated from signal: fresh/stale/
   missing/blocked counters, MONITORING vs FORMAL eligibility, unresolved
   contracts, provenance table with PIT timestamps.

Screenshots for review: `docs/screenshots/` (1440×900).
