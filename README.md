# Cross-Asset Allocation Decision Engine

本项目是本地运行的跨资产配置决策引擎，核心原则是 Point-in-Time 数据、可解释信号和可重建的历史回放。模型只使用 canonical asset/series id，数据供应商映射保存在 `config/`。

## 初始化

需要 Python 3.12。复制 `.env.example` 为 `.env`，按需填写本地凭据（不要提交 `.env`）。

```text
scripts/bootstrap.ps1
cross-asset init-db
cross-asset probe-data
cross-asset validate-data-file <file> [--manifest <yaml-or-json>] [--output <json>]
```

首轮公共 CLI 已预留 `ingest`、`quality-check`、`build-features`、`score`、`allocate`、`run-daily`、`backtest`、`report` 和 `ui` 接口；具体实现由对应模块延迟接入。缺少并行模块时命令会明确提示，而不会静默成功。

## Model core v0.2

当前研究核心使用统一、可审计的 signal contract，而不是把不同量纲的原始值直接相加：

- `trend_signal_v0.2`：1M/3M/6M/12M 多周期趋势，使用 log move / 同周期已实现波动率构造无量纲信号；缺失周期降低 confidence，不做零填充。
- `risk_signal_v0.2`：20 日波动率相对其严格历史基线的 causal z-score，风险越高分数越低。
- `macro_v0.2`：先按 observation_date 去除同一期的旧 revision，再做 transform；可选 causal z-score 只使用当前观测之前的历史，freshness 按单序列计算。
- 宏观转换语义：`pct_change_12m` 对精确匹配的 12 个月前 observation_date 输出同比百分比；`difference_12m` 输出原始单位差值；`change_in_yoy_pp` 适用于原始值已是同比增速的序列，输出同比增速变化的百分点（pp）。缺少对应期间时保持不可用，不按有效值位置补齐。
- 月末/闰日政策：月度序列按 `YearMonth` 经济期间匹配，季度序列按 `YearQuarter` 匹配，不 rollforward/rollback 到邻近期间；因此 `2025-02-28` 与 `2024-02-29` 属于同一月度期间。日频序列仍按精确日期匹配。当前期值为缺失时保持不可用，不回退到上一期。
- `asset_score_v0.2`：按预声明 component weight 聚合，并把 component confidence 与 weighted coverage 纳入最终 confidence。
- Price 与 yield proxy 统一转成 price-like return index；债券收益率使用显式 duration proxy，不再把 yield level 当价格。
- `valuation`、`carry`、`structure` 在没有可信输入时保持 `None`；系统不会为补齐模型而伪造信号。
- 关键 trend 不可用或上游 health 失败时 allocation 进入 `FROZEN`；若存在最近一次 ACTIVE 权重则冻结到该权重，否则回退战略权重。

这些参数目前仍是 `DEVELOPMENT_PRIOR`，不代表 OOS 验证结论。

## 回测与研究口径

- 决策只能使用 `available_at <= decision_time` 的信息。
- 已实现显式价格/现金/yield-duration holding-period return 语义。
- 末端 decision 没有下一持有期，因此 realized return 为缺失值，而不是 0。
- 默认不对首个战略建仓收取交易成本；如需要可通过显式参数启用。
- turnover convention 明确记录为 `two_sided_notional` 或 `one_way`。
- 提供按显式交易日生成的 calendar walk-forward manifest，可落实 5 年最短训练、12 个月测试、3 个月步长等研究协议，同时不虚构交易日期。

## WP3/WP6 业务验收与实施路线

| 序列 | 原始单位（当前配置） | 转换 | 派生单位 | 备注 |
|---|---|---|---|---|
| US_CPI | index（FRED CPIAUCSL） | `pct_change_12m` | percent | 指数水平先转同比百分比 |
| US_CORE_PCE | index（FRED PCEPILFE） | `pct_change_12m` | percent | 指数水平先转同比百分比 |
| US_INDUSTRIAL_PRODUCTION | index | `pct_change_12m` | percent | 指数水平先转同比百分比 |
| CN_CPI/CN_PPI/CN_M1/CN_M2 | 未冻结 | `ambiguous_raw_semantics`（fail closed） | 不输出 | Wind 原始字段语义待证据快照核对，暂不进入宏观分数 |

WP3 验收覆盖指数同比、同比增速变化 pp、缺月/缺季和 revision cutoff；正式研究仍需冻结来源快照与 PIT 证据。WP6 的 `generate_research_brief` 只渲染已有结构化市场事实和可选持仓字段；没有持仓时明确“未提供”，并保留数据时间、来源、缺失限制、人工研究问题、支持/反证、下次检查及不行动记录。当前交付是辅助研究，不代表交易建议或模型收益验证完成。后续路线是先由 CLI 统一装配这些结构化字段，再以真实周度周期测量追溯率和人工复盘使用情况；旧审计状态证据保留，不将其改写为完成。

## 目录约定

- `docs/LLM_HANDOFF_AND_ROADMAP.md`：面向后续 LLM 和维护者的当前基线、业务目标、分阶段路线、验收门槛与接手检查清单。

- `config/`：canonical 资产、序列、来源映射、因子和配置约束。
- `data/raw/`：不可变原始快照；`data/db/`：本地数据库文件。
- `data/manual_inbox/`：专业数据手工导入入口；成功导入后归档。
- `artifacts/`：能力报告、日报和回测产物。
- `src/cross_asset/domain/`：Provider、存储和模型层共享的 Pydantic 契约。

## 开发检查

```text
make check
make test
```

GitHub Actions 在 Ubuntu 与 Windows、Python 3.12 上执行 compile、Ruff 和全量 pytest。

所有外部数据应保留 `observation_date`、`available_at`、`vintage_date` 和 `ingested_at`。历史查询必须使用 `available_at <= decision_time`，不得以观察期日期代替可用时间。

`validate-data-file` 是只读验收入口，不写入 observations；它按 Data Acceptance Gate 返回 PASS/PARTIAL/FAIL（exit code 0/2/1）。

`coverage-report --database <db> --as-of <ISO> --output <json>` 是只读 coverage/PIT 报告；仅统计 `available_at <= as_of`，空数据保持 `DATA_BLOCKED`，日历覆盖范围外标记 `UNKNOWN`。

离线 benchmark 已支持 `MACRO_ONLY` 与 `RISK_ONLY`；benchmark 与 FULL_MODEL 共享资产收益语义，但接口 READY 不等于 OOS 验证。

`probe-fred` 仅检查 FRED DGS10/DFII10 metadata 能力；key 只从 `FRED_API_KEY` 环境变量读取，未经 PIT 证据不会写正式 observations。
