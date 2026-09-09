# Cross-Asset Data Availability & Source Strategy v1

**Repository**：`yjiao4903-lang/cross-asset`  
**Purpose**：定义后续数据扩充时的来源优先级、用户操作边界、自动化原则和专业数据最小集，避免把可自动取得的数据继续转嫁给用户手工导出。  
**Baseline date**：2026-09-09  
**Status**：`SOURCE_STRATEGY_GUIDANCE`，不代表任何候选源已通过 production acceptance / PIT / OOS 门禁。  
**Must read with**：`AGENTS.md`、`docs/CROSS_ASSET_RESEARCH_ENRICHMENT_ROADMAP_v1_20260909.md`、`docs/DATA_ACCEPTANCE_GATE.md`、`docs/RESEARCH_PROTOCOL.md`。

---

## 1. Core principle

后续数据扩充的目标不是“尽可能多接数据”，而是以**最少用户操作**取得能够显著提升跨资产研究信息密度的数据。

统一采用四级来源策略：

| Tier | Definition | User action | Default policy |
|---|---|---:|---|
| **A — Public Auto** | 官方免费、API/CSV/稳定下载或正式发布页，可自动拉取 | 0 | 首选 |
| **B — Public Engineering** | 免费但需要 HTML/JSON 解析、adapter、raw archive 或较高维护 | 0 | 可用，但必须 source-health + parser tests |
| **C — Professional Bridge** | 免费世界长期历史、语义稳定性或授权不足，使用 Wind/iFind 等专业数据 | 一次本地配置 | 只用于高信息增量领域 |
| **D — Reject / Defer** | 高摩擦、高成本、高脆弱、授权不清或当前增量价值不足 | 0 | 不做/暂缓 |

禁止将“用户可以手工导 Excel”作为默认捷径。只要存在稳定、合法且可审计的自动来源，开发端必须优先自动化。

---

## 2. Expected coverage split

目标状态下，P0/P1 研究数据大致应满足：

```text
70%–80%  Public Auto / Public Engineering
10%       one-time key / local configuration
10%–20%   Professional Bridge
```

这个比例是工程目标，不是硬性验收阈值；任何数据仍需独立通过 source identity、PIT、quality、license/usage、coverage 和 research admission。

---

## 3. US / Global — default to public official sources

### 3.1 Macro / rates / inflation

优先：FRED / ALFRED / Federal Reserve / New York Fed。

候选：

- CPI / Core CPI / PCE / Core PCE
- unemployment / payroll-related macro / initial claims
- industrial production / retail / housing / financial conditions inputs
- EFFR / SOFR
- UST 2Y / 5Y / 10Y / 30Y
- real yields
- 5Y / 10Y inflation breakeven
- yield-curve slopes / curvature
- ACM Treasury term premium

**Tier**：A。  
**User action**：0；如某 API 需要 key，只允许一次性本地环境变量配置。

PIT 要求：宏观优先使用 ALFRED / release-aware policy；不得用最新修订值伪装历史可见值。

### 3.2 Financial stress / credit / funding

优先公开源：

- OFR Financial Stress Index
- Chicago Fed NFCI / ANFCI
- VIX / VIX3M 等官方/公开可验证指数
- FRED credit-spread series where license/history permits
- NY Fed Primary Dealer statistics
- FINRA margin debt
- Treasury TIC
- BIS global liquidity / credit-to-GDP gap / DSR

**Tier**：A/B。

特殊规则：若公开信用利差提供方缩短历史窗口，必须立即做 immutable local archive；长历史不足时允许专业源补历史，但禁止把经济语义不同的代理硬拼成一条生产序列。

### 3.3 CFTC positioning

CFTC official historical compressed files / release schedule。

**Tier**：A。  
**User action**：0。  
必须遵守 Tuesday observation / Friday publication 的 PIT 语义和实际 release schedule。

---

## 4. China macro — public official first, not Wind manual

### 4.1 NBS

以下应优先自动化国家统计局正式发布页，而不是要求用户导 Wind：

- `CN_PMI`
- `CN_CPI`
- `CN_PPI`
- 后续可扩展 Core CPI / CPI components / PPI components
- industrial production / retail / fixed investment 等慢变量

**Tier**：A/B。  
**User action**：0。

开发要求：

1. 保存 official page / release identity；
2. `observation_date` 与 `available_at` 分离；
3. 页面存在正式发布时间时必须使用该时间；
4. parser 需 fixture + raw snapshot；
5. 页面结构变更不得静默回退到第三方聚合。

### 4.2 PBOC

以下应优先自动化中国人民银行正式发布：

- `CN_M1`
- `CN_M2`
- 社融存量 / 社融增量
- RMB loans / sector financing where useful

**Tier**：A/B。  
**User action**：0。

关键要求：**definition/version contract**。例如 M1 统计口径发生制度性调整时，应保存 definition version / valid_from / valid_to，不能把不同定义的历史直接当作完全同质序列。

---

## 5. China market / breadth / leverage

### 5.1 Margin financing

SSE / SZSE official disclosure first。

可自动化：

- financing balance
- margin buying
- securities lending fields where definition remains stable
- daily / 20D / 60D change
- causal rolling percentile

**Tier**：A/B。  
**User action**：0。

### 5.2 A-share breadth

研究层可使用 BaoStock 或其他经审计的公开 EOD adapter 取得大范围股票日线/成分信息，用于：

- % above MA20 / MA60 / MA200
- advance / decline
- 52W high / low
- equal-weight vs cap-weight
- median return
- dispersion / breadth thrust

**Tier**：B。  
**Usage**：`RESEARCH/BREADTH`，不能无审查地替代专业主源。

开源 adapter 只负责 transport；canonical provider identity 应尽量指向原始数据来源，而不是把 AKShare/BaoStock 名字当作经济数据定义。

### 5.3 ChinaMoney adapter caution

公开接口/适配器可以用于 FDR001/FDR007 等定盘利率研究，但必须保持 canonical 语义。

**禁止：**`FDR007 == DR007`。

如果正式 `CN_DR007` 无法从稳定、合法的官方 bulk history 自动获得，则 `CN_DR007` 进入 Professional Bridge；`CN_FDR007` 可作为独立候选序列。

---

## 6. CFFEX / derivatives public layer

公开页面可尝试自动化：

- IF / IH / IC / IM daily settlement / price / OI
- basis
- public member positioning / ranking if source remains stable

**Tier**：B。

规则：

- 两次受控集成仍脆弱后停止反复逆向；
- 不允许 CFFEX 网页抓取阻塞主研究路线；
- 完整历史 Level-1/Level-2、分钟数据或深度持仓若需要，应转 Professional Bridge 或 defer。

---

## 7. Professional Bridge — minimum high-value scope

Professional source 不应成为所有数据的默认入口，只用于免费世界最薄弱、同时研究增量最高的区域。

### 7.1 P0 — CN Rates & Credit

优先通过 Wind/iFind：

- CGB 1Y / 2Y / 5Y / 10Y / 30Y
- CDB 5Y / 10Y
- CDB-CGB spread
- DR007（正式全天口径）
- NCD 1Y or representative NCD curve
- AAA credit 3Y / 5Y
- AA+ credit 3Y / 5Y
- AA/AAA or AA+/AAA spread

目标：建立 `CN_RATES_STATE` + `CN_CREDIT_STATE`，而不是只保留单一 `CN_BOND_10Y`。

### 7.2 P0 — Cross-Asset Valuation

专业源优先用于长期、稳定、可回测的：

- CN large/small equity PE / PB / dividend yield
- HK broad equity PE / PB / dividend yield
- US broad equity valuation where public history is inadequate
- sector/style valuation spreads
- forward PE / consensus EPS / earnings revision（仅在 entitlement 可用时）

必须区分 trailing / forward、price / total-return universe、index provider 和 revision semantics。

### 7.3 P1 — Commodity Futures Structure

如 entitlement 可用，获取 Gold / Copper / Oil：

- front / 2nd / 3rd contract
- settlement
- expiry
- open interest
- roll mapping

用于 carry / backwardation / contango / roll yield。

Yahoo continuous proxy 可继续承担 trend，但不得替代严谨的 futures-curve carry。

### 7.4 P2 — Professional extras

仅在 P0/P1 完成后考虑：

- MOVE
- option skew / selected implied-vol indices
- richer consensus / earnings revision
- true ETF flow data
- deeper institutional flow datasets

---

## 8. Explicit defer / reject list

以下默认 D 级，除非后续研究证明边际价值足以覆盖维护成本：

- 新闻/社交媒体情绪作为核心 allocation factor
- full historical option chain / IV surface
- dealer GEX / gamma black-box data
- Level-2 order book
- 大规模逆向抓取授权边界不清的 ChinaBond/CFETS 深度数据
- 自建完整 CME 长历史期货库替代合法专业数据
- 用 AUM change 冒充 ETF flow
- 用 Yahoo intraday 作为 production core
- 用 FDR007 冒充 DR007
- 重新构造已经不再稳定公开披露的 Northbound legacy net-buy production factor

---

## 9. Professional Data Bridge target architecture

开发目标是在用户本地 Windows 环境中建立 capability-based bridge，而不是长期要求用户导 Excel：

```text
Official Public Sources
        ↓
Public Adapters
        ↓
Canonical / PIT Store
        ↑
Professional Data Bridge
  ├─ WindPy
  └─ iFinDPy
```

首个入口应为：

```text
cross-asset probe-professional-data
```

输出建议：

```json
{
  "windpy": {"available": true, "authenticated": true},
  "ifind": {"available": false, "authenticated": false},
  "capabilities": {
    "cn_rates": true,
    "cn_credit": true,
    "valuation": true,
    "consensus": false,
    "global_futures_curve": false
  },
  "credential_exposure": false
}
```

capability probe 不得输出用户名、密码、token、session id 或原始错误中的敏感片段。

---

## 10. Credential policy

用户不得向 ChatGPT/Codex/GitHub issue 提供 Wind/iFind 账号密码或 token。

允许：

- `.env`（gitignored）
- OS credential store
- vendor-native local authenticated session

禁止：

- CLI 明文参数
- committed config
- logs / artifacts / tests
- issue / PR comments

---

## 11. Manual fallback — only when API entitlement is unavailable

只有 Professional Bridge probe 证明 API/SDK entitlement 不可用时，才允许用户进行一次性历史 backfill。

最多压缩为两个 pack：

### Pack A — CN Rates / Credit / Valuation

`cn_rates_credit_valuation_v1_YYYYMMDD.xlsx`

### Pack B — Derivatives Structure

`derivatives_structure_v1_YYYYMMDD.xlsx`

禁止恢复成“每个宏观序列都由用户逐条导出”的模式。

---

## 12. Source selection algorithm for development LLMs

任何新增 series，开发 LLM 必须按以下顺序执行：

```text
1. Is there an official public source?
   YES -> evaluate Tier A/B and automate.

2. Is there a stable public adapter to the original source?
   YES -> reuse/derive adapter, keep original provider identity.

3. Is the free source insufficient because of history, semantics, license or derivatives depth?
   YES -> query Professional Bridge capability.

4. Is professional entitlement unavailable?
   YES -> decide manual one-time backfill or DEFER.

5. Never ask the user for data before steps 1-4 are documented.
```

---

## 13. Admission requirements

无论数据来自免费还是专业源，都必须满足现有门禁：

- canonical identity
- provider / source_series_id
- license / usage boundary
- observation_date / available_at / vintage_date
- raw archive where applicable
- parser/source health
- acceptance registry
- approved-observation query path
- no fixture satisfying live gate
- Factor/Series Admission Contract
- OOS before production allocation influence

“专业数据”不等于“自动可信”；“官方数据”也不等于“自动具备 PIT”。

---

## 14. Primary implementation order

### Phase DA-0 — remove unnecessary user work

- NBS auto ingestion for PMI/CPI/PPI
- PBOC auto ingestion for M1/M2/TSF
- SSE/SZSE leverage ingestion
- public global rates/stress/positioning expansion

### Phase DA-1 — build Professional Data Bridge

- capability probe
- WindPy adapter
- iFinDPy adapter
- credential-safe local configuration
- capability manifest

### Phase DA-2 — professional P0

- CN Rates & Credit
- valuation

### Phase DA-3 — professional P1

- commodity futures curves
- optional consensus / professional extras

---

## 15. Decision rule

后续开发的默认原则：

> **自动化官方数据优先；专业源只补最有价值的空缺；用户手工操作永远是最后 fallback，而不是正常工作流。**
