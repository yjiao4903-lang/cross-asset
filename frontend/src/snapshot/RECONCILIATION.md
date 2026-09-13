# Snapshot reconciliation — frontend UI vs #117 producer (authoritative)

## Status (R2 — final reconciliation)

- The authoritative `DashboardSnapshotV0` producer is the #117 decision-support
  core, **accepted at commit `c64ae88d4851dc5ee1847a20e24a6cce00b5942f`**
  (merge-approval record: #117 comment `5654310388`; authorization: PR #116
  comment `5654314322`).
- `src/snapshot/golden/snapshot_benign.json` and
  `src/snapshot/golden/snapshot_tightening.json` are **byte-equivalent copies**
  of the producer's golden fixtures at that exact head. `golden/manifest.json`
  records the source commit, source paths and SHA-256 of each blob (computed
  over LF bytes). A regression test re-hashes the imported files and fails if
  they ever drift from the manifest.
- The UI **renders only adapted producer data**. `src/snapshot/adapt.js` is a
  presentation-only adapter: selection, renaming, display formatting and
  vocabulary mapping. It contains **no** sign/economic inference, **no**
  contribution recomputation, and **no** invention of fields the producer does
  not emit.

## Version identity

- `metadata.snapshot_version === "DashboardSnapshotV0"` — producer-owned, the
  only version identity (no frontend-invented top-level marker; a top-level
  `contract` field is actively rejected by `schema.js`).

## Real producer → UI mapping

| Producer field | UI surface | Notes |
|---|---|---|
| `metadata.*` | status ribbon | `lane`, `as_of`, `decision_time`, `run_id`, `model_version` rendered verbatim |
| `data_health_summary.overall` | header `DATA <overall>` badge | producer emits **no overall confidence**; the UI does not fabricate one |
| `macro_climate.direction/confidence/coverage` | climate pill 1 | state text = `regime.quadrant_label` (producer-owned classification) |
| `climate_components[]` (`POLICY_LIQUIDITY`, `FINANCIAL_CONDITIONS`, `MARKET_CONFIRMATION`, `RISK_APPETITE`, `INVESTMENT_CLIMATE`) | climate pills 2–4 | rendered directly; **no client-side sign/economic inference**; regression proves benign `POLICY_LIQUIDITY=NEUTRAL/FLAT` while growth is EXPANDING/RISING |
| `clusters[]` (`cluster_id/family/horizon/score/weekly_delta/direction/confidence/coverage/top_positive/top_negative/missing_factors/stale_factors/freshness_status`) | heatmap (family × horizon), Weekly Pulse delta chart, drill-down | `freshness_status` vocabulary map: `OK→FRESH`, `PARTIAL→STALE` (amber), others pass through |
| `weekly_change.information_set_delta` `{status, events[], stale_factors[]}` | Overview "what changed" + Weekly Pulse releases | `event_type NEW_OBSERVATION/REVISION → UPDATED` (blue), `OVERDUE → STALE` (amber); `surprise` metadata displayed verbatim incl. method |
| `weekly_change.macro_state_delta.entries` | Weekly Pulse | previous→current, delta, producer `cause` tag rendered verbatim (`NO_NEW_INFORMATION` entries have delta 0 — no synthetic drift) |
| `weekly_change.market_condition_delta.moves` | Overview + Weekly Pulse | `unit PCT→%`, `BPS→bps`, `POINT→pt`; sign coloring is market-direction only |
| `weekly_change.asset_view_delta.entries` | Weekly Pulse | stance chips + producer `reason_tags` + `confidence_delta` |
| `regime` (`quadrant_label, growth_state/direction, inflation_state/direction, dwell_weeks, transition_flag, confidence, coverage, lens_disagreement`) | Overview regime panel | quadrant mini-map highlights the cell named by `quadrant_label` (selection, not derivation) |
| `asset_views[]` | stance board, Asset Lens | `drivers` are backend strings: `"FAMILY:+0.22"` parsed for display verbatim; `"market_confirmed:FACTOR"` renders as qualitative row with `null` contribution (no value fabricated); `market_confirmation` rendered directly, `UNKNOWN` → gray dashed data-state chip |
| `cross_asset_pulse.entries` (`ret_1w/1m/3m`, `momentum_label`) | Weekly Pulse matrix | producer V0 emits **no YTD** — the UI shows 1W/1M/3M + momentum label and does not invent YTD |
| `executive_brief` (`what_changed, why_it_matters, what_to_watch[]`) | Overview brief | verbatim |
| `data_health_summary` (`overall, stale_components, missing_components, blockers`) + `details.family_information_status` | Data Health page | counts are presentation tallies of producer lists; FORMAL_OOS eligibility is **not emitted** by producer V0 and is shown as "not disclosed" rather than invented |
| `details` | Data Health drill-down notes | lineage note, taxonomy version, parameter status |

## Deliberate non-inventions (producer does not emit these)

- overall confidence score (header shows `data_health_summary.overall` instead);
- YTD returns (only 1W/1M/3M + momentum label shown);
- multi-week stance history (only current + prior stance shown);
- per-series provenance/timestamps, MONITORING-vs-FORMAL eligibility flags,
  unresolved-contract registers (Data Health renders only the compact
  producer lists; if #114/#117 later emit them, the page can consume them).

## Reconciliation rules going forward

1. When the producer contract changes, update the golden copies (same source
   commit recorded in `manifest.json`), the adapter vocabulary maps if needed,
   and re-run `npm run test` — the byte-equivalence and contract regressions
   must pass unchanged.
2. Any UI field the producer does not provide becomes a contract change
   request on #114/#117, never a frontend-side invention.
3. No backend domain/engine file is modified by the frontend; golden JSON
   copies are the only bridge and are provably tied to the producer commit.

## Invariants preserved

- `NO_PROXY_SUBSTITUTION = TRUE`: no DXY proxy anywhere; USD exposure is the
  independent `USD_CNY` identity (regression-enforced).
- Overview 1440×900 zero vertical scroll (regression: `scrollHeight <= 900`).
- red/green only for market/stance direction; amber = data warning; gray =
  unavailable / `NO_NEW_INFORMATION`; data-health states never masquerade as
  market direction (unit-tested, including `UNKNOWN` confirmation).
