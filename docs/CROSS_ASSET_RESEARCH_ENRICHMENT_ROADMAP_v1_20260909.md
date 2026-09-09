# Cross-Asset Research Enrichment Roadmap v1

**Repository**：`yjiao4903-lang/cross-asset`  
**文档目的**：为 Codex / ChatGPT / 其他开发型 LLM 提供后续研究体系扩展的统一技术与研究基线。  
**评估基线日期**：2026-09-09  
**评估时 main**：`1c9e6446acee73bad4958423f085bf604c4c7758`  
**状态**：`RESEARCH_ARCHITECTURE_GUIDANCE`，不是生产完成声明，也不代表任何新因子已通过 OOS 验证。  
**必须同时遵守**：根目录 `AGENTS.md`、`docs/DATA_ACCEPTANCE_GATE.md`、`docs/RESEARCH_PROTOCOL.md`、现有 PIT / accepted-observation / execution-timing / provenance 约束。

---

## 1. 一句话结论

当前项目的主要瓶颈已经不是工程框架，而是**研究信息密度显著落后于工程成熟度**。

现有系统在以下方面已经具备较好基础：

- Point-in-Time / `available_at` / `vintage_date`；
- 数据准入、provenance、raw archive；
- replay / walk-forward / execution timing；
- missing-aware score contract；
- CFTC、China leverage、risk-stress 的基础管线；
- DuckDB、研究协议、实验存储、可重建 artifact。

但当前实际可用于资产评分的经济信息仍高度集中在：

```text
Macro + Trend
```

而不是配置层名义上的：

```text
Macro + Trend + Valuation + Carry + Risk + Structure
```

后续开发的首要目标不是增加新闻、研报摘要或财经信息流，而是把系统升级为：

> **Cross-Asset Market State & Risk-Premia Research Engine**

即能够持续回答：

1. 当前是什么宏观状态？
2. 市场实际在定价什么？
3. 哪些资产有赔率，哪些只有趋势？
4. 当前最大的隐含风险敞口是什么？
5. 什么新证据出现时，应当改变当前判断？

---

## 2. 当前仓库审计结论

### 2.1 工程底座强于研究内容

当前资产池约为：

```text
CN_EQ
HK_EQ
US_EQ
CN_BOND
GOLD
COMMODITY
CASH
```

基础市场序列主要覆盖：

```text
CN_EQ_LARGE / CN_EQ_SMALL
HK_EQ
US_EQ
CN_BOND_10Y
US_GOV_10Y
US_REAL_10Y
GOLD
COPPER
DXY
OIL
USDCNH
```

这足以建立基础跨资产状态，但不足以支持高质量资产配置研究。

主要缺失：

- 完整利率曲线与利率分解；
- 信用利差体系；
- 真实 valuation 输入；
- 真实 carry 输入；
- 商品期限结构；
- 权益 market breadth；
- 系统性 positioning / flow；
- cross-asset covariance / correlation regime；
- risk-factor decomposition；
- 中国信用、流动性、估值、期货/期权等专业数据层。

### 2.2 现有六组件配置与实际可用信息不一致

当前 `config/allocation.yml` 声明：

```text
macro      0.25
trend      0.30
valuation  0.15
carry      0.10
risk       0.10
structure  0.10
```

但现有 `asset_signal_map` 主要只显式连接 `macro + trend`。

`valuation / carry / structure` 在没有可信输入时保持 `None`，这是正确的 fail-closed 行为；但当前 `score_asset()` 会对 available components 的权重重新归一化。

因此当只有 `macro + trend` 可用时，经济上等价于大致：

```text
macro: 25 / (25+30) ≈ 45.5%
trend: 30 / (25+30) ≈ 54.5%
```

这意味着系统可能在报告层表现为“六维框架”，但在有效评分层仍接近“Macro + Trend 双因子”。

### 2.3 P0 模型治理要求

在继续扩数据前，开发 LLM 必须先显式审查 missing-component policy。

不得未经研究验证直接改变现有行为，但必须新增或评估以下能力：

```text
effective_component_weights
missing_component_budget
component_coverage
research_grade
allocation_eligibility
```

建议比较两类策略：

**A. 当前策略**

```text
renormalize_available_components = true
```

**B. 保留声明权重策略**

缺失组件不自动把全部权重让渡给已存在组件，而是：

- 降低 score magnitude；或
- 降低 confidence / tactical tilt；或
- 达不到最低 component coverage 时只输出 research state，不进入 allocation。

任何变更必须通过 replay / walk-forward / OOS 研究，不允许仅凭直觉修改。

---

## 3. 目标研究架构：八个独立证据层

后续研究体系应拆为以下八层，避免 Macro 成为所有资产结论的唯一解释器。

| Layer | 核心问题 | 第一阶段状态 |
|---|---|---|
| Macro State | 经济增长、通胀、政策处于什么阶段 | 已有基础，需扩展 |
| Rates & Credit | 市场如何定价利率、通胀、期限与信用风险 | P0 新增 |
| Valuation | 当前价格相对基本面和替代资产是否昂贵 | P0 新增 |
| Carry | 假设价格不变，仅持有该资产能获得什么 | P0 新增 |
| Trend & Breadth | 趋势是否健康、是否广泛扩散 | 趋势已有，Breadth P0 |
| Positioning & Flow | 仓位是否拥挤、资金行为是否确认趋势 | 已开工，P1 扩展 |
| Stress & Liquidity | 风险是否正在从波动转向信用/融资/流动性压力 | 已开工，P0/P1 扩展 |
| Cross-Asset Risk | 组合真正押注哪些共同风险因子 | P0/P1 新增 |

原则：

```text
Macro = evidence source
Macro != commander of all assets
```

---

## 4. P0-A：Rates & Credit State

这是当前最高优先级研究缺口之一。

### 4.1 美国利率曲线

建议正式 canonical 化：

```text
US_EFFR
US_TSY_2Y
US_TSY_5Y
US_TSY_10Y
US_TSY_30Y
US_REAL_5Y      # source/license evidence permitting
US_REAL_10Y
US_BREAKEVEN_5Y
US_BREAKEVEN_10Y
US_TERM_PREMIUM_10Y
```

现有 `sources.yml` 已出现 EFFR、DGS2、DGS5、DGS30、T5YIE、T10YIE 等候选映射，应优先完成 acceptance / PIT / evidence，而不是重新发明来源。

### 4.2 派生利率结构

至少实现：

```text
US_2S10S = 10Y - 2Y
US_5S30S = 30Y - 5Y
US_CURVATURE = 2Y - 2*5Y + 10Y   # 如采用其他定义需冻结语义
REAL_RATE_CHANGE_20D
BREAKEVEN_CHANGE_20D
TERM_PREMIUM_CHANGE_20D
```

长期目标是把 10Y nominal yield 拆成：

```text
expected short-rate path
+ inflation compensation
+ term premium
```

禁止把“10Y 上升”直接解释为单一 hawkish / inflation / growth 信号。

### 4.3 信用利差

新增候选：

```text
US_IG_OAS
US_HY_OAS
US_HY_MINUS_IG
US_BAA10Y     # long-history shadow proxy，不能冒充 HY OAS
```

派生：

```text
level
20D / 60D change
rolling percentile
causal z-score
spread momentum
credit-vs-equity divergence
```

中国后续专业数据层建议：

```text
CN_AAA_GOV_SPREAD
CN_AAP_AAA_SPREAD
CN_LGFV_SPREAD
CN_POLICYBANK_GOV_SPREAD
CN_NCD_POLICY_SPREAD
```

### 4.4 第一阶段输出

```text
rates_state
curve_state
inflation_pricing_state
term_premium_state
credit_state
credit_confirmation
```

第一阶段不直接生成 BUY/SELL。

---

## 5. P0-B：Valuation Engine

当前 `valuation` 有权重但缺少可信输入，应优先从“空组件”变成可研究组件。

### 5.1 权益估值

每个主要权益资产至少建立：

```text
PE_TTM
PE_FORWARD       # 只有来源与 PIT 语义可证明时
PB
DIVIDEND_YIELD
EARNINGS_YIELD
```

候选 canonical：

```text
VAL_CN_EQ_PE
VAL_CN_EQ_PB
VAL_CN_EQ_EY
VAL_HK_EQ_PE
VAL_HK_EQ_PB
VAL_HK_EQ_EY
VAL_US_EQ_PE
VAL_US_EQ_PB
VAL_US_EQ_EY
```

### 5.2 历史相对估值

实现：

```text
3Y percentile
5Y percentile
10Y percentile
causal z-score
```

禁止用当前完整历史计算过去时点 percentile。

### 5.3 跨资产估值

必须优先加入相对无风险/实际利率的比较，而不是单独陈述“PE 高/低”。

示例：

```text
US_EY_MINUS_REAL10Y
CN_EY_MINUS_CN10Y
HK_DIVY_MINUS_BOND_YIELD
```

必要时再研究 ERP，但必须冻结：

- earnings 定义；
- forward / trailing；
- risk-free benchmark；
- currency；
- observation/revision/PIT。

### 5.4 第一阶段 Valuation Score

建议仅使用透明、单调、可解释的输入：

```text
absolute percentile
relative-to-bond spread percentile
cross-sectional relative valuation
```

不得第一阶段就用黑盒 ML 输出 valuation score。

---

## 6. P0-C：Carry Engine

Carry 是当前最值得补齐且最容易被误用的组件之一。

必须按资产类型分别定义，禁止统一写成 `carry = yield`。

### 6.1 Bonds

目标：

```text
income carry
+ roll-down
```

候选：

```text
CARRY_US_TSY_10Y
CARRY_CN_GOV_10Y
```

必须显式记录 duration、curve point、holding horizon。

### 6.2 FX

目标：短端利率差 / 可实现 carry。

候选：

```text
CARRY_USDCNH
CARRY_USDJPY
CARRY_EURUSD
```

第一阶段只实现数据语义可靠、资金利率可获得的货币对。

### 6.3 Commodities

商品 carry 不应使用 spot return 代替。

至少建立连续合约所需的：

```text
front contract
second contract
third contract
expiry
roll calendar
```

派生：

```text
term_structure_slope
annualized_roll_yield
backwardation_contango_state
```

### 6.4 Equity carry-like inputs

可研究：

```text
dividend yield
earnings yield
```

但应在报告中明确其为 carry-like / valuation-carry overlap，避免重复计权。

---

## 7. P0-D：Commodity Structure

当前 `COMMODITY` 主要使用 `COPPER` 作为 trend proxy，研究语义过薄。

禁止继续把：

```text
COPPER == COMMODITY
```

作为长期模型语义。

建议拆分：

### Energy

```text
WTI
BRENT
NATURAL_GAS
```

### Industrial Metals

```text
COPPER
ALUMINUM
ZINC
```

### Precious Metals

```text
GOLD
SILVER
```

Agriculture 暂可 P2/P3。

每类商品研究至少应尝试组合：

```text
spot/futures price trend
term structure
inventory (若 PIT/来源可靠)
relative strength
USD sensitivity
```

典型解释应区分：

```text
price up + backwardation deepening + inventory down
```

与：

```text
price up + contango deepening + inventory up
```

两者不得输出同一结构结论。

---

## 8. P0-E：Equity Breadth & Style

当前 style 只有 SIZE 基本可用，GROWTH / CYCLICAL / TECH 仍缺少完整语义。

### 8.1 Breadth

对 CN/HK/US 权益至少研究：

```text
pct_above_MA20
pct_above_MA60
pct_above_MA200
advance_decline
new_high_new_low
equal_weight_vs_cap_weight
sector_diffusion
index_concentration
```

### 8.2 Style axes

将 `config/factors.yml` 中空的轴补成可审计 pair：

```text
SIZE
VALUE_GROWTH
CYCLICAL_DEFENSIVE
TECH_BROAD
```

每一轴必须：

- 明确 lhs/rhs；
- 冻结指数/篮子定义；
- 保持 constituent/PIT 合法；
- 禁止使用当前成分股回填历史；
- 输出 relative return + relative breadth + valuation spread（如可得）。

### 8.3 Breadth 的角色

Breadth 第一阶段建议属于：

```text
structure
risk confirmation
trend quality
```

不应直接成为单独方向 alpha。

---

## 9. P0-F：中国 Macro / Credit / Liquidity 语义冻结

当前 CN CPI / PPI / M1 / M2 存在 raw semantic 未冻结的 fail-closed 状态。

这必须优先解决，不能长期以 `ambiguous_raw_semantics` 留在正式 Macro 维度中。

### 9.1 数据源优先级

对于中国专业数据，目标结构应逐步调整为：

```text
Wind / iFind / licensed professional source = Primary
Official exchange / PBOC / NBS = Validation / fallback / evidence
Public aggregators = Research-only fallback when semantically safe
```

不得静默使用 Yahoo / 社区镜像替代专业 Tier-1 canonical input。

### 9.2 中国宏观核心字段

增长：

```text
PMI
PMI_NEW_ORDERS
INDUSTRIAL_PRODUCTION
RETAIL_SALES
FIXED_ASSET_INVESTMENT
EXPORT_GROWTH
PROPERTY_SALES
PROPERTY_INVESTMENT
```

通胀：

```text
CPI
CORE_CPI
PPI
```

信用：

```text
TSF_STOCK_GROWTH
NEW_TSF
NEW_RMB_LOANS
M1
M2
M1_MINUS_M2
CREDIT_IMPULSE
```

流动性：

```text
DR007
R001
SHIBOR
NCD_YIELD
POLICY_RATE
MONEY_MARKET_RATE_MINUS_POLICY_RATE
```

### 9.3 Transform 标准

每个宏观序列优先考虑：

```text
level
momentum
acceleration
surprise      # 只有 consensus PIT 合法时
historical percentile
```

禁止只因 level 高/低直接映射方向。

### 9.4 Credit Impulse

允许作为中国慢变量，但禁止神化为单指标交易信号。

建议与：

```text
TSF/GDP
TSF growth
M1 acceleration
property financing
government bond financing
```

联合研究。

---

## 10. P1-A：Positioning & Flow

现有 CFTC 与 China leverage 基础方向正确，应继续沿现有 task/gate 推进，不重写管线。

### 10.1 CFTC 扩展候选

在已有 Gold / Copper / S&P500 / US10Y 基础上研究：

```text
NASDAQ
RUSSELL
WTI
USD index / major FX
EUR
JPY
US2Y
US5Y
US30Y
```

派生统一支持：

```text
net position
pct_open_interest
3Y rolling percentile
causal z-score
4W change
13W change
crowding score
```

### 10.2 中国 Positioning

在两融之外逐步研究：

```text
margin_balance / market_cap        # denominator 需 PIT 稳定
ETF net subscription/redemption
CFFEX basis
IF/IH/IC/IM positioning
options put_call
Southbound/Northbound only if disclosure/PIT remains legitimate
```

原则：

```text
positioning = crowding / confirmation / risk filter
positioning != automatic contrarian directional alpha
```

---

## 11. P1-B：Stress & Liquidity System

系统不应把 `risk` 等价于 realized volatility。

目标正交结构：

```text
Realized Vol
+ Implied Vol / Term Structure
+ Credit Stress
+ Funding / Financial Conditions
+ Positioning / Crowding
```

### 11.1 建议 benchmark

可评估接入：

```text
OFR Financial Stress Index
Chicago Fed NFCI
Chicago Fed ANFCI
```

它们首先应作为：

```text
external benchmark
model divergence diagnostic
research validation reference
```

不要求第一阶段直接进入 allocation score。

### 11.2 慢风险层

评估 BIS 数据：

```text
credit_to_GDP_gap
debt_service_ratio
total_credit
global_liquidity
```

这些变量应归入：

```text
structural_vulnerability
```

而不是短周期 market timing。

---

## 12. P0/P1：Cross-Asset Risk Engine

这是长期应与 Macro Engine 同等重要的核心模块。

### 12.1 相关性与协方差

至少实现候选：

```text
20D / 60D / 252D covariance
EWMA covariance
shrinkage covariance
20D / 60D / 252D correlation
average_pairwise_correlation
equity_bond_correlation
```

所有 estimator 必须仅使用 decision_time 之前的数据。

### 12.2 Correlation Regime

输出：

```text
correlation_level
correlation_change
correlation_percentile
diversification_state
```

重点识别：名义上多资产，但共同风险相关性突然上升。

### 12.3 Risk clustering

可参考成熟开源实现的思想，但不得无评估直接引入依赖。

候选方法：

```text
hierarchical clustering
HRP diagnostic
HERC diagnostic
NCO diagnostic
```

第一阶段可以只生成研究 artifact，不改变正式 allocation。

### 12.4 风险因子分解

目标从“资产权重”升级为“风险暴露”。

候选共同因子：

```text
GLOBAL_GROWTH
INFLATION
DURATION
USD
CHINA_GROWTH
LIQUIDITY
EQUITY_BETA
COMMODITY_BETA
```

系统最终应能够回答：

```text
组合有多少名义 CN_EQ/HK_EQ/COMMODITY
```

以及更重要的：

```text
组合有多少风险实际上来自 China Growth beta
```

### 12.5 风险指标

逐步研究：

```text
volatility
max drawdown
VaR
CVaR
CDaR
risk contribution
marginal risk contribution
scenario loss
```

复杂优化器不得先于风险语义、PIT 与 OOS 研究成熟。

---

## 13. Allocation 长期演进方向

当前 `score -> tactical tilt` 适合作为 v0.x 基线，不应贸然废弃。

长期可以研究：

```text
Signal / View
    -> Confidence
    -> Expected Return / Risk View
    -> Posterior / Constraint Layer
    -> Allocation
```

Black-Litterman 可以作为候选研究方向，因为项目已经拥有：

```text
score
confidence
```

两个有价值的契约。

但必须遵守：

1. 先保留现有 allocation 作为 benchmark；
2. 不将 score 随意线性解释成年化收益；
3. view uncertainty / confidence 必须校准；
4. 与现有 strategic weights、max tactical tilt 做严格兼容测试；
5. OOS 不通过则不进入 production allocation。

---

## 14. 不建议当前优先引入复杂 ML

当前问题不是“拟合能力不够”，而是经济输入维度仍不完整。

因此 P0/P1 阶段禁止把主要开发资源投入：

```text
Transformer alpha
RL allocation
LLM directional trading
large XGBoost feature soup
news sentiment as core allocation factor
```

可参考 Microsoft Qlib 的：

```text
Data -> Dataset -> Model -> Experiment -> Portfolio
```

研究工作流，以及 experiment recorder / data handler 思想；但不需要复制其完整 ML 栈。

本项目更应优先强化：

```text
Signal Registry
Experiment Registry
Factor Admission Gate
Research Artifact Reproducibility
```

---

## 15. Factor / Series Admission Contract

任何新增 series / feature / factor，在进入正式评分之前必须回答以下问题：

```text
1. Economic hypothesis
2. Canonical identity
3. Source / license / provider
4. observation_date / available_at / revision policy
5. Transformation semantics
6. Expected direction / monotonicity
7. Target horizon
8. Affected assets / expected interaction
9. Falsification test
```

建议新增机器可读 registry，例如：

```text
config/factor_registry.yml
```

示例：

```yaml
US_HY_OAS:
  economic_hypothesis: >-
    Rising high-yield option-adjusted spread represents higher compensation
    demanded for private credit risk and weaker risk appetite.
  role: [risk, credit_confirmation]
  target_horizon: [1w, 1m, 3m]
  direction:
    US_EQ: negative
    HK_EQ: negative
    CN_EQ: weak_negative
    CASH: positive
  transforms:
    - level_percentile
    - change_20d
    - change_60d
  falsification:
    - incremental_vs_macro_trend
    - drawdown_prediction
    - regime_stability
```

此示例仅为 contract 形式，不代表上述方向和窗口已经通过验证。

---

## 16. Factor Admission Gate

建议建立通用研究门禁，区别于 source/data acceptance。

### G0 — Specification

必须有：

- economic hypothesis；
- canonical id；
- source candidate；
- transform；
- horizon；
- falsification plan。

不得进入正式模型。

### G1 — Data Evidence

必须通过：

- source identity；
- license/permission；
- PIT/available_at；
- revision policy；
- raw archive；
- source health；
- acceptance registry。

仍不得进入正式 allocation。

### G2 — Feature Semantics

必须有：

- causal transform；
- missing semantics；
- unit tests；
- edge cases；
- no future leakage；
- deterministic artifact。

允许 shadow research。

### G3 — Shadow Research

至少比较：

```text
BASELINE
BASELINE + candidate factor
```

输出：

- multi-horizon behavior；
- turnover impact；
- regime stability；
- redundancy/correlation；
- failure cases。

不得因为单一 Sharpe 改善就晋级。

### G4 — OOS Qualification

通过预注册的 walk-forward / CPCV / embargo 测试后，才允许标记：

```text
RESEARCH_QUALIFIED
```

仍需保留 uncertainty。

### G5 — Allocation Eligible

只有满足：

- OOS 增量价值；
- 稳定性；
- 数据持续性；
- 可解释性；
- 交易成本后仍成立；
- 与现有组件无严重重复计权；

才允许：

```text
ALLOCATION_ELIGIBLE
```

任何 LLM 不得跳过 G0-G4 直接改 `component_weights`。

---

## 17. Research Evaluation：不只看 Sharpe

新增因子必须至少与以下基线比较：

```text
STRATEGIC_ONLY
MACRO_ONLY
TREND_ONLY
MACRO_TREND
CURRENT_FULL_MODEL
CURRENT_FULL_MODEL + CANDIDATE
```

建议评估：

```text
forward return conditional spread
rank / cross-sectional behavior where meaningful
drawdown avoidance
realized volatility change
Sharpe / Sortino / Calmar
turnover
transaction cost sensitivity
regime stability
parameter sensitivity
confidence calibration
correlation/redundancy with existing factors
```

小资产池下不要机械追求横截面 IC；应根据因子角色选择正确评价对象。

Risk / stress / positioning 因子可能更适合验证：

```text
drawdown probability
future realized vol
left-tail loss
risk-on confirmation failure
```

而不是平均收益。

---

## 18. Walk-Forward 与 CPCV

保留现有 walk-forward / PIT / execution timing 体系，不重写。

在其上可新增：

```text
purge
embargo
combinatorial purged cross-validation
```

用于检查候选 factor 是否只依赖某一条历史路径。

任何新增 CV 机制必须输出可重建 manifest，禁止 sklearn 风格随机打散时间序列。

---

## 19. 推荐代码/配置结构

以下是建议目标，不要求一次性全部创建。

### Config

```text
config/valuation.yml
config/carry.yml
config/credit.yml
config/breadth.yml
config/commodity_structure.yml
config/risk_factors.yml
config/factor_registry.yml
```

### Features

```text
src/cross_asset/features/valuation.py
src/cross_asset/features/carry.py
src/cross_asset/features/credit.py
src/cross_asset/features/breadth.py
src/cross_asset/features/curve.py
src/cross_asset/features/commodity_structure.py
src/cross_asset/features/risk_factor.py
```

### Engines

```text
src/cross_asset/engines/valuation.py
src/cross_asset/engines/carry.py
src/cross_asset/engines/credit.py
src/cross_asset/engines/structure.py
src/cross_asset/engines/cross_asset_risk.py
```

### Reports

```text
market_state
risk_premia_state
market_behavior
structural_risk
portfolio_risk_exposure
supporting_evidence
contradicting_evidence
no_material_change
```

禁止创建大量重复 engine；优先复用现有 contracts、normalization、PIT、storage、research protocol。

---

## 20. 输出层目标：禁止演变为财经新闻推送

默认日报/周报不应以新闻列表为核心。

目标结构：

### 20.1 Market State

```text
Growth
Inflation
Liquidity
Policy
Credit
Financial Stress
```

每个状态包含：

```text
level
change
direction
confidence
source coverage
```

### 20.2 Risk Premia

```text
Equity Valuation
Bond Carry
FX Carry
Commodity Carry
Credit Compensation
```

### 20.3 Market Behavior

```text
Trend
Breadth
Credit Confirmation
Positioning
Correlation Regime
```

### 20.4 Structural Risk

```text
Credit Gap
Debt Service
Global USD Liquidity
Concentration
Diversification Breakdown
```

### 20.5 Portfolio Implication

每个资产必须同时显示：

```text
score / state
confidence
supporting evidence
contradicting evidence
missing evidence
next falsification trigger
```

如果没有显著变化，允许且鼓励：

```text
NO MATERIAL CHANGE
```

禁止为了日报可读性而人为制造观点变化。

---

## 21. 明确禁止事项

后续开发 LLM 必须遵守：

- 不以“信息越多越好”为原则堆数据；
- 不把新闻聚合升级为核心功能；
- 不让 LLM 新闻情绪直接进入 allocation score；
- 不把 `COPPER` 长期当作全部 `COMMODITY`；
- 不把 10Y yield level 解释为完整 Rates State；
- 不把 realized volatility 当作完整 risk state；
- 不把 CFTC 极端仓位自动转成反向交易；
- 不把融资余额单日变化自动转成方向 alpha；
- 不用当前指数成分股回填历史 breadth；
- 不用 revised macro 数据覆盖历史真实 vintage；
- 不让 fixture / synthetic data 满足 real-data gate；
- 不因单一 backtest Sharpe 提升修改 production factor weight；
- 不因存在开源库就未经 license/security/maintenance/API 稳定性评估直接引入；
- 不把不同语义的长期代理序列拼成一个“更长”的 canonical 历史；
- 不隐藏 missing component，不把 missing 自动解释为 neutral 0；
- 不在缺少数据持续性证据时宣称 LIVE READY。

---

## 22. 开源项目参考策略

开发复杂功能前，依 `AGENTS.md` 先做 reuse assessment。

优先研究但不默认依赖：

```text
Microsoft Qlib
Riskfolio-Lib
skfolio
PyPortfolioOpt
statsmodels / scikit-learn covariance utilities
```

重点借鉴：

- experiment registry；
- risk contribution；
- HRP/HERC/NCO；
- CVaR/CDaR；
- Black-Litterman；
- purged/embargo validation；
- shrinkage covariance；
- pipeline / estimator contract。

每个候选必须记录：

```text
reuse / adapt / self-build
license
maintenance activity
security/dependency cost
API stability
PIT compatibility
why it fits / why rejected
```

---

## 23. 推荐开发阶段

### Phase 0 — Model Semantics Audit

目标：确保现有六组件名义结构不会掩盖实际 Macro+Trend 集中。

工作：

- effective component weights artifact；
- missing policy benchmark；
- component coverage gate；
- baseline 固化。

### Phase 1 — Rates + Credit

优先完成：

- Treasury curve；
- breakeven；
- term premium（若 source/PIT 通过）；
- IG/HY credit；
- China credit candidate spec。

### Phase 2 — Valuation + Carry

优先让 `valuation`、`carry` 从长期 `None` 变成真实 research component。

### Phase 3 — Breadth + Style + Commodity Structure

补齐市场内部健康度和商品曲线。

### Phase 4 — Cross-Asset Risk

实现 covariance / correlation regime / clustering / factor risk exposure。

### Phase 5 — China Professional Data Backbone

正式启用经验证的 Wind / iFind 路径，逐步替换 manual / ambiguous semantic。

### Phase 6 — Allocation Research

只有前述组件通过 admission gate 后，才研究：

- component weight calibration；
- confidence-aware tilt；
- Black-Litterman candidate；
- risk budgeting candidate。

### Phase 7 — Text / Alternative Data

仅在结构化研究体系成熟后研究：

```text
central-bank text
news NLP
earnings calls
search trends
LLM interpretation
```

默认只做解释/annotation，不直接进入 allocation。

---

## 24. 推荐 PR 拆分

禁止一次 PR 把所有研究层塞入一个大改动。

建议：

```text
PR 1: model component coverage / effective-weight audit
PR 2: US rates curve + inflation pricing
PR 3: US credit state
PR 4: valuation foundation
PR 5: carry foundation
PR 6: equity breadth + style completion
PR 7: commodity curve foundation
PR 8: cross-asset covariance/correlation regime
PR 9: risk-factor decomposition research artifact
PR 10+: China professional data packs
```

每个 PR 必须有：

```text
scope
non-goals
canonical ids
source evidence
PIT policy
research role
unit/integration tests
artifact example
known limitations
gate reached
```

---

## 25. 开发 LLM 的执行模板

任何 LLM 准备实现本路线中的一个子任务时，先输出并记录：

```md
## Reuse assessment
- Problem:
- Official sources checked:
- Mature OSS checked:
- Reuse candidate:
- License/maintenance/security assessment:
- Decision: reuse / adapt / self-build

## Research contract
- Economic hypothesis:
- Canonical ids:
- Source/provider:
- PIT / available_at:
- Revision policy:
- Transform:
- Expected role:
- Target horizon:
- Falsification test:
- Current factor-admission gate: G0/G1/G2/G3/G4/G5

## Implementation scope
- Files to change:
- Tests:
- Artifacts:
- Out of scope:
- Production wiring allowed: yes/no
```

如果无法完整回答以上问题，不开始 production factor wiring。

---

## 26. 成功标准

本路线成功，不是指仓库增加更多 series 或更多页面，而是系统能够逐步做到：

```text
Market State
+ Risk Premia
+ Positioning
+ Financial Stress
+ Market Breadth
+ Cross-Asset Risk
+ Explicit Contradicting Evidence
+ Reproducible OOS Evaluation
```

最终目标不是回答：

> 今天市场发生了什么新闻？

而是回答：

> 当前市场状态、风险补偿、资金行为和共同风险因子分别是什么；哪些证据支持当前配置，哪些证据反对；如果下一条关键证据变化，应该重新评估什么？

这才是本项目应持续优化的核心参考价值。

---

## 27. 外部研究/工具候选（实现前必须重新核验官方文档）

以下仅作为后续开发检索入口，不构成依赖批准：

- Federal Reserve / FRED / ALFRED：宏观、Treasury、breakeven、credit series。
- New York Fed ACM Term Premia：Treasury term-premium decomposition。
- Chicago Fed NFCI / ANFCI：financial conditions benchmark。
- Office of Financial Research FSI：financial stress benchmark。
- BIS Statistics：credit-to-GDP gap、debt service、global liquidity。
- CFTC COT：positioning。
- SSE / SZSE / CSF / CFFEX：China leverage / futures evidence。
- Microsoft Qlib：research pipeline / experiment design reference。
- Riskfolio-Lib：risk measures / hierarchical allocation reference。
- skfolio：portfolio/risk/CV research reference。
- PyPortfolioOpt：Black-Litterman / optimization reference。

任何实现必须在当次任务重新检查官方文档、许可、数据可用性、PIT 和接口稳定性；不得把本列表视为长期不变的事实。
