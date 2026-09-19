# HANDOFF — LOCAL-A MULTIWEEK-MONITORING-CLOSURE-REDTEAM-V1

- Owner lane: `LOCAL-DEV-A` (#139, parent #123)
- Authoritative start main: `036b58450226e2b4c2e88401ca246aa2b3fe6024`
- Mode: OVERNIGHT / HIGH-TOKEN / LOCAL-DB / CURRENT-MAIN / ONE-WINDOW — completed autonomously.
- **NO MERGE PERFORMED.** This handoff stops at the WEB-CONTROL review boundary.

## Answer to the mission question

> Can the accepted monitoring Decision Kernel continue truthfully into a second
> economic week when the monitored macro information set changes, while
> preserving all source/time/lane/history invariants?

**Yes — after this branch.** On `036b584` it could not: week 2 with genuinely new
monthly data raised `SyntheticMovementError` (ADV-P1-01). On this branch a
five-week monitoring loop with a new observation in week 2, same-week retries,
restarts and backfills produces truthful `UPDATED`/`NO_NEW_INFORMATION` weekly
information sets, zero synthetic movement, correct canonical history and a
correct latest pointer.

## What this branch changes (production code, narrow)

| File | Change |
|---|---|
| `src/cross_asset/decision_support/monitoring_adapter.py` | (1) exact narrow port of the unmerged #138 identity revalidation (fail-closed per series, `identity_blockers`, raw provenance retained); (2) per-series capture-time observation identities recorded in provenance |
| `src/cross_asset/decision_support/enums.py` | new `ReleaseEventType.OBSERVED_UPDATE` — MONITORING capture-time lane only, never a first-release claim |
| `src/cross_asset/decision_support/producer.py` | derives OBSERVED_UPDATE events from observation-identity diffs vs the causal prior snapshot; records identities in `details.series_provenance`; observed-update factors join `changed_by_release` (guard preserved) |
| `src/cross_asset/decision_support/weekly.py` | docstring-only updates for the OBSERVED_UPDATE semantics |

No new provider/factor/schema. No economic policy change. No
launcher/frontend/runtime edits (asserted by `test_b8_09`). FORMAL_OOS untouched.

## Phase completion

- **Phase 0** — #138's 16 findings reclassified against current main with fresh
  reproductions: `CURRENT_MAIN_RECLASSIFICATION.{json,md}`.
- **Phase 1** — no authoritative populated local DB exists on this workstation
  (the #137-era DB is empty schema; SHA-256 recorded). All work ran on
  task-scoped scratch stores via accepted code paths:
  `LOCAL_STATE_INVENTORY.{json,md}`.
- **Phase 2** — identity attack reproduced on current main, then the exact
  narrow #138 fix ported + regressions (`repro_current_main.py` ATTACK 1,
  `test_b1_*`).
- **Phase 3** — ADV-P1-02 **closed by merged #135**, proven with all six required
  cases (`test_b6_01..b6_12`).
- **Phase 4** — OBSERVED_UPDATE contract + analysis:
  `MULTIWEEK_INFORMATION_SET_ANALYSIS.{json,md}`.
- **Phase 5** — 166-case matrix, two red-team passes: `ADVERSARIAL_MATRIX.{json,md}`,
  `REDTEAM_PASSES.md`, `BLOCKER_LEDGER.{json,md}`.
- **Phase 6** — 10-iteration five-week soak, deterministic across iterations,
  restarts mid-loop, retries stay one economic step: `soak_repeatability.py` →
  `SOAK_RESULTS.json`.

## Test evidence (this branch, local run)

```
tests/unit + tests/integration + tests/redteam139  -> 901 passed
  (main baseline was 763 passed; +138 redteam139 cases, 0 regressions)
```

All offline: no Wind, no network in the adversarial suite (socket-guarded
loopback only), no proprietary local files. Synthetic observations are TEST-ONLY
mechanics inputs and are never described as real market evidence.

## Ledger summary

- 0 × P0.
- 2 × P1 findings from #138: **ADV-P1-01 closed here**, **ADV-P1-02 closed by
  #135** (verified).
- 1 × P2 from #138 ported and closed here (ADV-P2-01).
- 9 × P2 open, each with owner and the decision needed — no unilateral fixes:
  see `BLOCKER_LEDGER.md` (incl. new RT139-P2-09 across-binding duplicates).
- 1 × P2 stale on current main (ADV-P2-10 conftest shadowing; lesson applied).

## Non-overlap statement

`serving.py`, `decision_history.py`, `research/weekly_core.py`, `launcher/**`,
`frontend/**` and all LOCAL-B surfaces are untouched by this branch
(`test_b8_09` asserts it in CI). `monitoring_adapter.py` intentionally ports the
unmerged #138 fix exactly as #139 instructed; if PR #138 merges first, this
branch rebases with a trivial diff.

## Residual risks (truthful)

- The OBSERVED_UPDATE derivation is fail-closed against pre-#139 prior
  snapshots: week 2 after upgrading raises `SyntheticMovementError` if the prior
  week's snapshot predates this contract. Production snapshots persisted after
  this merge record identities going forward.
- The corrupted-`latest.json` error remains untyped (fail-closed) — ledger
  RT139-P2-04 for the #133/#135 owner.
- Wind/manual/CN-proprietary lanes remain NOT_EXERCISED (no capability in this
  window); this is not a blocker for the verified surfaces.

Final marker:

`HANDOFF_COMPLETE: LOCAL-A-MULTIWEEK-MONITORING-CLOSURE-REDTEAM-V1`
