# 开源项目可复用性评估报告（量化资产监控系统）

- 生成日期：2026-09-01
- 数据截点：2026-09-01（GitHub API / PyPI JSON / 官方文档当日抓取）
- 范围：与本项目"多资产量化监控 + 严格 PIT 数据纪律"相关的开源量化研究与回测框架、金融数据管线与数据治理工具
- 评估维度：许可证兼容性、维护活跃度、能力覆盖、数据边界适配性、依赖成本、安全风险

> 结论一句话：开源生态可"直接复用"的是**组合优化器、交易日历、报表指标库、FRED vintage API**四类成熟组件；可"适配集成"的是 **qlib 的 PIT 设计模式、Soda v4 数据契约引擎、zipline as-of 语义、DuckDB ASOF JOIN、vectorbt 参数扫描**；而本项目的差异化核心——**bi-temporal PIT 表模型、DATA_BLOCKED 准入状态机、evidence shadow 影子测试、provenance 运行级溯源**——在检索范围内无现成实现，属必要自研。

---

## 1. 执行摘要

| 结论 | 项目/组件 | 理由 |
|------|-----------|------|
| 直接复用 | exchange_calendars、DuckDB 1.5.x（ASOF JOIN）、fredapi、Riskfolio-Lib / PyPortfolioOpt、quantstats / ffn | 能力完全匹配、许可证宽松、输入输出与本项目 PIT 边界解耦 |
| 适配集成 | qlib（PIT 理念）、zipline-reloaded（as-of 语义）、Soda Core v4（准入检查引擎）+ soda-duckdb、vectorbt（扫描加速）、alphalens-reloaded（因子审核）、OpenBB（可选数据接入） | 功能方向对，但需写适配层对接 DuckDB canonical 层 |
| 必要自研 | PIT 表模型与查询层、准入状态机与证据链、evidence shadow 编排、provenance 采集层 | 18+13 个候选中无任何项目内建上述纪律，社区仅停留在"文档警告"层面 |
| 不引入 | backtrader（GPL+停滞）、bta-lib（已死）、nautilus_trader（过重）、LEAN（C#/Docker）、lakeFS（边界冲突）、yfinance（ToS 冲突）、Great Expectations（收购后不确定+重依赖） | 许可证传染、架构不匹配或数据纪律冲突 |

---

## 2. 方法与来源分级

- 来源分级：P0 = GitHub REST API / PyPI JSON 实时抓取；P1 = 官方文档；P2 = 社区综述与深度分析；未在本会话直读的数据标注 `[unverified]`。
- GitHub unauthenticated API 会话中部分仓库被限流，star/commit 数据以 PyPI JSON + P2 交叉佐证，逐项标注。
- 关键生态变化（本会话验证）：DVC 归属 Iterative → treeverse（Iterative 被 lakeFS 母公司收购）[[$TRAE_REF](https://github.com/treeverse/dvc)]；Great Expectations 被 Fivetran 收购，仓库迁移至 `fivetran/great_expectations` [ [$TRAE_REF](https://api.github.com/repos/fivetran/great_expectations) ]；dbt-core 主语言已迁移至 Rust [ [$TRAE_REF](https://api.github.com/repos/dbt-labs/dbt-core) ]；Soda Core v4 转为"数据契约引擎"并发布官方 `soda-duckdb` 数据源包 [ [$TRAE_REF](https://github.com/sodadata/soda-core) ]；exchange_calendars 迁移至个人维护者账号、PyPI 4.10（2025-03）后无新 release [ [$TRAE_REF](https://pypi.org/project/exchange-calendars/) ]。

---

## 3. 候选项目总览

### 3.1 量化研究与回测框架（18 项）

| 项目 | 仓库 | 最新版本（PyPI） | 许可证 | 维护状态 | 结论 |
|------|------|------------------|--------|----------|------|
| qlib | microsoft/qlib | pyqlib 0.9.7（2025-08） | MIT | 活跃（2026-07 push，47.9k stars）[ [$TRAE_REF](https://api.github.com/repos/microsoft/qlib) ] | 适配集成 |
| vectorbt | polakowo/vectorbt | 1.1.0（2026-07） | NOASSERTION 非标准 | 活跃 | 适配集成（先审许可证）[ [$TRAE_REF](https://api.github.com/repos/polakowo/vectorbt) ] |
| zipline-reloaded | stefan-jansen/zipline-reloaded | 3.1.1（2025-07） | Apache-2.0 | 社区维护 | 适配集成 |
| backtrader | mementum/backtrader | 1.9.78.123（2023-04） | GPL-3.0 | 停滞 | 不引入 [ [$TRAE_REF](https://api.github.com/repos/mementum/backtrader) ] |
| backtesting.py | kernc/backtesting.py | 0.6.6（2026-07） | AGPL-3.0 | 慢速 | 不引入（单资产/AGPL） |
| nautilus_trader | nautechsystems/nautilus_trader | 1.231.0（2026-08） | LGPL-3.0 | 非常活跃 | 不引入（执行系统过重）[ [$TRAE_REF](https://api.github.com/repos/nautechsystems/nautilus_trader) ] |
| OpenBB | OpenBB-finance/OpenBB | openbb 4.7.2（2026-05） | AGPL-3.0（GitHub 标注 NOASSERTION） | 活跃 | 可选备选 [ [$TRAE_REF](https://api.github.com/repos/OpenBB-finance/OpenBB) ] |
| bt | pmorissette/bt | 1.2.0（2026-04） | MIT | 慢速 | 适配集成 |
| ffn | pmorissette/ffn | 1.1.5（2026-03） | MIT | 慢速 | 直接复用 |
| quantstats | ranaroussi/quantstats | 0.0.81（2026-01） | Apache-2.0 | 年更 | 直接复用 |
| pyfolio-reloaded | stefan-jansen/pyfolio-reloaded | 0.9.9（2025-06） | Apache-2.0 | 年更 | 可选（与 quantstats 重叠） |
| Riskfolio-Lib | dcajasn/Riskfolio-Lib | 7.3.0（2026-05） | BSD-3-Clause | 活跃 | 直接复用 |
| PyPortfolioOpt | robertmartin8/PyPortfolioOpt | 1.6.0（2026-02） | MIT | 活跃 | 直接复用 |
| cvxportfolio | cvxgrp/cvxportfolio | 1.5.1（2025-07） | PyPI 标注 GPLv3（与仓库 Apache-2.0 记忆冲突） | 年更 | 引入前必须复核 LICENSE |
| bta-lib | bta-lib/bta-lib | 1.0.0（2020-03） | MIT | 已弃用 | 不引入 |
| LEAN | QuantConnect/Lean | 持续发布（C#） | Apache-2.0 [unverified] | 活跃 | 仅作架构对标 |
| alphalens-reloaded | stefan-jansen/alphalens-reloaded | 0.4.6（2025-06） | Apache-2.0 | 年更 | 适配集成（因子审核） |
| OptimalPortfolios | ArturSepp/OptimalPortfolios | [unverified] | [unverified] | 新项目，单源信息 | 待核 |

### 3.2 数据管线 / 数据治理工具（13 项）

| 项目 | 仓库 | 最新版本 | 许可证 | 维护状态 | 结论 |
|------|------|----------|--------|----------|------|
| Great Expectations | fivetran/great_expectations | [unverified] | Apache-2.0 | 活跃（被收购）[ [$TRAE_REF](https://api.github.com/repos/fivetran/great_expectations) ] | 备选，重依赖 |
| Soda Core v4 | sodadata/soda-core | v4.15.0（2026-06） | Apache-2.0 | 重构后活跃 | 适配集成（首选准入引擎）[ [$TRAE_REF](https://github.com/sodadata/soda-core) ] |
| dbt-core | dbt-labs/dbt-core | 持续发布 | Apache-2.0 | Rust 化进程中 | 适配集成（若走 SQL 转换层）[ [$TRAE_REF](https://api.github.com/repos/dbt-labs/dbt-core) ] |
| dbt-duckdb | duckdb/dbt-duckdb | 持续发布 | Apache-2.0 | 活跃 | 配套适配器 [ [$TRAE_REF](https://github.com/duckdb/dbt-duckdb) ] |
| DVC | treeverse/dvc | 3.67.1（2026-03） | Apache-2.0 | 活跃（已归 treeverse）[ [$TRAE_REF](https://github.com/treeverse/dvc) ] | 仅借鉴 provenance 理念 |
| lakeFS | treeverse/lakeFS | 持续发布 | Apache-2.0 | 近一年未动（2025-07 后）[ [$TRAE_REF](https://api.github.com/repos/treeverse/lakeFS) ] | 不引入 |
| qlib PIT DB | microsoft/qlib（PIT 组件 2022-03 发布） | 同 qlib | MIT | 活跃 | 借鉴设计模式 [ [$TRAE_REF](https://github.com/microsoft/qlib) ] |
| fredapi | mortada/fredapi | v0.5.2（2024-05） | Apache-2.0 | 维护缓慢 | 直接复用（vintage API）[ [$TRAE_REF](https://github.com/mortada/fredapi) ] |
| exchange_calendars | gerrymanoim/exchange_calendars | 4.10（2025-03） | Apache-2.0 | 维护放缓 | 直接复用（首选）[ [$TRAE_REF](https://pypi.org/project/exchange-calendars/) ] |
| pandas_market_calendars | rsheftel/pandas_market_calendars | 已冻结 | [unverified] | 停更 | 不引入 |
| DuckDB | duckdb/duckdb | 1.5.5（2026-07） | MIT | 活跃（25.9k+ stars）[ [$TRAE_REF](https://api.github.com/repos/duckdb/duckdb) ] | 直接复用（已服役）[ [$TRAE_REF](https://pypi.org/project/duckdb/) ] |
| OpenBB（ODP） | OpenBB-finance/OpenBB | 同 OpenBB | AGPL-3.0 | 活跃 | 可选 [ [$TRAE_REF](https://www.openbb.co/blog/openbb-releases-open-data-platform) ] |
| yfinance | ranaroussi/yfinance | v1.4.0（2026-05） | Apache-2.0 | 非常活跃 | 不引入生产 [ [$TRAE_REF](https://github.com/ranaroussi/yfinance) ] |

---

## 4. 分领域评估

### 4.1 量化研究与回测引擎

**qlib（microsoft/qlib）——研究范式最接近的框架**
- 内置 PIT 数据库：provider 时间对齐、快照/版本化，确保特征只使用当时可得数据 [$TRAE_REF](https://refft.com/en/microsoft_qlib.html)。
- 与本项目对照：PIT 内建能力是全部候选中唯一的系统级实现，与 available_at/vintage_date 纪律同源；但不提供 Market→Macro→Style→Asset Score→Allocation 五级链语义，也不支持多资产（股/债/现金）配置回测。
- 适配点：需自定义 provider 对接 DuckDB canonical 序列（12 序列 7 资产跨市场），qlib 自带 .bin/parquet 格式需写双向适配器。
- 风险：依赖面大（pyarrow/numba/sklearn/可选 LightGBM/Torch），核心贡献者集中 [unverified]，MIT 许可安全。

**zipline-reloaded —— PIT 语义与事件驱动真实性的参照系**
- 数据束（bundle）摄入管线 + PIT 数据处理防 look-ahead + Pipeline 跨截面因子 API。
- 复用点：PIT 数据束/as-of 语义可直接作为 DuckDB 层设计的对标基准；Pipeline 因子研究模式可供五级链 Market/Style 层参考。
- 代价：旧组件（bcolz 等）在 Windows + Python 3.12 上安装常出问题；公司行为调整时间戳的处理存在前瞻修正争议 [unverified]。

**vectorbt（v1.1.0）——参数扫描加速**
- Numba 向量化，万级参数组合秒级扫描，原生多资产/多策略矩阵，与 QuantStats 集成；v1 重写后 2026-07 发布 1.1.0（py>=3.11）[$TRAE_REF](https://github.com/jeff3388/awesome-backtesting-python)。
- 边界：无 PIT 概念，须从 DuckDB vintage 视图先物化"当时可得"DataFrame 再喂入；许可证 NOASSERTION 非 OSI 标准，引入前必须法务审阅。

**nautilus_trader / LEAN / backtrader / backtesting.py —— 不建议引入**
- nautilus_trader：Rust 内核事件驱动交易系统，日频 12 序列属过度设计，依赖成本（Rust 工具链）不匹配。
- LEAN：多资产算法框架分层（Alpha→Portfolio→Execution）与本项目五级链概念最接近，值得作架构对标，但引入需 C#/Docker 成本过高。
- backtrader：2021 后无实质维护，GPL-3.0 传染性许可证。
- backtesting.py：AGPL-3.0，单资产/单标的，多资产笨重。

### 4.2 组合优化与报表指标

- **Riskfolio-Lib**（BSD-3）：均值-方差/CVaR/Black-Litterman/HRP 全谱配置算法，输入仅收益/协方差，天然位于 PIT 边界之后 —— **直接复用**为 Allocation 层优化器。
- **PyPortfolioOpt**（MIT）：MVO/BL/HRP 经典实现，sklearn 风格，可作轻量基线（不引入 cvxpy 时）。
- **quantstats**（Apache-2.0）/ **ffn**（MIT）：tearsheet 与纯函数指标，直接服务 evidence shadow 报表生成。
- **alphalens-reloaded**（Apache-2.0）：因子 IC/分位数收益分析，若五级链 Asset Score/Market 打分需因子有效性审核，可作"因子维度"现成工具（适配集成）。

### 4.3 数据质量与准入（数据侧）

- **Soda Core v4（首选）**：YAML 数据契约（schema + 50+ 内置检查）、CLI/Python API 可嵌入管线、**官方 soda-duckdb 数据源包**原生支持嵌入式 DuckDB —— 作为数据准入检查的**执行引擎**，外部包装为本项目 Grade 分级与 DATA_BLOCKED 判定的一部分；不引入 Soda Cloud 即可本地执行 [$TRAE_REF](https://github.com/sodadata/soda-core)。
- **Great Expectations（备选）**：Expectations 声明式断言 + Data Docs + 支持 DuckDB 后端；但 v3→v4 API 破坏性变化、Fivetran 收购后路线不明、依赖重，仅作 Soda 备选 [$TRAE_REF](https://api.github.com/repos/fivetran/great_expectations)。
- **dbt-core + dbt-duckdb**：staging/mart 分层与项目 staging→canonical 结构同构，freshness 对应最新可用时间监控，manifest 可做溯源；但 dbt 无 PIT/禁 look-ahead 语义、无准入状态机，且引入即把 Python 数据层改造成 SQL 转换框架 —— 本阶段不建议（成本>收益），除非转换层规模扩大 [$TRAE_REF](https://api.github.com/repos/dbt-labs/dbt-core)[$TRAE_REF](https://github.com/duckdb/dbt-duckdb)。

### 4.4 PIT / vintage 数据管理（本项目核心关切）

- **检索结论**：开源生态中"内置 PIT 数据纪律"的框架极少且均不完整：qlib PIT DB 是唯一系统级实现；zipline-reloaded 提供 as-of PIT 基本面；其余全部框架把 look-ahead 防护视为用户责任，社区综述亦将 PIT 列为"关键陷阱"（look-ahead、生存者偏差、过拟合、成本滑点）[$TRAE_REF](https://github.com/jeff3388/awesome-backtesting-python)。
- **fredapi**：唯一一个把"某时点知道什么"（as-of queries）作为一等公民的开源库 —— `get_series_as_of_date` / `get_series_all_releases` / `get_series_vintage_dates` 与本项目 available_at/vintage_date 语义完全对齐，输出可直接映射为 vintage 证据；风险是维护近乎停滞（0.5.2 至今），建议薄封装固化语义 [$TRAE_REF](https://github.com/mortada/fredapi)。
- **DuckDB ASOF JOIN**：DuckDB 无内置 bi-temporal 特性，但原生支持 ASOF JOIN，PIT join 的实现基础已具备，属直接复用数据库能力 [$TRAE_REF](https://pypi.org/project/duckdb/)。
- **qlib PIT 设计模式**：原值+修订链+生效时间区间的概念模型可作为本项目 bi-temporal schema 设计的蓝本；其 A 股日历爬取思路（近期改为 baostock）可参考。

### 4.5 交易日历

- **exchange_calendars（直接复用，首选）**：50+ 交易所日历（ISO-10383 MIC 编码），含 XSHG（上交所）、XHKG（港交所）、XTKS、XNYS、CME 等；session 概念（is_session、sessions_window、date_to_session、previous_session）覆盖交易日判定与最新可用时间推算 [$TRAE_REF](https://pypi.org/project/exchange-calendars/)。
- 风险：最后 release 距今约 1.5 年维护放缓；未来假期公布滞后导致"预测性日历"缺口 —— 需自研假期公告落地流程或标记 PARTIAL；中国市场假日规则变化快，需比对交易所公告复核。
- 备选 pandas_market_calendars 已冻结，官方建议迁移 exchange_calendars。

### 4.6 Provenance 与数据版本

- **DVC**：文件/目录级哈希 + Git 绑定 + 管道依赖图，与本项目 model_runs 的 code_version/source_tree_hash/config_hash 理念一致但粒度不同（DVC 需远端存储，单机 DuckDB 项目引入额外运维面）——仅作运行级 provenance 记录设计参照，不引入 [$TRAE_REF](https://github.com/treeverse/dvc)。
- **lakeFS**：对象存储上的 Git 式数据版本控制，快照为表/目录级而非行级 vintage，需自托管 Go 服务 + S3 兼容对象存储，与嵌入式 DuckDB 边界冲突，维护放缓 —— 不引入 [$TRAE_REF](https://api.github.com/repos/treeverse/lakeFS)。

---

## 5. 需求逐项对照矩阵

| 本项目需求 | 最优候选 | 定位 |
|---|---|---|
| 五级链 Market→Macro→Style→Asset Score→Allocation | 无（LEAN 仅概念近似；qlib 覆盖因子/模型两环） | **自研**，qlib/LEAN 仅作职责切分参考 |
| 历史回测 replay | qlib（Experiment 回放）、bt（组合级 DSL） | 适配集成（自建 DuckDB 时点物化） |
| PIT（available_at/vintage_date） | qlib PIT DB / zipline as-of / fredapi vintage / DuckDB ASOF JOIN | **自研为主**，借鉴其模式 |
| evidence shadow 影子测试 | quantstats/alphalens（报表与因子审核） | 直接复用工具，自研对比编排 |
| DATA_BLOCKED 数据准入门槛 | Soda v4 契约引擎（执行层）、GE（备选） | 适配集成检查引擎 + 自研状态机 |
| provenance（code_version/source_tree_hash） | DVC（理念） | **自研**（当前已实现，持续加固） |
| 7 资产 12 条 canonical 日频序列 | 无框架内建跨市场 canonical 层 | 自研存储层 + 导出适配器 |
| 配置/Allocation 输出 | Riskfolio-Lib、PyPortfolioOpt | 直接复用 |
| 参数敏感性/阴影扫描加速 | vectorbt | 适配集成（先审许可证） |
| 交易日历/最新可用时间推算 | exchange_calendars | 直接复用 + 自研假期复核 |
| FRED/ALFRED vintage 采集 | fredapi | 直接复用（薄封装） |

---

## 6. 三分类落地清单

### 直接复用（引入依赖，零源码改造）
1. **exchange_calendars 4.10** —— 日历层唯一现成方案，Apache-2.0、轻依赖、含 A 股/港交所/主要市场；落 DuckDB 做日历维表。
2. **DuckDB 1.5.x + 官方核心扩展** —— 已服役；升级确认 1.5.5 与 Python 3.12 兼容；PIT join 用原生 ASOF JOIN，证据归档用 parquet 扩展。
3. **fredapi** —— 接入 FRED/ALFRED 时直接消费其 vintage/as-of API，薄封装保留语义。
4. **Riskfolio-Lib（或 PyPortfolioOpt 轻量基线）** —— Allocation 层优化器，输入收益/协方差，位于 PIT 边界之后。
5. **quantstats / ffn** —— evidence shadow 报表与指标计算。

### 适配集成（需写适配层）
1. **Soda Core v4（soda-duckdb）** —— 数据准入检查的执行引擎，YAML 契约描述必查项，外部包装为 Grade 分级与 DATA_BLOCKED 判定；不引入 Soda Cloud。
2. **qlib PIT 设计模式** —— 仅借概念模型（修订链+生效区间），不安装依赖，落入自研 schema。
3. **zipline-reloaded** —— 若追加基本面因子研究，其 PIT/as-of 与 Pipeline 为参照；Windows/Py3.12 生态成本高，需评估。
4. **vectorbt** —— 参数敏感性/阴影扫描加速；先解决许可证审阅（NOASSERTION）。
5. **alphalens-reloaded** —— 因子维度审核（Asset Score/Market 打分有效性）。
6. **OpenBB（含 ODP）** —— 仅在需要多 provider 标准化数据接入时引入；AGPL 内部使用可接受（对外 SaaS 才触发义务），其数据无 PIT 契约，仍需本项目自研层保证。

### 必要自研（无现成实现，本项目差异化核心）
1. **PIT 数据模型与查询层** —— bi-temporal（valid time + transaction time）表结构、available_at/vintage_date 判定、ASOF PIT join 封装、防 look-ahead 断言（跑批时校验引用时间戳）。qlib PIT 与 SQL temporal tables 均为概念等价、架构不匹配。
2. **数据准入状态机与证据链** —— DATA_BLOCKED/生产准入/采样审核流程编排、Grade A/B/C/D 分级规则引擎、审核记录与证据快照存储（与 model_runs provenance 联动）。
3. **evidence shadow 影子测试编排** —— 对比编排与门禁判定（可复用 quantstats/alphalens 做报表层，但编排逻辑自研）。
4. **provenance 采集运行层** —— 固化 code_version/source_tree_hash/config_hash 的采集时机与校验（当前已实现，持续加固）。

### 明确不引入
- backtrader（GPL 传染 + 停滞）、bta-lib（已弃用）、backtesting.py（AGPL + 单资产）、nautilus_trader（Rust 执行系统过重）、LEAN（C#/Docker 成本）、lakeFS（需服务端 + 对象存储，边界冲突，维护放缓）、yfinance（无 ToS 授权、无修订保证，与 DATA_BLOCKED 纪律冲突，仅可作非生产 demo 且必须打标 PARTIAL）、pandas_market_calendars（已冻结）。

---

## 7. 风险与依赖成本汇总

| 项目 | 依赖成本 | 安全/合规风险 |
|---|---|---|
| qlib | 高（pyarrow/numba/sklearn + 可选 lightgbm/torch） | MIT 无约束；核心贡献者集中，供应链面大需锁版本 |
| vectorbt | 中（numba 版本敏感） | 许可证 NOASSERTION 非标准 —— 引入前必做法务审阅；商业双轨 |
| zipline-reloaded | 高（旧 C 扩展、Windows 编译痛点） | Apache-2.0；社区维护无 SLA |
| backtrader | 低 | GPL-3.0 传染 + 停滞（安全更新缺位） |
| backtesting.py | 中（Bokeh） | AGPL-3.0（部署边界需审） |
| nautilus_trader | 高（Rust 工具链） | LGPL-3.0；活跃项目漏洞响应快 |
| OpenBB | 极高（数百依赖） | AGPL-3.0；主仓库开发迁移状态 [unverified] |
| Soda Core v4 | 轻-中（duckdb driver、pydantic） | Apache-2.0；v4 新架构稳定性待观察；Cloud 付费但本地可不用 |
| dbt-core + dbt-duckdb | 中-高（生态庞大） | Apache-2.0；Rust 迁移期接口变动 |
| DVC / lakeFS | 中-高（需远端存储/服务端） | Apache-2.0；运维面增大 |
| fredapi | 极低（仅 pandas） | Apache-2.0；维护停滞需薄封装 |
| exchange_calendars | 极低 | Apache-2.0；维护放缓，未来假期滞后风险 |
| Riskfolio-Lib / PyPortfolioOpt | 中（scipy/cvxpy） | BSD-3 / MIT，低风险 |
| quantstats / ffn | 极低-低 | Apache-2.0 / MIT，低风险 |
| cvxportfolio | 中（cvxpy） | PyPI 标注 GPLv3 与仓库 Apache-2.0 冲突 —— 需复核 LICENSE 后决定 |
| yfinance | 低 | Apache-2.0，但无 ToS 授权、数据可被限流/变更、无 vintage |

通用安全提示：候选框架均未发现已知严重 CVE 的公开证据 `[INSUFFICIENT DATA]`；主要风险是 PyPI 供应链与传递依赖，建议统一锁版本 + 依赖漏洞扫描。引入任何框架都不影响本项目"数据边界外置、Live 数据留证"的纪律——框架不接触本项目数据源。凭据管理遵守项目规则：仅从安全环境/忽略文件读取，不写入命令行参数。

---

## 8. 建议落地路线

| 阶段 | 动作 | 预期收益 |
|------|------|----------|
| 阶段一（低风险快赢） | 引入 exchange_calendars 物化日历维表；升级确认 DuckDB 1.5.x；接入 fredapi 后重跑 FRED/ALFRED vintage 采集 | 解决 CALENDAR_BLOCKED 与 FRED PARTIAL 两条阻塞 |
| 阶段二（准入与证据） | 以 Soda v4 契约为执行引擎包装 DATA_BLOCKED 状态机；Riskfolio/PyPortfolioOpt 接入 Allocation 层 | 数据准入自动化，Allocation 落地 |
| 阶段三（研究增强） | qlib PIT 模式落地自研 bi-temporal schema；quantstats/alphalens 生成 evidence shadow 报表；vectorbt（审许可证后）做参数扫描 | 研究范式与影子测试成熟 |
| 阶段四（远期） | LEAN/nautilus_trader 作为实盘执行层架构对标 | 预留升级路径 |

---

## 9. 与本项目现状的对接结论（2026-09-02 复核）

将上述评估与本项目实际代码逐一核对后，落地清单如下（全部以源码复核为准）：

### 9.1 日历层：依赖声明与代码存在错位（可立即修复）

- 现状：`src/cross_asset/operations/exchange_calendar.py` 已实现 `ExchangeCalendarAdapter`，`cn_hk_calendar()` 优先 `_load_exchange_calendars()`（即 exchange_calendars 的 XSHG/XHKG），失败才回退 `_load_pandas_market_calendars()`；缺失时抛 `CalendarBlockedError`，无 Mon-Fri 近似。
- 问题：`pyproject.toml` 依赖声明为 `pandas-market-calendars>=5.4,<6`（评估判定已冻结、官方建议迁移），**未声明 `exchange-calendars`**——代码首选的是未声明的第三方包，声明的是已被冻结的备选。
- 落地建议：`pyproject.toml` 增加 `exchange-calendars>=4.10`；部署环境安装后运行日历准入复检，推动 `CALENDAR_BLOCKED` 解除。exchange_calendars 4.10 含 XSHG/XHKG，为评估首选"直接复用"组件 [ [$TRAE_REF](https://pypi.org/project/exchange-calendars/) ]。

### 9.2 FRED 层：自研实现已覆盖 fredapi 价值，不引入依赖

- 现状：`src/cross_asset/providers/fred.py` 已自研 `FREDProvider`，直连官方 API，含 PIT 证据、重试与脱敏错误处理（`_safe_error` 对 API key 打码）。
- 结论：fredapi 的复用价值仅是"as-of/vintage 语义参考"；其维护近乎停滞（0.5.2，2024-05），引入依赖反而增加风险。当前自研实现方向正确，需复核 ALFRED 分支对 `realtime_start/realtime_end` 的语义处理是否等价 fredapi 的 `get_series_as_of_date`/`get_series_vintage_dates` [ [$TRAE_REF](https://github.com/mortada/fredapi) ]，此复核不依赖引入任何第三方包。

### 9.3 Allocation 层：自研逻辑保留，优化器作为增强项

- 现状：`src/cross_asset/engines/allocation.py` 自研 `allocate()`（strategic + tactical tilt，`tanh` 投影 + `bounded_projection` 约束求解），透明、可审计、确定性。
- 结论：当前不替换。Riskfolio-Lib/PyPortfolioOpt 的"直接复用"价值体现为**未来增强**（均值-方差/CVaR/HRP 等高级优化器），仅在需要超越 tilt 逻辑的优化能力时引入，且输入约束（收益/协方差）仍必须位于 PIT 边界之后。

### 9.4 yfinance：与数据纪律存在张力，需打标或隔离

- 现状：`src/cross_asset/providers/yahoo.py` 与 `src/cross_asset/providers/live.py` 已在用 yfinance（live 模块、chart endpoint fallback），且为可选导入。
- 结论：评估判定 yfinance 无 ToS 授权、无修订保证、无 vintage [ [$TRAE_REF](https://github.com/ranaroussi/yfinance) ]，与本项目 `DATA_BLOCKED` 边界存在张力。落地建议：live/yahoo 数据源必须显式打标 PARTIAL 且不得进入 production admission 通道，或将其隔离为演示通道；不得绕过准入状态机。

### 9.5 自研核心：方向已被评估确认为差异化价值

- `storage/provenance.py`（code_version/source_tree_hash/config_hash）、`pit/` 模块（asof/grades/release_mapping）、`ingestion/evidence_shadow.py`、`ingestion/acceptance.py`（准入）—— 评估确认这些"必要自研"项在开源生态中无现成实现，本项目已落地且纪律完整度高于主流 OSS 框架，继续保持自研、无需引入 DVC/lakeFS 等重量级方案。

---

## Sources

1. GitHub REST API：microsoft/qlib（2026-09-01）：https://github.com/microsoft/qlib
2. GitHub REST API：polakowo/vectorbt（2026-09-01）：https://github.com/polakowo/vectorbt
3. GitHub REST API：OpenBB-finance/OpenBB（2026-09-01）：https://github.com/OpenBB-finance/OpenBB
4. GitHub REST API：nautechsystems/nautilus_trader（2026-09-01）：https://github.com/nautechsystems/nautilus_trader
5. GitHub REST API：mementum/backtrader（2026-09-01）：https://github.com/mementum/backtrader
6. GitHub：fivetran/great_expectations（2026-09-01）：https://github.com/fivetran/great_expectations
7. GitHub：sodadata/soda-core（含 Releases，2026-09-01）：https://github.com/sodadata/soda-core
8. GitHub：treeverse/dvc（2026-09-01）：https://github.com/treeverse/dvc
9. GitHub：treeverse/lakeFS（2026-09-01）：https://github.com/treeverse/lakeFS
10. GitHub：mortada/fredapi（2026-09-01）：https://github.com/mortada/fredapi
11. GitHub：ranaroussi/yfinance（2026-09-01）：https://github.com/ranaroussi/yfinance
12. PyPI：exchange-calendars 4.10（2026-09-01）：https://pypi.org/project/exchange-calendars/
13. PyPI：duckdb 1.5.5（2026-09-01）：https://pypi.org/project/duckdb/
14. GitHub：duckdb/dbt-duckdb：https://github.com/duckdb/dbt-duckdb
15. GitHub：dbt-labs/dbt-core：https://github.com/dbt-labs/dbt-core
16. Awesome Backtesting Python（2026-04）：https://github.com/jeff3388/awesome-backtesting-python
17. Qlib 深度分析（refft.com，快照 2025-08-28）：https://refft.com/en/microsoft_qlib.html
18. OpenBB 官方博客——Open Data Platform：https://www.openbb.co/blog/openbb-releases-open-data-platform
19. PyPortfolioOpt 仓库页：https://github.com/PyPortfolio/PyPortfolioOpt
20. ArturSepp/OptimalPortfolios：https://github.com/ArturSepp/OptimalPortfolios