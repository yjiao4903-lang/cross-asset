# CURRENT-MAIN RECLASSIFICATION — #139 LOCAL-A

- Owner lane: `LOCAL-DEV-A`
- Authoritative main: `036b58450226e2b4c2e88401ca246aa2b3fe6024`
- Evidence source: PR #138 (head `98c3d48`, **unmerged**, read-only) — all 16 ledger items re-derived on current main.
- Rule: **no finding carried forward without a fresh reproduction on current main.**

| Finding | Old status | Current-main evidence | New status | Action |
|---|---|---|---|---|
| ADV-P1-01 week-2 information set | OPEN/BLOCKER P1 | week 2 with a genuinely new monthly observation raised `SyntheticMovementError` (repro ATTACK 3) | STILL_REPRODUCIBLE → **CLOSED this task** | OBSERVED_UPDATE contract + regressions |
| ADV-P1-02 latest-pointer monotonicity | OPEN/BLOCKER P1 | backfill of an older week no longer displaces `latest`; retries keep the week; corrupted/missing pointer typed; restart readback OK | **CLOSED by merged #135** | required-case regressions only |
| ADV-P2-01 read-model identity | FIXED in unmerged #138 | wrong `source_series_id` and wrong row `source` both served as evidence at 036b584 | STILL_REPRODUCIBLE → **FIXED this task** | exact narrow port of the #138 adapter fix + regressions |
| ADV-P2-02 duplicate dates (direct pack) | OPEN P2 | still accepted by `_validate_pack` | STILL_REPRODUCIBLE | ledger (contract decision) |
| ADV-P2-03 as_of/cutoff divergence | OPEN P2 | still accepted in hand-built packs | STILL_REPRODUCIBLE | ledger |
| ADV-P2-04 deadband default quadrant | OPEN P2 | documented default still resolves a named quadrant | STILL_REPRODUCIBLE | ledger (product decision) |
| ADV-P2-05 corrupted latest.json error surface | OPEN P2 | raw `ValidationError` still propagates (fail-closed, no fixture) | STILL_REPRODUCIBLE | ledger (serving owner) |
| ADV-P2-06 snapshot_id ignores lineage | OPEN P2 | identical id with/without `previous_snapshot` | STILL_REPRODUCIBLE | ledger (identity contract) |
| ADV-P2-07 to_json ordering docstring | OPEN P2 | unchanged | STILL_REPRODUCIBLE | ledger |
| ADV-P2-08 retry copies prior delta | OPEN P2 | unchanged (retry-is-not-a-new-week) | STILL_REPRODUCIBLE | ledger |
| ADV-P2-09 unit cross-check absent | OPEN P2 | unchanged (no authority) | STILL_REPRODUCIBLE | ledger |
| ADV-P2-10 conftest shadowing | FIXED in #138 | condition absent on main (no second un-packaged conftest) | STALE on current main | lesson applied: `tests/redteam139/__init__.py` |
| ADV-GAP-01 history surfaces | GAP (#135 WIP) | present and exercised | **CLOSED by merged #135** | regression coverage |
| ADV-GAP-02 weekly comparability | GAP (#132 WIP) | gate present | **CLOSED by merged #132** | none |
| ADV-GAP-03 launcher/runtime | NOT_EXERCISED | untouched (git diff) | NOT_EXERCISED | LOCAL-B lane |
| ADV-GAP-04 Wind lanes | NOT_EXERCISED | providers disabled in config | NOT_EXERCISED | explicit non-blocking cell |
| **ADV-P2-11 (new)** | — | duplicate canonical series across bindings not rejected; over-weights family aggregate | **NEW / OPEN P2** | ledger (WEB-CONTROL authority) |

Headline reproduction evidence lives in `repro_current_main.py` (three attacks, run at `036b584`):
1. **ATTACK 1** — `fred:PAYEMS` and `wind:CPIAUCSL` rows served as `US_CORE_CPI` evidence (fixed by the ported #138 fix).
2. **ATTACK 2** — latest-pointer monotonicity already closed by #135 on current main.
3. **ATTACK 3** — week 2 raised `SyntheticMovementError` (closed by the OBSERVED_UPDATE contract on this branch).
