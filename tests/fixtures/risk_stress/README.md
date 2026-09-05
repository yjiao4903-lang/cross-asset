# SYNTHETIC TEST FIXTURES — Risk Stress C0

Everything in this directory is **synthetic test fixture data** generated for
unit tests of `cross_asset.ingestion.risk_stress` (Issue #38, C0 scope).

These files are NOT real market data. They do NOT satisfy the real-data
admission gate (#18) and must never be cited as real-data acceptance or as
evidence about actual VIX / VIX3M / HY OAS / BAA10Y levels, publication
timing, or history coverage.

- `synthetic_vix_close.csv` — synthetic VIX-shaped daily closes (cboe/VIX shape)
- `synthetic_vix3m_close.csv` — synthetic VIX3M-shaped leg for RISK_VIX_TS
- `synthetic_vix3m_with_future_publication.csv` — synthetic leg whose
  available_at is deliberately later than the test decision time
- `synthetic_hy_oas_truncated.csv` — synthetic HY OAS shape whose coverage
  starts after the contract's expected_history_start, to exercise the
  truncated-history warning
- `synthetic_baa10y.csv` — synthetic BAA10Y shape; must stay identity-separate
  from HY OAS
- `synthetic_malformed.csv` — deliberately malformed rows for parser tests
