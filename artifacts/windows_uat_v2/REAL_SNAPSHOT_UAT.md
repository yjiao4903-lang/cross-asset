# Real Snapshot UAT V2

Generated: `2026-09-19T01:33:00.908546+00:00`
Status: **REAL_SNAPSHOT_PERSISTED_PARTIAL**

## Runtime roots

- DB: `<local-b-worktree>\artifacts\windows_uat_v2\monitoring-20260919T013300907545Z.duckdb`
- Workbench: `<local-b-worktree>\artifacts\windows_uat_v2\workbench`
- Snapshots: `<local-b-worktree>\artifacts\windows_uat_v2\dashboard_snapshots`

## Provider ingestion

### FRED

- status: `success`
- rows_written: `1873`
- formal_admission_attempted: `False`
- errors: `{}`

### YAHOO

- status: `success`
- rows_written: `2514`
- formal_admission_attempted: `False`
- errors: `{}`

## Identity / provenance

- real observation rows: `4387`
- acceptance registry rows: `0`
- all real ingestion lineage MONITORING: `True`
- exact identity checks passed: `True`

## Persisted snapshot

- snapshot_id: `dsv0-monitoring-20260919-8258e11a5b5065b8`
- run_id: `wb-live-windows-uat-v2-20260919T013300Z`
- economic_week_id: `2026-09-14`
- lane: `MONITORING`
- history technical count: `1`
- history canonical count: `1`
- data health: `PARTIAL`
- missing components: `BREAKEVEN_5Y5Y, CFTC_RISK_POSITIONING, CN_BOND_TREND_63D, CN_CREDIT_IMPULSE, CN_DR007, CN_EQ_TREND_63D, CN_EQ_VALUATION, CN_M1_M2_GAP, CN_MFG_PMI, CN_NEW_LOANS_TREND, COPPER_TREND_63D, FED_POLICY_STANCE, GOLD_REAL_RATE_OVERLAY, GOLD_TREND_63D, USD_BROAD_MOMENTUM, US_EQ_ERP_PROXY, US_FIN_COND_TREND, US_HY_SPREAD, US_ISM_PMI, US_PPI_TREND, US_WAGE_PRESSURE, US_YIELD_CURVE_10Y2Y, VIX_LEVEL`
- stale components: `US_10Y_REAL_YIELD, US_CORE_CPI_TREND, US_PAYROLLS_TREND`
- blockers: `CASH: POLICY_LIQUIDITY — cyclical cluster score unavailable; excluded from stance, not zero-filled, CASH: FINANCIAL_CONDITIONS — cyclical cluster score unavailable; excluded from stance, not zero-filled, CASH: VIX_LEVEL — market confirmation input unavailable; reported as UNKNOWN, not as observed divergence, CN_BOND: POLICY_LIQUIDITY — cyclical cluster score unavailable; excluded from stance, not zero-filled, CN_BOND: CHINA_CYCLE — cyclical cluster score unavailable; excluded from stance, not zero-filled, CN_BOND: CN_BOND_TREND_63D — market confirmation input unavailable; reported as UNKNOWN, not as observed divergence, CN_EQ: CHINA_CYCLE — cyclical cluster score unavailable; excluded from stance, not zero-filled, CN_EQ: POLICY_LIQUIDITY — cyclical cluster score unavailable; excluded from stance, not zero-filled, CN_EQ: CN_EQ_TREND_63D — market confirmation input unavailable; reported as UNKNOWN, not as observed divergence, CN_EQ: CN_EQ_VALUATION — valuation overlay unavailable; cap/cushion not applied, COPPER: CHINA_CYCLE — cyclical cluster score unavailable; excluded from stance, not zero-filled, COPPER: COPPER_TREND_63D — market confirmation input unavailable; reported as UNKNOWN, not as observed divergence, GOLD: POLICY_LIQUIDITY — cyclical cluster score unavailable; excluded from stance, not zero-filled, GOLD: FINANCIAL_CONDITIONS — cyclical cluster score unavailable; excluded from stance, not zero-filled, GOLD: GOLD_TREND_63D — market confirmation input unavailable; reported as UNKNOWN, not as observed divergence, GOLD: GOLD_REAL_RATE_OVERLAY — valuation overlay unavailable; cap/cushion not applied, HK_EQ: CHINA_CYCLE — cyclical cluster score unavailable; excluded from stance, not zero-filled, HK_EQ: FINANCIAL_CONDITIONS — cyclical cluster score unavailable; excluded from stance, not zero-filled, HK_EQ: CN_EQ_TREND_63D — market confirmation input unavailable; reported as UNKNOWN, not as observed divergence, USD_CNY: FINANCIAL_CONDITIONS — cyclical cluster score unavailable; excluded from stance, not zero-filled, USD_CNY: POLICY_LIQUIDITY — cyclical cluster score unavailable; excluded from stance, not zero-filled, USD_CNY: USD_BROAD_MOMENTUM — market confirmation input unavailable; reported as UNKNOWN, not as observed divergence, US_EQ: POLICY_LIQUIDITY — cyclical cluster score unavailable; excluded from stance, not zero-filled, US_EQ: FINANCIAL_CONDITIONS — cyclical cluster score unavailable; excluded from stance, not zero-filled, US_EQ: US_EQ_ERP_PROXY — valuation overlay unavailable; cap/cushion not applied`
- all snapshot provenance formal_admission_granted=false: `True`

## Blockers

- bound_series_real_source_unavailable:CN_EQ_LARGE
- bound_series_real_source_unavailable:COPPER
- bound_series_real_source_unavailable:GOLD

