# ADVERSARIAL MATRIX — MULTIWEEK-MONITORING-CLOSURE-REDTEAM-V1

- Owner lane: `LOCAL-DEV-A` (#139)
- Baseline main: `036b58450226e2b4c2e88401ca246aa2b3fe6024`
- Total cases: **166**
- Status counts: {"PASS": 138, "FAIL_FIXED": 12, "NOT_EXERCISED": 7, "FAIL_BLOCKER": 6, "BLOCKED_POLICY": 2, "GAP": 1}
- Per-layer counts: {"identity_source": 24, "time_causality": 16, "freshness_calendar": 10, "factor_regime": 14, "asset_rules": 10, "snapshot_history_api": 26, "weekly_lane": 18, "runtime_boundary": 14, "emergent": 16, "lane_separation": 2, "evidence": 7, "soak": 5, "history": 2, "snapshot_history": 2}
- Environment: NO WIND / no proprietary local files; such cells are NOT_EXERCISED, which is not a blocker.

Status vocabulary: `PASS` (invariant holds), `FAIL_FIXED` (violated on current main, narrow fix shipped
on this branch), `FAIL_BLOCKER` (violated, recorded in the ledger), `GAP` (no authority yet),
`BLOCKED_POLICY` (needs WEB-CONTROL decision), `NOT_EXERCISED` (outside this window's surfaces).

| Case | Layer | Invariant | Status | Severity | Fix owner / note | Evidence |
|---|---|---|---|---|---|---|
| RT139-B1-01 | identity_source | governed identity is admissible for monitoring, never formal | **PASS** | none | n/a | tests/redteam139/test_b1_identity_source.py::test_b1_01_governed_identity_is_accepted_without_formal_authority |
| RT139-B1-02 | identity_source | wrong source_series_id is not comparable evidence (#138 P2-01 regression) | **FAIL_FIXED** | P1 | fixed this task (ported #138 fix) | tests/redteam139/test_b1_identity_source.py::test_b1_02_wrong_source_series_id_is_blocked |
| RT139-B1-03 | identity_source | row source != run provider is never silently relabelled | **FAIL_FIXED** | P1 | fixed this task | tests/redteam139/test_b1_identity_source.py::test_b1_03_row_source_mismatch_is_blocked |
| RT139-B1-04 | identity_source | series without an enabled mapping blocks (no guessed identity) | **FAIL_FIXED** | P1 | fixed this task | tests/redteam139/test_b1_identity_source.py::test_b1_04_series_without_enabled_mapping_is_blocked |
| RT139-B1-05 | identity_source | identity-blocked rows never reach the producer as evidence | **PASS** | none | n/a | tests/redteam139/test_b1_identity_source.py::test_b1_05_snapshot_refuses_when_only_poisoned_rows_exist |
| RT139-B1-06 | identity_source | one poisoned series does not corrupt a healthy sibling | **PASS** | none | n/a | tests/redteam139/test_b1_identity_source.py::test_b1_06_poisoned_series_does_not_corrupt_healthy_sibling |
| RT139-B1-07 | identity_source | duplicate canonical identity inside one binding is rejected | **PASS** | none | n/a | tests/redteam139/test_b1_identity_source.py::test_b1_07_duplicate_canonical_identity_is_rejected |
| RT139-B1-08 | identity_source | disabled source mapping cannot be bound | **PASS** | none | n/a | tests/redteam139/test_b1_identity_source.py::test_b1_08_disabled_source_mapping_cannot_be_bound |
| RT139-B1-09 | identity_source | ungoverned canonical series is rejected | **PASS** | none | n/a | tests/redteam139/test_b1_identity_source.py::test_b1_09_ungoverned_canonical_series_is_rejected |
| RT139-B1-10 | identity_source | a binding referencing an unknown factor is rejected | **PASS** | none | n/a | tests/redteam139/test_b1_identity_source.py::test_b1_10_binding_referencing_unknown_factor_is_rejected |
| RT139-B1-11 | identity_source | formal acceptance never leaks into the monitoring pack | **PASS** | none | n/a | tests/redteam139/test_b1_identity_source.py::test_b1_11_formal_rows_are_not_monitoring_evidence |
| RT139-B1-12 | identity_source | monitoring run provider must resolve | **FAIL_FIXED** | P1 | fixed this task | tests/redteam139/test_b1_identity_source.py::test_b1_12_unresolvable_run_provider_is_blocked |
| RT139-B1-13 | identity_source | poisoned inflation axis refuses the snapshot truthfully | **PASS** | none | n/a | tests/redteam139/test_b1_identity_source.py::test_b1_13_blocked_identity_refuses_snapshot_and_records_provenance |
| RT139-B1-14 | identity_source | proprietary providers stay disabled in the shipped config | **PASS** | none | n/a | tests/redteam139/test_b1_identity_source.py::test_b1_14_proprietary_providers_stay_disabled |
| RT139-B1-15 | identity_source | Wind-only identity lanes stay NOT_EXERCISED (no-Wind window) | **NOT_EXERCISED** | none | NO-WIND window | tests/redteam139/test_b1_identity_source.py::test_b1_15_wind_lanes_not_exercised |
| RT139-B1-16 | identity_source | identity revalidation is part of the read model, not only ingestion | **FAIL_FIXED** | P1 | fixed this task | tests/redteam139/test_b1_identity_source.py::test_b1_16_read_model_revalidates_directly_persisted_rows |
| RT139-B1-17 | identity_source | valid sibling in the same run is unaffected by direct persist | **PASS** | none | n/a | tests/redteam139/test_b1_identity_source.py::test_b1_17_direct_persist_healthy_row_still_served |
| RT139-B1-18 | identity_source | unit semantics remain declared for governed series | **PASS** | none | n/a | tests/redteam139/test_b1_identity_source.py::test_b1_18_series_catalog_declares_units |
| RT139-B2-01 | time_causality | future available_at is rejected at ingestion | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_01_observation_available_after_decision_time_is_rejected |
| RT139-B2-02 | time_causality | observation after data_cutoff is a hard boundary | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_02_observation_after_cutoff_never_served_by_read_model |
| RT139-B2-03 | time_causality | duplicate observation dates resolve to latest vintage | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_03_duplicate_dates_resolve_to_latest_vintage |
| RT139-B2-04 | time_causality | direct pack duplicate dates stay unguarded (P2-02 doc) | **FAIL_BLOCKER** | P2 | ADV-P2-02 (open, diagnostic path only) | tests/redteam139/test_b2_time_causality.py::test_b2_04_direct_pack_duplicate_dates_not_guarded |
| RT139-B2-05 | time_causality | late arrival within causality is admissible | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_05_late_arriving_row_within_cutoff_is_admitted |
| RT139-B2-06 | time_causality | stale evidence reduces confidence, never dropped/zero-filled | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_06_stale_series_keeps_score_with_reduced_confidence |
| RT139-B2-07 | time_causality | missing available_at is rejected (availability mandatory) | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_07_missing_available_at_is_rejected |
| RT139-B2-08 | time_causality | capture-time history never grants formal/PIT status | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_08_capture_time_history_never_grants_formal_status |
| RT139-B2-09 | time_causality | out-of-order rows are served ordered | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_09_out_of_order_direct_pack_is_rejected |
| RT139-B2-10 | time_causality | same observation across two runs is deduplicated | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_10_same_observation_two_runs_deduplicated |
| RT139-B2-11 | time_causality | available_at equal to decision_time is admissible (boundary) | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_11_available_at_equal_to_decision_time_boundary |
| RT139-B2-12 | time_causality | observation_date one day past cutoff never enters the pack | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_12_observation_date_past_cutoff_not_served |
| RT139-B2-13 | time_causality | as_of/data_cutoff divergence in hand-built packs (P2-03 doc) | **FAIL_BLOCKER** | P2 | ADV-P2-03 (open, hand-built packs only) | tests/redteam139/test_b2_time_causality.py::test_b2_13_as_of_cutoff_divergence_documented |
| RT139-B2-14 | time_causality | revision visible in a later week is an OBSERVED_UPDATE (#139) | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_14_revised_value_next_week_is_observed_update |
| RT139-B2-15 | time_causality | observation identities are persisted for later diffs (#139) | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_15_observation_identities_persisted_in_snapshot |
| RT139-B2-16 | time_causality | direct-pack release events are honored by the producer | **PASS** | none | n/a | tests/redteam139/test_b2_time_causality.py::test_b2_16_direct_pack_release_events_honored |
| RT139-B3-01 | freshness_calendar | fresh evidence keeps full health | **PASS** | none | n/a | tests/redteam139/test_b3_freshness_calendar.py::test_b3_01_captured_monthly_data_is_usable |
| RT139-B3-02 | freshness_calendar | #129 publication-frequency exception stays narrow | **PASS** | none | n/a | tests/redteam139/test_b3_freshness_calendar.py::test_b3_02_calendar_mapping_missing_maps_to_stale_with_limitation |
| RT139-B3-03 | freshness_calendar | provider/schema failures never downgrade to stale | **PASS** | none | n/a | tests/redteam139/test_b3_freshness_calendar.py::test_b3_03_identity_failure_stays_blocked |
| RT139-B3-04 | freshness_calendar | stale is not missing | **PASS** | none | n/a | tests/redteam139/test_b3_freshness_calendar.py::test_b3_04_stale_is_not_missing |
| RT139-B3-05 | freshness_calendar | missing series stays explicit MISSING, not zero | **PASS** | none | n/a | tests/redteam139/test_b3_freshness_calendar.py::test_b3_05_missing_series_is_explicit |
| RT139-B3-06 | freshness_calendar | calendar lag is recorded when a calendar is configured | **PASS** | none | n/a | tests/redteam139/test_b3_freshness_calendar.py::test_b3_06_calendar_lag_recorded_when_configured |
| RT139-B3-07 | freshness_calendar | no Mon-Fri heuristic fallback for unconfigured calendars | **PASS** | none | n/a | tests/redteam139/test_b3_freshness_calendar.py::test_b3_07_no_weekday_heuristic_fallback |
| RT139-B3-08 | freshness_calendar | snapshot data health mirrors explicit staleness | **PASS** | none | n/a | tests/redteam139/test_b3_freshness_calendar.py::test_b3_08_snapshot_health_lists_components |
| RT139-B3-09 | freshness_calendar | freshness state is per-series, not global | **PASS** | none | n/a | tests/redteam139/test_b3_freshness_calendar.py::test_b3_09_freshness_is_per_series |
| RT139-B3-10 | freshness_calendar | holiday-adjacent capture cannot fabricate freshness | **PASS** | none | n/a | tests/redteam139/test_b3_freshness_calendar.py::test_b3_10_weekend_capture_stays_truthful |
| RT139-B4-01 | factor_regime | missing growth axis refuses to synthesize | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_01_missing_growth_axis_refuses |
| RT139-B4-02 | factor_regime | missing inflation axis refuses to synthesize | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_02_missing_inflation_axis_refuses |
| RT139-B4-03 | factor_regime | one stale bound factor keeps reduced confidence | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_03_stale_factor_reduces_confidence_only |
| RT139-B4-04 | factor_regime | the pack never invents factors beyond the registry | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_04_pack_never_invents_factors |
| RT139-B4-05 | factor_regime | wrong transform type for a factor identity is rejected at load | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_05_wrong_transform_rejected |
| RT139-B4-06 | factor_regime | min_history is enforced causally | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_06_insufficient_history_is_missing_not_fabricated |
| RT139-B4-07 | factor_regime | three same-week retries remain one economic step | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_07_same_week_retry_is_one_economic_step |
| RT139-B4-08 | factor_regime | three distinct weeks are three economic steps | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_08_three_distinct_weeks_are_three_steps |
| RT139-B4-09 | factor_regime | restart + replay equals continuous run (determinism) | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_09_replay_is_deterministic |
| RT139-B4-10 | factor_regime | first snapshot deadband resolves via documented default (P2-04 doc) | **PASS** | none | ADV-P2-04 documented (product decision needed) | tests/redteam139/test_b4_factor_regime.py::test_b4_10_first_snapshot_deadband_default_documented |
| RT139-B4-11 | factor_regime | regime dwell carries prior quadrant context | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_11_regime_dwell_retained |
| RT139-B4-12 | factor_regime | regime history is ordered by economic week | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_12_regime_history_ordered |
| RT139-B4-13 | factor_regime | factor absent in prior produces no fabricated delta | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_13_factor_missing_in_prior_has_no_delta |
| RT139-B4-14 | factor_regime | snapshot records both taxonomy and binding versions | **PASS** | none | n/a | tests/redteam139/test_b4_factor_regime.py::test_b4_14_snapshot_records_versions |
| RT139-B5-01 | asset_rules | asset views exist with bounded stance and confidence | **PASS** | none | n/a | tests/redteam139/test_b5_asset_rules.py::test_b5_01_asset_views_wellformed |
| RT139-B5-02 | asset_rules | asset keys are stable across weeks | **PASS** | none | n/a | tests/redteam139/test_b5_asset_rules.py::test_b5_02_asset_keys_stable |
| RT139-B5-03 | asset_rules | prior_stance chains across weeks | **PASS** | none | n/a | tests/redteam139/test_b5_asset_rules.py::test_b5_03_prior_stance_chains |
| RT139-B5-04 | asset_rules | same-week retry copies the prior asset delta (P2-08 doc) | **PASS** | none | ADV-P2-08 documented (retry semantics) | tests/redteam139/test_b5_asset_rules.py::test_b5_04_same_week_retry_copies_delta_documented |
| RT139-B5-05 | asset_rules | market confirmation may be UNKNOWN without market data | **PASS** | none | n/a | tests/redteam139/test_b5_asset_rules.py::test_b5_05_market_confirmation_explicit_when_unknown |
| RT139-B5-06 | asset_rules | counter signals and invalidators are lists/strings, never silent | **PASS** | none | n/a | tests/redteam139/test_b5_asset_rules.py::test_b5_06_counter_signals_and_invalidator_typed |
| RT139-B5-07 | asset_rules | stance change in week 2 has reason tags | **PASS** | none | n/a | tests/redteam139/test_b5_asset_rules.py::test_b5_07_stance_change_has_reason_tags |
| RT139-B5-08 | asset_rules | asset view delta entries are well-formed | **PASS** | none | n/a | tests/redteam139/test_b5_asset_rules.py::test_b5_08_asset_delta_entries_wellformed |
| RT139-B5-09 | asset_rules | week1 asset delta is empty without a causal prior | **PASS** | none | n/a | tests/redteam139/test_b5_asset_rules.py::test_b5_09_first_week_asset_delta_empty |
| RT139-B5-10 | asset_rules | gates cannot fabricate stances from missing factors | **PASS** | none | n/a | tests/redteam139/test_b5_asset_rules.py::test_b5_10_missing_factor_gates_do_not_fabricate |
| RT139-B6-01 | snapshot_history_api | later economic week persists FIRST | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_01_later_week_persisted_first_is_latest |
| RT139-B6-02 | snapshot_history_api | older backfill later never displaces latest | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_02_backfilled_older_snapshot_must_not_become_latest |
| RT139-B6-03 | snapshot_history_api | same-week retry after latest keeps the week | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_03_same_week_retry_after_latest_keeps_week |
| RT139-B6-04 | snapshot_history_api | a later-decision same-week retry becomes representative | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_04_same_week_retry_with_later_decision_time_is_canonical |
| RT139-B6-05 | snapshot_history_api | future-dated economic week handled explicitly | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_05_future_week_snapshot_persists_as_its_own_week |
| RT139-B6-06 | snapshot_history_api | corrupted latest pointer degrades typed | **FAIL_BLOCKER** | P2 | ADV-P2-05 (open, fail-closed but raw error) | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_06_corrupted_latest_pointer_typed_failure |
| RT139-B6-07 | snapshot_history_api | missing latest pointer recovers via canonical list | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_07_missing_latest_pointer_recovers |
| RT139-B6-08 | snapshot_history_api | restart/readback preserves the full state | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_08_restart_readback_preserves_state |
| RT139-B6-09 | snapshot_history_api | canonical current/prior selection | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_09_canonical_current_and_prior |
| RT139-B6-10 | snapshot_history_api | a backfilled older week does not become the prior of a newer week | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_10_backfill_does_not_steal_prior |
| RT139-B6-11 | snapshot_history_api | list ordering is economic, not write-time | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_11_list_snapshots_ordered_by_economic_week |
| RT139-B6-12 | snapshot_history_api | canonical_by_week keeps the later decision_time retry | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_12_canonical_by_week_keeps_latest_decision |
| RT139-B6-13 | snapshot_history_api | invalid snapshot id is rejected | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_13_invalid_snapshot_id_rejected |
| RT139-B6-14 | snapshot_history_api | missing snapshot is FileNotFoundError, not fixture | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_14_missing_snapshot_is_file_not_found |
| RT139-B6-15 | snapshot_history_api | empty store load_latest is FileNotFoundError | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_15_empty_store_load_latest_raises |
| RT139-B6-16 | snapshot_history_api | history surfaces exist post-#135 (GAP-01 closed) | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_16_history_surfaces_exist |
| RT139-B6-17 | snapshot_history_api | diff surface exists post-#135 (GAP-01 closed) | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_17_diff_surface_exists |
| RT139-B6-18 | snapshot_history_api | weekly comparability gate exists post-#132 (GAP-02 closed) | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_18_weekly_comparability_gate_exists |
| RT139-B6-19 | snapshot_history_api | API /api/snapshot/latest serves the canonical latest | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_19_api_latest_endpoint |
| RT139-B6-20 | snapshot_history_api | API failure is an error payload, never a fixture fallback | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_20_api_failure_is_not_fixture_fallback |
| RT139-B6-21 | snapshot_history_api | snapshot id collision across lineage (P2-06 doc) | **FAIL_BLOCKER** | P2 | ADV-P2-06 (open, store dedup by id) | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_21_snapshot_id_ignores_previous_snapshot_documented |
| RT139-B6-22 | snapshot_history_api | to_json ordering contract (P2-07 doc) | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_22_to_json_ordering_documented |
| RT139-B6-23 | snapshot_history_api | asset history surface exists | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_23_asset_history_surface |
| RT139-B6-24 | snapshot_history_api | snapshots() limit and week window work | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_24_snapshots_window_and_limit |
| RT139-B6-25 | snapshot_history_api | store never serves latest.json content differing from canonical | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_25_latest_pointer_matches_canonical |
| RT139-B6-26 | snapshot_history_api | store root is created lazily and is a pure technical artifact | **PASS** | none | n/a | tests/redteam139/test_b6_snapshot_history_api.py::test_b6_26_store_creates_root_lazily |
| RT139-B7-01 | weekly_lane | the DB adapter still supplies no release events itself | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_01_adapter_supplies_no_release_events |
| RT139-B7-02 | weekly_lane | week 2 with a new observation is truthfully UPDATED | **FAIL_FIXED** | P1 | ADV-P1-01 closed this task | tests/redteam139/test_b7_weekly_lane.py::test_b7_02_week2_with_new_observation_is_updated |
| RT139-B7-03 | weekly_lane | same-week retry of the same observation is not a second event | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_03_same_week_retry_is_not_second_information_event |
| RT139-B7-04 | weekly_lane | a week with no new observation is NO_NEW_INFORMATION and zero movement | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_04_week_without_new_data_stays_zero |
| RT139-B7-05 | weekly_lane | a revised value in a later week is a truthful observed update | **FAIL_FIXED** | P1 | ADV-P1-01 closed this task | tests/redteam139/test_b7_weekly_lane.py::test_b7_05_revised_value_is_observed_update |
| RT139-B7-06 | weekly_lane | prior without recorded identities fails closed (#139 fail-closed rule) | **FAIL_FIXED** | P1 | fail-closed rule implemented this task | tests/redteam139/test_b7_weekly_lane.py::test_b7_06_prior_without_identities_fails_closed |
| RT139-B7-07 | weekly_lane | OBSERVED_UPDATE never asserts a publication timestamp | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_07_no_invented_publication_timestamp |
| RT139-B7-08 | weekly_lane | family information status reflects observed updates | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_08_family_information_status_updated |
| RT139-B7-09 | weekly_lane | factor movement carries NEW_INFORMATION cause in week 2 | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_09_macro_delta_cause_is_new_information |
| RT139-B7-10 | weekly_lane | three consecutive weeks each classify their own information set | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_10_three_consecutive_weeks_chained |
| RT139-B7-11 | weekly_lane | OVERDUE events are filtered from the classification | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_11_overdue_events_filtered |
| RT139-B7-12 | weekly_lane | event count matches the number of newly visible identities | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_12_event_count_matches_new_identities |
| RT139-B7-13 | weekly_lane | the snapshot lane stays MONITORING and formal stays untouched | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_13_lane_separation_intact |
| RT139-B7-14 | weekly_lane | information delta survives persistence and readback | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_14_delta_survives_persistence |
| RT139-B7-15 | weekly_lane | expected_releases absent means no invented stale factors | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_15_no_invented_stale_factors |
| RT139-B7-16 | weekly_lane | identity-blocked series contributes no observed update | **PASS** | none | n/a | tests/redteam139/test_b7_weekly_lane.py::test_b7_16_blocked_series_contributes_no_event |
| RT139-B8-01 | runtime_boundary | FIXTURE origin is rejected by the producer | **PASS** | none | n/a | tests/redteam139/test_b8_runtime_boundary.py::test_b8_01_fixture_origin_rejected |
| RT139-B8-02 | runtime_boundary | non-LIVE workbench lineage is rejected | **PASS** | none | n/a | tests/redteam139/test_b8_runtime_boundary.py::test_b8_02_non_live_lineage_rejected |
| RT139-B8-03 | runtime_boundary | MISSING factor scores stay None, never zero | **PASS** | none | n/a | tests/redteam139/test_b8_runtime_boundary.py::test_b8_03_missing_scores_stay_none |
| RT139-B8-04 | runtime_boundary | direct store writes record no attempts; read model re-validates | **PASS** | none | n/a | tests/redteam139/test_b8_runtime_boundary.py::test_b8_04_direct_writes_record_no_attempts |
| RT139-B8-05 | runtime_boundary | failed run followed by successful run leaves no ghost rows | **PASS** | none | n/a | tests/redteam139/test_b8_runtime_boundary.py::test_b8_05_failed_then_successful_run |
| RT139-B8-06 | runtime_boundary | corrupted snapshot file is a typed failure, not a silent skip | **PASS** | none | n/a | tests/redteam139/test_b8_runtime_boundary.py::test_b8_06_corrupted_snapshot_file_typed_failure |
| RT139-B8-07 | runtime_boundary | monitoring origin is preserved into snapshot details | **PASS** | none | n/a | tests/redteam139/test_b8_runtime_boundary.py::test_b8_07_origin_preserved |
| RT139-B8-08 | runtime_boundary | snapshot store writes are atomic (no partial latest.json) | **PASS** | none | n/a | tests/redteam139/test_b8_runtime_boundary.py::test_b8_08_store_writes_are_atomic |
| RT139-B8-09 | runtime_boundary | launcher / frontend runtime untouched by this task (static) | **PASS** | none | n/a | tests/redteam139/test_b8_runtime_boundary.py::test_b8_09_launcher_frontend_untouched |
| RT139-B8-10 | runtime_boundary | the read API binds loopback only | **PASS** | none | n/a | tests/redteam139/test_b8_runtime_boundary.py::test_b8_10_api_binds_loopback |
| RT139-B8-11 | runtime_boundary | monitoring ingestion never grants formal admission | **PASS** | none | n/a | tests/redteam139/test_b8_runtime_boundary.py::test_b8_11_no_formal_admission_from_monitoring |
| RT139-B8-12 | runtime_boundary | deterministic inputs give a byte-identical snapshot (no hidden clock) | **PASS** | none | n/a | tests/redteam139/test_b8_runtime_boundary.py::test_b8_12_no_hidden_clock_in_snapshot |
| RT139-C2-01 | emergent | three-week loop with persistence and pointer correctness | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_01_three_week_loop_with_store |
| RT139-C2-02 | emergent | poisoned identity mid-loop blocks the week, history intact | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_02_poisoned_identity_mid_loop |
| RT139-C2-03 | emergent | corrupted latest.json mid-loop then persist recovers | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_03_corrupted_pointer_recovered_by_next_persist |
| RT139-C2-04 | emergent | the same two-week sequence replays deterministically | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_04_two_week_sequence_is_deterministic |
| RT139-C2-05 | emergent | process restart between weeks yields the same state | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_05_restart_between_weeks |
| RT139-C2-06 | emergent | observed update propagates coherently through delta surfaces | **FAIL_FIXED** | P1 | ADV-P1-01 closed this task | tests/redteam139/test_c2_emergent.py::test_c2_06_observed_update_propagation_is_coherent |
| RT139-C2-07 | emergent | no formal-lane contamination across weeks | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_07_no_formal_contamination_across_weeks |
| RT139-C2-08 | emergent | identical re-capture next week is not a new information event | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_08_identical_recapture_is_not_new_information |
| RT139-C2-09 | emergent | a late backfilled older observation is truthfully reported | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_09_late_backfill_reports_older_observation_date |
| RT139-C2-10 | emergent | across-binding duplicate canonical series (documented effect) | **FAIL_BLOCKER** | P2 | ADV-P2-11 (open, config-authority decision) | tests/redteam139/test_c2_emergent.py::test_c2_10_duplicate_canonical_across_bindings_documented |
| RT139-C2-11 | emergent | retry then canonical representative selection | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_11_retry_then_canonical_representative |
| RT139-C2-12 | emergent | diff surface reflects macro change only in updated weeks | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_12_diff_reflects_updated_weeks |
| RT139-C2-13 | emergent | five-week soak loop keeps every invariant each step | **FAIL_FIXED** | P1 | ADV-P1-01 closed this task | tests/redteam139/test_c2_emergent.py::test_c2_13_five_week_soak_loop |
| RT139-C2-14 | emergent | interleaved retries inside the soak loop stay one step | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_14_interleaved_retries_stay_one_step |
| RT139-C2-15 | emergent | snapshot id collision does not corrupt the store (P2-06 doc) | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_15_snapshot_id_collision_overwrites_consistently |
| RT139-C2-16 | emergent | fresh world after restart reads back the full history | **PASS** | none | n/a | tests/redteam139/test_c2_emergent.py::test_c2_16_history_readback_after_restart |
| STATIC-01 | runtime_boundary | LOCAL-A must not edit launcher/frontend runtime | **NOT_EXERCISED** | none | LOCAL-B lane (per #139 lane separation) | LOCAL-B lane (per #139 lane separation) |
| STATIC-02 | runtime_boundary | Windows process ownership logic is LOCAL-B surface | **NOT_EXERCISED** | none | issue #140 (LOCAL-B soak/UAT) | issue #140 (LOCAL-B soak/UAT) |
| STATIC-03 | identity_source | Wind identity lanes | **NOT_EXERCISED** | none | config/sources.yml | config/sources.yml |
| STATIC-04 | identity_source | iFinD identity lanes | **NOT_EXERCISED** | none | config/sources.yml | config/sources.yml |
| STATIC-05 | identity_source | Tushare identity lanes | **NOT_EXERCISED** | none | config/sources.yml | config/sources.yml |
| STATIC-06 | identity_source | #93 manual source intake semantics unchanged | **NOT_EXERCISED** | none | git diff evidence | git diff evidence |
| STATIC-07 | lane_separation | FORMAL_OOS activation (#81) stays blocked | **BLOCKED_POLICY** | none | issue #81 / control #123 | issue #81 / control #123 |
| STATIC-08 | lane_separation | YTD return surface stays unimplemented | **BLOCKED_POLICY** | none | control #123 §5 | control #123 §5 |
| STATIC-09 | identity_source | provider contract vs catalog unit cross-check | **GAP** | P2 | ADV-P2-09 (carried from #138) | ADV-P2-09 (carried from #138) |
| STATIC-10 | identity_source | duplicate canonical series across bindings | **FAIL_BLOCKER** | P2 | ADV-P2-11 / test_c2_10 | ADV-P2-11 / test_c2_10 |
| STATIC-11 | evidence | identity attack reproduced on current main BEFORE fix | **FAIL_FIXED** | P1 | repro_current_main.py ATTACK 1 | repro_current_main.py ATTACK 1 |
| STATIC-12 | evidence | P1-02 backfill attack reproduced against pre-#135 semantics | **PASS** | none | repro_current_main.py ATTACK 2 | repro_current_main.py ATTACK 2 |
| STATIC-13 | evidence | P1-01 week-2 SyntheticMovementError reproduced on current main BEFORE fix | **FAIL_FIXED** | P1 | repro_current_main.py ATTACK 3 | repro_current_main.py ATTACK 3 |
| STATIC-14 | soak | 10-iteration five-week rebuild loop is deterministic | **PASS** | none | SOAK_RESULTS.json | SOAK_RESULTS.json |
| STATIC-15 | soak | same-week retries remain one economic step in soak | **PASS** | none | SOAK_RESULTS.json | SOAK_RESULTS.json |
| STATIC-16 | soak | mid-loop restart reads identical state | **PASS** | none | soak_repeatability.py index==2 check | soak_repeatability.py index==2 check |
| STATIC-17 | soak | no fixture fallback anywhere in the soak | **PASS** | none | soak_repeatability.py | soak_repeatability.py |
| STATIC-18 | soak | no formal-lane contamination in soak | **PASS** | none | soak_repeatability.py | soak_repeatability.py |
| STATIC-19 | evidence | full unit suite on the task branch | **PASS** | none | pytest tests/unit (this branch) | pytest tests/unit (this branch) |
| STATIC-20 | evidence | full integration suite on the task branch | **PASS** | none | pytest tests/unit tests/integration tests/redteam139 | pytest tests/unit tests/integration tests/redteam139 |
| STATIC-21 | evidence | redteam139 suite on the task branch | **PASS** | none | pytest tests/redteam139 | pytest tests/redteam139 |
| STATIC-22 | history | conftest packaging lesson (ADV-P2-10) applied | **PASS** | none | tests/redteam139/__init__.py | tests/redteam139/__init__.py |
| STATIC-23 | history | cross-window non-overlap respected | **PASS** | none | git diff --name-only main | git diff --name-only main |
| STATIC-24 | evidence | runtime adapter keeps as_of == data_cutoff | **PASS** | none | monitoring_adapter.py pack construction | monitoring_adapter.py pack construction |
| STATIC-25 | snapshot_history | P1-02: latest pointer ordered by (economic week, decision_time), not write time | **PASS** | none | decision_history.py + test_b6_01..b6_12 | decision_history.py + test_b6_01..b6_12 |
| STATIC-26 | weekly_lane | #132 weekly semantic comparability gate present on main | **PASS** | none | test_b6_18 | test_b6_18 |
| STATIC-27 | snapshot_history | OBSERVED_UPDATE events never assert first-release semantics | **PASS** | none | enums.py ReleaseEventType | enums.py ReleaseEventType |
| STATIC-28 | weekly_lane | executive brief reflects observed-update counts | **PASS** | none | producer.py brief construction | producer.py brief construction |
