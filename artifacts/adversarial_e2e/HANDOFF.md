# HANDOFF — ADVERSARIAL-E2E-VALIDATION-V1 (issue #137)

- **Owner lane:** `WEEKEND-REDTEAM`
- **Baseline main (fresh-read at start):** `5cac5c44b08e43760888362636cadbf3ffb40f1e`
- **Newest main at final recheck:** `5cac5c44b08e43760888362636cadbf3ffb40f1e` (unchanged)
- **Branch / PR:** `WEEKEND-REDTEAM` → PR #138 (open, **not merged**)
- **Environment:** NO Wind / NO WindPy / no Wind export / no proprietary local files.

## Completion criteria

| # | Criterion | Status |
|---|---|---|
| 1 | dependency map exists | `artifacts/adversarial_e2e/DEPENDENCY_MAP.{json,md}` |
| 2 | ≥80 adversarial cases classified | **128** cases in `ADVERSARIAL_MATRIX.{json,md}` |
| 3 | two red-team passes completed | `REDTEAM_PASSES.md` (contract attacks, then emergent cross-layer attacks) |
| 4 | high-value cases are executable regressions | `tests/adversarial/` — **154** deterministic offline tests |
| 5 | every reproduced P0/P1 has a narrow tested fix **or** a ledger item with a non-overlapping owner | 2 × P1: both ledger items with named owners; the one fixable P1 was fixed |
| 6 | final newest-main recheck performed | main unchanged; no drift, no rebase needed |
| 7 | no-Wind limitations explicit | every matrix row carries severity/status; Wind-only cells are `NOT_EXERCISED` |
| 8 | full test evidence for changed shared code | below |

## Exact-head evidence (head `9f382806`, source change `monitoring_adapter.py` only)

```text
python -m ruff check src tests                 -> All checks passed
python -m pytest -q   (whole suite, one run)   -> 917 passed
GitHub Actions CI (ubuntu-latest)              -> pass
GitHub Actions CI (windows-latest)             -> pass
```

## What was shipped

**One production fix** — `src/cross_asset/decision_support/monitoring_adapter.py` (+61/−5, one file).

The monitoring **ingestion** path validates row identity; the **read model** is a separate boundary and
did not. A row filed under `US_CORE_CPI` carrying the provider symbol `PAYEMS`, or a `MONITORING:fred`
run whose rows declare `source='wind'`, was silently consumed as evidence for the canonical series.
The adapter now re-validates against the accepted `catalog.expected_source_identities` authority;
violating series become `BLOCKED` with explicit `identity_blockers`, mirroring the existing
`MONITORING_SCHEMA_ERROR → FAILED → BLOCKED` mapping, with raw provenance retained for diagnosis.

This was the only failure that was reproducible, backed by existing authority, and outside the
`serving.py` / `weekly_core.py` / `launcher/` surfaces owned by PR #135/#132/#136.

## Findings by class

| Class | Count | Notes |
|---|---|---|
| `PASS` (invariant holds) | 108 | identity, time, freshness, regime, asset rules, API, lane separation |
| `FAIL_FIXED` | 2 | monitoring identity re-validation (ADV-B1-02/03); conftest shadowing (ADV-B8-09) |
| `FAIL_BLOCKER` | 10 | see ledger |
| `BLOCKED_POLICY` | 1 | release-event policy for the monitoring lane |
| `GAP_ADJACENT_WIP` | 3 | #133/#135 history, #131/#132 comparability, #134/#136 launcher |
| `NOT_EXERCISED` | 3 | Wind/proprietary lanes, native Windows runtime |

## P0 / P1 state

**No P0 was found.** Severity was not inflated: nothing in this window can fabricate or overwrite
decision authority or cross the monitoring/formal lane boundary — that boundary held under every attack.

Two P1 items are open, both with non-overlapping owners:

- **ADV-P1-01** — the real multi-week monitoring loop cannot produce week 2 once a new monthly
  observation arrives. The adapter supplies no release events, so `information_set_delta` is always
  `NO_NEW_INFORMATION` while cyclical factor scores genuinely move, and the producer's
  synthetic-movement guard then (correctly) raises. Week 2 without new data still succeeds, which
  proves the failure is data-driven. Fixing it requires deciding what counts as a new release for a
  non-PIT, capture-time monitoring lane — a product-policy decision this window is not authorised to
  invent. **Owner:** REAL-SNAPSHOT-V1 (ONLINE-DEV-A) with WEB-CONTROL.
- **ADV-P1-02** — `SnapshotStore.persist` has no economic monotonicity guard on `latest.json`, so a
  backfilled older snapshot can take the latest pointer. `serving.py` is inside PR #135's active edit
  surface. **Owner:** PR #135 / issue #133.

## Final drift classification

| Classification | Items |
|---|---|
| `CLOSED_ON_NEW_MAIN` | none (main did not move) |
| `STILL_REPRODUCIBLE` | all recorded findings — main at final recheck is identical to the baseline |
| `STALE_DUE_TO_MERGED_AUTHORITY` | none (#135/#132/#136 all still open, unmerged) |
| `NOT_EXERCISED_NO_WIND/LOCAL` | ADV-B1-12 (Wind/iFinD/Tushare identity), ADV-B3-12 (CN interbank calendar), ADV-B8-07 (native Windows process semantics) |

No old-main failure is attributed to current main: the two SHAs are the same commit, verified by
`git rev-parse origin/main` at start and at handoff, and the branch base equals that commit.

## Residual risk / recommended next actions

1. **WEB-CONTROL:** decide the release-event policy for the monitoring lane (ADV-P1-01). Until then the
   real product loop is single-week; the harness pins the current behaviour so the fix will surface as a
   test change rather than a silent regression.
2. **PR #135:** fold the `latest.json` monotonicity guard (ADV-P1-02) and the corrupt-pointer error
   typing (ADV-P2-05) into the decision-history work, since it already owns `serving.py`.
3. **PR #135 / #133:** consider whether `snapshot_id` should cover `previous_snapshot` (ADV-P2-06) and
   whether a same-week retry should expose intra-week asset changes (ADV-P2-08) before history ships.
4. **Any future lane adding tests under a new `tests/` subdirectory:** add an `__init__.py`
   (ADV-P2-10) — an un-packaged `conftest.py` shadows `tests/conftest.py` and breaks unrelated suites
   as soon as it is collected first.

## Stop point

`HANDOFF_COMPLETE: WEEKEND-ADVERSARIAL-E2E-VALIDATION-V1`

Boundary reached: WEB-CONTROL review. No merge performed by the executor.
