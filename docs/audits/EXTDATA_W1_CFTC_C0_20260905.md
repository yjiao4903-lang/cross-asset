# Cross W1 CFTC Positioning — C0 Audit Note

**Date:** 2026-09-05
**Task:** `REQ-CROSS-MARKET-STATE-W1-20260905` / Cross #36
**Gate reached:** `C0` only
**Status:** `CANDIDATE_ONLY / DATA_BLOCKED` for production use

## Scope

This package provides an isolated parser and research transform for:

- CFTC Disaggregated Futures-and-Options Combined: Gold and Copper;
- CFTC Traders in Financial Futures (TFF) Futures-and-Options Combined: S&P
  500 and US 10-year Treasury;
- centralized contract/report mappings in
  [`config/cftc_positioning.yml`](../../config/cftc_positioning.yml);
- explicit source identity, report type, contract code, report date,
  participant category, long/short/spreading/open interest, source file/year,
  publication, availability, ingestion, and origin fields;
- raw snapshot archiving through the existing immutable archive interface;
- an immutable `.meta.json` sidecar through
  `src/cross_asset/ingestion/cftc_evidence.py`, recording the complete raw
  SHA-256, parser version, archive path, source identity, fetch time, row count,
  coverage, latest observation/availability, warnings, and failure status;
- as-of filtering, revision selection, source health, net position, percent of
  open interest, rolling percentile, and causal z-score diagnostics.

The evidence-bearing C0 entry point is `ingest_cftc_snapshot_with_evidence`.
It requires an `ImmutableRawArchive`, delegates parsing/source-health behavior
to `ingest_cftc_snapshot`, and persists the provenance sidecar adjacent to the
content-addressed raw snapshot. Repeated writes of identical evidence are
idempotent; conflicting content at the same sidecar path fails closed.

The output is diagnostic/crowding data only. It does not create `LONG`,
`SHORT`, `BUY`, `SELL`, or directional-alpha decisions.

## Binding source and PIT evidence

The official CFTC [release schedule](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm)
states that Futures-and-Options Combined reports are normally released on
Friday at 3:30 p.m. Eastern Time using the previous Tuesday's data, with
Federal holidays delaying the release. The parser therefore requires a
timezone-aware actual publication timestamp and rejects `available_at` before
that timestamp. It never derives availability from the Tuesday observation
date and does not guess holiday dates.

The official [Historical Compressed](https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm)
page provides annual machine-readable files for the Disaggregated and TFF
families. Annual schema aliases are confined to this adapter so that column
changes do not leak into model code.

The accepted evidence record in [Cross #37](https://github.com/yjiao4903-lang/cross-asset/issues/37)
binds contract identity to `CFTC_Contract_Market_Code`, including Gold
`088691`, Copper `085692`, S&P 500 `13874A`/`13874+`, and US 10Y Treasury
`043602`. It also confirms that source suitability is not a production
admission decision. Historical multi-year archive naming and special delayed
publication episodes remain live-source/release-calendar integration work; the
C0 parser deliberately consumes caller-supplied source bytes and actual
publication timestamps rather than guessing them.

## Failure and health behavior

- missing or malformed target fields fail the snapshot; target rows are not
  silently dropped;
- missing participant columns, invalid report weekdays, non-timezone-aware
  timestamps, and `available_at < publication_at` remain explicit failures;
- same-time conflicting republished rows raise a duplicate-report failure;
  later revisions are selected only after their own availability time;
- records after the decision boundary are excluded before research transforms;
- missing expected series are `PARTIAL`, stale latest reports are `STALE`,
  parser failures are `FAILED`, unapproved providers are `UNAPPROVED`, and no
  admissible records are `DATA_BLOCKED`;
- fixture origin is retained and cannot be interpreted as real-data evidence;
- raw SHA-256 and parser-version provenance is persisted independently of
  source-health success, so a failed/partial candidate never loses its raw
  evidence trail when an archive path exists.

## Gate boundary and non-goals

This is a C0 foundation. It does not write `observations`, bind the #18
acceptance registry, bypass `approved-observations`, change strategic weights
or tactical tilt, call Allocation, or wire a run/report artifact. Production
ingestion and formal consumption remain disabled/shadow until #18 and the
related audit gates are accepted by WEB-CONTROL.

The CFTC network fetch/release-calendar integration and historical live
validation remain separate evidence work. The synthetic fixtures in
`tests/fixtures/cftc_positioning/` prove parser, PIT, source-health, and raw
provenance behavior only; they do not satisfy a real-data gate.
