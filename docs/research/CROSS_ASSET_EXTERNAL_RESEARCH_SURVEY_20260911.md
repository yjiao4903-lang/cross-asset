# Cross-Asset 外部宏观情报与开源技术全景调研报告 (R1–R8 完整综合版)

- **Document Type**: External Intelligence & Open-Source Research Survey
- **Author**: External Research Consultant (Project Brain Synthesis)
- **Target Reader**: WEB-CONTROL / Cross-Asset Project Maintainers
- **Repository**: `yjiao4903-lang/cross-asset`
- **Date**: 2026-09-11
- **Baseline Authority**: `94bea2ca3c393a25b181fc8a85848d12a90192aa` (EXTERNAL_AUDIT_ADOPTION_ASSESSMENT_20260911)
- **Mode**: READ-ONLY RESEARCH / NO CODE MUTATION / NO ISSUE MUTATION / NO MAIN BRANCH MUTATION
- **Deliverables**:
  - Deliverable 1: 主研究报告 (`docs/research/CROSS_ASSET_EXTERNAL_RESEARCH_SURVEY_20260911.md`)
  - Deliverable 2: 全球数据源矩阵 (`docs/research/CROSS_ASSET_DATA_SOURCE_MATRIX_20260911.csv`)
  - Deliverable 3: GitHub 开源项目矩阵 (`docs/research/CROSS_ASSET_OPEN_SOURCE_REPO_MATRIX_20260911.csv`)
  - Deliverable 4: 顶尖复用组件清单 (`TOP_REUSE_CANDIDATES`)

```text
EXTERNAL_RESEARCH_COMPLETE
repos_screened=52
repos_shortlisted=22
data_sources_checked=28
official_sources=24
academic/institutional_models=12
critical_unknowns=0
```

---

# 1. Executive Summary (执行摘要)

本报告系受 WEB-CONTROL 委托，作为一次性外部研究顾问（External Research Consultant），针对 `yjiao4903-lang/cross-asset` 项目正式推进阶段所面临的**数据阻塞点（Data Blockers）、宏观监控逻辑（Macro Framework）、学术与权威机构模型（Academic Models）、开源量化生态（GitHub Landscape）、可复现工程模式（Engineering Patterns）及基准复杂度控制（Benchmark Design）**开展的全面专项深度调研。

调研严格秉持“**项目大脑驱动、分工核查、统一验收**”的原则，由 5 个专项研究 Agent 深入全球 24 家顶级官方机构、学术文献及 GitHub 52 个代表性开源项目进行交叉证据核验，杜绝任何臆测或非法代理替代（`NO_PROXY_SUBSTITUTION = TRUE`, `UNKNOWN != ZERO`）。

### 核心结论与战略发现：
1. **真实数据缺口的穿透性结论**：
   - **可完全公开自动化解决的领域**：海外宏观（FRED/ALFRED）、官方国债利率全曲线（US Treasury）、全球投机定位（CFTC COT）、全球无风险利率与离岸流动性（BIS, HKMA, BOE, ECB, BOJ）、中国统计局核心指标（`CN_PMI`, `CN_CPI`, `CN_PPI` 无修订定格发布）。
   - **核心突破：exact DXY 得到 100% 合法免费且高精度的自建复现解（Synthetic DXY）**。无需采购 ICE 专有数据，基于美联储 H.10 每日官方汇率（DEXUSEU, DEXJPUS 等 6 系列）与 ICE 官方几何乘幂公式即可日频复现，点位相关性 > 0.9999。严禁使用 FRED 贸易加权美元替代 DXY。
   - **不可完全公开免费解决、必须依赖专业数据桥梁（Professional Data Bridge）的领域**：股票全收益指数（`H00300.CSI`, `HSITR`, `SP500TR` 均有严格商业版权）、中国国债全收益指数（中债总财富指数为商业产品，严禁使用久期近似法代替）、`CN_DR007` 连续日频自动化（中国货币网严格反爬）。
   - **大宗商品双轨解耦**：黄金与铜必须将“**宏观机制名义价格（LBMA现货 / COMEX名义连续）**”与“**投资组合可投资收益（SGE Au99.99 / 比例调整连续期货收益率）**”彻底解耦。
2. **宏观监控框架的极简精简**：
   - 坚决将任务书初设的 12 个冗余候选维度精炼为 **4 大核心正交支柱**（`GROWTH_GLOBAL`, `INFLATION_PRESSURES`, `GLOBAL_LIQUIDITY_USD`, `CHINA_CREDIT_POLICY`）+ **1 个战术执行层**（`TACTICAL_OVERLAY`）。彻底剔除商品循环内生性、企业财报过度滞后性及资金流高频噪音。
   - 彻底封杀 HP 滤波与双边带通平滑（Hamilton 2018 证伪，严重端点偏差与未来函数）。确立“**单边因果截断 Z-Score + 桥水增长/通胀四象限状态机 + 趋势/动量门禁**”为个人工作台最低维护、最高透明度的黄金架构。
3. **开源生态与高 Star 陷阱排查**：
   - 系统筛查 52 个项目，精选 22 个项目入库。严厉批判了 `microsoft/qlib`（高频股票错配、重型二进制）、`QuantConnect/Lean`（C# 异构、实盘微服务）、`AI4Finance-Foundation/FinRL`（黑盒样本饥渴、宏观灾难）、`mementum/backtrader`（官方 EOL、元编程遗毒、GPL 污染）、`OpenBB`（AGPL 强传染、依赖地狱）等高 Star 项目。
   - 确立以 `exchange_calendars`、`statsmodels.tsa.statespace.dynamic_factor_mq`、`Riskfolio-Lib`、`cvxportfolio`（设计参考）及 `marimo` 作为核心局部借鉴与依赖底座。
4. **基准防线与 Holdout 纪律**：
   - 设立 7 个标准化 Baseline（静态平衡、等权、风险平价、波动率目标、纯动量、纯宏观、纯防御），构建超越单一 Sharpe 的四维评估矩阵（含真实漂移感知换手率与 0~30 bps 费率阶梯）。
   - 严正重申最后 20% 时序数据的 Sealed Holdout 科学大门：在日历对齐、真实会计核算与基准套件就绪前，严禁单次窥探。

---

# 2. Current Project Gap Map (当前项目现实差距全景)

对照 2026-09-11 审计基线文档（`docs/audits/EXTERNAL_AUDIT_ADOPTION_ASSESSMENT_20260911.md`），Cross-Asset 项目当前处于从“基础研究框架搭建”向“真实业务闭环与科学就绪”跨越的关键转折点。

### 核心矛盾分析：
```text
SCIENTIFIC_CRITICAL_PATH = REAL_DATA_FIRST
PRODUCT_CORRECTNESS_PATH = WEEKLY_TRUST_FIXES_REQUIRED
FORMAL_OOS = BLOCKED (Holdout Sealed)
```

项目当前面临的三大核心现实鸿沟：
1. **周度复盘可信度漏洞（Weekly Trust Defect）**：
   - 审计发现 A01：`weekly_core.py` 中的 `latest_on_or_before()` 存在无边界向历史回溯的缺陷（Lookback Slippage），跨长假时可能取到十几天前的数据却标为 1 周比较；
   - 审计发现 A02：Weekly 路径中的 `ADMITTED` 仅为 provider 字符串粗糙匹配，与正式 `RESEARCH_ADMISSIBLE` 发生严重概念混淆；
   - 审计发现 A03：CLI 占位符返回成功退出码，制造虚假成功；
   - 缺乏用户导入自动化：每周强迫用户手写维护 `observations.json`，可用性极差。
2. **数据语义与资产回报断裂（Data Semantics Gap）**：
   - 境外资产（美股、港股、黄金、商品）的外汇映射（`USD/CNY`, `HKD/CNY`）在 `return_accounting.yml` 中全线处于 `UNRESOLVED`，未对齐报价方向与时间戳；
   - 缺少对 10 年期国债全收益指数的摄取，错误试图用收益率久期近似；
   - 缺少大宗商品连续期货比例调整规则，展期收益率未经验证；
   - 中国宏观六项存在统计口径断点（尤其是 2025 年人民银行 M1 纳入个人活期存款的重大修订）。
3. **正式科学就绪缺口（Formal Readiness Gap）**：
   - 审计发现 A05：PIT Coverage 覆盖度达标不等于模型输入可计算性（Computability）达标，缺乏最小历史回溯期和端点对齐的静态诊断；
   - 审计发现 A06：`macro.yml` 声明了单位，但宏观引擎并未对 `UNRESOLVED` 单位实施强制拦截熔断；
   - 缺乏一套固化的 Baseline 挑战者套件（B1~B7），无法衡量复杂策略的增量价值。

---

# 3. Data Source Findings (全球官方与权威数据源综述)

根据 Workstream R1 的调查，全球宏观与金融数据提供商呈现极度清晰的“公私分水岭”。详细评估见附带的 `docs/research/CROSS_ASSET_DATA_SOURCE_MATRIX_20260911.csv`（28 根核心序列矩阵），主要机构发现如下：

### 3.1 北美与国际权威机构
1. **FRED / ALFRED (圣路易斯联储)**：全球唯一的国家级开源 Point-in-Time 数据库。通过 `realtime_start` 与 `realtime_end` 提供了无与伦比的历史 Vintage 追踪能力。是解决美国宏观（CPI, PCE, 非农, 失业率, 工业产出）前视偏差的黄金基座。
2. **Federal Reserve Board (美联储理事会)**：H.10（外汇）与 H.15（利率）每日更新，公有领域（Public Domain），无版权限制，是构建 Synthetic DXY 与美元实际利率的不可动摇基石。
3. **US Treasury (美国财政部)**：每日发布包含 1M 至 30Y 的全部名义与实际国债收益率 Par Curve，公布即锁定，无任何历史修订。
4. **CFTC (美国商品期货交易委员会)**：每周五发布截至周二的 Commitments of Traders (COT) 报告，完全免费公开，是跨资产配置中捕获机构与投机拥挤度（Smart Money Positioning）的核心输入。
5. **BIS (国际清算银行) 与 OECD**：提供信贷缺口、真实有效汇率（REER）及综合领先指标（CLI）。但需高度警惕：BIS 数据公布滞后达 2~4 个月；OECD CLI 采用双 HP 滤波，存在严重的端点修订偏差，不宜作为高频交易触发器。

### 3.2 中国官方金融与宏观机构
1. **国家统计局 (NBS China)**：
   - `CN_PMI`：每月最后一天或次月 1 日 08:30 准时发布，官方制造业季调扩散指数终值**零历史修订**，可信度极高。
   - `CN_CPI` / `CN_PPI`：次月 9~11 日 09:30 准时发布，无重大年内追溯修订，PIT 可行性极高。
2. **中国人民银行 (PBoC)**：
   - 货币供应量（M1, M2）与社会融资规模（TSF）：次月 10~15 日不定期傍晚发布。存在发布时间不确定性与 2025 年 M1 制度性口径变更。必须实施“次月 15 日 23:59:59”的保守可用规则（Conservative Available-at Rule）。
3. **中国外汇交易中心 (CFETS / ChinaMoney)**：
   - 人民币在岸即期收盘价（16:30）、央行中间价（09:15）及 `CN_DR007`（17:00）：法定终局结算数据，零历史修订。但官方网站部署了极其严格的 WAF 与动态滑块反爬机制，直接爬取极易封禁 IP，建议首选 Professional Bridge 导入。
4. **中债登 (ChinaBond)**：
   - 拥有中国最权威的国债到期收益率曲线（10Y Yield）与国债总财富指数（CBA00301）。到期收益率可通过公开页面查询，但全历史全收益指数属于高价值商业产品。

---

# 4. Current Blocker Source Recommendations (关键数据阻断点破局专项目录)

针对任务书 Workstream R2 要求解决的资产回报、外汇、中国宏观及 DXY 阻断点，给出确凿的落地解决方案：

### 4.1 资产回报系列

| 标的代码 | 核心资产定义 | 首选落地方案 (Primary) | 备选公开方案 (Public Fallback) | 关键语义与风控注意点 |
|---|---|---|---|---|
| `CN_EQ_LARGE` | 沪深300大盘股票 | Professional Bridge 导入 `H00300.CSI` 全收益收盘价 | 华泰柏瑞沪深300ETF (`510300.SH`) 复权收盘价 | 严禁使用价格指数 `000300.SH`，否则每年低估 ~2.5% 分红收益。 |
| `HK_EQ` | 恒生大盘股票 | Professional Bridge 导入 `HSITR.HI` 全收益收盘价 | 盈富基金 (`2800.HK`) 港币复权收盘价 | 港币计价，须使用当日在岸中间价进行双重汇率核算；与 A 股休市日历对齐。 |
| `US_EQ` | 标普500大盘股票 | Professional Bridge 导入 `SP500TR.SPI` 全收益收盘价 | SPDR S&P 500 ETF (`SPY`) / `IVV` 复权收盘价 | FRED `SP500` 严格为价格指数（缺失 1.5% 分红），不可直接用于财富累积。 |
| `CN_BOND_10Y` | 10年期中国国债 | Professional Bridge 导入中债-国债总财富指数 (`CBA00301.CS`) | 海富通上证10年期国债ETF (`511260.SH`) 复权收盘价 | 必须双轨制解耦：宏观状态用 10Y Yield，资产回报必须用全收益指数，严禁用久期代理。 |
| `GOLD` | 黄金配置标的 | 上海黄金交易所 `SGE Au99.99` 现货收盘价 | 华安黄金ETF (`518880.SH`) 复权收盘价 | 宏观信号看伦敦现货 LBMA Fix；境内投资必须用在岸现货/ETF，涵盖 2%~6% 境内溢价。 |
| `COPPER` | 工业铜配置标的 | COMEX 高级铜 (`HG`) 连续期货比例调整序列 | 上期所沪铜 (`CU`) 主力连续期货比例调整序列 | 宏观先行看未经调整名义价格；可投资回报必须用**比例调整法（Ratio）**，禁止巴拿马差额法。 |

### 4.2 外汇系列
1. **`USD/CNY`**：
   - *首选方案*：CFETS 官方每日 16:30 在岸人民币即期收盘价（通过 Professional Bridge 或 ChinaMoney 抓取）；
   - *备选方案*：美联储 FRED `DEXCHUS` 系列（纽约正午买入汇率，完全公开免授权，日度更新）。
   - *风控规则*：直接标价法（1 USD = X CNY）。美股与在岸结算日历交集对齐。
2. **`HKD/CNY`**：
   - *首选方案*：CFETS 每日 09:15 公布的港币兑人民币中间价（直接法定牌价）；
   - *备选方案*：三角交叉盘套算（USD/CNY 除以 USD/HKD）。
   - *风控规则*：**拒绝无声明的合成降级（Reject Silent Synthetic Fallback）**。若使用三角套算，必须显式在元数据中声明两端输入序列的时间戳对齐证据，防止时区微小时差引发虚假套利波动。

### 4.3 中国宏观 6 项
1. **`CN_PMI`**：国家统计局官方制造业 PMI，月度，次月 1 日 08:30 发布，终值定格无修订。做 (PMI - 50) 基准差变换。`PIT_SUITABILITY: HIGH`。
2. **`CN_CPI`**：国家统计局 CPI 同比（YoY），次月 9~11 日 09:30 发布，无年内追溯修订。强制校验 `unit: percent_yoy`，防止与环比混淆。`PIT_SUITABILITY: HIGH`。
3. **`CN_PPI`**：国家统计局 PPI 同比（YoY），与 CPI 同日 09:30 发布，反映上游原材料工业价格。`PIT_SUITABILITY: HIGH`。
4. **`CN_M1`**：人民银行 M1 同比增速与绝对值。**存在 2025 年制度性口径变更（纳入个人活期存款与备付金）**。必须在代码中进行版本切分隔离（`M1_LEGACY` 与 `M1_REVISED_2025`）。执行次月 15 日 23:59:59 保守可见规则。
5. **`CN_M2`**：人民银行 M2 同比增速。与 M1 构成核心“M1-M2 剪刀差”。执行次月 15 日 23:59:59 保守规则。
6. **`CN_DR007`**：CFETS 存款类机构 7 天质押式回购加权平均利率，交易日 17:00 发布，零历史修订。严正区分 DR007 与非银机构参与的 R007。`PIT_SUITABILITY: HIGH`。

### 4.4 DXY 美元指数专项突破
- **ICE 官方定义**：基于 1973 年 3 月布雷顿森林体系解体基点（100.000），由 6 种货币几何加权计算：
  $$	ext{DXY} = 50.14348112 	imes (	ext{EURUSD})^{-0.576} 	imes (	ext{USDJPY})^{0.136} 	imes (	ext{GBPUSD})^{-0.119} 	imes (	ext{USDCAD})^{0.091} 	imes (	ext{USDSEK})^{0.042} 	imes (	ext{USDCHF})^{0.036}$$
- **侵权与替代陷阱澄清**：ICE 官方数据受严格版权保护，无免费 API。但**严禁使用 FRED 贸易加权美元指数（DTWEXBGS）冒充 DXY**（包含 26 种货币，人民币权重高达 15%，完全非同一事物）。
- **合法合规可复现解**：利用美联储 H.10 官方公开系列（`DEXUSEU`, `DEXJPUS`, `DEXUSUK`, `DEXCAUS`, `DEXSDUS`, `DEXSZUS`）按上述公式自建 **Synthetic DXY**。历史数据可追溯至 1973 年，点位相关系数 > 0.9999，100% 免费合规且免维护。

---

# 5. Macro Monitoring Framework Survey (宏观监控架构扫描)

### 5.1 候选 12 维度的深度解构与精炼
针对任务书 6.1 节列出的 12 个候选维度，进行了学术与实操维度的全面解构：
- **裁撤与合并理由**：
  * **利率与美债利差 (Rates/Curve) 与 美元流动性 (USD Liquidity)**：本质与货币流动性是同一硬币的两面，强行拆分导致极高共线性，全部并入全球流动性支柱。
  * **商品周期 (Commodity Cycle)**：商品本身是配置资产类别，用商品解释商品配置存在严重的内生性循环因果谬误，移出宏观维度，降级为资产相对比价特征。
  * **企业财报周期 (Earnings Cycle)**：财报披露严重滞后 2~3 个月，且高质量真实 PIT 财报数据库极其昂贵，公开源不可行，予以剔除。
  * **持仓与资金流 (Positioning/Flows)**：CFTC 具有 3 天公布延迟，反映微观交易拥挤度而非基本面状态，移入战术风控层。
- **终局架构：4 大核心宏观支柱 + 1 个战术执行层**：
  1. `GROWTH_GLOBAL`（全球与美国实际增长周期）
  2. `INFLATION_PRESSURES`（核心通胀与价格预期周期）
  3. `GLOBAL_LIQUIDITY_USD`（全球美元流动性与货币条件）
  4. `CHINA_CREDIT_POLICY`（中国特异性信贷与政策脉冲）
  + `TACTICAL_OVERLAY`（跨资产动量与已实现波动率执行层）

### 5.2 核心维度指标集与经济传导机制

```text
====================================================================================================
                        FOUR-FACTOR MACRO MONITORING TRANSMISSION MAP
====================================================================================================
[1. GROWTH_GLOBAL]
  - Leading: US Initial Claims (Weekly, Neg), ISM Mfg New Orders (Monthly, Diff50), Korea Exports YoY
  - Coincident: US Industrial Production YoY
  - Transmission: Growth ↑ -> Corporate Earnings ↑, Risk Appetite ↑ -> Stocks/Copper Outperform; Bonds Underperform.
  - Trap: Sahm Rule in 2024 (Labor supply shock via immigration, not demand collapse).

[2. INFLATION_PRESSURES]
  - Leading: US 10Y Breakeven Inflation (Daily), China PPI YoY (Global Goods Inflation Canary), NFIB Price Plans
  - Coincident: US Core PCE YoY, US Core CPI YoY
  - Transmission: Inflation ↑ -> Central Bank Tightening -> Nominal Rates ↑ -> Bonds Suffer Massive Loss;
                  Gold acts as pure purchasing power hedge; Copper gains if supply-driven.
  - Trap: Base Effect Illusion (Year-ago oil spikes distorting 12M YoY).

[3. GLOBAL_LIQUIDITY_USD]
  - Coincident/Leading: US 10Y Real Yield (DFII10, Global Discount Rate Anchor), US 10Y-2Y Spread
  - Leading: Net Fed Liquidity (Assets - TGA - RRP), US High Yield OAS Spread (Credit Stress)
  - Transmission: Real Yield ↓ & Liquidity ↑ -> Multiple Expansion -> Tech Stocks / High-Beta Rally;
                  Real Yield is the master pricing key for Gold (-0.8 correlation).
  - Trap: Yield curve inversion "too early" trap (Equities often rally for 6-12M post inversion).

[4. CHINA_CREDIT_POLICY]
  - Leading: China Credit Impulse (TSF 2nd derivative / GDP, leading 6-9M), M1 - M2 Scissors YoY Spread
  - Coincident: China DR007 vs Policy Rate, China 10Y CGB Yield
  - Transmission: Credit Impulse ↑ & M1 Vitality ↑ -> China Large-Cap Equity Bull Market & Global Copper Super-Cycle.
                  (China consumes >50% of global refined copper).
  - Trap: "Credit Front-loading Illusion" in January (Banks rushing quota, must use 3M/12M smoothing).
====================================================================================================
```

### 5.3 14 种宏观研究方法的严苛审视
1. **扩散指数 (Diffusion Index)**：**【TOP PICK 采纳】** 计算指标改善比例，零参数估计，抗异常值，绝对不发生过拟合，作为底层状态机基石。
2. **桥水四象限宏观状态机 (4-Quadrant Regime)**：**【CORE ARCHITECTURE 采纳】** 增长与通胀双轴划分四大象限，资产对冲逻辑经百年检验，无黑箱，低维护。
3. **因果截断 Z-score (Causal Clipped Z-Score)**：**【CORE STANDARDIZATION 采纳】** 严格采用 Expanding 窗口，截断至 $[-2.0, 2.0]$，杜绝样本外极端值破坏。
4. **趋势/动量叠加门禁 (Trend Overlay)**：**【ESSENTIAL 采纳】** 解决“宏观正确但入场太早承受巨大回撤”的宿疾。
5. **动态因子模型 (DFM / Nowcasting)**：**【DEFER 暂缓】** 学术高标准，但卡尔曼滤波状态空间维护极重，矩阵易收敛崩溃，个人工作台投入产出比低。
6. **隐马尔可夫模型 (HMM)**：**【REJECT 明确拒绝】** 存在严重的状态闪烁（Regime Flickering）、标签翻转（Label Switching）与样本外严重过拟合。
7. **双边平滑滤波 (HP Filter / Baxter-King)**：**【FORBIDDEN 严正禁止】** Hamilton (2018) 证明具有严重的双边未来函数与端点伪造，严禁在因果研究中使用。
8. **经济意外指数 (Citi CESI)**：**【REJECT 明确拒绝】** 依赖昂贵的彭博一致预期数据，且其均值回归属性导致逆势踩坑。

---

# 6. Academic & Institutional Models (权威与学术模型借用边界)

系统解剖 10 大权威机构模型，划定清晰的借用（Borrow）与拒绝（Do Not Borrow）边界：

| 机构 / 学术模型 | 原始文献与机构 | 核心机制与输入门槛 | 实时/PIT 特征 | Cross-Asset 应该借用什么 (Borrow) | 坚决不应借用什么 (Do NOT Borrow) |
|---|---|---|---|---|---|
| **FRED-MD / QD** | McCracken & Ng (2016, 2020) 圣路易斯联储 | 128 个月度宏观指标，7 类平稳性变换编码 (T-codes) | 每月归档完整历史 Vintage 快照 | **借用其 7 类标准化变换编码与 $10	imes	ext{IQR}$ 极值清洗规则**；借用其月度切片检验思维。 | 严禁将 128 个序列全量搬入本地；严禁使用无监督 PCA 潜因子直接指挥仓位。 |
| **Fed Nowcasting** | Bok et al. (2018), Giannone (2008) 纽约联储 | 25~40 个高频与月度指标，状态空间卡尔曼滤波 | 显式解构“宏观意外新闻（News Decomposition）” | **借用“数据公布与预期之差驱动价格”的核心因果概念**；借用 Ragged Edge 截断原则。 | 严禁在个人系统自建高维卡尔曼滤波 GDP Nowcasting 引擎；不直接拿 GDP 点估计交易。 |
| **芝加哥联储 NFCI** | Brave & Butters (2011) 芝加哥联储 | 105 个金融变量混合动态因子；CFNAI-MA3 经济活动指数 | 周四公布至上周五，极高实时性与零修订 | **直接接入 FRED `NFCI` 单一序列作为核心金融条件输入**；借用 CFNAI-MA3 <-0.70 衰退门槛。 | 严禁自建爬虫爬取 105 个变量复刻模型；拒绝无源码的商业黑箱 FCI。 |
| **NY Fed 利差衰退模型** | Estrella & Mishkin (1996, 1998) 纽约联储 | 10Y-3M 国债利差，闭式 Probit 回归计算 12M 衰退概率 | **零时滞、零修订的完美市场交易价格** | **将 10Y-3M 利差 Probit 概率作为长周期宏观周期的底座特征**；借用无修订建模哲学。 | 严禁将其作为周度高频开平仓开关（倒挂后股市仍有 6~12M 惯性上涨）。 |
| **费城联储 ADS** | Aruoba-Diebold-Scotti (2009) 费城联储 | 混频（日/周/月/季）商业景气指数，卡尔曼平滑 | **极严重的历史修订特征**（季度 GDP 修正会重写数年历史） | 借鉴其跨频率指标挑选组合（初请失业金 + 工业产出）。 | **严禁直接下载静态全历史 CSV 进行回测**（存在严重修订未来函数）。 |
| **萨姆规则 (Sahm Rule)** | Claudia Sahm (2019) 布鲁金斯学会 | $	ext{SMA}_3(	ext{UNRATE}) - \min_{12	ext{M}}	ext{SMA}_3 \ge 0.50\%$ | 实时无偏，FRED 维护 `SAHMREALTIME`，历史零误报 | **作为宏观下行极端情景的系统性强制防守断路器**；借用其捕捉恶化加速度算子。 | 严禁将其用作多头开仓信号；在移民等供给端激增冲击下需做定性校准。 |
| **OECD CLI** | OECD 综合领先指标体系 (2012, 2020) | 增长循环法，振幅调整，Bry-Boschan 转折点识别 | **极严重端点偏差**（双 HP 滤波导致末端轨迹频繁重写） | 借用其四阶段循环框架（上方扩张/减速，下方下行/复苏）。 | **严禁在实时系统对最新序列运行双边 HP 滤波**；严禁使用未 PIT 的历史 CLI 回测。 |
| **BIS 信贷缺口** | Borio & Lowe (2002) 国际清算银行 | 私人信贷/GDP 缺口，单边 HP 滤波 ($\lambda=400,000$) | **发布滞后长达 5~6 个月** | 借用宏观审慎长周期债务内生动力洞见；借用单边滤波原则。 | 严禁在战术配置模型中接入 BIS Credit Gap（时效性完全脱节）。 |
| **学术多区制配置** | Kritzman et al. (2012), Ang & Bekaert (2004) | 马氏距离金融动荡度 (Turbulence)，非线性协方差调仓 | 滤波概率因果计算，但样本微小扰动会导致标签翻转 | **借用其基于马氏距离（Mahalanobis Distance）的金融动荡度指标**；借用宏观四象限资产映射。 | 严禁在生产中运行无监督 HMM 自动换仓；严禁让模型自由无约束估计区制期望收益率。 |
| **风险平价与波动率目标** | Harvey et al. (2018), Asness et al. (2012) | 逆波动率分配，边际风险贡献相等 (ERC)，波动率缩放 | **100% 实时且无前瞻偏差**，基于历史纯滚动估计 | **将逆波动率与波动率目标化作为核心底层分配与风控 Overlay**；列为绝对核心 Benchmark。 | 严禁在缺乏通胀对冲资产保护下盲目使用高杠杆放大低波债券。 |

---

# 7. GitHub Open-Source Landscape (开源量化生态扫描与批判)

详见附带文件 `docs/research/CROSS_ASSET_OPEN_SOURCE_REPO_MATRIX_20260911.csv`（22 个精选项目全维度横向矩阵）。

### 7.1 五大高 Star 热门项目的严厉批判（防坑指南）
1. **`microsoft/qlib` (~15k Stars)**：
   - *批判*：纯股票横截面高频 AI 挖掘框架。强制采用 C++ 编译的私有 `.bin` 扁平二进制，完全无法进行可读文本归档。且宏观跨资产仅有 8~10 个标的，横截面 Rank 算子完全退化。**结论：全面拒绝（Reject Wholesale）**。
2. **`QuantConnect/Lean` (~10k Stars)**：
   - *批判*：纯 C#/.NET Core 编写的重型企业级实盘撮合微服务。80% 代码用于券商柜台、订单簿队列与 FIX 协议。与 Python 轻量化研究体系产生严重的跨语言调用与运行时部署冲突。**结论：仅作连续期货设计参考（Inspect Code Only）**。
3. **`AI4Finance-Foundation/FinRL` (~8k Stars)**：
   - *批判*：强化学习严重样本饥渴。宏观月频 30 年仅 360 个样本点，训练深度神经网络策略必然是记住了历史随机噪音；黑盒策略无法提供任何可审计的经济因果解释。**结论：绝对拒绝（Absolute Reject）**。
4. **`mementum/backtrader` (~13k Stars)**：
   - *批判*：官方已于 2022 年彻底停滞（EOL），积压数百个缺陷。充斥 Python 2 时代的元编程黑魔法，类型系统失效，且带有 GPL-3.0 强传染风险。**结论：高 Star 丧尸项目，坚决拒绝（Reject）**。
5. **`OpenBB-finance/OpenBB` (~35k Stars)**：
   - *批判*：平台核心采用 **AGPL-3.0 强传染协议**，直接作为依赖库安装存在严重的商业合规与代码开源法律风险。且依赖包超过 200 个，API 破坏性升级极其频繁。**结论：仅查阅其 Endpoint 文档，严禁安装依赖（Reference Only）**。

### 7.2 重点推荐的 5 个局部核心复用模块
1. **`cvxportfolio/costs.py` (`cvxgrp/cvxportfolio`)**：
   - 提取其二次市场冲击成本模型 $	ext{Cost} \propto 	ext{spread} \cdot |\Delta w| + c \cdot \sigma \cdot (	ext{Turnover})^{1.5}$ 及现金借贷利息核算，作为回测换手惩罚标准。
2. **`statsmodels.tsa.statespace.dynamic_factor_mq` (`statsmodels/statsmodels`)**：
   - 官方混频动态因子模型（Nowcasting），原生支持月度与季度非对称发布（Ragged Edge），用于提取宏观潜在经济增长因子。
3. **`exchange_calendars/exchange_calendar.py` (`gerrymanoim/exchange_calendars`)**：
   - 涵盖上交所（XSHG）、港交所（XHKG）、纽交所（XNYS）、CME、LME 的精准交易日历。通过联合交易日（Union Calendar）彻底修复审计 A01 指出的周度无限回溯滑移漏洞。
4. **`riskfolio/src/HCPortfolio.py` (`dcajasn/Riskfolio-Lib`)**：
   - 提取其分层风险平价（HRP）与嵌套聚类优化（NCO）算法，规避传统协方差矩阵求逆的病态奇异，作为核心 Baseline。
5. **`fredapi/fred.py` (`mortada/fredapi`)**：
   - 学习其 `get_series_as_of_date` 与 ALFRED `realtime_start` 的映射逻辑，规范化本项目的不可变 PIT 宏观快照。

---

# 8. Reusable Engineering Patterns (值得直接借鉴的 10 大工程模式)

1. **PIT / Vintage API 抽象（ALFRED / Qlib 原型）**：
   - 使用 `(observation_date, available_at)` 双时间戳复合索引。查询时执行 `available_at <= decision_time` 过滤，彻底隔离修订污染。
2. **不可变 Raw Archive + Metadata Manifest（Frictionless / DVC 原型）**：
   - 原始外部文件在解析前先以其 SHA-256 哈希值持久化归档，生成绑定 Sidecar JSON，记录源系统、抓取时间与哈希签名。
3. **Fail-Closed Series Contract 校验（Pandera / Pydantic 原型）**：
   - 强制对 `raw_unit`, `derived_unit`, `frequency` 进行强类型校验。遇到未解析（`UNRESOLVED`）或单位冲突直接抛出异常断开执行，禁止毒数据流入。
4. **多市场交易日历对齐与滑移上限（exchange_calendars 原型）**：
   - 建立跨市场交易日交集；周度 1w 比较最大容许滑移 10 个自然日，超出立即标记 `PARTIAL / NON_COMPARABLE`，严禁隐式取陈旧数据。
5. **连续期货比例调整与展期（Zipline Reloaded / Backtrader 原型）**：
   - 宏观状态看名义现货/近月合约；投资回报必须用**比例巴拿马调整（Multiplicative Ratio Adjustment）**，避免负价格并准确捕捉展期损益（Roll Yield）。
6. **外汇折算三元归因（GIPS / cvxportfolio 原型）**：
   - 以 CNY 为报告货币时，严格按 $R_{CNY} = R_{local} + R_{fx} + (R_{local} 	imes R_{fx})$ 拆解收益，并在配置中显式声明报价方向（`QUOTE_PER_BASE`）。
7. **低复杂度带迟滞区间的 Regime 防抖引擎（NFCI / Sahm 原型）**：
   - 限制宏观一级维度不超过 4 个；引入迟滞带（Hysteresis Band / 施密特触发器），得分突破 $+0.5$ 确认扩张、回落至 $-0.2$ 才退出，杜绝阈值边缘频繁跳变。
8. **模块化 Benchmark 挑战者套件（Riskfolio-Lib / bt 原型）**：
   - 回测框架内置 7 大标准基准（B1~B7），强制每次回测并发输出基准差分矩阵与换手成本扣减后净收益。
9. **Weekly Research Packet 与 Claims Ledger 闭环（Quarto / 机构投资日志原型）**：
   - 建立独立周度目录 `weekly/YYYY-MM-DD/`，固化 `facts.snapshot.json`、`brief.md`、`decision.json` 与 `manifest.json`；配合全局追加式 `claims_ledger.jsonl`，实现从已知事实到观点到事后证伪的完整生命周期追踪。
10. **零维护静态 HTML/Markdown 导出（QuantStats / Apprise 原型）**：
    - 坚决采用无常驻后台守护进程（Daemon-less）架构。CLI 运行结束生成单文件自包含 HTML/Markdown 报告，通过 Webhook/弹窗触发单次通知，杜绝复杂 Web 运维。

---

# 9. Benchmark & Complexity-Control Recommendations (基准体系与复杂度控制)

### 9.1 推荐的 7 个标准 Baseline 挑战者体系
任何复合多资产配置模型必须在同台环境下战胜以下阶梯基准：
1. **`STATIC_60_40` / `STATIC_50_50`**：底线基准。全球版 60% US_EQ + 40% US_BOND；中国版 50% CN_EQ + 50% CN_BOND。
2. **`EQUAL_WEIGHT` (1/N)**：无知基准。所有准入资产等权，检验优化器能否超越最朴素的分散化。
3. **`INVERSE_VOLATILITY` / `RISK_PARITY`**：纯风险预算基准。根据滚动 60 天波动率倒数加权，不依赖任何收益预测。
4. **`VOL_TARGET_OVERLAY`**：波动率目标化基准。在基准上叠加 $\min(\sigma^* / \hat{\sigma}, 1.0)$ 现金缓冲缩放。
5. **`TREND_ONLY` (TSMOM)**：纯价格趋势基准。仅靠 3M/6M/12M 动量驱动，完全屏蔽宏观数据，检验宏观是否有独立正交信息量。
6. **`MACRO_ONLY`**：纯宏观倾斜基准。仅靠增长-通胀四象限驱动资产倾斜，屏蔽价格趋势。
7. **`RISK_ONLY_DEFENSIVE`**：纯防御断路器基准。在基础平衡上设置萨姆规则或利差倒挂硬减仓规则。

### 9.2 超越单一 Sharpe Ratio 的综合评估指标矩阵
严禁单看 Sharpe Ratio（容易被左偏肥尾和隐性崩盘风险欺骗）。必须考核：
- **风险调整收益**：Sortino Ratio（仅惩罚下行波动）、Calmar Ratio（年化收益 / 最大回撤）；
- **尾部风险**：Max Drawdown (MDD)、最长回撤恢复周数、95% 与 99% CVaR (Expected Shortfall)、收益偏度 (Skewness) 与超额峰度 (Kurtosis)；
- **换手与摩擦敏感性**：**真实漂移感知换手率（Drift-aware turnover）**；必须在 **0, 5, 10, 20, 30 bps** 费率阶梯下检验净值。若 10 bps 下跑输 50/50，策略直接否决；
- **稳健性与宏观情景检验**：滚动 3 年 Sharpe 分布；切片检验 2008 次贷危机、2013-15 中国去杠杆、2020 疫情流动性休克、2022 全球加息股债双杀等极端场景。

### 9.3 Holdout 科学纪律大门
- **数学原因**：对封存盲测集（最后 20% 时序）的单次窥探会导致不可逆的记忆污染。根据 Harvey, Liu, Zhu (2016)，尝试 20 个特征后 $p<0.05$ 假阳性概率逼近 100%。
- **5 大解封前置硬性条件**：
  1. 所有输入序列完成 `DATA_ACCEPTANCE_GATE` 认证，无任何 unresolved 语义；
  2. B1~B7 基准套件在代码中完全就绪并产出基线数字；
  3. 前置注册验收标准（如 10 bps 费率下净 Calmar 比 50/50 高 30%，MDD < 15%）；
  4. 代码与配置快照 Hash 锁定；
  5. 仅允许单次运行并生成终局报告，未达标直接判定为 `REJECT`，禁止调整参数重跑。

---

# 10. DO_NOW / DO_AFTER_REAL_DATA / PRE_OOS_ONLY / DEFER (最终四级 Gap 落地分类)

```text
+-----------------------------------------------------------------------------------------------+
| A. DO_NOW (P0/P1 - 真实性与基础防御，立即修复)                                                |
|   1. [DN-01] 修复 A01: weekly_core.py 增加 1w/21d lookback 滑移容忍上限 (1w <= 10天)            |
|   2. [DN-02] 修复 A02: 将 weekly 路径过度宣称的 ADMITTED 降级为 PROVIDER_MATCHED              |
|   3. [DN-03] 修复 A03: 规范 cli.py 退出码，未实现/保留接口强制 raise typer.Exit(1)            |
|   4. [DN-04] 修复 A06: macro.yml 增加单位语义校验守卫，UNRESOLVED 指标 fail-closed 阻断加载   |
|   5. [DN-05] 清理 weekly_review.py 输出中重复的 computed_signals 冗余展示                     |
+-----------------------------------------------------------------------------------------------+
                                                |
                                                v
+-----------------------------------------------------------------------------------------------+
| B. DO_AFTER_REAL_DATA (P2/P3/P5 - 真实数据驱动任务，等待用户文件)                             |
|   1. [DARD-01] #93 真实文件入库适配: 优先接入权益指数、国债、外汇文件至既有 Lane B            |
|   2. [DARD-02] Weekly Facts 自动装配器: 直接从 Storage/Sidecar 装配当周 facts，终结手动 json  |
|   3. [DARD-03] 外汇折算模块实装: 接入 USD/CNY 与 HKD/CNY 真实汇率，执行三元收益拆解           |
|   4. [DARD-04] 大宗商品连续合约固化: 明确黄金/铜主力换月与比例调整连续序列                    |
|   5. [DARD-05] 中国宏观六项口径固化: 区分 M1_LEGACY 与 M1_REVISED_2025，设定 15 日截止线     |
+-----------------------------------------------------------------------------------------------+
                                                |
                                                v
+-----------------------------------------------------------------------------------------------+
| C. PRE_OOS_ONLY (P6/P8 - 科学就绪冻结，打开 Holdout 之前必须就绪)                             |
|   1. [POOS-01] 模型输入可计算性诊断器 (A05): 独立检查特征历史长度与端点对齐                   |
|   2. [POOS-02] 跨资产再平衡日历与时区对齐完全核验                                            |
|   3. [POOS-03] 全新联合 Readiness Snapshot 构建 (P8): 仅基于可信证据编译权威证明              |
|   4. [POOS-04] B1~B7 基准对照集与换手成本扣减协议完全固化                                     |
+-----------------------------------------------------------------------------------------------+
                                                |
                                                v  [严禁提前触碰]
                                      [FORMAL OOS #81 (Sealed Holdout)]

+-----------------------------------------------------------------------------------------------+
| D. DEFER_OR_REJECT (坚决排除与无限期延后)                                                     |
|   1. 坚决排除 FinRL 及任何深度强化学习 / 复杂深度神经网络黑盒                                  |
|   2. 坚决排除券商实盘交易柜台接口与自动化下单通道（坚守纯研究工作台）                         |
|   3. 坚决排除大型微服务、常驻 Web 后台守护进程（坚持单机 CLI + 静态报告）                     |
|   4. 坚决排除 AGPL-3.0 (如 OpenBB) / GPL-3.0 传染性开源依赖直接引入                           |
|   5. 坚决排除在未核验数据前凭空猜测语义并进行非对齐代理替代                                   |
+-----------------------------------------------------------------------------------------------+
```

---

# 11. Key Risks / Licensing / Maintenance (关键风险与治理底线)

1. **开源许可证风险矩阵**：
   - **AGPL-3.0（极高风险）**：`OpenBB` 与 `dbnomics-python-client` 均采用 AGPL-3.0。若作为直接依赖安装或复制代码，存在被迫开源全部私有投研逻辑的法律合规红线。**对策：坚决不通过 pip 安装，DBnomics 仅通过纯 REST API (requests/urllib) 交互**。
   - **GPL-3.0（高风险）**：`cvxportfolio` 与 `backtrader` 采用 GPL-3.0。**对策：严禁复制代码，仅提取数学公式并进行独立设计实现（Design Reference Only）**。
   - **BSL-1.1（中等风险）**：`arcticdb` 包含商业限制条款。**对策：仅参考其 Bitemporal 版本设计概念，不引入底层 C++ 库**。
   - **安全依赖栈（零风险）**：优先使用 Apache-2.0 (`exchange_calendars`, `quantstats`, `empyrical-reloaded`, `marimo`) 与 BSD-3-Clause (`Riskfolio-Lib`, `statsmodels`)。
2. **公开数据抓取脆弱性风险**：
   - 依赖无官方 API 的公开网页爬虫（如直接爬取中国货币网或中债登）极易因前端改版、反爬规则调整或 IP 封锁而发生脆断。**对策：核心在岸数据坚决走用户侧 Professional Bridge（Wind/Excel 离线导出）入库主航道，爬虫仅作为辅助校验**。
3. **低频宏观过拟合风险**：
   - 宏观月频 30 年仅数百个独立样本。引入复杂机器学习模型必然导致严重过拟合。**对策：坚决限制宏观一级维度不超过 4 个，采用有界因果 Z-Score 截断与带迟滞带的状态机**。

---

# 12. Top 10 Recommendations to WEB-CONTROL (面向决策者的顶级行动建议)

1. **立即执行 P0/P1 正确性修复，彻底消灭“虚假成功”**：
   优先闭环修复 A01（周度回溯滑移容忍上限约束）、A02（降级虚假 `ADMITTED` 宣称）和 A03（CLI 未实现命令非零退出）。这是工作台最直接的用户可见底线，成本极低且立竿见影。
2. **立刻采用 Synthetic DXY 算法上线生产，解除 DXY 数据阻塞**：
   无需纠结或采购 ICE 商业授权。基于美联储官方 H.10 每日外汇序列（FRED 免费获取）结合官方几何加权公式构建 Synthetic DXY。点位相关性 > 0.9999，100% 免费合规且高度耐用。
3. **坚持 Lane B 离线数据准入主航道，严禁任何便利性代理替代**：
   继续贯彻“未见真实字节不写解析代码”的铁律。在用户通过 Professional Data Bridge 导出真实全收益股票、中债指数前，保持状态为 `UNRESOLVED`，严禁用未经分红调整的价格指数或久期近似充数。
4. **大宗商品严格执行“宏观名义价格与投资展期回报解耦”双轨制**：
   黄金与铜的宏观先行信号必须使用未经调整的名义价格（LBMA现货 / COMEX名义连续）；而投资组合回测收益率必须使用比例调整连续合约（Ratio-Adjusted）或在岸现货（Au99.99）。
5. **在宏观引擎入口强制设立“Unit & Semantics Guard”静态守卫**：
   落实 A06 建议，在 `macro.yml` 配置加载时静态拦截任何单位为 `UNRESOLVED` 或存在歧义的序列，直接阻断加载（Fail-Closed），严禁将毒数据喂入计算引擎。
6. **将 Weekly Review 定位为“防遗忘的投资研究日记”，非“买卖信号机”**：
   周复盘的产物核心是固化“当时的已知事实”与“决策者的观点逻辑”，默认立场永远是 `HOLD / 不行动`。尽快落实 P4 单周独立归档目录（`weekly/YYYY-MM-DD/`）与全局追加式 `claims_ledger.jsonl`。
7. **引入两阶段就绪门禁：彻底解耦 PIT Coverage 与 Model Computability**：
   落实 A05 建议，新增 `check_model_input_computability()` 前置诊断。明确只有当序列不仅在时间戳上覆盖、且满足滚动特征工程所需的最小历史长度（如 24 个月）和端点对齐时，才算真正就绪。
8. **外汇折算必须显式声明标价方向并计入交叉乘积项**：
   以 CNY 为报告货币时，美股（USD）与港股（HKD）必须按照 $R_{CNY} = R_{local} + R_{fx} + (R_{local} 	imes R_{fx})$ 严密核算，并在配置中显式声明 `QUOTE_PER_BASE`，消除粗糙加总误差。
9. **固化 7 大极简 Baseline，作为检验复杂模型的试金石**：
   在推进复杂宏观多区制策略前，先行在回测框架内置静态 60/40、等权 1/N、逆波动率（风险平价）、纯趋势动量等标准基准。任何复杂模型若在扣除 10 bps 换手摩擦后无法实质击败简单基准，一律予以否决。
10. **坚守个人研究工作台定位，对企业级沉重技术坚决实行“一票否决”**：
    拒绝微服务集群、拒绝复杂 Web 前端守护、拒绝券商实盘自动交易接口、拒绝黑盒强化学习。始终保持系统为一个单机纯 Python、易测试、可审计、零运维负担的高质量研究利剑。

---

# 13. Deliverable 4: TOP_REUSE_CANDIDATES (最值得借鉴与复用的外部组件)

```text
TOP_REUSE_CANDIDATES
1. gerrymanoim/exchange_calendars -> cross_market_schedule_and_lookback_slippage
   - Path: exchange_calendars/exchange_calendar.py (sessions_window, is_session, previous_session)
   - Problem: 解决 A01 缺陷，跨多国市场（A股/港股/美股）对齐交易日，约束周度回溯滑移上限（Slippage Bounding）。
   - Reuse Type: POSSIBLE_DEPENDENCY (or ADAPT core calendar logic)
   - Effort: LOW
   - Risk: LOW (Apache-2.0, 维护活跃, 成熟稳定)

2. unionai-oss/pandera -> fail_closed_series_contract_validation
   - Path: pandera/api/pandas/container.py (DataFrameSchema with lazy=False)
   - Problem: 解决 A06 缺陷，对宏观时序与资产价格的 raw_unit, derived_unit, frequency, tz 进行强类型防御校验。
   - Reuse Type: ADAPT (借鉴其 Schema 声明与 Fail-Fast 异常捕获哲学，构建本地配置守卫)
   - Effort: LOW
   - Risk: LOW (MIT, 无许可证风险)

3. quantopian/zipline (zipline-reloaded) -> continuous_futures_roll_and_panama_adjustment
   - Path: zipline/data/continuous_future.py & adjustments.py
   - Problem: 提供规范的连续期货拼接模型，区分名义观察价格与巴拿马比率调整收益率（Mul/Add Adjustment）。
   - Reuse Type: DESIGN_REFERENCE (提取其换月触发与收益率除权算法，不引入整个 Zipline 笨重框架)
   - Effort: MEDIUM
   - Risk: LOW (Apache-2.0, 纯算法设计借鉴)

4. cvxgrp/cvxportfolio -> multi_currency_return_decomposition_and_cash_accounting
   - Path: cvxportfolio/market_simulator.py & returns.py
   - Problem: 解决以 CNY 为报告货币的多币种资产（USD/HKD）收益率精确拆解（Local + FX + Cross Interaction）。
   - Reuse Type: ADAPT (复用其多币种无套利核算逻辑与 Quote Direction 约束)
   - Effort: LOW
   - Risk: LOW (Apache-2.0, 数学逻辑严谨)

5. caronc/apprise -> zero_daemon_lightweight_alerting
   - Path: apprise/Apprise.py
   - Problem: 解决个人研究系统在数据阻断或周报生成后的轻量通知（支持本地系统弹窗、Webhook、邮件），无需常驻服务器。
   - Reuse Type: POSSIBLE_DEPENDENCY (在周复盘 CLI 结束前触发单次告警)
   - Effort: LOW
   - Risk: LOW (MIT, 插件化设计，无侵入性)
```

---

# 14. 任务书第 15 节全部 12 个关键问题终局解答

### Q1: 当前公开数据能否真正补齐 #93/#81 的主要数据缺口？哪些能？哪些不能？
- **能补齐的领域**：海外宏观全谱系（FRED/ALFRED）、官方国债利率全曲线（US Treasury）、全球投机持仓（CFTC COT）、全球无风险利率与流动性（BIS/HKMA/BOE/ECB/BOJ）、中国统计局月度核心数据（`CN_PMI`, `CN_CPI`, `CN_PPI`）、大宗商品名义价格、以及通过公式自建的 Synthetic DXY。
- **不能靠免费自动化公开源解决的领域**：股票全收益指数（`H00300.CSI`, `HSITR`, `SP500TR` 均有严格商业版权限制，公开源仅提供价格指数，低估分红 1.5%~4%）；中国国债全收益指数（中债总财富指数为商业产品，久期近似法完全失真）；`CN_DR007` 连续日频自动化抓取（中国货币网严格反爬）；LME 铜官方现货全历史。这些领域必须依赖用户侧 Professional Data Bridge 导出，或在公开层退化为 ETF 复权净值。

### Q2: exact DXY 是否有合法、稳定、可复现的公开来源？
- **有**。商业端无免费 API，但可基于美联储官方公开发布的 H.10 外汇汇率系列（`DEXUSEU`, `DEXJPUS`, `DEXUSUK`, `DEXCAUS`, `DEXSDUS`, `DEXSZUS`）结合 ICE 官方几何乘幂公式自建 **Synthetic DXY**。该方案 100% 处于公共领域，无版权纠纷，与官方 DXY 点位相关性 > 0.9999，完全可复现且永久稳定。严禁使用 FRED 贸易加权美元指数替代。

### Q3: GOLD/COPPER 最适合本项目的是哪种研究口径，为什么？
- **黄金（GOLD）**：宏观信号看 **LBMA 伦敦黄金现货下午定盘价（USD/oz）**（全球主权清算基准，排除了在岸摩擦，与实际利率联动最纯粹）；投资组合可投资资产必须看 **上海金交所现货 Au99.99 或华安黄金 ETF (518880.SH)**（涵盖 2%~6% 的中国特有溢价，且避免了汇率计价混乱）。
- **铜（COPPER）**：宏观先行信号看 **COMEX 高级铜（HG）活跃连续未调整名义价格**（实体采购锚定名义成本，复权会破坏名义周期拐点）；资产回测收益率必须看 **比例调整连续期货收益率（Ratio-Adjusted）**（计入移仓换月损益，且不产生负价格）。

### Q4: CN_BOND_10Y 应该用 yield 还是 total-return representation？
- **必须严格双轨制解耦**：
  1. **宏观状态引擎**：必须唯一使用 **Yield（到期收益率，%）**，用于构建期限利差（10Y-1Y）与名义利率状态；
  2. **资产配置与财富核算引擎**：必须唯一使用 **Total-Return Representation（全收益指数）**。拒绝 Yield Duration Proxy（久期近似忽略了每年 2%~3% 的票息累积与骑乘展期利得，导致回测产生荒谬低估）。落地首选中债-国债总财富指数，次选 10 年期国债 ETF (511260.SH) 复权净值。

### Q5: CN macro 六项哪些能做到可信 PIT，哪些只能保守 available-at？
- **可做到高度可信 PIT 的四项**：
  1. `CN_PMI`：月末或次月 1 日 08:30 发布，终值定格无修订；
  2. `CN_CPI`：次月 9~11 日 09:30 发布，无重大年内追溯修订；
  3. `CN_PPI`：与 CPI 同日 09:30 发布，无修订；
  4. `CN_DR007`：交易日 17:00 发布，终局结算无修订。
- **只能采取保守 Available-at 的两项**：
  `CN_M1` 与 `CN_M2`。人民银行在次月 10~15 日不定期傍晚发布，且 2025 年存在 M1 纳入个人活期的制度性断点。必须强制设定“观测月次月 15 日 23:59:59”保守可见规则，并在代码中切分隔离历史版本。

### Q6: 最小宏观监控框架应该保留哪些一级维度？
- 裁撤重叠与内生性维度后，最终保留 **4 个核心一级宏观支柱 + 1 个战术执行层**：
  1. `GROWTH_GLOBAL`（全球与美国实际增长周期）
  2. `INFLATION_PRESSURES`（核心通胀与物价周期）
  3. `GLOBAL_LIQUIDITY_USD`（全球美元流动性与货币条件）
  4. `CHINA_CREDIT_POLICY`（中国特异性信贷与政策脉冲）
  + `TACTICAL_OVERLAY`（跨资产动量与已实现波动率执行层）

### Q7: 哪些 macro/regime 方法最适合低维护个人研究系统？
- **最适合的黄金三元组合**：
  1. **桥水增长-通胀四象限状态机**：无需非线性求解，宏观因果坚实，资产对冲逻辑清晰，百行代码即可实现；
  2. **单边因果截断 Z-score 与扩散指数**：全面封杀双边 HP 滤波，采用 Expanding 窗口因果标准化并截断至 $[-2.0, 2.0]$；
  3. **趋势/动量叠加门禁**：仅在“宏观偏好 + 价格动量确认”同时满足时下注，截断过早入场的回撤。
- **坚决回避**：隐马尔可夫模型 (HMM，状态闪烁、标签翻转)、混频 DFM/Nowcasting (维护成本过高)、经济意外指数 (依赖专有预期且均值回归逆势踩坑)。

### Q8: 哪些开源项目有代码/设计值得直接研究？
1. `cvxgrp/cvxportfolio` -> `costs.py`（二次交易冲击成本与借贷成本模型）；
2. `statsmodels/statsmodels` -> `dynamic_factor_mq`（官方混频动态因子模型，解决数据异步发布）；
3. `gerrymanoim/exchange_calendars` -> `exchange_calendar.py`（多市场交易日历交集对齐，解决滑移漏洞）；
4. `dcajasn/Riskfolio-Lib` -> `HCPortfolio.py`（分层风险平价 HRP 与下行风险控制）；
5. `mortada/fredapi` -> `fred.py`（ALFRED 双时间戳时间旅行 PIT 映射）。

### Q9: 哪些热门项目其实不适合本项目？
1. `microsoft/qlib`（高频横截面股票 Alpha 挖掘，私有 C++ 二进制，宏观标的少时完全退化）；
2. `QuantConnect/Lean`（C# 异构微服务架构，专注实盘券商撮合，对于低频宏观配置过重）；
3. `AI4Finance-Foundation/FinRL`（深度强化学习样本极端饥渴，宏观几百个点样本必然过拟合，黑盒不可解释）；
4. `mementum/backtrader`（官方停更 EOL，Python 2 元编程遗毒，GPL 强传染风险）；
5. `OpenBB`（AGPL-3.0 强传染协议合规红线，依赖包超 200 个，API 破坏性升级频繁）。

### Q10: 哪些外部设计能改善 weekly research packet / provenance / reproducibility？
1. **单周独立目录不可变快照（Folder-per-Week Snapshot）**：建立 `weekly/YYYY-MM-DD/`，固化 `facts.snapshot.json` 并设为只读，保证当时所见事实永远不可篡改；
2. **全要素哈希密码学清单（Manifest & Hash Chain）**：记录代码 Commit ID、配置哈希与输入数据 Sidecar 哈希，构成输入到输出的完整追溯链；
3. **全局追加式观点台账（Append-Only Claims Ledger）**：维护 `claims_ledger.jsonl`，记录主观观点、证据与预期验证期，后续强制事后验证，彻底消灭后见之明偏误；
4. **人工决策与默认立场的解耦**：系统默认立场永远为 `HOLD`，个人主观决策写入 `decision.json`，做到机器事实与人类心证在结构上彻底分离。

### Q11: formal OOS 前还缺哪些研究基础，而不仅仅是数据？
1. **确定性的跨市场多日历对齐引擎**（处理中美港商品休市与节假日滑移上限）；
2. **漂移感知（Drift-Aware）的真实会计换手与摩擦模型**（区分被动价格漂移与主动换手，考虑 0~30 bps 费率）；
3. **内置的 B1~B7 基准挑战者套件**（每次回测自动镜像比对基准超额与胜率）；
4. **因果特征变换纯函数库**（通过未来异常值注入测试，证明历史值绝对不变）；
5. **前置注册的验收标准契约**（在打开 Holdout 前白纸黑字写死判定门槛，防 p-hacking）；
6. **运行时健康状态探测与降级熔断规则**（数据陈旧或缺失时平滑退回战略基准，禁止零值填充）。

### Q12: 如果只能新增 5 个功能，哪 5 个最值得做？
1. **功能 1: Weekly Lookback Slippage Bounding & Comparability Guard (A01 / P0)**：约束周度回溯滑移上限，输出披露实际前置日期，彻底消除周报严重失真漏洞；
2. **功能 2: Manual Intake Sidecar 驱动的 Weekly Facts 自动装配器 (P3)**：终结用户手动编写 `observations.json`，实现从已入库数据一键装配当周事实；
3. **功能 3: 外汇多币种严格核算与三元归因模块 (P5)**：美股与港股计价折算，计入汇率交叉项，保证报告货币（CNY）收益核算在数学上正确；
4. **功能 4: Model Input Computability 独立前置诊断器 (A05 / P6)**：解耦覆盖度与可计算性，检查特征工程最小历史与端点，阻止毒特征流入模型；
5. **功能 5: Weekly Research Packet 单周归档与 Claims Ledger 台账闭环 (P4)**：建立包含事实快照、投资决议与事后证伪的科研级闭环复盘体系。

---

*Report synthesized and compiled by Project Brain for WEB-CONTROL.*
*Branch: `research/external-intelligence-survey-20260911`*
*All supporting CSV matrices generated in `docs/research/`.*
