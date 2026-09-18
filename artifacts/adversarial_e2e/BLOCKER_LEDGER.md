# BLOCKER LEDGER — ADVERSARIAL-E2E-VALIDATION-V1

- Owner lane: `WEEKEND-REDTEAM`
- Baseline main: `5cac5c44b08e43760888362636cadbf3ffb40f1e`
- Items: **16**
- Severity: P0 fabricates/overwrites authority or crosses lanes; P1 misstates data/decision/history or breaks
  normal use; P2 diagnosability/maintenance gap without current decision corruption.
- No severity was inflated to consume work: no P0 was found by this window.

## ADV-P1-01 — Real multi-week monitoring loop cannot produce week 2 once new monthly data arrives

- **Severity:** P1
- **Invariant:** capture_time != first_release_time; MONITORING != FORMAL_OOS
- **Affected path:** `src/cross_asset/decision_support/monitoring_adapter.py -> producer.build_monitoring_snapshot -> weekly.build_macro_state_delta`
- **Owner:** REAL-SNAPSHOT-V1 owner (ONLINE-DEV-A) with WEB-CONTROL coordination
- **Status:** OPEN / BLOCKER
- **Fixability:** NOT FIXED BY THIS WINDOW — requires a product-policy decision about what constitutes a new release for the monitoring lane (first-release vs capture-time, revision handling). Any narrow implementation would invent that policy.
- **Overlap check:** monitoring_adapter.py and producer.py are not touched by PR #135/#132/#136; the policy decision is adjacent to #133/#135 multi-week continuity, so it must not be fixed unilaterally.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_c2_emergent.py -k e2_01
or: build_monitoring_pack_from_db(store, workbench_run(week1)) -> build_monitoring_snapshot -> ok
then: build_monitoring_pack_from_db(store, workbench_run(week2 with a new monthly row)) ->
build_monitoring_snapshot(pack2, previous_snapshot=snapshot1) raises SyntheticMovementError
```

**Current evidence:** tests/adversarial/test_c2_emergent.py::test_adv_e2_01...; tests/adversarial/test_b7_weekly_lane.py::test_adv_b7_04...

**Root-cause hypothesis:** build_monitoring_pack_from_db never populates release_events/expected_releases, so information_set_delta.status is always NO_NEW_INFORMATION while cyclical factor scores genuinely move; the producer's synthetic-movement guard then (correctly) refuses to emit the week.

## ADV-P1-02 — SnapshotStore.persist has no economic monotonicity guard on the latest pointer

- **Severity:** P1
- **Invariant:** late technical creation != economic latest
- **Affected path:** `src/cross_asset/decision_support/serving.py (SnapshotStore.persist/load_latest)`
- **Owner:** PR #135 / issue #133 (DECISION-HISTORY-V1)
- **Status:** OPEN / BLOCKER
- **Fixability:** NOT FIXED BY THIS WINDOW — serving.py is inside PR #135's active edit surface.
- **Overlap check:** serving.py is modified by PR #135; a competing edit would create a real conflict. The CLI mitigates by never looking ahead (ADV-E2-09) but direct store use does not.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_b6_snapshot_api.py -k b6_06
persist a snapshot with as_of 2026-09-18, then persist a backfilled snapshot with as_of 2026-09-11
SnapshotStore.load_latest() now returns the older snapshot
```

**Current evidence:** tests/adversarial/test_b6_snapshot_api.py::test_adv_b6_06_backfilled_older_snapshot_must_not_become_latest

**Root-cause hypothesis:** latest.json is written unconditionally on every persist; the pointer is ordered by write time, not by (as_of, decision_time).

## ADV-P2-01 — Monitoring read model did not re-validate persisted row identity (FIXED)

- **Severity:** P2
- **Invariant:** provider/source identity mismatch != comparable series
- **Affected path:** `src/cross_asset/decision_support/monitoring_adapter.py`
- **Owner:** WEEKEND-REDTEAM (this task)
- **Status:** FIXED / REGRESSION-TESTED
- **Fixability:** FIXED — narrow fail-closed validation reusing the accepted catalog.expected_source_identities authority; violating series are represented as BLOCKED with explicit identity_blockers, mirroring MONITORING_SCHEMA_ERROR -> FAILED -> BLOCKED.
- **Overlap check:** monitoring_adapter.py is not in any of PR #135/#132/#136; no product/economic policy changed.

**Exact reproduction**

```text
before the fix: persist US_CORE_CPI rows with source_series_id=PAYEMS under a MONITORING:fred run
build_monitoring_pack_from_db -> US_CORE_CPI accepted with source_refs ['fred:PAYEMS']
```

**Current evidence:** tests/adversarial/test_b1_identity_source.py::test_adv_b1_02, ::test_adv_b1_03, ::test_adv_b1_15

**Root-cause hypothesis:** MonitoringRunner._validate_rows enforces identity at ingestion, but the read model is a separate boundary where rows may have been written directly or by another window.

## ADV-P2-02 — Direct MonitoringObservationPack contract has no duplicate-observation-date guard

- **Severity:** P2
- **Invariant:** duplicate observation dates are not comparable evidence
- **Affected path:** `src/cross_asset/decision_support/producer.py (_validate_pack)`
- **Owner:** REAL-SNAPSHOT-V1 owner
- **Status:** OPEN / LOW-IMPACT
- **Fixability:** NOT FIXED — the correct resolution (reject vs latest-vintage-wins) is a contract decision, and the affected surface is the diagnostic --input path.
- **Overlap check:** producer.py not in PR #135/#132/#136.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_b2_time_causality.py -k b2_04
append two rows with the same observation_date and different available_at to a hand-built pack
build_monitoring_snapshot accepts it
```

**Current evidence:** tests/adversarial/test_b2_time_causality.py::test_adv_b2_04_duplicate_dates_in_direct_pack_are_not_guarded

**Root-cause hypothesis:** The ordering check does not imply de-duplication; the DB read model resolves duplicates by latest vintage (ADV-B2-03), so only hand-built packs are affected.

## ADV-P2-03 — metadata.as_of may diverge from details.data_cutoff in the pack contract

- **Severity:** P2
- **Invariant:** one snapshot identity must correspond to one economic state
- **Affected path:** `src/cross_asset/decision_support/producer.py + monitoring_adapter.py`
- **Owner:** REAL-SNAPSHOT-V1 owner
- **Status:** OPEN / LOW-IMPACT
- **Fixability:** NOT FIXED — needs a decision on whether as_of is derived from data_cutoff or independently meaningful.
- **Overlap check:** producer.py not in PR #135/#132/#136.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_b2_time_causality.py -k b2_14
build a pack whose as_of is 30 days before lineage.data_cutoff
the snapshot is accepted; metadata.as_of is the older date while details.data_cutoff is the newer one
```

**Current evidence:** tests/adversarial/test_b2_time_causality.py::test_adv_b2_14_as_of_cutoff_divergence_is_visible_in_the_snapshot

**Root-cause hypothesis:** as_of is treated as a display field while data_cutoff carries the evidence boundary; the runtime adapter always sets them equal, so only hand-built packs diverge.

## ADV-P2-04 — First snapshot with both regime axes inside the deadband resolves to a named quadrant

- **Severity:** P2
- **Invariant:** NO_GUESSED_SOURCE_SEMANTICS / MISSING != ZERO
- **Affected path:** `src/cross_asset/decision_support/regime.py (candidate_quadrant default prior)`
- **Owner:** Decision-Support-V2 owner / WEB-CONTROL
- **Status:** OPEN / DIAGNOSABILITY
- **Fixability:** NOT FIXED — changing the first-snapshot label changes product semantics and would invalidate accepted Scope E behaviour.
- **Overlap check:** regime.py not in PR #135/#132/#136.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_b4_factor_regime.py -k b4_20
RegimeEngine(axis_threshold=0.25).candidate_quadrant(0.0, 0.0, prior=None) -> GOLDILOCKS
```

**Current evidence:** tests/adversarial/test_b4_factor_regime.py::test_adv_b4_20_first_snapshot_all_deadband_resolves_via_the_documented_default; tests/unit/decision_support/test_regime.py::test_initial_state_without_prior

**Root-cause hypothesis:** Deadband hysteresis inherits a prior quadrant; with no prior it defaults to GOLDILOCKS, so an ambiguous first reading becomes a specific economic label.

## ADV-P2-05 — A corrupted latest.json surfaces a raw pydantic ValidationError

- **Severity:** P2
- **Invariant:** failure semantics must be typed and must not leak internals
- **Affected path:** `src/cross_asset/decision_support/serving.py`
- **Owner:** PR #135 / issue #133
- **Status:** OPEN / BLOCKER (overlap)
- **Fixability:** NOT FIXED — serving.py is inside PR #135's active edit surface.
- **Overlap check:** serving.py is modified by PR #135.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_b6_snapshot_api.py -k b6_04
write '{ not json' to <root>/latest.json, then call SnapshotReadService.health()
a pydantic ValidationError propagates (the HTTP layer turns it into a 404 carrying that text)
```

**Current evidence:** tests/adversarial/test_b6_snapshot_api.py::test_adv_b6_04..., ::test_adv_b6_05..., ::test_adv_b6_12b...

**Root-cause hypothesis:** health() only guards FileNotFoundError; parse/validation failures fall through the generic ValueError handler and lose their severity semantics.

## ADV-P2-06 — snapshot_id does not cover previous_snapshot, so distinct bodies can collide

- **Severity:** P2
- **Invariant:** one snapshot id == one snapshot body
- **Affected path:** `src/cross_asset/decision_support/producer.py (_snapshot_id)`
- **Owner:** REAL-SNAPSHOT-V1 owner with PR #133/#135
- **Status:** OPEN / LOW-IMPACT (store would silently overwrite)
- **Fixability:** NOT FIXED — changing the identity formula alters persisted snapshot ids and interacts with #133/#135 history.
- **Overlap check:** producer.py not in PR #135/#132/#136, but the identity contract is shared with decision history.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_b6_snapshot_api.py -k b6_07
build the same pack with and without previous_snapshot
identical snapshot_id, different serialized bodies
```

**Current evidence:** tests/adversarial/test_b6_snapshot_api.py::test_adv_b6_07_snapshot_id_ignores_previous_snapshot_lineage

**Root-cause hypothesis:** The hash covers the pack, registry version, taxonomy version and model version, but not the lineage inputs that change regime dwell and weekly deltas.

## ADV-P2-07 — to_json documents 'sorted keys' but preserves details insertion order; the HTTP layer sorts

- **Severity:** P2
- **Invariant:** documented serialization contract must match behaviour
- **Affected path:** `src/cross_asset/decision_support/snapshot.py (to_json) and serving.py (_Handler._json)`
- **Owner:** PR #135 (serving.py) / REAL-SNAPSHOT-V1 owner (docstring)
- **Status:** OPEN / DIAGNOSABILITY
- **Fixability:** NOT FIXED — either the docstring or the serializer must change, and serving.py overlaps PR #135.
- **Overlap check:** both files touch PR #135's surface or its neighbours.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_b6_snapshot_api.py -k b6_12b
compare snapshot.to_json() bytes with the /api/snapshot/latest payload bytes for the same snapshot
```

**Current evidence:** tests/adversarial/test_b6_snapshot_api.py::test_adv_b6_12b_http_layer_sorts_keys_while_the_model_does_not

**Root-cause hypothesis:** pydantic model_dump_json preserves mapping order; the docstring overstates the guarantee.

## ADV-P2-08 — Same-week retry copies the prior asset delta while recomputing the asset views

- **Severity:** P2
- **Invariant:** weekly-change surfaces must describe real week-over-week movement
- **Affected path:** `src/cross_asset/decision_support/producer.py (build_monitoring_snapshot same_week_retry branch)`
- **Owner:** REAL-SNAPSHOT-V1 owner / PR #133-#135
- **Status:** OPEN / DIAGNOSABILITY
- **Fixability:** NOT FIXED — requires deciding whether an intra-week revision is a new weekly-change event; overlaps decision-history semantics.
- **Overlap check:** producer.py not in PR #135/#132/#136, but the semantic overlaps #133's multi-week continuity.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_c2_emergent.py -k e2_03
build week W, then a same-week retry whose market confirmation flips
the retry's asset views change while its copied asset_view_delta stays empty
```

**Current evidence:** tests/adversarial/test_c2_emergent.py::test_adv_e2_03_same_week_retry_can_desynchronise_delta_and_views

**Root-cause hypothesis:** Carrying the prior weekly deltas forward is correct for 'a retry is not a new week', but the recomputed views are then not represented anywhere, so an intra-week information change becomes invisible.

## ADV-P2-09 — No unit cross-check between the provider contract and the series catalog

- **Severity:** P2
- **Invariant:** unit semantics are part of the source-identity contract
- **Affected path:** `src/cross_asset/decision_support/monitoring_adapter.py, src/cross_asset/ingestion/monitoring.py, src/cross_asset/storage/catalog.py`
- **Owner:** PROVIDER-CALENDAR-V1 owner (ONLINE-DEV-B)
- **Status:** OPEN / DIAGNOSABILITY
- **Fixability:** NOT FIXED — no authority currently defines a machine-checkable unit contract for the monitoring lane.
- **Overlap check:** no overlap with PR #135/#132/#136.

**Exact reproduction**

```text
config/series.yml declares US_NONFARM_PAYROLLS as thousands_persons
FRED_MONITORING_CONTRACTS declares the same unit, but no code compares them; update_catalog_from_monitoring_rows only fills empty fields
```

**Current evidence:** static review; tests/adversarial/test_b1_identity_source.py covers identity but no unit case exists

**Root-cause hypothesis:** Monitoring factor transforms are unit-free (z-scores / trends), so a unit divergence has no decision impact today; it would matter for any level-based consumer.

## ADV-P2-10 — A second un-packaged tests/**/conftest.py silently shadows tests/conftest.py (FIXED)

- **Severity:** P2
- **Invariant:** test collection must not change the meaning of an existing import
- **Affected path:** `tests/**/conftest.py import identity; affects tests/integration/test_formal_consumption_gate.py, tests/unit/integration/test_marco_provider.py and tests/integration/test_first_real_marco_cross_e2e.py`
- **Owner:** WEEKEND-REDTEAM (this task); relevant to any lane adding a new tests/ subdirectory
- **Status:** FIXED / REGRESSION-TESTED
- **Fixability:** FIXED in this task: the new test directory is now an importable package, so its conftest gets a qualified module name. Any future lane adding tests under a new directory should do the same.
- **Overlap check:** no overlap with PR #135/#132/#136.

**Exact reproduction**

```text
add tests/<newdir>/conftest.py without tests/<newdir>/__init__.py
run: python -m pytest tests/<newdir> tests/integration/test_formal_consumption_gate.py
ImportError: cannot import name 'approve_test_series' from 'conftest'
the same suite passes when tests/integration is collected first, so the breakage is ordering-dependent
```

**Current evidence:** reproduced on commit 98c3d488 with the plain `pytest -q` collection order; fixed in d08aed91 by adding tests/adversarial/__init__.py

**Root-cause hypothesis:** pytest's prepend import mode imports a conftest.py from a directory without __init__.py under the bare name `conftest`; two such files cannot coexist, and only the first collected wins.

## ADV-GAP-01 — No history-enumeration or current/prior diff surface on baseline main

- **Severity:** P2
- **Invariant:** decision history must exist for the product
- **Affected path:** `src/cross_asset/decision_support/serving.py`
- **Owner:** PR #135 / issue #133
- **Status:** GAP / ADJACENT-WIP
- **Fixability:** NOT FIXED BY DESIGN — dedicated adjacent WIP.
- **Overlap check:** explicit non-overlap rule for this task.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_b6_snapshot_api.py -k b6_15
SnapshotStore exposes only load/load_latest/persist
```

**Current evidence:** tests/adversarial/test_b6_snapshot_api.py::test_adv_b6_15_history_and_diff_surfaces_are_absent_on_current_main

**Root-cause hypothesis:** Intentionally unmerged: PR #135 implements it.

## ADV-GAP-02 — Weekly semantic-comparability gate absent on baseline main

- **Severity:** P2
- **Invariant:** lookback/source changes must stay comparable
- **Affected path:** `src/cross_asset/research/weekly_core.py`
- **Owner:** PR #132 / issue #131
- **Status:** GAP / ADJACENT-WIP
- **Fixability:** NOT FIXED BY DESIGN — dedicated adjacent WIP.
- **Overlap check:** explicit non-overlap rule for this task.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_b7_weekly_lane.py -k b7_12
cross_asset.research.weekly_core has no source/semantic comparability gate
```

**Current evidence:** tests/adversarial/test_b7_weekly_lane.py::test_adv_b7_12_weekly_comparability_gate_is_owned_by_131_132

**Root-cause hypothesis:** Intentionally unmerged: PR #132 implements it.

## ADV-GAP-03 — Windows launcher / process-ownership scenarios not exercisable in this window

- **Severity:** P2
- **Invariant:** native runtime behaviour needs native evidence
- **Affected path:** `PR #136 files`
- **Owner:** PR #136 / issue #134
- **Status:** NOT_EXERCISED
- **Fixability:** NOT FIXED BY DESIGN — EXTERNAL_EVIDENCE.
- **Overlap check:** explicit non-overlap rule for this task.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_b8_runtime_boundary.py -k b8_07
launcher/ and START_MACRO_WORKBENCH.cmd are absent from baseline main
```

**Current evidence:** tests/adversarial/test_b8_runtime_boundary.py::test_adv_b8_07_native_windows_process_semantics_are_not_exercised_here

**Root-cause hypothesis:** PR #136 is the owner of native process proof; CI/Linux cannot prove Windows process semantics.

## ADV-GAP-04 — Wind / iFinD / Tushare / CN proprietary identity lanes not exercised

- **Severity:** NONE
- **Invariant:** no-Wind window must be explicit
- **Affected path:** `config/sources.yml, config/wind_canonical_mapping.yml`
- **Owner:** LOCAL-DEV-A / issue #93 (only when real files exist)
- **Status:** NOT_EXERCISED / NO-WIND
- **Fixability:** NOT APPLICABLE — must remain NOT_EXERCISED/BLOCKED.
- **Overlap check:** no code or config was changed to manufacture Wind-equivalent data.

**Exact reproduction**

```text
python -m pytest tests/adversarial/test_b1_identity_source.py -k b1_12
config/sources.yml keeps wind/ifind/tushare disabled
```

**Current evidence:** tests/adversarial/test_b1_identity_source.py::test_adv_b1_12_wind_only_identity_is_not_exercisable_in_this_window; tests/adversarial/test_b3_freshness_calendar.py honours the same limit

**Root-cause hypothesis:** Hard environment assumption of this dispatch window.
