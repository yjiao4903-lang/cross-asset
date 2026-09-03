# Cross-Asset Next Phase Implementation Plan v1

**Baseline:** `main@65199cca40964354f56f0bfe06ad9a873fc16d37`  
**Status:** implementation plan / post-PR #15 consolidation  
**Scope:** Real Wind 6-Series → Real E2E → Calendar Contract → Asset Component Eligibility → Minimal Valuation / Carry / Risk → Shadow Validation → Decision Delta

---

## 1. Authority and non-goals

This plan inherits the current Marco/Cross boundary and the merged Wind canonicalizer. It does not redesign the provider framework, DuckDB schema, Marco Integration Contract, or allocation architecture from scratch.

Hard boundaries:

- Marco remains the sole Macro / Fundamental / Structural / Regime engine.
- Cross remains the Cross-Asset Decision & Allocation engine.
- No zero-fill or raw forward-fill.
- No guessed Wind codes or silent semantic substitution.
- No synthetic/web substitute presented as formal production market history.
- Price Index semantics stay unchanged for the first real E2E.
- CNY and CN_CREDIT remain non-allocation diagnostics/view-only where applicable.
- Development priors are not promoted to optimal parameters before real-data OOS validation.

### Documentation authority note

`WIND_MANUAL_DATA_REQUIREMENTS.md` and parts of `DEVELOPMENT_ROADMAP.md` reflect an older source strategy in which Yahoo/FRED could act as primary sources for several market series. For the first formal real-data E2E defined by this plan, that source strategy is superseded: the six hard market series must be confirmed from Wind/PC-B and ingested through the formal Wind → canonical CSV → production importer path. Older documents remain historical context until separately cleaned up.

---

## 2. Current facts at this baseline

- Wind Canonicalizer v1 is merged through PR #15.
- `config/wind_canonical_mapping.yml` defines the six required first-E2E series and intentionally keeps every `source_series_id: null` until PC-B terminal confirmation.
- `src/cross_asset/ingestion/wind_canonicalizer.py` and `src/cross_asset/ingestion/production_csv.py` already provide the approved conversion and production-ingestion path.
- `src/cross_asset/engines/asset_score.py` currently renormalizes component weights over only the available components. This is correct for ordinary missing data but is not sufficient to represent components that are economically inapplicable to an asset.
- `src/cross_asset/operations/calendar.py` already provides a configuration-backed calendar abstraction, but its current generic weekend rule cannot represent CN_INTERBANK make-up working weekends.
- `config/calendars.yml` currently contains only unverified generic US/CN/HK/FX placeholders.
- `config/series_calendars.yml` is currently empty.
- `config/series.yml` still relies on fixed `stale_after_hours`; this must not be treated as the final calendar-aware freshness contract.

---

## 3. Delivery sequence and gates

```text
P0-A  PC-B Wind 6-Series semantic confirmation
  ↓
P0-B  Real 2014→latest complete-day backfill
  ↓
P0-C  First formal Marco + Cross real E2E
  ↓
P0-D  Calendar Contract v1
  ↓
P0-E  Calendar-Aware Data Health
  ↓
P1-A  Asset × Component Eligibility Contract
  ↓
P1-B  Minimal Valuation v1
  ↓
P1-C  Minimal Carry v1
  ↓
P1-D  Risk Data v1
  ↓
P1-E  Source Shadow Validation
  ↓
P1-F  Decision Delta / Why Changed
  ↓
P2    Real PIT walk-forward / OOS and parameter admission
```

A later stage must not silently compensate for an unmet earlier semantic/data gate.

---

# 4. P0-A — PC-B Wind 6-Series Confirmation

## Scope

Confirm exactly these canonical series:

- `CN_EQ_LARGE` — CSI 300 Price Index
- `HK_EQ` — Hang Seng Price Index
- `US_EQ` — S&P 500 Price Index
- `CN_BOND_10Y` — ChinaBond 10Y Government Yield
- `GOLD` — COMEX Gold continuous proxy
- `COPPER` — COMEX Copper continuous proxy

For each series PC-B must record:

1. exact Wind code;
2. exact instrument/indicator name;
3. field name;
4. unit and currency;
5. price vs total-return semantics;
6. for futures: continuous construction method and adjusted/unadjusted semantics;
7. for futures: SETTLE vs CLOSE;
8. earliest reliable history and latest complete observation;
9. Wind export timestamp and entitlement/terminal notes.

## Dependency

PR #15 merged and canonicalizer available.

## Data required

Wind Terminal confirmation. No candidate code is sufficient evidence.

## Code touchpoints

Only after confirmation:

- `config/wind_canonical_mapping.yml`

No model code should change in this step.

## Tests

- mapping parser accepts confirmed IDs;
- raw workbook dry-run resolves all six intended series;
- no unresolved/mis-mapped extra series;
- field semantics in report match the approved checklist.

## Acceptance criteria

- six exact Wind IDs confirmed;
- futures `price_type=settle` confirmed if `COMEX_EOD_V1` 06:00 policy is retained;
- no Price/Total Return ambiguity;
- no guessed mapping remains.

## Out of scope

Valuation PE series, COT, VIX, HY OAS, style series, additional commodities.

---

# 5. P0-B — Real 6-Series Backfill

## Scope

Backfill from `2014-01-01` to the latest complete trading/business day using genuine Wind exports.

Formal path:

```text
PC-B Wind raw export
→ cross-asset canonicalize-wind-export
→ canonical production CSV
→ cross-asset ingest-production-csv
→ formal DuckDB on PC-A
```

PC-B transfers inputs only; PC-B does not transfer DuckDB/WAL/cache/runtime state.

## Dependency

P0-A complete.

## Data required

Six confirmed Wind series with complete raw exports and immutable raw files.

## Code touchpoints

Expected reuse, not redesign:

- `src/cross_asset/ingestion/wind_canonicalizer.py`
- `src/cross_asset/ingestion/production_csv.py`
- `src/cross_asset/cli.py`
- `config/wind_canonical_mapping.yml`

Only fix defects proven by real exports.

## Tests

- canonicalizer dry-run before write;
- duplicate observation rejection;
- blank omission without fill;
- invalid numeric rejection;
- aware `available_at` normalization to UTC-naive storage semantics;
- idempotent repeated ingest;
- immutable raw archive hash preserved;
- min/max observation date and row counts per series audited.

## Acceptance criteria

- all six series exist in formal Cross DuckDB;
- no synthetic/web observations in the formal six-series history;
- coverage begins no later than the approved start date or the shortfall is explicitly documented;
- no unresolved mapping or semantic mismatch warnings.

## Out of scope

Automatic PC-B daemon, cloud DB sync, generic Wind API framework.

---

# 6. P0-C — First Formal Marco → Cross Real E2E

## Scope

Run one end-to-end decision using:

- a real Marco Integration Contract v1 bundle;
- the formal Cross DuckDB containing the six real market series.

Validate the whole decision chain through score/allocation/report outputs without introducing new factors merely to improve apparent completeness.

## Dependency

P0-B complete and a valid Marco bundle available.

## Code touchpoints

Primarily existing runtime integration and live/report path. Any edit must be driven by a reproducible failure.

## Tests / evidence

- Marco manifest exact-byte validation passes;
- Cross reads only observations available by the selected cutoff;
- no unavailable Marco signal is zero-filled;
- score contribution and confidence are reproducible;
- allocation weights sum to 1 and respect constraints;
- run manifest records model/data cutoff versions.

## Acceptance criteria

A reproducible real-data run can be rebuilt from archived inputs and the exact code revision.

## Out of scope

Performance claims, optimized tactical parameters, expanded asset universe.

---

# 7. P0-D — Calendar Contract v1

## Scope

Introduce explicit calendars:

- `CN_EQ`
- `HK_EQ`
- `US_EQ`
- `CN_INTERBANK`
- `CME_COMEX`

The key semantic split is `CN_EQ != CN_INTERBANK`.

Required capabilities:

- special closures;
- early close where applicable;
- DST-aware timezone handling;
- CME trade/business date preservation;
- Chinese interbank make-up working weekends;
- versioned static calendar data/audit evidence.

## Dependency

First real E2E completed so calendar changes can be validated against actual observations rather than only fixtures.

## Code touchpoints

- `src/cross_asset/operations/calendar.py`
- `src/cross_asset/operations/exchange_calendar.py`
- `config/calendars.yml`
- `config/series_calendars.yml`
- new versioned calendar CSV files if required
- calendar unit tests and PIT boundary tests

## Minimal design change

Do not keep the current universal `day.weekday() >= 5 => CLOSED` rule as the authoritative session rule. Session openness must come from the calendar contract/data so CN_INTERBANK can legitimately be OPEN on selected make-up weekends.

## Tests

- CN_EQ closed on weekends including make-up work weekends;
- CN_INTERBANK can be open on approved make-up work weekends;
- historical HK special closures and early-close regime cases;
- US DST boundaries;
- CME business date around evening sessions and holidays;
- unknown/out-of-coverage years return UNKNOWN rather than fabricated OPEN/CLOSED.

## Acceptance criteria

Every formal six-series market observation can resolve to an explicit `calendar_id`; calendar decisions are deterministic and auditable.

## Out of scope

US_BOND, NYMEX, FX_24X5 until P1/P2 need them.

---

# 8. P0-E — Calendar-Aware Data Health

## Scope

Replace simplistic elapsed-time interpretation with session-aware states:

- `EXPECTED_FRESH`
- `EXPECTED_CLOSED`
- `EXPECTED_STALE`
- `UNEXPECTED_MISSING`
- `SOURCE_STALE`

Existing `stale_after_hours` may remain as a fallback/secondary threshold during migration but must not classify a known market closure as an error.

## Dependency

Calendar Contract v1.

## Code touchpoints

- `src/cross_asset/ingestion/quality.py`
- live/quality report path
- `config/series.yml`
- `config/series_calendars.yml`
- `src/cross_asset/operations/shadow.py` reporting logic

## Tests

- CN holiday closure => expected stale/closed, not critical failure;
- CN_INTERBANK OPEN with no observation => unexpected missing;
- genuine provider delay after expected session => source stale;
- allocation freeze only follows configured critical unhealthy states.

## Acceptance criteria

Data-health output explains *why* a stale-looking series is acceptable or abnormal and does not rely solely on wall-clock age.

---

# 9. P1-A — Asset × Component Eligibility Contract

## Scope

Add explicit eligibility state per asset/component:

- `ACTIVE`
- `UNAVAILABLE`
- `DIAGNOSTIC`
- `OVERLAY`
- `HURDLE`

This contract separates structural inapplicability from ordinary data missingness.

## Why required

`score_asset()` currently divides each available component contribution by the total available weight. If an asset only has one economically meaningful component, that component can absorb 100% of effective score weight. This is acceptable for transient missingness only if the missing components were genuinely expected; it is wrong when components are structurally inapplicable.

## Dependency

Real E2E and calendar/data-health stable enough to distinguish data missingness from semantic eligibility.

## Code touchpoints

- `config/allocation.yml` or a small dedicated eligibility config;
- `src/cross_asset/engines/asset_score.py`;
- `AssetScore` output fields / report serialization;
- confidence/coverage tests;
- allocation/report UI consumers as needed.

## Minimal implementation principle

Do not create a complex inheritance/type hierarchy. A validated mapping of `asset_id -> component -> eligibility` plus explicit score handling is sufficient for v1.

## Tests

- ACTIVE + missing data lowers expected coverage/confidence;
- UNAVAILABLE does not count as missing data and is never renormalized as if it were expected;
- DIAGNOSTIC cannot alter base asset score;
- OVERLAY cannot enter the linear component sum;
- HURDLE can influence a threshold/opportunity-cost path but not masquerade as ordinary carry;
- CASH carry/hurdle case cannot become a 100%-weight linear score by missing-component renormalization.

## Acceptance criteria

Every asset/component has an explicit semantic state and score attribution can distinguish `missing` from `not applicable`.

---

# 10. P1-B — Minimal Valuation v1

## Scope

Only:

- CN_EQ trailing earnings yield;
- HK_EQ trailing earnings yield;
- US_EQ trailing earnings yield.

Gold and commodity valuation remain `UNAVAILABLE`; no pseudo-valuation using real yield/DXY.

## Dependency

Eligibility contract plus Wind/source semantics confirmation for valuation series.

## Data required

Exact index PE TTM/earnings-yield source semantics, historical reconstruction/restatement risk, constituent-history behavior, daily snapshot/PIT confidence.

## Code touchpoints

New factor implementation should use existing feature/engine conventions; exact module location is selected after auditing neighboring feature modules. Add only the minimal series/config required for the three equity assets.

## Tests

- PE <= 0 / invalid handling;
- earnings-yield transform;
- rolling percentile uses only prior/available history;
- insufficient history returns unavailable/low coverage, not zero;
- PIT metadata propagated.

## Acceptance criteria

Three equity valuation components can be replayed without forward information; 5Y percentile, if used initially, remains labelled `DEVELOPMENT_PRIOR` pending 3Y/5Y/7Y OOS comparison.

---

# 11. P1-C — Minimal Carry v1

## Scope

First active research candidates:

- `CN_BOND_CARRY_PROXY_V1`;
- Copper COMEX front-next curve carry.

`CASH` is a `HURDLE`, not an ordinary carry component. Gold carry remains diagnostic-only/unavailable for active score.

## Dependency

Eligibility contract; exact data semantics available.

## Data required

- CN bond yield/slope inputs and explicit proxy definition;
- COMEX front and next contract/continuous data with roll convention and SETTLE semantics.

## Tests

- no label implying true carry when formula is a proxy;
- roll-boundary continuity and contract identity;
- no future contract information before available;
- missing leg => unavailable, no synthetic fill.

## Acceptance criteria

Carry contribution is economically interpretable and does not alter assets for which carry is not ACTIVE.

---

# 12. P1-D — Risk Data v1

## Scope

Only:

- VIX — `OVERLAY` / implied volatility;
- US HY OAS — credit stress;
- CFTC Gold COT — `DIAGNOSTIC` warning/crowding/fragility.

Do not freeze externally suggested VIX multipliers before real-data/OOS testing. COT is not contrarian alpha.

## Dependency

Eligibility/overlay semantics available.

## Data required

Canonical source, available_at/revision semantics and immutable raw snapshots. Historical HY OAS source must not assume unlimited FRED history if entitlement/history is incomplete.

## Acceptance criteria

Risk mechanisms remain separated by responsibility and do not become another undifferentiated linear alpha score.

---

# 13. P1-E — Source Shadow Validation

## Scope

Add semantic-aware canonical-vs-shadow checks:

- date mismatch;
- staleness;
- level difference when semantically comparable;
- return difference when level comparison is invalid.

Shadow source never auto-falls back into production simply because it exists.

## Dependency

Stable canonical sources and calendar semantics.

## Code touchpoints

Reuse/extend existing `src/cross_asset/operations/shadow.py`; keep source comparison separate from trading/allocation decisions.

## Tests

- index vs ETF cannot be declared level-equivalent by default;
- different continuous futures construction cannot be compared by raw level;
- warning emitted without automatic provider substitution.

---

# 14. P1-F — Decision Delta / Why Changed

## Scope

Persist/report previous vs current score and driver deltas, e.g.:

```text
CN_EQ
last score:     0.42
current score:  0.61
delta:         +0.19

drivers:
Trend       +0.13
Valuation   +0.08
Macro       -0.02

Risk: NORMAL
Crowding: N/A
```

## Dependency

Stable component semantics and versioned score history.

## Code touchpoints

- `AssetScore.contributions` and serialized score outputs;
- run/report history query;
- later UI presentation.

## Tests

- driver deltas sum consistently with score delta subject to clipping/overlay semantics;
- unavailable/diagnostic components are labelled, not silently treated as zero;
- model-version changes are visible in comparison metadata.

## Acceptance criteria

A user can answer “why did the recommendation change?” from stored outputs without reconstructing internal state manually.

---

# 15. Immediate blockers and parallelizable work

## External blocker

Real 6-Series mapping/backfill cannot proceed until PC-B confirms exact Wind semantics. This is the next production-data gate.

## Safe parallel work while waiting for PC-B

Only design/test preparation that does not pretend the data gate is closed:

1. prepare the six-series terminal confirmation checklist;
2. prepare calendar fixtures/contracts and document known special cases;
3. write eligibility contract tests/design against existing `score_asset()` behavior;
4. audit and mark stale source-strategy documentation.

Do not populate mapping IDs, create fake formal DB rows, or claim real E2E completion.

---

# 16. Definition of done for this phase

The next phase is considered complete only when:

- six approved real Wind market series are in the formal PC-A DuckDB;
- at least one real Marco → Cross decision run is reproducible;
- calendar and data-health states are session-aware;
- asset/component eligibility prevents structural renormalization errors;
- minimal valuation/carry/risk modules use only semantically approved data;
- shadow validation cannot silently replace canonical sources;
- decision outputs expose score change and drivers;
- walk-forward/OOS can replay point-in-time inputs without future leakage.

Until those gates pass, research parameters remain `DEVELOPMENT_PRIOR` and production claims remain limited to the capabilities actually demonstrated.
