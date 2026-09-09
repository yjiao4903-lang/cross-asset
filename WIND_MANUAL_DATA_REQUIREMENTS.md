# Professional Data Manual Backfill Requirements

> Historical filename retained for compatibility. This document supersedes the old “Wind 人工取数需求（MVP）” workflow.

**Repository**：`yjiao4903-lang/cross-asset`  
**Purpose**：只定义 Professional Data Bridge 无法自动取得关键专业数据时的**最后人工 fallback**。  
**Default policy**：用户不应为公共可自动取得的数据逐条导 Wind/iFind Excel。  
**Must read first**：`docs/DATA_AVAILABILITY_AND_SOURCE_STRATEGY_v1_20260909.md`、`docs/tasks/REQ-PROFESSIONAL-DATA-BRIDGE-W1-20260909.md`、`docs/DATA_ACCEPTANCE_GATE.md`。

---

## 1. Major policy change

旧版文档曾要求用户人工提供：

- CN_EQ_LARGE / CN_EQ_SMALL
- CN_PMI / CN_CPI / CN_PPI
- CN_M1 / CN_M2 / CN_SOCIAL_FINANCING
- CN_DR007
- China style indices
- CN_BOND_10Y 等

该默认工作流现已废止。

后续必须先执行：

```text
1. Official public source discovery / ingestion
2. Public adapter if needed
3. cross-asset probe-professional-data
4. Professional API/SDK automatic ingestion
5. ONLY THEN manual one-time backfill
```

任何开发 LLM 在步骤 1–4 未完成前，不得要求用户手工提供数据。

---

## 2. Data that should NOT normally be requested from the user

以下默认由开发端自动解决，不再列入人工 Wind 清单：

### China macro

- `CN_PMI` — NBS official release
- `CN_CPI` — NBS official release
- `CN_PPI` — NBS official release
- `CN_M1` — PBOC official release
- `CN_M2` — PBOC official release
- `CN_SOCIAL_FINANCING` — PBOC official release

### China leverage

- SSE / SZSE margin financing public disclosures where available

### US / Global public layer

- FRED / ALFRED macro and Treasury series
- NY Fed public rates / term premium / dealer data
- OFR / NFCI / BIS public datasets
- CFTC positioning
- EIA public energy data
- public market proxies already accepted in existing source mappings

### Breadth research

A-share EOD breadth should first use an audited public research adapter and/or official/index constituent information; it should not automatically require a professional export.

---

## 3. Data that MAY require Professional Bridge

Only the following high-value areas are expected to require Wind/iFind or another legitimately entitled professional source.

### P0 — CN Rates & Credit

Candidate minimum set:

| canonical target | Description | Priority |
|---|---|---:|
| CN_CGB_1Y | CGB 1Y yield | P0 |
| CN_CGB_2Y | CGB 2Y yield | P0 |
| CN_CGB_5Y | CGB 5Y yield | P0 |
| CN_CGB_10Y | CGB 10Y yield | P0 critical |
| CN_CGB_30Y | CGB 30Y yield | P0 |
| CN_CDB_5Y | CDB 5Y yield | P0 |
| CN_CDB_10Y | CDB 10Y yield | P0 |
| CN_DR007 | official DR007 daily rate | P0 critical |
| CN_NCD_1Y | representative 1Y NCD rate | P0 |
| CN_CREDIT_AAA_3Y | stable AAA credit yield/spread component | P0 |
| CN_CREDIT_AAA_5Y | stable AAA credit yield/spread component | P0 |
| CN_CREDIT_AAP_3Y | stable AA+ credit component | P0 |
| CN_CREDIT_AAP_5Y | stable AA+ credit component | P0 |

Exact Wind/iFind code must be discovered by the local bridge or verified in the entitled terminal. No code should be guessed in committed config.

### P0 — Valuation

Candidate minimum set:

- CN large-cap PE/PB/dividend yield
- CN small-cap PE/PB/dividend yield
- HK broad index PE/PB/dividend yield
- selected style/sector valuation spreads
- forward PE / consensus EPS only if entitlement and historical semantics are adequate

### P1 — Commodity Futures Structure

Candidate set:

- Gold front / 2nd / 3rd
- Copper front / 2nd / 3rd
- WTI front / 2nd / 3rd
- settlement / expiry / open interest / contract identity

This is for carry / term structure. Yahoo continuous futures remain trend proxies only.

### P2 — Optional professional extras

- MOVE
- selected implied-vol/skew indices
- true ETF flow
- consensus revisions
- richer institutional-flow data

P2 must not block P0/P1.

---

## 4. Preferred user experience

### Normal path — no manual export

User runs once:

```text
cross-asset probe-professional-data
```

The system identifies available Wind/iFind capabilities and automatically ingests entitled datasets through vendor-supported local SDK/API.

User should not need to copy account credentials into ChatGPT/Codex or GitHub.

### Fallback path — only when API entitlement is unavailable

The program generates:

```text
artifacts/professional_data/manual_backfill_requirements.json
```

Only unresolved, high-priority professional gaps may appear there.

---

## 5. Maximum manual delivery scope

If manual backfill is genuinely required, compress it into at most two packs.

### Pack A — CN Rates / Credit / Valuation

Suggested filename:

```text
cn_rates_credit_valuation_v1_YYYYMMDD.xlsx
```

Possible sheets:

```text
rates
credit
valuation
metadata
```

### Pack B — Derivatives Structure

Suggested filename:

```text
derivatives_structure_v1_YYYYMMDD.xlsx
```

Possible sheets:

```text
gold_curve
copper_curve
oil_curve
metadata
```

Do not create separate user tasks for dozens of individual series unless the vendor export tooling makes one combined pack impossible.

---

## 6. Canonical manual schema

Every imported row must still preserve the project’s canonical audit fields.

Minimum:

```text
series_id
source_series_id
observation_date
available_at
value
unit
currency
timezone
vintage_date
is_final
source
```

Recommended professional metadata:

```text
provider
vendor_field
vendor_code
exported_at
price_type
yield_type
index_provider
contract_code
expiry
revision_notes
license_scope_notes
```

Manual import is not allowed to weaken PIT requirements.

---

## 7. PIT rules for manual professional data

### Market daily / rate daily

- `observation_date` = trading/valuation date
- `available_at` = earliest point the value could legitimately be used
- if exact publication time cannot be established, use a documented conservative lag

### Macro

Macro should normally come from public official releases, not manual professional export.

If a professional historical backfill is exceptionally used:

- current revised history must not be represented as historical vintage
- release date/time evidence must be stored separately
- inability to reconstruct vintage => research limitation / lower PIT grade

### Valuation / consensus

Must distinguish:

- trailing vs forward
- observation date vs vendor snapshot date
- forecast vintage
- index constituent/version effects

Consensus data without historical snapshot semantics cannot automatically qualify for PIT backtest.

### Futures curve

Must store contract identity and expiry. Continuous synthetic price alone cannot support carry/roll research.

---

## 8. Credential handling

Never ask the user to paste professional credentials into:

- ChatGPT / Codex prompt
- GitHub issue / PR
- committed config
- CLI command history

Allowed local mechanisms:

- `.env` ignored by git
- OS credential store
- vendor-native local authenticated session

`.env.example` may contain variable names only.

---

## 9. What the user may need to do — maximum expected interaction

Expected normal interaction should be limited to one of the following:

### Case A — SDK/API already available

```text
Run capability probe once.
```

No further action.

### Case B — local vendor SDK exists but requires one-time local login/config

User performs vendor-supported local authentication once; credentials remain local.

### Case C — terminal subscription exists but Data API is not entitled

Only then request Pack A and/or Pack B historical export once.

### Case D — professional dataset is not entitled at all

Do not repeatedly ask the user. Mark:

```text
PROFESSIONAL_DATA_UNAVAILABLE
```

Then use public fallback if semantically valid, otherwise `DATA_BLOCKED` / `DEFER`.

---

## 10. Forbidden shortcuts

- Do not ask user to manually export PMI/CPI/PPI/M1/M2/TSF before official-source automation is attempted.
- Do not use FDR007 as semantic replacement for DR007.
- Do not use current revised macro history as PIT vintage history.
- Do not use Yahoo `^TNX` as semantic equivalent of FRED DGS10.
- Do not use continuous futures price as a valid term-structure/carry dataset.
- Do not merge economically different credit proxies to fabricate long history.
- Do not allow a manual file or fixture to bypass acceptance registry.
- Do not treat professional provider status as research/OOS validation.

---

## 11. Manual file validation

If a file is supplied, importer must validate at least:

- file SHA-256 / idempotency
- provider identity
- vendor code / field identity
- duplicate dates
- unit consistency
- timezone
- future `available_at`
- observation coverage
- missingness
- monotonic timestamps
- contract expiry for futures
- valuation semantic metadata
- credential leakage scan

Successful import still requires normal acceptance before formal consumption.

---

## 12. Developer decision rule

Before generating any manual data request for the user, the implementing LLM must record:

```text
Official public source checked: YES/NO
Public adapter checked: YES/NO
Professional capability probe checked: YES/NO
Professional API entitlement: AVAILABLE/UNAVAILABLE/UNKNOWN
Reason manual backfill is unavoidable:
Exact minimum missing series:
Expected one-time user action:
```

If those fields are not available, do not ask the user for data.

---

## 13. Final operating principle

> **The user is not the data pipeline.**
>
> Public official data should be automated; professional local entitlements should be bridged automatically; manual export is a one-time emergency/backfill path only.
