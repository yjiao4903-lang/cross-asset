# Cross-Asset 外部情报搜集窗口任务规划

- **Document type**: External research intelligence brief
- **Prepared by**: WEB-CONTROL
- **Date**: 2026-09-11
- **Repository**: `yjiao4903-lang/cross-asset`
- **Target reader**: 可访问 GitHub、具备强搜索与资料发现能力的外部研究窗口
- **Mode**: READ-ONLY RESEARCH / NO CODE CHANGE / NO MERGE / NO ISSUE MUTATION
- **Purpose**: 为 Cross-Asset 项目补充外部高质量参考，不直接改变现有代码、研究协议、数据 admission 或 allocation。

---

## 1. 你的角色

你不是项目开发角色，也不是新的治理角色。你是一次性的 **External Research Consultant**。

你的任务是：

> 对数据源、宏观分析/监控逻辑、研究方法、开源量化与交易项目进行系统搜集、筛选、比较，并把真正值得 Cross-Asset 项目借鉴的内容提炼成结构化报告。

禁止：

- 不修改 `main`；
- 不创建或更新 Issue/PR；
- 不改 Schema/Contract；
- 不提交代码；
- 不主动启动数据采集；
- 不把外部项目直接复制进本仓库；
- 不因为资料看起来方便而建议 proxy substitution；
- 不把 backtest 漂亮当成项目采用依据。

你的输出只作为 WEB-CONTROL 的决策输入。

---

## 2. 开始前只读这些仓库内容

请先读取以下文件，避免脱离本项目现实做泛泛调研：

### Governance / current state

1. `AGENTS.md`
2. `docs/CURRENT_STATE.md`
3. `docs/audits/EXTERNAL_AUDIT_ADOPTION_ASSESSMENT_20260911.md`

### Data / research contracts

4. `docs/DATA_ACCEPTANCE_GATE.md`
5. `docs/DATA_AVAILABILITY_AND_SOURCE_STRATEGY_v1_20260909.md`
6. `docs/RESEARCH_PROTOCOL.md`
7. `docs/LIVE_CORE_8_REQUIREMENTS.md`
8. `config/return_accounting.yml`
9. `config/macro.yml`
10. `config/weekly_review.yml`
11. `config/personal_weekly_admission.yml`

### Key implementation surfaces

12. `src/cross_asset/ingestion/manual_intake.py`
13. `src/cross_asset/ingestion/fred_alfred_pit.py`
14. `src/cross_asset/ingestion/fred_alfred_staging.py`
15. `src/cross_asset/storage/queries.py`
16. `src/cross_asset/research/readiness.py`
17. `src/cross_asset/research/weekly_core.py`
18. `src/cross_asset/research/weekly_review.py`
19. `src/cross_asset/features/macro.py`
20. `src/cross_asset/engines/macro.py`

不要全文扫描所有历史 Issue/PR，除非为了验证某个具体结论确实需要。

---

## 3. 项目当前需要解决的现实问题

你的所有调研都应围绕以下问题，而不是追求“最先进”本身。

### 3.1 数据问题

项目正式研究仍缺/未完全解决的真实数据与语义包括：

#### Return / market series

- `CN_EQ_LARGE`
- `HK_EQ`
- `US_EQ`
- `CN_BOND_10Y`
- `GOLD`
- `COPPER`

#### FX

- USD -> CNY
- HKD -> CNY

#### China macro

- `CN_PMI`
- `CN_CPI`
- `CN_PPI`
- `CN_M1`
- `CN_M2`
- `CN_DR007`

#### Other

- exact DXY

特别需要解决：

- source identity；
- exact series definition；
- unit；
- frequency；
- timezone；
- release / availability timing；
- revision/vintage behavior；
- spot vs futures；
- continuous-futures roll/adjustment；
- FX quote direction；
- licensing/access restrictions；
- PIT suitability；
- whether public automated access is actually durable。

### 3.2 宏观监控问题

项目目标不是简单仪表盘，而是形成一个可以辅助资产配置与市场风格判断的研究系统。

需要回答：

- 哪些宏观维度真正值得长期监控；
- 每个维度最少需要哪些指标；
- 哪些指标是 leading / coincident / lagging；
- 哪些指标容易 revision；
- 怎样形成 regime / score，而不堆几十个高度共线变量；
- 怎样把宏观状态映射到 equity/bond/USD/gold/copper 等资产；
- 怎样区分结构性信息和短期噪音；
- 怎样保留研究可解释性。

### 3.3 开源项目借鉴问题

我们不缺“一个能回测的框架”，缺的是：

- durable data ingestion；
- vintage/PIT handling；
- semantic contracts；
- reproducible research；
- macro feature engineering；
- regime detection；
- simple but credible portfolio baselines；
- risk/accounting correctness；
- research journal / review workflow；
- low-maintenance personal deployment。

因此搜索量化/交易开源项目时，重点不是“谁功能最多”，而是“谁有值得局部借鉴的模块或设计”。

---

# 4. Workstream R1 — 全球数据源地图

请建立一份当前仍可访问、维护状态真实的数据源地图。

## 4.1 优先顺序

优先级：

1. 官方政府/央行/监管/交易所 API；
2. 官方 downloadable files；
3. 高可信国际组织；
4. 稳定的开源数据聚合；
5. 商业数据库文档，仅作为语义参考；
6. 非官方 scraping/网页接口仅作为最后参考，不作为默认正式源。

## 4.2 至少覆盖的机构/类别

请系统检查，而不是默认这些机构一定适合：

- FRED / ALFRED
- Federal Reserve / Treasury
- BLS / BEA
- CFTC
- BIS
- IMF
- World Bank
- OECD
- ECB
- BOE
- BOJ
- PBoC
- NBS China
- SAFE
- CFETS / NIFC 等可能相关官方来源
- HKMA
- Hong Kong exchanges/regulators where relevant
- major futures exchanges for gold/copper semantics
- index-provider public documentation for DXY/equity indices
- DBnomics and similar public aggregators

## 4.3 每个候选数据源必须记录

请至少给出：

| Field | Requirement |
|---|---|
| Institution/provider | 必填 |
| Exact dataset/series | 尽量到 series id |
| Official URL/API docs | 必填 |
| Asset/macro mapping | 必填 |
| Frequency | 必填 |
| Unit | 必填 |
| SA/NSA | 如适用 |
| Observation date meaning | 必填 |
| Release/available-at semantics | 必填 |
| Revision/vintage support | 必填 |
| Historical depth | 必填 |
| Access method | API/CSV/XLSX/manual |
| Authentication | none/key/account |
| Rate limits | 已知则写 |
| License/terms | 必填 |
| China accessibility concerns | 如有 |
| PIT suitability | HIGH/MEDIUM/LOW/UNKNOWN |
| Durability | HIGH/MEDIUM/LOW |
| Recommendation | USE / INVESTIGATE / REFERENCE_ONLY / REJECT |

不要只说“可通过某网站获取”。要尽量给 exact endpoint、series id、文档页、下载页或明确的 access path。

---

# 5. Workstream R2 — 当前真实数据 blocker 专项

这是最重要的数据调研部分。

对以下每个项目，至少给出 1 个首选方案 + 1 个备选方案；如果没有真正符合要求的公开方案，请明确写 `NO_GOOD_PUBLIC_SOURCE_FOUND`。

## 5.1 Return series

### `CN_EQ_LARGE`

研究：

- 哪个指数最适合作为中国大盘股研究代理；
- 指数 price / total return / net total return 有何差异；
- 能否公开、稳定、长期获取；
- 如果只能通过用户终端手工导出，需明确终端字段与 exact index identity。

### `HK_EQ`

同上，同时确认：

- HKD 计价；
- price vs total return；
- index methodology；
- FX translation requirements。

### `US_EQ`

重点比较：

- S&P 500 price / total return / other broad indices；
- FRED public series 与 official index-provider semantics 的差异；
- 是否适合 research proxy；
- 是否满足当前项目的历史深度与可维护性。

### `CN_BOND_10Y`

必须区分：

- 10Y government bond yield；
- bond total-return index；
- price proxy；
- 当前项目若需要 return series，yield 不等于 bond return。

给出最合理的 research representation 建议，但不要替项目直接决定 Contract。

### GOLD

必须单独比较：

- spot；
- London fixing/reference price；
- futures front month；
- continuous futures；
- ETF proxy。

重点研究：

- 哪种口径适合宏观 cross-asset research；
- total return / roll yield implications；
- public availability；
- USD->CNY translation；
- PIT/revision concerns。

### COPPER

必须重点研究：

- LME vs COMEX/CME；
- cash/spot vs futures；
- continuous-futures construction；
- back-adjusted vs non-adjusted；
- roll calendar；
- public licensing/data availability；
- macro signal用途与可投资 return proxy 的差异。

## 5.2 FX

### USD/CNY

比较：

- onshore CNY spot close；
- central parity fixing；
- CNH；
- FRED/official alternatives；
- quote direction；
- timezone/timing alignment。

### HKD/CNY

确认：

- 是否存在 stable direct series；
- 是否应通过 HKD/USD 与 USD/CNY 构造；
- 构造是否会引入额外 timing mismatch；
- direct vs triangulated evidence requirements。

只做研究建议，不允许 silent synthetic fallback。

## 5.3 CN macro

分别对：

- PMI
- CPI
- PPI
- M1
- M2
- DR007

回答：

- exact official series；
- raw level / YoY / MoM / index point；
- SA/NSA；
- release date；
- revision practice；
- earliest history；
- downloadable/API access；
- publication calendar；
- likely `available_at` rule；
- whether vintage history exists；
- if not, what conservative PIT treatment is academically defensible。

特别注意：中国宏观常见二次数据源可能把 level、同比、累计同比混在一起，必须明确。

## 5.4 DXY

确认：

- exact ICE U.S. Dollar Index definition；
- weights/methodology；
- public official access availability；
- FRED or other proxy 是否 exact match；
- license constraints；
- 若无法获得 exact DXY historical series，应明确“不能用类似 broad dollar index 冒充 DXY”。

---

# 6. Workstream R3 — 宏观监控框架扫描

请研究机构框架、学术框架、开源实现，最终形成一个适合个人长期维护的最小宏观监控架构建议。

## 6.1 候选一级维度

至少研究以下维度是否值得保留：

1. Growth / activity
2. Inflation
3. Liquidity / money / credit
4. Financial conditions
5. Rates / real rates / curve
6. USD / global dollar liquidity
7. Risk appetite / volatility
8. Global manufacturing / trade
9. China-specific credit & policy cycle
10. Commodity cycle
11. Earnings / corporate cycle
12. Positioning / flows（如果数据成本可控）

不要假设全部都应该进入最终模型。

## 6.2 对每个维度请回答

- 最小 2–5 个高信息量指标是什么；
- leading/coincident/lagging；
- 数据频率；
- revision risk；
- 标准化方法；
- 是否适合 level / change / z-score / percentile / diffusion；
- 是否需要趋势滤波；
- 是否和其他维度高度重复；
- 对 equities/bonds/USD/gold/copper 的经济传导链；
- 常见 false positive；
- 哪些指标“看起来专业但实际低增量”。

## 6.3 重点搜集的研究方法

至少评估：

- diffusion index
- dynamic factor model
- PCA/factor extraction
- Markov switching / regime models
- HMM（仅作为比较，不默认采用）
- yield-curve recession models
- financial conditions indices
- economic surprise indices
- credit impulse
- global liquidity measures
- inflation regime classification
- growth/inflation four-quadrant regimes
- trend/momentum overlay
- volatility/risk-state overlay
- Bayesian/nowcasting approaches

要求说明：

- 哪些适合本项目当前阶段；
- 哪些过度复杂；
- 哪些需要 proprietary data；
- 哪些可保持可解释与低维护。

---

# 7. Workstream R4 — 机构与学术宏观模型参考

不要只搜 GitHub。请搜官方/学术来源，特别是具有公开方法或代码的项目。

优先研究：

- FRED-MD / FRED-QD
- Federal Reserve nowcasting/dynamic-factor related public work
- Chicago Fed financial conditions / activity indicators
- New York Fed recession / nowcast / financial indicators
- Philadelphia Fed ADS 或相关高频 activity work
- yield-curve recession literature
- Sahm-rule type real-time recession indicators
- OECD CLI
- BIS global liquidity / credit cycle
- IMF / World Bank / OECD composite indicators
- academic cross-asset regime allocation research
- inflation-growth regime allocation
- trend + macro hybrid allocation
- risk parity / volatility targeting / defensive overlays

每个重要框架写：

- 原始 paper/document；
- implementation/code if any；
- input data requirements；
- real-time/PIT treatment；
- main strengths；
- main weaknesses；
- maintenance burden；
- what Cross-Asset should borrow；
- what not to borrow。

---

# 8. Workstream R5 — GitHub 开源量化/交易项目扫描

请进行**广搜 + 精筛**。

## 8.1 搜索规模

- 初筛不少于 50 个项目；
- 最终 shortlist 15–25 个真正有参考价值的项目；
- 不要用 stars 直接排名。

## 8.2 必须覆盖的项目类别

### Data / research platform

搜索：

- macro/economic data ingestion
- FRED/ALFRED/vintage data
- DBnomics clients
- point-in-time research data
- financial research notebooks/platforms

### Backtesting / portfolio research

搜索：

- multi-asset backtesting
- vectorized research
- portfolio construction
- risk parity
- factor allocation
- transaction cost models
- walk-forward / OOS research

### Econometrics / regime

搜索：

- macro regime detection
- Markov switching
- HMM finance
- dynamic factor model
- recession models
- financial conditions
- nowcasting

### Quant/trading frameworks

搜索并评估代表性项目，例如但不限于：

- Qlib
- Zipline / Zipline Reloaded
- Backtrader
- vectorbt
- bt
- Riskfolio-Lib
- cvxportfolio
- FinRL
- QuantStats / pyfolio / empyrical 类工具
- LEAN/QuantConnect 开源组件
- OpenBB 相关可复用部分

不要因为本清单出现就默认推荐；你可以找到更好的当前项目。

### Workflow / research reproducibility

搜索：

- reproducible research pipelines
- experiment tracking for quant
- data lineage/provenance
- research notebooks -> reports
- immutable data snapshots
- signal/claim journals

## 8.3 每个 shortlisted GitHub repo 必须记录

| Field | Requirement |
|---|---|
| Repo | `owner/name` |
| URL | 必填 |
| License | 必填 |
| Last meaningful activity | 必填 |
| Release cadence | 尽量 |
| Stars/forks | 仅背景 |
| Main language | 必填 |
| Test quality | HIGH/MEDIUM/LOW |
| Documentation quality | HIGH/MEDIUM/LOW |
| Dependency health | HIGH/MEDIUM/LOW |
| Architecture relevance | 必填 |
| Candidate modules/files | 尽量到路径/类/函数 |
| Reuse mode | COPY_NOT_ALLOWED / DESIGN_REFERENCE / ADAPT / POSSIBLE_DEPENDENCY |
| License risk | 必填 |
| Maintenance risk | 必填 |
| Fit for personal workbench | HIGH/MEDIUM/LOW |
| Recommendation | ADOPT_IDEA / INSPECT_CODE / DEPENDENCY_CANDIDATE / REFERENCE_ONLY / REJECT |

特别要求：

- GPL/AGPL/copyleft 项目必须明确许可风险；
- 不能默认把代码复制进本项目；
- 如果建议“借鉴”，尽量指出具体文件/模块，而不是整个 repo；
- 如果项目已停止维护或核心包依赖陈旧，必须标记；
- 如果项目设计高度企业化，不适合个人维护，也要降级。

---

# 9. Workstream R6 — 值得直接借鉴的工程模式

从所有外部项目中，不是找“大而全替代方案”，而是找局部模式。

重点回答：

1. 有无更好的 PIT/vintage API abstraction；
2. 有无 raw archive + metadata manifest 的简洁实现；
3. 有无 series contract/schema 设计值得参考；
4. 有无可靠的 calendar/as-of alignment；
5. 有无 continuous futures roll 语义实现值得研究；
6. 有无 FX conversion/accounting 设计值得借鉴；
7. 有无 regime/score engine 保持低复杂度的方法；
8. 有无 backtest baseline/benchmark 设计值得借鉴；
9. 有无 weekly research packet / research diary 类设计；
10. 有无低成本 dashboard/alerting 方案适合个人研究。

每个模式写清：

- source project；
- exact code/document reference；
- problem solved；
- why useful here；
- integration cost；
- license implications；
- whether worth opening a future Issue。

---

# 10. Workstream R7 — Benchmark 与策略复杂度控制

请搜集适合 cross-asset research 的简单 baseline 体系，用来约束未来模型复杂度。

至少研究：

- static strategic allocation；
- equal weight；
- risk parity；
- inverse volatility；
- volatility targeting；
- trend-only；
- macro-only；
- risk-only；
- simple growth/inflation regime；
- 60/40 或地区适配版本；
- diversified trend/carry/value reference implementations（只作研究参考）。

最终需要建议：

- 哪 4–8 个 baseline 足以判断复杂模型是否有增量；
- 用哪些 metrics；
- 如何考虑 turnover/cost；
- 怎样避免只看 Sharpe；
- 怎样看 robustness、drawdown、subperiod、regime dependency；
- 怎样保持 holdout discipline。

不要进行本项目的真实 OOS，也不要看 sealed holdout。

---

# 11. Workstream R8 — 最终 Gap Map

把外部调研映射回 Cross-Asset 当前项目，分为四类：

## A. `DO_NOW`

特征：

- 明显修复 correctness / reproducibility / data reality；
- 开发量低或中；
- 不依赖新架构；
- 不违反 frozen protocol。

## B. `DO_AFTER_REAL_DATA`

特征：

- 需要真实 manual intake/output 形状；
- 需要实际 CN/FX/commodity semantics；
- 现在做容易过度抽象。

## C. `PRE_OOS_ONLY`

特征：

- 只为 formal scientific readiness；
- 必须在 OOS 前冻结；
- 不应提前看 outcome。

## D. `DEFER_OR_REJECT`

特征：

- ML/AI 复杂度高但增量不明确；
- 自动交易/券商接入；
- 大型 UI；
- microservices；
- enterprise orchestration；
- license/maintenance 风险高；
- 与个人工作台目标不匹配。

---

# 12. 强制研究纪律

你的报告必须遵守：

```text
UNKNOWN != ZERO
MISSING != ZERO
NO_PROXY_SUBSTITUTION = TRUE
NO_SILENT_SOURCE_FALLBACK = TRUE
NO_ADMISSION_RELAXATION = TRUE
NO_GUESSED_SOURCE_SEMANTICS = TRUE
NO_OUTCOME_DRIVEN_TUNING = TRUE
```

如果资料不足，请写 `UNKNOWN` 或 `NEEDS_VERIFICATION`。

不要：

- 用网页转载替代官方定义；
- 用一个类似指数替代 exact DXY；
- 把 yield 当成 bond total return；
- 把 gold ETF 自动当成 gold spot；
- 把 front-month futures 自动当成 continuous return；
- 把 vendor convenience field 当作 PIT release time；
- 把 current revised macro history 当作 historical real-time vintages；
- 因为某 repo stars 很高就建议采用。

---

# 13. 搜索与证据要求

## 13.1 时间要求

以执行任务当天的最新信息为准。

对于 GitHub 项目，必须检查：

- current repo state；
- latest meaningful commit/release；
- open/closed maintenance signals；
- license；
- issue activity；
- docs freshness。

## 13.2 来源优先级

优先：

1. official docs/source repository；
2. academic paper / institution research note；
3. maintainers’ docs；
4. high-quality secondary analysis。

低质量 SEO 文章只能帮助发现线索，不能作为最终依据。

## 13.3 可验证性

重要结论尽量带：

- URL；
- repo path；
- paper DOI/arXiv/official publication；
- series ID；
- exact quoted terminology（只需短引用）；
- last checked date。

---

# 14. 最终交付格式

请最终输出以下文件/内容。若你的环境方便生成文件，可生成；否则直接用 Markdown 返回完整内容。

## Deliverable 1 — 主报告

建议文件名：

`CROSS_ASSET_EXTERNAL_RESEARCH_SURVEY_202609XX.md`

结构必须包含：

1. Executive Summary
2. Current Project Gap Map
3. Data Source Findings
4. Current Blocker Source Recommendations
5. Macro Monitoring Framework Survey
6. Academic/Institutional Models
7. GitHub Open-Source Landscape
8. Reusable Engineering Patterns
9. Benchmark/Complexity-Control Recommendations
10. DO_NOW / DO_AFTER_REAL_DATA / PRE_OOS_ONLY / DEFER
11. Key Risks / Licensing / Maintenance
12. Top 10 Recommendations to WEB-CONTROL

## Deliverable 2 — Data source matrix

建议文件名：

`CROSS_ASSET_DATA_SOURCE_MATRIX_202609XX.csv`

至少一行一个 exact dataset/series candidate。

## Deliverable 3 — GitHub repo matrix

建议文件名：

`CROSS_ASSET_OPEN_SOURCE_REPO_MATRIX_202609XX.csv`

包含全部 shortlist 15–25 个 repo。

## Deliverable 4 — Reuse shortlist

在主报告中单独列：

```text
TOP_REUSE_CANDIDATES
1. repo/module/path -> problem -> reuse type -> effort -> risk
2. ...
```

不要直接贴大段外部源码。

---

# 15. 最终答案必须回答的 12 个问题

1. 当前公开数据能否真正补齐 #93/#81 的主要数据缺口？哪些不能？
2. exact DXY 是否有合法、稳定、可复现的公开来源？
3. GOLD/COPPER 最适合本项目的是哪种研究口径，为什么？
4. CN_BOND_10Y 应该用 yield 还是 total-return representation？
5. CN macro 六项哪些能做到可信 PIT，哪些只能保守 available-at？
6. 最小宏观监控框架应该保留哪些一级维度？
7. 哪些 macro/regime 方法最适合低维护个人研究系统？
8. 哪些开源项目有代码/设计值得直接研究？
9. 哪些热门项目其实不适合本项目？
10. 哪些外部设计能改善 weekly research packet / provenance / reproducibility？
11. formal OOS 前还缺哪些研究基础，而不仅仅是数据？
12. 如果只能新增 5 个功能，哪 5 个最值得做？

---

# 16. 评价标准

WEB-CONTROL 会按以下标准评价你的研究：

```text
SOURCE_ACCURACY
SEMANTIC_PRECISION
CURRENTNESS
PIT_AWARENESS
LICENSE_AWARENESS
MAINTENANCE_REALISM
PROJECT_FIT
SPECIFICITY
ACTIONABILITY
NO_HYPE
```

高质量报告的特征不是链接多，而是：

> 能明确告诉项目“哪些值得借、借什么、为什么、何时做、代价是什么、哪些不要做”。

---

# 17. 推荐执行顺序

如果时间有限，优先级如下：

```text
R2 Current Data Blockers
-> R1 Data Source Map
-> R5 GitHub Open-Source Scan
-> R3 Macro Monitoring Logic
-> R6 Reusable Engineering Patterns
-> R4 Academic/Institutional Models
-> R7 Benchmark Design
-> R8 Final Gap Map
```

不要在前几小时大量阅读泛量化教程。优先解决项目已经明确存在的问题。

---

# 18. 返回给用户/WEB-CONTROL 时的简短状态格式

最终报告前可用：

```text
EXTERNAL_RESEARCH_COMPLETE
repos_screened=<n>
repos_shortlisted=<n>
data_sources_checked=<n>
official_sources=<n>
academic/institutional_models=<n>
critical_unknowns=<n>
```

随后给完整主报告与矩阵。

如果遇到资料无法确认，不要自行补猜；把 `critical_unknowns` 明确列出即可。
