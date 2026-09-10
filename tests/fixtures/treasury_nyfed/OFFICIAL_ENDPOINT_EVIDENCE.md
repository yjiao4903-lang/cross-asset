# C67 official endpoint evidence

Live metadata was read from official endpoints. No FRED/Wind/CFTC fallback.

## Treasury FiscalData

Base: `https://api.fiscaldata.treasury.gov/services/api/fiscal_service`

Discovery (2026-09-09):
- DTS Operating Cash `/v1/accounting/dts/operating_cash_balance` HTTP 200
- DTS Deposits `/v1/accounting/dts/deposits_withdrawals_operating_cash` HTTP 200
- Debt to the Penny `/v2/accounting/od/debt_to_penny` HTTP 200
- Auctions `/v1/accounting/od/auctions_query` HTTP 200
- MSPD table 1 `/v1/debt/mspd/mspd_table_1` HTTP 200

Short-window live collection (2026-09-10, fetched_at 12:00 UTC):
- TREASURY_DTS_OPERATING_CASH 2026-09-01..2026-09-08 HEALTHY rows=20
- TREASURY_DTS_DEPOSITS_WITHDRAWALS 2026-09-01..2026-09-08 HEALTHY rows=900
- TREASURY_DEBT_TO_PENNY 2026-09-01..2026-09-08 HEALTHY rows=5
- TREASURY_AUCTIONS 2026-09-01..2026-09-08 rows=9
- TREASURY_MSPD_TABLE_1 2026-08-01..2026-08-31 HEALTHY rows=14

## NY Fed Markets API

Base: `https://markets.newyorkfed.org/api`

Discovery (2026-09-09):
- `/rp/reverserepo/all/results/last/5.json` HTTP 200
- `/rp/repo/all/results/last/5.json` HTTP 200
- `/soma/summary.json` HTTP 200
- `/pd/list/timeseries.json` HTTP 200; keyid `PDPOSGST-TOT`
- `/pd/get/PDPOSGST-TOT.json` HTTP 200
- OMO transaction history: UNRESOLVED (quarterly Excel only)
- `/rp/results/search.json?startDate=&endDate=` official date-range search (WG7)
- `/rp/.../results/last/N.json` is a recent-window helper only; it cannot satisfy a requested historical range
- `/rp/.../search.json` path variants under `/rp/{type}/.../search.json` returned HTTP 400 on 2026-09-09

Short-window live collection (2026-09-10):
- NYFED_ONRRP_RESULTS 2026-09-01..2026-09-08 rows=5
- NYFED_REPO_RESULTS 2026-09-01..2026-09-08 rows=8
- NYFED_SOMA_SUMMARY 2026-08-01..2026-09-08 HEALTHY rows=5 last=2026-09-02
- NYFED_PD_TREASURY_POSITIONS 2026-08-01..2026-09-08 HEALTHY rows=4 last=2026-08-26 keyid=PDPOSGST-TOT
- NYFED_OMO_TRANSACTION_HISTORY remains UNRESOLVED / BLOCKED
- Official `/api/rp/results/search.json?startDate=2026-09-01&endDate=2026-09-08` HTTP 200 on 2026-09-10
