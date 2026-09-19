# MULTIWEEK INFORMATION SET ANALYSIS — #139 Phase 4

## The question

> Can the accepted monitoring Decision Kernel continue truthfully into a second
> economic week when the monitored macro information set changes, while
> preserving all source/time/lane/history invariants?

On current main (`036b584`) the answer was **no**: the moment a genuinely newer
macro observation became visible in week 2, cyclical factor scores moved, the
information set was still classified `NO_NEW_INFORMATION` (the adapter supplies
no release events), and the producer's synthetic-movement guard — correctly —
raised `SyntheticMovementError`. Week 2 was unproducible whenever reality moved.

## Frozen semantic rule (from #139)

Monitoring capture history MUST NOT claim a historical first-release timestamp
it does not know. The only event the product may assert from capture-time
monitoring is:

> A NEW OBSERVATION / VALUE BECAME VISIBLE TO THIS MONITORING DECISION SET

## Options considered

| Option | Verdict | Why |
|---|---|---|
| `release_time = captured_at` | **rejected** | invents first-release evidence; violates `capture_time != first_release_time` |
| emit `NEW_OBSERVATION` events from capture-time data | **rejected** | `NEW_OBSERVATION` is read as first-release semantics; capture-time monitoring cannot know it is first |
| relax the synthetic-movement guard for monitoring | **rejected** | destroys the accepted protection against fabricated movement |
| keep week 2 blocked until a formal release authority exists | **rejected** | leaves the product dead exactly when its information truthfully changed |
| **monitoring-only `OBSERVED_UPDATE` derived from observation-identity diffs vs the causal prior snapshot** | **implemented** | truthful (visibility, not release), derived from persisted canonical state, no invented timestamp, guard preserved |

## Implemented contract

- `ReleaseEventType.OBSERVED_UPDATE` — new enum member, MONITORING capture-time
  lane only; explicitly documented as never a formal first-release claim.
- Derivation lives in the producer (`_observed_update_events`): the current
  pack's per-series observation identities are diffed against
  `previous_snapshot.details["series_provenance"][series_id]["observations"]`.
- Information identity is `(observation_date, value)`: re-capturing the same
  value with a later `available_at` is **not** a new information event; any
  newly visible value for a real observation date is. `available_at`,
  `source`, `source_series_id` are recorded as capture provenance.
- Event note: `monitoring_observed_update: a new observation/value became
  visible to this monitoring decision set at <available_at>; capture-time
  semantics, no publication timestamp asserted`.
- Guard interplay: observed-update factor ids join `changed_by_release`, so
  `build_macro_state_delta` still refuses every movement without an observed
  information event. The guard is preserved, not relaxed.
- Same-week retry semantics are unchanged: a retry copies the prior weekly
  deltas wholesale, so the same observation can never become a second event.
- Fail-closed: if the causal prior snapshot does not record observation
  identities (a pre-#139 snapshot), no update is claimed and genuine movement
  keeps raising `SyntheticMovementError` (test `b7_06`).
- FORMAL_OOS is untouched: no formal surface reads or emits `OBSERVED_UPDATE`
  (tests `b7_13`, `c2_07`).

## Truthfulness checks (each backed by a test)

| #139 requirement | Evidence |
|---|---|
| observation_date is real | `b7_02`, `c2_09` (late backfill reports the real older month) |
| capture-time/non-PIT semantics preserved | `b2_08`, `b2_15` |
| source/provider/source_series_id preserved | `b2_15` (+ identity revalidation from Phase 2) |
| no publication timestamp invented | `b7_07` |
| same-week retry ≠ second information event | `b7_03`, `c2_14` |
| newly visible observation supports truthful week-2 update | `b7_02`, `b2_14`, `c2_06`, `c2_13` |
| FORMAL_OOS untouched | `b7_13`, `c2_07` |
| deterministic decision state | `b4_09`, `c2_04`, soak (SOAK_RESULTS.json) |

## Answer

With the OBSERVED_UPDATE contract, the monitoring Decision Kernel continues
truthfully into week 2 and beyond: a five-week loop with a genuinely new monthly
observation in week 2 produces `UPDATED` once (with real observation dates),
`NO_NEW_INFORMATION` afterwards, zero synthetic movement, and a canonical
history whose latest pointer and per-week representatives stay correct.
