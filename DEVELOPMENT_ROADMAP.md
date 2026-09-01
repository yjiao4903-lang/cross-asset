# Cross-Asset Allocation Decision Engine Roadmap

## 1. 目标与硬约束

目标是建立本地、可解释、可回放的“市场状态—因子—资产偏好—受约束配置倾向”引擎。核心输入必须带 `observation_date`、`available_at`、`vintage_date`、`ingested_at`；原始快照不可覆盖；provider 与模型解耦；缺失、陈旧、失败不得静默；critical 数据不健康时不得产生正常建议。第一阶段不做高频、自动交易、LLM 决策、网页爬虫、黑盒收益预测、复杂优化器或微服务。

## 2. 已完成门禁（Phase 0/1）

Phase 0 已完成 provider contract、FRED/Yahoo/Tushare/Wind/iFinD/Manual 骨架、延迟 SDK 导入、结构化错误与 Markdown/JSON capability report。离线门禁为 `python -m compileall -q src`、provider 导入、缺包路径、能力报告生成。

Phase 1 已完成 domain PIT 字段、DuckDB schema/init、raw archive、ingestion run、as-of 查询和质量事件。实际门禁为 `uv sync`、`pytest`、PIT no-lookahead、失败 provider、stale、重复 ingestion 幂等与 raw archive 测试；产物包括 `data/db/cross_asset.duckdb`、`artifacts/data_capability_report.{md,json}`。真实外部账户/网络能力尚未宣称已验证。

## 3. 本轮 Phase 2：Market Data MVP

已配置 12 条 canonical series：CN_EQ_LARGE、CN_EQ_SMALL、HK_EQ、US_EQ、CN_BOND_10Y、US_GOV_10Y、US_REAL_10Y、GOLD、COPPER、DXY、OIL、USDCNH；见 `config/series.yml` 和 `config/sources.yml`。Yahoo/FRED 映射为公开或 proxy；中国权益/中国债券保留 Manual 映射，避免爬虫和未经授权的 fallback。新增 `FixtureProvider` 完成 10 条核心序列的配置加载→DataRequest→Observation normalize→raw archive→DuckDB observations 端到端离线验收；重复 ingestion、PIT as-of、raw_file 和语义映射字段均有测试。真实抓取、历史长度、权限和口径仍待显式 live probe，不得写成完成。语义不等价的代理不得自动 fallback。新增测试 2 个；全量结果 `7 passed`。

未解决权限：FRED API key、Yahoo 网络可达性、Tushare token/积分、WindPy 登录与行情/宏观 entitlement、iFinD 登录与 EDB entitlement；本地 fixture 只能证明 schema/PIT/质量链路，不能证明供应商可用性。

## 4. 后续开发轮次

### Round 3 — Market Engine
范围：收益、趋势、波动、回撤、相对强弱、相关性纯函数。明确不做：个股选股、ML regime、自动交易。依赖：Phase 2 normalized observations 与 PIT。产物：features modules、golden market fixture、Market State。测试：窗口边界、缺失、no-lookahead、滚动计算。放行：固定日期输出可复现且不读取未来 available_at。风险/回退：数据不足则输出缺失/低置信，不补 0。

### Round 4 — Macro Engine
范围：FRED/ALFRED CPI、PCE、就业、实际利率等状态变量及发布时点。明确不做：中国宏观自动爬虫、单一 regime 黑盒。依赖：PIT release rules、可用 series mappings。产物：Macro State v0.1、vintage fixtures。测试：发布日期隔离、修订版本、状态转换。放行：历史 as-of 结果不能看到未来发布值。风险/回退：FRED 不可用时 manual import，并降低覆盖率/置信度。

### Round 5 — Style Engine
范围：SIZE/GROWTH/CYCLICAL/TECH 的相对价格、趋势、宏观贡献。明确不做：盈利预测、估值增强、行业大规模覆盖。依赖：Round 3/4。产物：四轴 score/contribution schema。测试：相对序列对齐、缺失-aware reweighting、解释拆解。放行：每个分数可追溯到 canonical series 与 cutoff。风险/回退：缺风格代理则该轴为 unavailable，不跨语义替代。

### Round 6 — Asset Score + Allocation
范围：六类资产 [-2,+2] score、confidence、战略中枢上的受限 tilt、上下限和 critical health freeze。明确不做：均值方差精确最优、LLM 仓位、自动下单。依赖：Macro/Market/Style 与质量状态。产物：versioned score/allocation、归因。测试：权重和为 1、边界、低置信缩小 tilt、critical stale 冻结。放行：模型版本、data_cutoff、贡献均齐全。

### Round 7 — UI + Data Health
范围：Overview、Assets、Styles、Macro、Data Health。明确不做：UI 内业务逻辑、后台服务化。依赖：稳定 report/query API。产物：本地 Streamlit 页面。测试：stale/missing/failed/fallback 展示、无数据安全降级。放行：关键数据失效不可显示为正常建议。

### Round 8 — Backtest / Walk-Forward
范围：历史 replay、周频再平衡、基准、换手、成本、walk-forward。明确不做：随机 shuffle、全样本回填 regime、实盘交易。依赖：PIT、versioned scores/allocation。产物：回测报告与 golden outputs。测试：future release 隔离、成本、边界日期、样本外。放行：任意结果可重建并列出 cutoff/model version。

## 5. 依赖、决策点与风险登记

依赖链：provider capability → mappings/semantic equivalence → raw archive → normalization/quality → PIT → features → states/styles → scores → allocation → UI/backtest。关键决策点是：每条序列的 primary/backup 是否语义等价、critical 是否有稳定来源、中国数据 API 与 manual 的切换、FRED vintage 覆盖范围、stale threshold。

| 风险 | 影响 | 预防/回退 |
|---|---|---|
| API 无权限或限额 | 序列缺失 | Manual 导入；显式 FAILED/MISSING；不自动伪造 |
| proxy 口径不等价 | 回测偏差 | `semantic_equivalence=false` 禁止 fallback |
| 修订/发布日期混淆 | 前视偏差 | available_at/vintage 与 PIT 测试 |
| stale 数据仍生成建议 | 风险误导 | quality gate 冻结 critical tilt |
| 供应商 SDK 破坏环境 | 启动失败 | 延迟导入、可选依赖、fixture |
| raw 被覆盖 | 无法审计 | immutable timestamp/hash archive |

## 6. Definition of Done

每轮必须有明确输入、版本化产物、离线 fixture、最窄自动测试、失败可见、PIT 可回放、文档记录未解决权限；不得把 mock/fixture 结果写成真实能力。MVP 放行还要求至少 10 条核心序列可自动或半自动更新、critical data health 可见、score/allocation 可解释且所有结果含 `data_cutoff` 与 `model_version`。
