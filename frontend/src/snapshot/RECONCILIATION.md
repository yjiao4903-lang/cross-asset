# Snapshot reconciliation — frontend fixture vs #114 backend source of truth

## Status

- The authoritative `DashboardSnapshotV0` producer is the Python decision-support
  core owned by **#114 (PRODUCT-DEV)**. As of this PR, **no #114 fixture has
  landed on `main`** (no backend PR exists).
- The JSON objects in `src/snapshot/fixtures/` are therefore an **isolated,
  hand-built frontend mirror**, clearly labelled `FIXTURE ONLY`, used to
  unblock UI work per #115 ("Frontend may proceed immediately with a
  deterministic fixture. Do not wait for production DB/data admission.").

## Reconciliation rules

1. The frontend **renders only** the frozen top-level sections:
   `metadata, macro_climate, investment_climate, clusters, weekly_change,
   regime, asset_views, cross_asset_pulse, executive_brief, data_health_summary`
   plus the optional `details`. Contract/version identity is owned by #114 and
   lives in `metadata.snapshot_version`; the frontend defines no competing
   top-level marker. `src/snapshot/schema.js` enforces the whitelist and fails
   loudly on unknown top-level sections, so a future #114 payload cannot
   silently introduce undocumented surfaces.
1a. Climate pills render snapshot-provided state/direction/confidence from
   their own factor clusters. React never derives a policy/liquidity direction
   from growth, and never reuses another lens' confidence — #114 must supply
   render-ready values for policy/liquidity and market confirmation.
2. When #114's fixture lands, the intended reconciliation is:
   - drop-in replacement of the objects in `src/snapshot/fixtures/` with the
     serialized #114 output (same section names, one file per scenario);
   - re-run `npm run test` — the schema/semantics tests below must pass
     unchanged against the #114 payload;
   - any field the UI needs that #114 does not provide becomes a **contract
     change request on #114/#111**, never a frontend-side invention.
3. No backend domain/engine file is modified in this PR. The fixture contains
   no live data: all values are synthetic and deterministic.

## Known intentional simplifications vs the #114 spec

- `weekly_change` is flattened into the four explicit change surfaces
  (`information_set_delta`, `macro_state_delta`, `market_condition_delta`,
  `asset_view_delta`) defined by #114 Scope C — the UI renders them exactly.
- Horizon classes (`CYCLICAL | TACTICAL | STRUCTURAL_CONTEXT`) ride on
  cluster entries; the UI never averages across horizons.
