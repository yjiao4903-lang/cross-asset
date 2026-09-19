# BLOCKER LEDGER — MULTIWEEK-MONITORING-CLOSURE-REDTEAM-V1

- Owner lane: `LOCAL-DEV-A` (#139)
- Baseline main: `036b58450226e2b4c2e88401ca246aa2b3fe6024`
- Items: **12** (3 closed, 9 open P2)
- Severity: P0 fabricates/overwrites authority or crosses lanes; P1 misstates data/decision/history or breaks normal use; P2 diagnosability/maintenance gap without current decision corruption.
- **No P0 was found. No severity was inflated.**

## Closed

### RT139-CLOSED-01 — ADV-P1-01: week 2 was unproducible once new monthly data arrived (P1 → CLOSED)
- Root cause: the DB adapter supplies no release events, so every week classified `NO_NEW_INFORMATION` while cyclical factor scores genuinely moved; `build_macro_state_delta` (correctly) raised.
- Fix (this task): monitoring-only `OBSERVED_UPDATE` contract derived from canonical observation-identity diffs vs the causal prior snapshot — see `MULTIWEEK_INFORMATION_SET_ANALYSIS.md`. Economic policy unchanged; guard preserved; FORMAL_OOS untouched.
- Evidence: `tests/redteam139/test_b7_weekly_lane.py`, `test_c2_emergent.py`.

### RT139-CLOSED-02 — ADV-P2-01: read model served mis-identified rows as evidence (P2 → CLOSED)
- Fix (this task): exact narrow port of the #138 `monitoring_adapter` identity revalidation (fail-closed per series, `identity_blockers`, raw provenance retained).
- Evidence: `tests/redteam139/test_b1_identity_source.py`.

### RT139-CLOSED-03 — ADV-P1-02: latest-pointer monotonicity (P1 → CLOSED by merged #135)
- Verified, not assumed: all six #139 Phase-3 required cases pass on current main (`test_b6_01..b6_12`).

## Open (P2 — decision needed, no unilateral fix)

| ID | Title | Decision needed | Owner | Evidence |
|---|---|---|---|---|
| RT139-P2-01 | duplicate observation dates unguarded in direct pack contract | reject vs latest-vintage-wins | REAL-SNAPSHOT-V1 owner / WEB-CONTROL | `test_b2_04` |
| RT139-P2-02 | `as_of`/`data_cutoff` divergence in hand-built packs | meaning of `as_of` | REAL-SNAPSHOT-V1 owner | `test_b2_13` |
| RT139-P2-03 | deadband first snapshot resolves to named quadrant | first-snapshot product semantics | Decision-Support-V2 owner / WEB-CONTROL | `test_b4_10` |
| RT139-P2-04 | corrupted `latest.json` surfaces raw ValidationError | typed error surface (serving.py) | DECISION-HISTORY owner | `test_b6_06` |
| RT139-P2-05 | snapshot_id ignores `previous_snapshot` lineage | identity formula change | REAL-SNAPSHOT-V1 + #133/#135 owner | `test_b6_21` |
| RT139-P2-06 | `to_json` ordering docstring vs behaviour | docstring or serializer | REAL-SNAPSHOT-V1 owner | `test_b6_22` |
| RT139-P2-07 | retry copies prior weekly deltas while views recompute | intra-week revision semantics | REAL-SNAPSHOT-V1 / #133-#135 owner | `test_b5_04` |
| RT139-P2-08 | no unit cross-check provider contract vs catalog | unit-contract authority | PROVIDER-CALENDAR-V1 owner | STATIC-09 |
| RT139-P2-09 (new) | duplicate canonical series across bindings not rejected | binding-config authority | WEB-CONTROL | `test_c2_10` |

## Explicit non-claims

- No Wind/iFinD/Tushare/manual-lane validation is claimed (NOT_EXERCISED cells).
- No FORMAL_OOS or YTD surface was created or activated (#81 / #93 untouched).
- Launcher/frontend runtime untouched (git diff evidence, `test_b8_09`).
