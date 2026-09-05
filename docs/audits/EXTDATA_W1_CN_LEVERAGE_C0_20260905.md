# Cross W1 China Leverage — C0 Audit Note

**Date:** 2026-09-05
**Task:** `REQ-CROSS-MARKET-STATE-W1-20260905` / Cross #36
**Gate reached:** `C0` only
**Status:** `CANDIDATE_ONLY / DATA_BLOCKED` for production use

## Scope

This package creates the first financing-first input for the single canonical
series `POS_CN_RZRQ`:

- centralized official source identities in
  [`config/china_leverage.yml`](../../config/china_leverage.yml);
- parser for exchange-style daily summary fields including trading date,
  publication date/time, financing balance, optional securities-lending
  balance, optional total balance, and explicit availability;
- source/provider identity, origin, source file, and ingestion metadata;
- conservative T+1 09:00 Asia/Shanghai PIT validation;
- as-of filtering and explicit revision/duplicate handling;
- financing balance, daily change, 20-observation change, 60-observation
  change, and causal rolling-percentile diagnostics;
- C0 source-health output and reuse of the existing immutable raw archive;
- an immutable `.meta.json` sidecar through
  `src/cross_asset/ingestion/china_leverage_evidence.py`, recording the full
  raw SHA-256, parser version, archive path, provider/source identity, fetch
  time, row count, coverage, latest observation/availability, warnings, and
  failure status.

The evidence-bearing C0 entry point is
`ingest_china_leverage_snapshot_with_evidence`. It requires an
`ImmutableRawArchive`, delegates parsing/source-health behavior to the existing
C0 ingest, and persists the deterministic provenance sidecar next to the raw
snapshot. Repeated writes of the same evidence are idempotent; a conflicting
sidecar fails closed.

The implementation does not introduce a second financing series, a free-float
market-cap denominator, CFFEX member positioning, Northbound net-buy data, or
a directional signal.

## Binding source and PIT evidence

The [Shanghai Stock Exchange margin summary](https://www.sse.com.cn/market/othersdata/margin/sum/)
documents daily financing, securities-lending, and total margin-balance
fields. The accepted evidence in [Cross #37](https://github.com/yjiao4903-lang/cross-asset/issues/37)
sets the conservative earliest usable time for a China margin balance at
T+1 09:00 Asia/Shanghai unless stronger source evidence is available.

The parser requires an explicit `available_at` and verifies that its local
date follows the observation date and its local time is not earlier than
09:00. It does not infer a next trading session from a weekend or holiday.
`conservative_margin_available_at` can be used only when the caller supplies
the next session date explicitly. Publication date-only input is represented
at the documented conservative 09:00 local boundary; an explicit timestamp
is preserved when supplied.

## Missing values and source separation

- financing balance is required and non-finite values fail the snapshot;
- securities-lending balance is optional and remains `None` when absent;
- total balance is retained when reported, or derived only when both
  financing and securities-lending values are present;
- a reported total that disagrees with both components fails closed;
- source identity must match the configured official provider and source ID;
  no third-party mirror fallback or cross-exchange concatenation is allowed;
- later revisions are selected only after their own availability time;
  same-time conflicts are explicit failures;
- missing as-of rows are `DATA_BLOCKED`, stale rows are `STALE`, parser errors
  are `FAILED`, and unapproved identities are `UNAPPROVED`;
- fixture origin remains visible and cannot satisfy real-data admission;
- archived candidate snapshots carry a complete SHA-256/parser-version
  provenance sidecar rather than relying on a truncated hash in the filename.

## Gate boundary and non-goals

This is a C0 foundation. It does not write `observations`, bind the #18
acceptance registry, bypass `approved-observations`, modify factor weights or
allocation constraints, call Allocation, or create reports. Production use
remains disabled/shadow until the #18/#19/#20/#22 audit gates are accepted by
WEB-CONTROL.

The fixtures in `tests/fixtures/china_leverage/` are synthetic engineering
inputs only. Real source capture, entitlement, historical calendar coverage,
and production stability remain separate evidence work. The provenance
sidecar proves engineering traceability only and does not upgrade real-data or
PIT admission status.
