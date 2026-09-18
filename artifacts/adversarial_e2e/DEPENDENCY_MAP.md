# DEPENDENCY MAP — ADVERSARIAL-E2E-VALIDATION-V1

- Owner lane: `WEEKEND-REDTEAM`
- Baseline main: `5cac5c44b08e43760888362636cadbf3ffb40f1e`
- Environment: NO WIND / NO WindPy / no proprietary local files.

## Target chain

```text
monitoring provider/input -> canonical identity / source mapping -> monitoring ingestion / DB -> catalog / freshness / data-health -> WorkbenchRun lineage -> governed factor binding / causal transforms -> climate / regime / asset rules -> DashboardSnapshotV0 -> SnapshotStore / history -> read-only API -> frontend/runtime consumption
```

## Components

| Authority | Role | Inputs | Outputs | Persisted identity | Time semantics | Failure semantics | Formal/monitoring boundary | Existing coverage |
|---|---|---|---|---|---|---|---|---|
| `providers/monitoring.py` | provider adapter (FRED public CSV / Yahoo) writing MONITORING-only rows | DataRequest(series_ids, start, end) | list[Observation] with origin=MONITORING, available_at=capture time | series_id + source + source_series_id | available_at = monitoring capture time (explicitly non-PIT) | ProviderError -> _failure(...); no fallback, no formal admission | MONITORING only; never writes acceptance registry | tests/unit/providers, tests/integration/test_fred_monitoring_source_expansion.py |
| `ingestion/monitoring.py` | MonitoringRunner: validate + persist monitoring observations | provider rows, request, run_id | observations rows, provider_attempts, data_quality_events | run provider 'MONITORING:<name>' + row identity | available_at required; ingested_at = now | fail the whole run on identity/origin/available_at violations | formal_admission_attempted=False always | tests/unit/ingestion, tests/integration/test_monitoring_provider_calendar.py |
| `storage/catalog.py + storage/duckdb.py` | series catalog, source mappings, observation persistence | config/series.yml, config/sources.yml, observation dicts | series_catalog, source_mapping, observations | series_id, provider, source_series_id | available_at / vintage_date / ingested_at | idempotent insert; no identity validation at the storage boundary | sync_series_catalog never writes the acceptance registry | tests/unit/storage |
| `engines/freshness.py + reports/monitoring_health.py` | calendar freshness and monitoring read-model health | series_calendars.yml, calendars.yml, observations, quality events | FreshnessResult(OK/STALE/BLOCKED) and monitoring_data_health rows | series_id | session-lag against market_data_cutoff; no weekday/hour heuristic | fail closed to BLOCKED for any missing mapping/coverage | formal_readiness reported separately; monitoring never implies formal | tests/unit/test_calendar_coverage.py, tests/integration/test_monitoring_provider_calendar.py |
| `operations/workbench_run.py` | canonical WorkbenchRun lineage and formal previous-valid selection | pipeline payload / explicit run object | persisted run JSON under artifacts/workbench/runs | run_id + decision_time + source_mode + provenance | economic decision_time ordering; created_at only breaks ties | FIXTURE/SIMULATED can never be formal previous-valid | formal eligibility requires LIVE + formal_gate provenance | tests/unit/operations, tests/unit/test_workbench_cli.py |
| `decision_support/binding.py + config/decision_support_v2_bindings.yml` | lane-aware factor binding governance | bindings yml, series.yml, sources.yml, taxonomy | FactorBindingRegistry | factor_id -> canonical_series_ids | n/a (config authority) | import-time rejection of ungoverned / non-equivalent / wrong-transform bindings | monitoring BOUND requires exact governed identity; formal independently BLOCKED | tests/unit/decision_support/test_binding_governance.py |
| `decision_support/monitoring_adapter.py` | MONITORING DB read-model -> canonical observation pack | store, WorkbenchRun, binding registry, calendar configs | MonitoringObservationPack | series_id + source + source_series_id (re-validated since this task) | available_at <= decision_time; observation_date <= data_cutoff; one vintage per date | identity violation -> series BLOCKED with explicit blockers; never silently consumed | validate() requires lane=MONITORING, origin=CANONICAL_MONITORING, source_mode=LIVE | tests/integration/test_real_snapshot_monitoring_adapter.py, tests/adversarial/test_b1_identity_source.py |
| `decision_support/producer.py` | canonical observations -> DashboardSnapshotV0 | MonitoringObservationPack + optional previous snapshot | DashboardSnapshotV0 (MONITORING lane) | snapshot_id = sha256(pack + registry version + taxonomy version + model version) | economic week id = Monday of data_cutoff; previous must precede by decision_time | MonitoringSnapshotBlocked for missing regime axes; SyntheticMovementError for uncaused movement | lane is MONITORING only; formal_admission_granted always False | tests/unit/decision_support/test_real_snapshot.py, tests/adversarial/* |
| `decision_support/{taxonomy,horizon,climate,regime,asset_rules,weekly}.py` | horizon separation, climate, interpretable regime, asset gates, weekly-change surfaces | bound subfactor scores, release events, market moves | clusters, regime state, asset views, four weekly-change surfaces | factor_id / family / horizon | deadband + dwell hysteresis; de-duplicated economic weeks | missing never becomes zero; horizon mixing raises; structural context excluded | no formal OOS path; no fitted weights | tests/unit/decision_support/* |
| `decision_support/serving.py` | SnapshotStore + read-only HTTP API | root directory of snapshot JSON files | latest/by-id/factors/asset/data-health/health payloads | snapshot_id filename + latest.json pointer | no monotonicity guard on latest.json (recorded blocker) | FileNotFoundError/ValueError -> 404; corrupt payload surfaces as 404 with internal text | read-only; no write routes; loopback default | tests/unit/decision_support/test_real_snapshot.py, tests/adversarial/test_b6_snapshot_api.py |
| `frontend/src/snapshot/loader.js + App.jsx` | API-first consumption with explicit demo/test mode | /api/snapshot/latest | adapted view model | metadata.snapshot_id | as_of/decision_time displayed, never recomputed | fail visibly; never substitute a golden/demo fixture for a failed API | lane badge from producer; no client-side economics | frontend/tests |

## Adjacent WIP boundaries

| PR | Issue | Title | Files | Rule |
|---|---|---|---|---|
| #135 | #133 | DECISION-HISTORY-V1 | `src/cross_asset/decision_support/decision_history.py`, `src/cross_asset/decision_support/serving.py`, `src/cross_asset/decision_support/snapshot_cli.py` | do not edit; serving.py blockers are owned here |
| #132 | #131 | weekly semantic comparability hardening | `src/cross_asset/research/weekly_core.py`, `tests/unit/test_weekly_*.py` | do not edit; record gap only |
| #136 | #134 | Windows REAL-runtime launcher | `launcher/**`, `START_MACRO_WORKBENCH.cmd`, `STOP_MACRO_WORKBENCH.cmd` | native process semantics are EXTERNAL_EVIDENCE; not exercised here |

## Hard environment assumption

```json
{
  "consequence": "Wind/manual-only cells are NOT_EXERCISED or BLOCKED; never waited for or bypassed",
  "proprietary_local_files": false,
  "wind_available": false,
  "windpy_available": false
}
```
