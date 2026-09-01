# Cross-Asset Allocation Decision Engine
# 外部独立评审包

复核时间：2026-08-31（Asia/Shanghai，UTC+8）

## 结论

当前工作区已完成 Phase 0、Phase 1、Autonomous Core 及 Stretch A/B 的离线工程验收。当前结论是：

- 功能测试、PIT/数据链路、模型基础模块、Replay、报告和 CLI smoke 均已通过。
- 最新全量测试：`33 passed`。
- `ruff check src tests`：通过，0 findings。
- `python -m compileall -q src`：通过。
- 工作区不是 Git 仓库，无法提供 branch、commit hash 或可靠的变更统计。
- 所有通过结果均为本地 fixture/manual/offline 语义；不等同于真实供应商 live 能力或投资表现验证。

完成度口径：按当前蓝图的工程交付范围计，Phase 0/1、Autonomous Core 和 Stretch A/B 的代码、测试与离线 CLI 验收已完成；live provider entitlement、真实市场数据、投资有效性和生产部署不在已完成口径内。

## 1. 项目目标与边界

项目目标是建设一个本地、可追溯、Point-in-Time 安全的跨资产配置决策引擎，逐步形成：

```text
PIT observations
→ market features/state
→ macro state
→ style state
→ asset score/confidence
→ constrained allocation
→ historical replay
→ daily/data-health/backtest reports
```

本阶段明确不包含：实盘交易、券商连接、个股 Alpha、黑盒机器学习、网页爬虫、复杂组合优化、自动购买数据权限，以及将模型输出描述为投资保证。

## 2. 已完成事项（Phase 0 → Autonomous Core/Stretch）

### Phase 0 — Provider 与能力探测

- FRED、Yahoo、Tushare、Wind、iFinD、Manual provider 骨架。
- 统一 Provider/domain 公共契约：`DataRequest`、`Observation`、`ProviderCapability`。
- SDK 延迟导入、结构化 provider error、缺凭据/缺依赖 graceful failure。
- capability Markdown/JSON 报告，支持 secret 脱敏。
- 12 条 canonical series 配置与 source mapping。

### Phase 1 — Storage + PIT

- DuckDB schema/init、`series_catalog`、`source_mapping`、`observations`、`ingestion_runs`、`data_quality_events`、模型结果表。
- `observation_date`、`available_at`、`vintage_date`、`ingested_at`。
- as-of query 严格使用 `available_at <= decision_time`。
- immutable/content-addressed raw archive，raw file 与 normalized observations 关联。
- ingestion transaction、失败记录、幂等写入和质量状态。

### Autonomous Core

- Returns、Trend、Volatility、Drawdown、Relative Strength、Correlation。
- Market State v0.1。
- Macro transforms、vintage-aware Macro State v0.1。
- Style State v0.1，语义不匹配时返回 unavailable。
- Asset Score v0.1、missing-aware reweighting、confidence。
- Allocation v0.1、bounded projection、min/max、sum-to-one、critical freeze、attribution。
- Historical Replay：W-FRI deterministic dates、next-period effective、turnover/cost。
- STATIC/TREND_ONLY benchmark plumbing。
- daily report、backtest report、research registry、golden metadata。

### Stretch A/B

- Data Health：`OK`、`CLOSED`、`STALE`、`MISSING`、`FAILED`、`FALLBACK`、`UNAVAILABLE`。
- critical unhealthy 检测与报告。
- Backtest metrics、cost comparison、Markdown report。
- `report daily`、`data-health`、`backtest` CLI。

## 3. 架构与关键数据流

```text
config/*.yml
      ↓
Provider contract / Fixture / Manual
      ↓
raw immutable archive (SHA-256 path)
      ↓
normalization + quality
      ↓
DuckDB observations + ingestion_runs + quality events
      ↓
PIT as-of query (available_at cutoff)
      ↓
pure feature functions
      ↓
Market / Macro / Style engines
      ↓
Asset Score + Confidence
      ↓
bounded Allocation / FROZEN fallback
      ↓
Replay + metrics + daily/backtest/data-health artifacts
```

Provider 不直接写 storage；feature 不读取 provider 或写数据库；报告层消费结果并明确 offline/live 来源。

## 4. 关键不变量与实现证据

| 不变量 | 实现/测试证据 |
|---|---|
| PIT 无前视 | `src/cross_asset/pit/asof.py`、`storage/queries.py`、PIT acceptance tests；Replay 的 next-return 只接收 decision-time 信息集 |
| Vintage 正确 | `tests/fixtures/macro_vintage/jan_vintage.json`；测试证明 2025-02-09 unavailable、2025-02-20=100、2025-03-20=102（raw contribution） |
| Raw immutable | `ingestion/raw_archive.py` 内容寻址、SHA-256、碰撞内容校验；raw archive existence test |
| Missing 不填 0 | Macro/Asset/Style tests；缺失返回 unavailable、reweight 或降低 confidence |
| Confidence 有界 | `confidence_score` 与 asset/macro/style tests；范围为 0 到 1 |
| Score 有界 | Asset/Macro/Allocation 测试；模型分数限制在 -2 到 +2 |
| Allocation constraints | `bounded_projection` 与随机/极端可行约束测试；权重和为 1 且满足 min/max |
| Critical freeze | allocation tests 验证 `FROZEN` 使用 previous valid weight，否则使用 strategic fallback |
| Replay 无前视 | `backtest/replay.py` 与第三波 replay tests；每个决策日期只消费 `available_at <= decision` |
| Determinism | Market/full-pipeline golden 文件、W-FRI replay deterministic test |
| Provider 失败可见 | `ProviderError`、`last_error`、ingestion run failed 状态、offline capability report |

## 5. 最终门禁与实际结果

在项目 `.venv` 中复核，使用项目内 `.uv-cache`；pytest 临时目录放在项目目录以规避主机默认 Temp 权限限制。

```text
uv sync --extra dev
  PASS

python -m compileall -q src
  PASS (exit 0)

ruff check src tests
  PASS (0 findings, exit 0)

pytest -q -p no:cacheprovider --basetemp .pytest-tmp-external-20260831
  PASS (33 passed, exit 0)
```

复核时曾用已存在的 `.pytest-tmp-external` 目录，pytest 清理该目录受到 Windows `PermissionError [WinError 5]` 影响；改用新的项目内临时目录后全量测试稳定通过。该现象是测试临时目录权限/占用问题，不是业务测试失败。

CLI smoke（全部 exit 0）：

```text
cross-asset build-features --as-of 2025-12-31
cross-asset score-market --as-of 2025-12-31
cross-asset score-macro --as-of 2025-12-31
cross-asset score-style --as-of 2025-12-31
cross-asset score-assets --as-of 2025-12-31
cross-asset allocate --as-of 2025-12-31
cross-asset replay --as-of 2025-12-31
cross-asset report daily --as-of 2025-12-31
cross-asset data-health --as-of 2025-12-31
cross-asset backtest --model static --cost-bps 10
```

pipeline CLI 明确输出 `offline pipeline stage` / `no live provider call`；报告 CLI 明确输出 `offline fixture`，避免假装 live 成功。

## 6. Offline / live 严格分类

### 已验证 offline

- 本地 Python/uv 项目环境。
- DuckDB schema/init 与本地数据库文件。
- Provider contract、Fixture/Manual provider、结构化错误。
- PIT/as-of、macro vintage、raw archive、幂等、stale/failed/missing。
- Market/Macro/Style/Asset Score/Allocation/Replay 的测试链路。
- STATIC/TREND_ONLY plumbing、cost/turnover metrics。
- Daily、Data Health、Backtest Markdown/JSON artifact。
- 所有 CLI smoke 与 golden 文件存在性/确定性相关测试。

### 已验证 live

- 无。

### 未验证 live

- FRED/ALFRED API key 与真实历史数据。
- Yahoo 网络可达性与真实行情。
- Tushare token、积分和 endpoint entitlement。
- WindPy 登录、权限和历史深度。
- iFinD SDK/EDB entitlement。
- 真实生产数据延迟、供应商切换与线上运行稳定性。
- 投资回报、样本外效果、参数有效性。

## 7. 主要模块与产物索引

### 核心模块

- `src/cross_asset/domain/models.py`：canonical domain contract。
- `src/cross_asset/providers/`：provider abstraction/adapters/fixture。
- `src/cross_asset/ingestion/`：normalization、quality、raw archive、runner。
- `src/cross_asset/storage/`：DuckDB schema、repository、queries。
- `src/cross_asset/pit/`：as-of 与 release rules。
- `src/cross_asset/features/`：market/macro feature primitives。
- `src/cross_asset/engines/`：market、macro、style、asset score、allocation。
- `src/cross_asset/backtest/`：replay、metrics、benchmarks。
- `src/cross_asset/reports/`：capability、daily、data health、backtest。
- `src/cross_asset/cli.py`：Typer CLI。

### 测试与配置

- `tests/test_phase01_acceptance.py`
- `tests/test_phase02_market_data.py`
- `tests/test_phase03_replay.py`
- `tests/unit/engines/`
- `tests/unit/features/`
- `tests/unit/backtest/`
- `tests/unit/reports/`
- `tests/fixtures/macro_vintage/jan_vintage.json`
- `tests/golden/market_state_2025_12_31.json`
- `tests/golden/full_pipeline_2025_12_31.json`
- `config/series.yml`、`sources.yml`、`macro.yml`、`allocation.yml`、`factors.yml`、`assets.yml`

### 运行产物

- `data/db/cross_asset.duckdb`
- `artifacts/data_capability_report.md`
- `artifacts/data_capability_report.json`
- `artifacts/reports/daily.md`
- `artifacts/reports/backtest.md`
- `artifacts/reports/data_health_2025-12-31.md`
- `artifacts/reports/data_health_2025-12-31.json`
- `artifacts/research_registry.yml`
- `artifacts/autonomous_run/`

## 8. 已知限制、风险与 NEEDS_HUMAN_DECISION

- 中国宏观数据源尚未选定并 live 验证。
- 估值、盈利修正、资金流等数据尚未纳入正式模型。
- strategic weights、max tactical tilt、交易成本和部分 proxy 仍是 `DEVELOPMENT_PRIOR`。
- 当前 CLI 的 pipeline stages 是离线 plumbing/smoke，不应误解为已执行完整生产数据计算。
- Live provider 权限、费率、限流、历史深度和服务稳定性未验证。
- Golden full-pipeline 文件当前主要是确定性集成元数据，不是投资结论或真实绩效报告。
- 工作区没有 `.git` 元数据：不能提供 branch、commit hash、git diff 或准确变更行数统计；未初始化 Git、未提交或发布。

NEEDS_HUMAN_DECISION：

- 确认中国宏观主数据源及备用源。
- 提供并授权使用真实 provider credentials/entitlements（如需 live 验证）。
- 确认 strategic allocation、proxy 语义、max tilt 与 cost assumptions。
- 确认生产部署、数据保留和告警要求。

## 9. 下一阶段建议与优先级

1. 先将 Replay 从 CLI plumbing 接到可审计的 fixture observation pipeline，生成真实的历史 Market/Macro/Style/Asset/Allocation 输出。
2. 强化 Data Health 与 allocation freeze 的端到端联动，并增加 report schema validation。
3. 建立版本化人工宏观导入模板和 source entitlement registry。
4. 在明确人类决策后，接入一项 live provider，保留 raw archive 与 capability evidence；不要并行接入多个未验证供应商。
5. 形成样本外 benchmark 与成本敏感性报告，再讨论参数验证；不先做参数优化或 ML regime。

## 10. 外部评审建议检查清单

- [ ] 独立执行 `uv sync --extra dev`、compileall、full Ruff、full pytest。
- [ ] 核对测试是否真的加载 macro vintage fixture，而不是只检查文件存在。
- [ ] 核对 Replay 每个 decision date 的信息集上界是 `available_at <= decision`。
- [ ] 核对 raw archive 在 normalization 前/同步持久化且 hash 可复算。
- [ ] 核对 duplicate ingestion 不因新的 `ingested_at` 产生重复业务 observation。
- [ ] 核对 missing 不被转为 0 或伪装成中性信号。
- [ ] 核对 confidence/score/weights 边界及 infeasible constraints 行为。
- [ ] 核对 critical unhealthy 时没有新的 risk-on tilt，且 previous/strategic fallback 可解释。
- [ ] 核对 daily/data-health/backtest 报告的来源标签和字段完整性。
- [ ] 核对 CLI offline 输出不被描述为 live provider 成功。
- [ ] 核对 golden 文件是可重复的工程快照，不是未经验证的投资结论。
- [ ] 评审人注意工作区非 Git 仓库，不能通过 Git diff 推断变更量。

## 11. 变更统计

未提供文件数、行数或 commit 统计：当前工作区不是 Git 仓库，无法准确取得可靠的变更基线；本评审包不编造统计数字。
