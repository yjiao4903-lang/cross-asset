# RED-TEAM PASSES — ADVERSARIAL-E2E-VALIDATION-V1

- Owner lane: `WEEKEND-REDTEAM`
- Baseline main: `5cac5c44b08e43760888362636cadbf3ffb40f1e`
- Environment: NO WIND / NO WindPy / no proprietary local files, no live provider calls in the core acceptance path.

Two passes were executed against the real monitoring decision chain, not against isolated modules.

---

## Pass 1 — contract attacks

Pass 1 attacked each frozen invariant at its own layer with hand-built adversarial inputs
(`tests/adversarial/test_b1..b8_*.py`, 127 matrix cases, 108 of them invariant-holding).

### What held

The contract surface is genuinely fail-closed almost everywhere:

- identity governance rejects ungoverned, disabled, non-equivalent and wrong-transform bindings at load time;
- the producer refuses future information, post-cutoff observations, unordered rows and missing `available_at`;
- `MISSING != ZERO` is enforced at the horizon, regime and asset-rule boundaries, and structural context can never enter a macro aggregate;
- regime hysteresis is exact at the deadband edges, same-week retries never create new economic weeks, and a future/backfilled prior is rejected;
- asset gates never let an unavailable confirmation input become a bearish reading, never let market confirmation become macro authority, and cap but never flip a stance;
- lane separation holds in both directions: monitoring rows never enter the formal query, and a formal acceptance-registry row does not make a monitoring identity formally consumable;
- the frontend normal path is API-first and fails visibly instead of substituting a demo fixture.

### What broke

| Case | Layer | Status |
|---|---|---|
| ADV-B1-02 / ADV-B1-03 | monitoring read model accepted rows whose provider or provider symbol did not match the governed mapping | FAIL_FIXED (this task) |
| ADV-B6-06 | `SnapshotStore.persist` lets a backfilled older snapshot take the `latest.json` pointer | FAIL_BLOCKER (PR #135) |
| ADV-B6-04 / ADV-B6-13 | corrupted `latest.json` surfaces a raw pydantic error; `to_json` key-order claim does not match behaviour | FAIL_BLOCKER (PR #135) |
| ADV-B6-07 | `snapshot_id` does not cover `previous_snapshot`, so two different bodies can share an id | FAIL_BLOCKER |
| ADV-B2-04 / ADV-B2-14 / ADV-B4-20 | duplicate observation dates, `as_of`/`data_cutoff` divergence, all-deadband first snapshot | FAIL_BLOCKER (P2) |
| ADV-B1-16 | no unit cross-check between provider contract and series catalog | GAP |

The single highest-value Pass-1 result was **ADV-B1-02/03**: the ingestion path validates row identity
(`MonitoringRunner._validate_rows`) but the read model — a separate boundary where rows can be written
directly or by another window — re-served those rows without re-validating them. A row filed under
`US_CORE_CPI` but carrying the provider symbol `PAYEMS`, or a `MONITORING:fred` run whose rows declare
`source='wind'`, was silently consumed as evidence for the canonical series. That is exactly
`provider/source identity mismatch != comparable series` and `NO_SILENT_SOURCE_FALLBACK`.

---

## Pass 2 — emergent cross-layer attacks

Pass 2 targeted interactions between layers that Pass 1 exposed
(`tests/adversarial/test_c2_emergent.py`).

### The load-bearing finding — ADV-P1-01

Pass 1 established (ADV-B7-04) that `build_monitoring_pack_from_db` never populates
`release_events`, `expected_releases`, `market_moves` or `pulse`. Pass 2 asked what that does to the
*second* week of the real product loop:

```text
week 1: monitoring DB capture -> pack -> build_monitoring_snapshot         -> OK
week 2: a new monthly observation arrives -> pack2 -> snapshot(previous=s1) -> SyntheticMovementError
        "factor US_CORE_CPI_TREND moved by 3.694172 while information set status was
         NO_NEW_INFORMATION; synthetic movement is forbidden"
```

The producer's synthetic-movement guard is *correct*: a cyclical factor may not move without an observed
release. The defect is that the adapter never supplies release evidence, so the information set is
permanently `NO_NEW_INFORMATION` and the guard fires exactly when the product must work — when new data
arrives. Week 2 with no new observation still succeeds (ADV-E2-02), which proves the failure is
data-driven rather than a lineage/argument error.

This is a genuine cross-layer correctness break that no module-level test could see: the adapter is
self-consistent, the producer is self-consistent, and only their combination is wrong.

**Not fixed.** Deciding what constitutes a new release for a non-PIT, capture-time monitoring lane is a
product-policy decision (first-release vs capture-time semantics, revision handling) that this window is
not authorised to invent. It is recorded as `ADV-P1-01` with the REAL-SNAPSHOT-V1 owner.

### Other Pass-2 results

| Case | Interaction | Result |
|---|---|---|
| ADV-E2-03 | same-week retry copies the prior `asset_view_delta` while recomputing the asset views | a within-week confirmation flip becomes invisible in the weekly-change surface — recorded `ADV-P2-08` |
| ADV-E2-04 | restart with legacy unkeyed regime rows | only the last legacy row is migrated to one economic week; dwell is not inflated — PASS |
| ADV-E2-05 | flat / zero-variance monitoring history | the axis becomes unavailable and the snapshot is blocked rather than read as neutral — PASS |
| ADV-E2-06 | #129 calendar downgrade | remains STALE with `freshness_verified=false` and confidence 0.5; no fabricated coverage — PASS |
| ADV-E2-07 | identity-blocked series | stays enumerated as BLOCKED with explicit blockers and a missing factor; it does not disappear — PASS |
| ADV-E2-08 | identity fix carried to the binding record | formal status remains BLOCKED end to end — PASS |
| ADV-E2-09 | CLI previous selection versus a look-ahead latest pointer | the CLI ignores a non-earlier pointer — PASS (the raw store does not; ADV-P1-02) |
| ADV-E2-10 | governed DB → pack → snapshot → store → HTTP after the fix | identity verified end to end, health PARTIAL — PASS |

### Checked-and-cleared interactions

- A freshness downgrade did not change factor coverage or confidence beyond the documented 0.5 stale discount.
- Formal acceptance plus monitoring lineage did not leak into the formal query at any layer.
- A missing calendar makes a series STALE/BLOCKED; it never makes a row disappear.
- The identity fix did not promote any monitoring identity toward formal authority.
- Repeated builds are byte-identical (restart/replay determinism) after the fix.

---

## The single shipped production fix

`src/cross_asset/decision_support/monitoring_adapter.py` now re-validates persisted row identity against
the accepted `catalog.expected_source_identities` authority — the same authority
`MonitoringRunner._validate_rows` already uses at ingestion. Violating rows are never consumed; the
affected canonical series is represented as `BLOCKED` with explicit `identity_blockers`, mirroring the
existing `MONITORING_SCHEMA_ERROR -> FAILED -> BLOCKED` mapping, and raw provenance is retained for
diagnosis.

Why this fix and nothing else:

1. reproducible (ADV-B1-02/03/15) with an executable regression;
2. expected behaviour was already established by current repository authority (the ingestion validator
   plus the #137 invariant list);
3. it is narrow, fail-closed, and changes no product/economic policy;
4. `monitoring_adapter.py` is not touched by PR #135/#132/#136.

Everything else that failed was recorded in the ledger instead, because it needed a policy decision
(ADV-P1-01, ADV-P2-02/03/04/06/08), needed new authority (ADV-P2-09), or lives inside an adjacent PR's
active edit surface (ADV-P1-02, ADV-P2-05, ADV-P2-07, ADV-GAP-01/02/03).
