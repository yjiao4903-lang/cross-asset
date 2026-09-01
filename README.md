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

## 目录约定

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

所有外部数据应保留 `observation_date`、`available_at`、`vintage_date` 和 `ingested_at`。历史查询必须使用 `available_at <= decision_time`，不得以观察期日期代替可用时间。

`validate-data-file` 是只读验收入口，不写入 observations；它按 Data Acceptance Gate 返回 PASS/PARTIAL/FAIL（exit code 0/2/1）。

`coverage-report --database <db> --as-of <ISO> --output <json>` 是只读 coverage/PIT 报告；仅统计 `available_at <= as_of`，空数据保持 `DATA_BLOCKED`，日历覆盖范围外标记 `UNKNOWN`。

离线 benchmark 已支持 `MACRO_ONLY` 与 `RISK_ONLY`；两者分别只读取宏观、风险/波动率输入，接口 READY 不等于 OOS 验证。

`probe-fred` 仅检查 FRED DGS10/DFII10 metadata 能力；key 只从 `FRED_API_KEY` 环境变量读取，未经 PIT 证据不会写正式 observations。
