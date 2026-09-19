# REDTEAM PASSES — MULTIWEEK-MONITORING-CLOSURE-REDTEAM-V1

- Owner lane: `LOCAL-DEV-A` (#139)
- Baseline main: `036b58450226e2b4c2e88401ca246aa2b3fe6024`
- Matrix: 166 classified cases (`ADVERSARIAL_MATRIX.{json,md}`), 138 test-backed.

## Pass 1 — frozen invariant attacks (frozen matrix)

Attacked the frozen invariant set (`UNKNOWN != ZERO`, `MISSING != ZERO`,
`MONITORING != FORMAL_OOS`, `NO_PROXY_SUBSTITUTION`, `NO_SILENT_SOURCE_FALLBACK`,
`NO_GUESSED_SOURCE_SEMANTICS`, `NO_ADMISSION_RELAXATION`,
`NO_OUTCOME_DRIVEN_TUNING`, `FRONTEND_BUSINESS_LOGIC = FORBIDDEN`,
`same economic week retry != new regime week`, `late technical creation !=
economic latest`, `future snapshot != valid prior`, `API failure != fixture
fallback`, `provider/source identity mismatch != comparable series`,
`calendar missing != fresh`, `capture_time != first_release_time`) plus the
causality/freshness/identity surfaces, seeded by the #138 matrix but re-derived
on current main.

Pass-1 headline results:

1. **Identity (B1)** — at `036b584` the monitoring read model served
   mis-identified rows (`fred:PAYEMS` as CPI evidence, `source=wind` rows under a
   `MONITORING:fred` run). Classified `FAIL_FIXED`: the narrow #138 fix was
   ported; 18 regression cases now enforce fail-closed identity revalidation.
2. **Latest pointer (B6)** — #135 closes ADV-P1-02 on current main. Proven, not
   assumed: later-week-first persist, older backfill, same-week retry, future
   week, corrupted/missing pointer, restart readback, canonical current/prior
   all verified.
3. **Week-2 information set (B7/C2)** — `SyntheticMovementError` reproduced at
   `036b584`; classified `FAIL_FIXED` via the OBSERVED_UPDATE contract.
4. **Corrupted artifacts** — truncated snapshot JSON is a typed failure; corrupted
   `latest.json` is fail-closed but untyped (ledger P2); a subsequent healthy
   persist repairs the pointer.
5. **Runtime boundaries (B8)** — fixture origin rejected, non-LIVE lineage
   rejected, missing scores stay `None` (MISSING != ZERO), API binds loopback
   only, launcher/frontend untouched.

## Pass 2 — emergent cross-layer attacks

Built from Pass-1 interactions:

1. **Identity × multi-week**: a poisoned identity mid-loop blocks the affected
   week (truthful refusal of the inflation axis) while the store/history stays
   intact and a healthy later week proceeds with the correct causal prior
   (`c2_02`).
2. **Corrupted pointer × producer loop**: garbage `latest.json` then a healthy
   persist rewrites the pointer from the canonical list (`c2_03`).
3. **Re-capture semantics**: re-capturing the identical monthly world in the next
   week is NOT a new information event — this falsified the first
   implementation's `(observation_date, available_at, value)` key and forced the
   truthful `(observation_date, value)` information key (`c2_08`, `b7_04`).
4. **Late backfill × visibility**: a backfilled older observation reports its
   real older `observation_date` as an OBSERVED_UPDATE — truthfully, without
   inventing a release time (`c2_09`).
5. **Retry × canonical representative**: same-week retries update the week's
   canonical representative by later `decision_time` while never adding an
   economic week (`c2_11`, `b6_12`, `c2_14`).
6. **Determinism**: identical two-week sequences and 10 soak iterations produce
   byte-identical snapshot state (`c2_04`, `b4_09`, `SOAK_RESULTS.json`).
7. **Across-binding duplicate canonical series** discovered during Pass 2:
   validation rejects duplicates within one binding but not across bindings;
   two factors on one series over-weight it in family aggregates. Recorded as
   new ledger item RT139-P2-09 (config-authority decision), documented by test,
   not fixed unilaterally (`c2_10`).
8. **Five-week soak loop** with a new observation in week 2 and retries in weeks
   2 and 4: information-set/movement coherence holds at every step; 5 canonical
   weeks remain 5 (`c2_13`).

## Evidence chain

- Reproduction on current main pre-fix: `repro_current_main.py` (3 attacks).
- Regression + adversarial suite: `tests/redteam139/` (138 tests).
- Soak: `soak_repeatability.py` → `SOAK_RESULTS.json` (10 iterations, all
  deterministic).
- Full suite on the task branch: **901 passed** (unit + integration + redteam139).
