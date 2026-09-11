# Cross-Asset 外部情报研究交付验收与采用矩阵

- **Document type**: WEB-CONTROL research-adoption review
- **Review date**: 2026-09-11
- **Repository**: `yjiao4903-lang/cross-asset`
- **Reviewed branch**: `research/external-intelligence-survey-20260911`
- **Reviewed commit**: `f4b708e16cbbb38e3e4ce349a0d9641411614a62`
- **Parent / accepted-main-at-review**: `6c5f1a17a07facf63f1975dc19bf39bd68e2df62`
- **Authority**: WEB-CONTROL
- **Verdict**: `ACCEPT_WITH_CORRECTIONS / REFERENCE_ONLY / DO_NOT_MERGE_RAW`
- **Execution effect**: 本文是规划与验收记录，不自动 dispatch，不激活 #81，不解封 holdout，不改变 formal model weights / allocation / frozen research protocol。

## 1. 验收范围与事实状态

外部研究分支是当前 main 的直接单提交后继，未夹带代码修改。该提交只新增三份研究交付物：

1. `docs/research/CROSS_ASSET_EXTERNAL_RESEARCH_SURVEY_20260911.md`
2. `docs/research/CROSS_ASSET_DATA_SOURCE_MATRIX_20260911.csv`
3. `docs/research/CROSS_ASSET_OPEN_SOURCE_REPO_MATRIX_20260911.csv`

提交共约 573 行新增、0 删除。分支隔离做法正确，main 在研究阶段保持纯净。

总体结论：交付质量高，覆盖了任务书 R1-R8，对项目后续数据、宏观监控、基准设计、开源复用与个人工作台边界具有显著参考价值；但报告中若干结论被表述得过于确定，并存在至少一处许可证内部矛盾和数处数据语义/替代关系问题。故不能把该分支原样提升为 authoritative source contract、DATA_ACCEPTANCE evidence 或 formal research protocol。

## 2. 采用原则

本轮采用下列六档：

- `ADOPT_NOW`：方向与当前项目约束一致，可直接进入后续开发设计。
- `ADOPT_WITH_MODIFICATION`：核心思想正确，但参数、边界或实现方式需要 WEB-CONTROL 修正。
- `USE_AS_REFERENCE`：作为未来方案/代码设计参考，不自动新增依赖或改变 formal model。
- `DEFER`：价值存在，但现在做会偏离当前 real-data / trust critical path。
- `REJECT`：与项目轻量、可解释、PIT、研究纪律或维护成本明显冲突。
- `NEEDS_VERIFICATION`：外部报告给出结论，但证据不足或存在事实/法律/语义冲突，不能作为准入依据。

## 3. 高价值结论：直接吸收

### 3.1 `ADOPT_NOW` — Weekly 与用户可见真实性

接受：

- A01 lookback slippage 必须 bounded，输出 target date / actual prior date / slippage / comparability reason；超限为 `PARTIAL/NON_COMPARABLE`。
- A02 weekly `ADMITTED` 过度声明必须降级，至少改为 `PROVIDER_MATCHED`，后续再增加 exact source identity / contract matching。
- A03 placeholder/no-op CLI 不得 success；明确 `IMPLEMENTED / FIXTURE_ONLY / NOT_IMPLEMENTED`。
- Weekly Research Packet 与 append-only claims ledger 的总体方向。
- 默认 software HOLD 与人工 decision 必须结构分离。

修正：外部报告建议 `1w <= 10 calendar days`，该数值**不在本轮冻结**。应采用 configurable、series/market-aware tolerance，并用 A/HK/US 节假日和跨市场反例测试确定。`exchange_calendars` 是候选依赖，不是修复 A01 的前提条件。

### 3.2 `ADOPT_NOW` — A06 Macro Unit & Semantics Guard

接受把 A06 从“仅 pre-OOS”前移到近期低风险修复：

- 在 config/model-load 边界调用现有 unit-semantics resolver；
- `UNRESOLVED` / ambiguous raw semantics fail closed；
- 不重建第二套 metadata/admission 系统；
- 这是保护未来 CN macro Phase-2 数据进入模型的前置安全带。

### 3.3 `ADOPT_NOW` — A05 独立 computability 诊断方向

保持既有决策：

- 不修改冻结的 B07 PIT coverage 定义；
- 新增正交的 `MODEL_INPUT_COMPUTABILITY`；
- 检查 required lag、normalization history、return start/end endpoints、FX endpoints、component computability。

实施时间仍放在 formal combined-readiness / OOS 之前，不用为当前 weekly trust 修复提前扩张。

### 3.4 `ADOPT_NOW` — Baseline / complexity discipline

接受建立简单 challenger suite 的方向：

- static allocation
- equal weight
- inverse-vol / simple risk parity
- volatility-target overlay
- trend-only
- macro-only
- risk-only defensive

这些 baseline 用于证明复杂模型是否有增量价值，不用于“为了过关”调参。

重要修正：外部报告示例中的 `Calmar +30%`、`MDD < 15%` 等**不自动成为 formal OOS pass/fail gate**。任何新增阈值都必须在不利用 holdout 且不存在 outcome-driven tuning 的前提下另行冻结；不能因为已看过 development 结果而事后挑选门槛。

## 4. 数据域：接受方向，但不接受 proxy promotion

### 4.1 Equity total-return / bond total-return

外部报告正确强调：

- equity wealth accounting 应使用 total-return representation，而非 price-only index；
- `CN_BOND_10Y` 的 macro state（yield）与 portfolio wealth return（total-return representation）应解耦。

采用：`ADOPT_WITH_MODIFICATION`。

但 ETF adjusted close（如 SPY/IVV、2800.HK、510300.SH、511260.SH）只能作为**不同 instrument definition**或 PERSONAL_WEEKLY / exploratory reference，不能静默替代 formal #81 当前要求的 exact series。若未来要把 formal target 从 index 改成 ETF，必须显式改变 source/series contract，并在看 holdout 前重新冻结；不是“fallback”。

因此继续保持：

```text
NO_PROXY_SUBSTITUTION = TRUE
NO_SILENT_SOURCE_FALLBACK = TRUE
```

### 4.2 USD/CNY 与 HKD/CNY

接受：显式 quote direction、时间戳、报告货币核算以及

`R_reporting = R_local + R_fx + R_local * R_fx`

的精确复合关系。

但 FRED `DEXCHUS` 或三角交叉汇率不能被自动升级为 formal CFETS source 的同义替代。任何备用来源必须是独立 contract，明确 source identity / observation timestamp / availability / quote direction。

### 4.3 GOLD

接受“双轨思维”：macro nominal/reference price 与 investable/accounting return 不应混为一条 series。

需要修正：数据源矩阵把 `LBMA Gold Price PM` 与 FRED identifier `GOLDAMGBD228NLBM` 写在同一条记录；identifier 本身指向 AM fixing 命名，存在 AM/PM source-identity mismatch。当前 source availability/licensing 也需重新核实。因此 GOLD source contract 继续 `UNRESOLVED`，不得依据该表直接准入。

SGE Au99.99、黄金 ETF、LBMA fix、COMEX futures 都是不同经济对象；必须先冻结用户真正要测的 investable return definition。

### 4.4 COPPER / continuous futures

接受：nominal macro-price series 与 portfolio-return series 分开。

不接受报告中“比例调整连续序列天然准确捕捉 roll yield”的过强表述。对 formal accounting，必须明确：

- underlying contracts；
- roll trigger/date；
- roll execution assumption；
- back/ratio adjustment method；
- return construction；
- fees/slippage；
- source vendor continuous-series semantics。

只有“ratio-adjusted continuous price”这一标签不足以证明真实可投资 roll return。

### 4.5 China macro

接受方向：

- PMI/CPI/PPI 与 M1/M2/DR007 必须分别记录单位、release/available-at、source identity；
- M1 口径变更必须 version-aware；
- M1/M2 在无可靠发布时间归档时可使用预注册的 conservative available-at 规则；
- DR007 与 R007 严格区分。

修正：外部报告多处使用“零修订”“终局”“每天固定 17:00”等绝对措辞。正式准入时仍必须由实际 source evidence / immutable publication / conservative rule 证明，不把调研文字本身当 admission evidence。

## 5. 重大修正：Synthetic DXY 不能解除 formal DXY blocker

外部报告将 Synthetic DXY 描述为：

- `exact mathematical equivalent`；
- `100% legal/free`；
- 可追溯 `1973 to present`；
- 可直接解除 exact DXY blocker。

WEB-CONTROL **不接受以上结论作为 formal source decision**。

原因：

1. ICE 当前公开产品页面明确声明 US Dollar Index 的 formulation、components、weightings、values 和 methods of calculation 属于 ICE Data Indices 的专有权利，并声明未经其书面同意不得使用。因此不能由项目自行宣称“公式属于 public / 100% 无版权风险”。这是许可/法律事实待澄清问题，不作法律意见。
2. Federal Reserve H.10 系列是纽约中午 buying rates；ICE USDX 是连续交易指数，ICE futures settlement 也使用独立的 closing window。用 H.10 noon observations 套公式得到的序列最多是**formula-consistent point-in-time reconstruction**，不是 ICE 官方 exact index observation。
3. 报告使用 `DEXUSEU`（EUR/USD）却同时宣称当前六币种方案 `1973 to present`。欧元并不存在于完整的 1973-1998 历史期，因此该连续历史主张至少需要额外 predecessor-currency methodology 证明，当前交付没有提供。

控制结论：

```text
FORMAL_DXY_BLOCKER = STILL_OPEN
SYNTHETIC_H10_USD_BASKET = RESEARCH_CANDIDATE_ONLY
DO_NOT_LABEL_AS_EXACT_DXY = TRUE
```

如未来需要独立 H.10-derived USD basket，可作为新的派生研究指标，用全新名称和独立 contract；它不能在当前 formal #81 中静默替换 exact DXY。

## 6. 开源项目采用矩阵

### 6.1 `ADOPT_WITH_MODIFICATION`

- `exchange_calendars`：高价值候选；优先用于 session/calendar helper，但先比较“轻量 bounded-asof 实现”是否已足够，避免为 A01 引入不必要依赖。
- `fredapi`：已有项目自己的 FRED/ALFRED ingestion；只借鉴 API ergonomics / as-of abstractions，不为了包装层替换现有 immutable raw + evidence path。
- `Riskfolio-Lib`：可作为 benchmark/reference；当前 simple inverse-vol/risk-parity baseline 应尽量 native/simple，只有需要 HRP/NCO 等扩展时再考虑依赖。
- `PyPortfolioOpt`：同上，研究参考优先，不进入近期 critical path。
- `quantstats` / `empyrical-reloaded`：可作为 metric cross-check/reference；不让第三方 report package 成为 accounting authority。
- `marimo`：可选研究 UX，不进入当前 core dependency。

### 6.2 `USE_AS_REFERENCE`

- `cvxportfolio`：交易成本、约束与多期优化设计参考；**不复制源码、不直接作为近期依赖**。
- `zipline-reloaded`：连续期货/滑点设计参考，不引入整套事件框架。
- `LEAN`：连续期货与数据语义设计参考，不引入 C# runtime。
- `findatapy` / `bt` / `kedro`：借接口与 pipeline 思想，不重建框架。
- `statsmodels DynamicFactorMQ`：保留为未来研究候选；不因为调研推荐而把 DFM 提前变成 formal model。

### 6.3 `REJECT / DEFER`

近期继续不引入：

- FinRL / reinforcement learning；
- Qlib wholesale；
- broker/live-execution stacks；
- microservice-heavy platforms；
- large web runtime；
- HMM auto-allocation；
- enterprise-grade data platforms。

### 6.4 License correction

外部 repo matrix 正确把 `cvxportfolio` 标为 `GPL-3.0`，但主报告 `TOP_REUSE_CANDIDATES` 又把它写成 `Risk: LOW (Apache-2.0)`，两者自相矛盾。WEB-CONTROL 已以 upstream LICENSE 核验：当前 `cvxgrp/cvxportfolio` 为 GPL v3。

因此：

```text
cvxportfolio = DESIGN_REFERENCE_ONLY (for now)
COPY_SOURCE = FORBIDDEN
```

另：对 AGPL/GPL 的影响不能简单写成“pip install 就必然要求整个私有项目开源”。这是法律问题，具体义务取决于使用/修改/分发/网络提供等事实。为了个人项目低维护和未来可迁移性，本项目仍可采取更保守的工程政策：优先 permissive dependency，对强 copyleft 项目默认 design-reference-only。

## 7. 宏观监控逻辑的采用边界

外部报告提出：

- `GROWTH_GLOBAL`
- `INFLATION_PRESSURES`
- `GLOBAL_LIQUIDITY_USD`
- `CHINA_CREDIT_POLICY`
- `TACTICAL_OVERLAY`

作为 4+1 极简框架。

评价：结构清晰、适合个人工作台、值得长期吸收，但当前只能为 `USE_AS_REFERENCE / FUTURE_CHALLENGER`，**不能直接覆盖已经冻结的 formal research model**。

原因：当前 formal protocol 已经冻结且存在 sealed holdout；现在新增一级宏观支柱、阈值、资产映射或 regime-to-weight mapping，都属于模型定义改变。若要研究 4+1，应：

1. 在 PERSONAL_WEEKLY / exploratory monitoring 中先作为解释框架；
2. 记录独立版本与预注册 hypothesis；
3. 不使用 holdout 调整维度、阈值或权重；
4. 只有未来新的 research cycle 才可作为 challenger 与现有 formal model 比较。

可立即吸收的是方法纪律：因果/单边变换、避免 future leakage、低维、可解释、避免高参数模型。

对“HP Filter 全面禁止”的措辞作窄化：**formal causal/PIT path 禁止使用需要未来样本的双边平滑与未做 realtime reconstruction 的滤波输出**；不需要把所有离线描述性 HP/filtering 学术分析一概视为非法，只是它们不能进入当前 causal allocation evidence。

## 8. 对 `critical_unknowns=0` 的修正

不接受 `critical_unknowns=0`。

至少以下关键问题仍未权威解决：

1. exact DXY source / license / timing；
2. GOLD exact formal instrument / source / AM-PM identity / licensing；
3. COPPER continuous-futures roll and return semantics；
4. equity/bond formal series 与 ETF fallback 的身份差异；
5. China macro historical release timestamps / revision claims 的逐序列证据；
6. selected professional-export field names / units / actual sidecar contents（必须等真实用户文件）。

因此更准确状态是：

```text
RESEARCH_CANDIDATES = STRONG
FORMAL_SOURCE_CONTRACTS = PARTIALLY_UNRESOLVED
CRITICAL_UNKNOWNS = NONZERO
```

## 9. 修正后的路线

### P0 — Weekly Trust + Surface Truthfulness

- A01 bounded/comparable lookback；
- A02 provenance state naming；
- A03 CLI truthful exit semantics；
- duplicate report cleanup；
- A06 unit/semantics guard 可作为同批低风险 hardening。

### P1 — Source Contract Verification

在真实文件进入前只做必要的 contract preparation，不造数据：

- exact DXY 继续 unresolved；
- GOLD/COPPER formal definition；
- equity/bond exact identity；
- FX quote/timing contract；
- CN macro unit/release semantics。

### P2 — #93 Real Data Admission

按现有 Lane B：

`USER_MANUAL_DATA_EXPORT -> IMMUTABLE_RAW -> SHA/SIDECAR -> SEMANTIC_VALIDATION -> CANONICAL_IMPORT -> RESEARCH_ADMISSIBLE -> SANCTIONED_QUERY`

不重建 admission。

### P3 — Weekly Input Adapter

至少第一批真实文件跑通后，再从真实 sanctioned/manual outputs 设计 adapter，终结手工 `observations.json`。

### P4 — Weekly Research Packet

facts -> claims -> scenarios -> explicit human decision -> later evaluation。

### P5 — Return Accounting Completion

- exact FX；
- CNY reporting return；
- GOLD/COPPER explicit semantics；
- exact asset-return identities。

### P6 — Pre-OOS Scientific Hardening

- MODEL_INPUT_COMPUTABILITY；
- calendar/timezone alignment；
- simple baseline challenger suite；
- drift-aware turnover / cost sensitivity；
- no retroactive threshold tuning。

### P7 — ALFRED Durable Rebuild

standard collector chunk/resume/merge/dedup，保留 B07 已接受 evidence，不重开其结论。

### P8 — Combined Readiness Rebuild

从 accepted code/config + immutable evidence 重新生成权威 snapshot。

### P9 — Formal OOS #81

仅在所有既有 hard blockers 解决后一次性激活；holdout 继续 sealed。

## 10. 外部研究分支处置

当前分支处理：

```text
branch = research/external-intelligence-survey-20260911
commit = f4b708e16cbbb38e3e4ce349a0d9641411614a62
status = ACCEPTED_AS_EXTERNAL_RESEARCH_EVIDENCE
merge_authorization = NO
reason = valuable but contains non-authoritative / overclaimed source semantics and license inconsistencies
```

不要求删除分支。它作为“外部调研原始快照”保留最有价值。后续开发应引用**本文的 adoption decision**，而不是直接把外部报告中的 `USE/REJECT` 视为项目 contract。

如未来需要把外部报告纳入 main，应先做一版 corrected research artifact，至少修正：DXY、GOLD AM/PM、proxy/fallback status、continuous-futures semantics、cvxportfolio license、absolute revision/timing claims。

## 11. 当前控制状态

```text
WEB-CONTROL = ACTIVE
EXTERNAL_RESEARCH = DELIVERED / REVIEWED
GPT-DEV = IDLE
LOCAL-DEV-A = IDLE_DATA_WAITING
LOCAL-DEV-B = IDLE
#93 = REAL_DATA_WAITING
#81 = BLOCKED_NOT_READY_FOR_ACTIVATION
HOLDOUT = SEALED
CONTROL_MODE = DATA_FIRST + WEEKLY_TRUST + NO_BUSYWORK
```

本轮只完成外部研究验收与规划校准，不创建开发任务，不派活，不启动 OOS。
