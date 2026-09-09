# C67 official endpoint evidence (2026-09-09)

Live metadata was read from official endpoints. No FRED/Wind/CFTC fallback.

## Treasury FiscalData
Base: `https://api.fiscaldata.treasury.gov/services/api/fiscal_service`
- DTS Operating Cash `/v1/accounting/dts/operating_cash_balance` HTTP 200
- DTS Deposits `/v1/accounting/dts/deposits_withdrawals_operating_cash` HTTP 200
- Debt to the Penny `/v2/accounting/od/debt_to_penny` HTTP 200
- Auctions `/v1/accounting/od/auctions_query` HTTP 200
- MSPD table 1 `/v1/debt/mspd/mspd_table_1` HTTP 200

## NY Fed Markets API
Base: `https://markets.newyorkfed.org/api`
- `/rp/reverserepo/all/results/last/5.json` HTTP 200
- `/rp/repo/all/results/last/5.json` HTTP 200
- `/soma/summary.json` HTTP 200
- `/pd/list/timeseries.json` HTTP 200; keyid `PDPOSGST-TOT`
- `/pd/get/PDPOSGST-TOT.json` HTTP 200
- OMO transaction history: UNRESOLVED (quarterly Excel only)
- `/rp/.../search.json` date filter: HTTP 400 on 2026-09-09
