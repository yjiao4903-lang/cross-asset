# Data Acceptance Gate v0.1

Status: `DATA_BLOCKED` until each series passes all four gates. Owner: TBD. Reviewer: TBD. Approved at: TBD.

## Series manifest

Each manifest must include: `series_id`, `provider`, `source_series_id`, `permission_scope`, `origin`, `observation_definition`, `unit`, `currency`, `timezone`, `price_type`, `adjustment_type`, `frequency`, `history_start`, `history_end`, `observation_date_rule`, `available_at_rule`, `vintage_rule`, `missing_policy`, `semantic_equivalence`, `template_version`, `file_sha256`, `reviewer`, `approved_at`, `reconciliation_notes`. Legacy `template_id/version/file_hash` is accepted only with a warning and normalized to the canonical names.

Each observation must carry `observation_date`, `available_at`, `value`, `source`, and vintage/revision metadata where applicable. `available_at` must never be inferred from observation date without an explicitly documented conservative lag.

## Four gates

1. `TECH`: source identity, fields, frequency, history and reproducible access.
2. `LEGAL`: permission to access, store, research and (if applicable) redistribute; API key is not automatic redistribution permission.
3. `PIT`: release/available_at, vintage/revision lineage, cutoff and calendar are reconstructible.
4. `STABILITY`: repeat acquisition, schema/error logs, fallback/source switch and reconciliation are auditable.

`PASS` requires all four gates and explicit approval. `PARTIAL` means some gates pass but the series remains unavailable for final research. `FAIL` means a mandatory gate or semantic check fails. Unknown is not PASS.

## PIT grade

`PITGrade` is evidence-based: A=true vintage/revision history, B=actual release timestamp, C=documented conservative lag (core with warning), D=observation-date-only (research-only). Unknown evidence remains unknown and cannot be upgraded. Registry writes are explicit and never promote PARTIAL or D to PASS.

Calendar status is separately governed: only an explicit `capability_status: VERIFIED` configuration with source/version/covered years/session times/timezone/holiday data may produce OPEN/CLOSED or calendar-derived coverage metrics. The default contract is UNVERIFIED.

## Manual rule and origin boundary

Manual data may be a formal source only after at least **three consecutive evidenced batches** using fixed `template_version`, source identity, distinct batch IDs and file SHA-256, exported_at, reviewer, timezone-aware `approved_at`, explicit `available_at`/vintage and cross-source reconciliation. A numeric `batch_count` alone is insufficient. `MANUAL`, `LIVE`, `FIXTURE`, and `SIMULATED` are not interchangeable. `^TNX` is auxiliary only and cannot replace FRED DGS10. Missing data must remain missing/unavailable, never zero-filled.

## Readiness aggregation for the first formal Marco -> Cross E2E

A global `DATA_READY` state must not be unlocked by an unrelated observation or by a `PASS` registry row for only one series. The `FIRST_REAL_MARCO_CROSS_E2E_V1` readiness profile requires all six current formal Wind market series:

- `CN_EQ_LARGE`
- `HK_EQ`
- `US_EQ`
- `CN_BOND_10Y`
- `GOLD`
- `COPPER`

For each required series, readiness requires an exact Wind acceptance-registry entry with `status=PASS`, all four gates at `PASS`, a non-empty accepted `source_series_id`, and at least one formal observation whose `series_id`, provider/source, and `source_series_id` match that accepted provenance. Observations from another provider or another source series do not satisfy the gate.

This aggregate is deliberately narrower than P0-B/P0-C completion. It does **not** prove the required 2014-to-latest complete-day backfill, does not produce `HISTORY_READY`, and does not establish a successful First Real Marco-to-Cross E2E. Those remain separate acceptance gates under `NEXT_PHASE_IMPLEMENTATION_PLAN_v1.md`.
