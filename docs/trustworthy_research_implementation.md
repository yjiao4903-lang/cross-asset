# 可信研究入口实施记录

本轮修复复用仓库已有的 `AssetReturnSpec`、`latest_formal_observations_asof`、`approved_observations_asof`、`ProvenanceStore` 和 DuckDB schema，没有新增依赖。依据项目 `AGENTS.md` 的官方/成熟实现复用要求，选择适配现有 PIT 查询和 provenance 存储；这些组件已经是仓库正式路径的一部分，替换为新框架会扩大迁移面而不增加可验证性。复用核查参考 [Python 3.12 import system](https://docs.python.org/3.12/reference/import.html) 的模块初始化语义，以及 [DuckDB INSERT/ON CONFLICT](https://duckdb.org/docs/current/sql/statements/insert) 和 [transactions](https://duckdb.org/docs/current/sql/statements/transactions) 文档。

## 已交付

- `run-daily --macro-source marco` 从研究 universe 装配显式收益契约，非现金资产缺契约时失败关闭。
- `python -m cross_asset.research.cli --help` 可在全新进程启动；operations 包改为惰性导入，消除循环依赖。
- OOS 运行按完整已审批信息集生成 snapshot identity，run ID 纳入 snapshot；fold 结果同内容幂等，重要字段冲突时报错。
- readiness 对每个决策时点重新选择 PIT vintage 并执行 freshness，避免用当前最新 vintage 回看历史。
- 日报成功和 `DATA_BLOCKED` 路径均生成简报；输出 JSON 返回 `brief_output`。独立入口为 `cross-asset research-brief`。

fixture 示例：

```powershell
python -m cross_asset.cli research-brief examples/research_brief_fixture.json --output artifacts/reports/research_brief_fixture.md
```

示例明确标记 `FIXTURE_ONLY`，不代表 Live、审批或研究收益验证。正式研究仍受 `DATA_BLOCKED`、协议审批和真实 PIT 证据约束。

## 验证与边界

本轮使用独立 basetemp `D:\CROSS\pytest_integrated_20260909_3` 完成针对性集成测试 `25 passed`；全量验证命令为：

```powershell
python -m ruff check src tests
python -m pytest --basetemp D:\CROSS\pytest_integrated_<unique> -q
python -m cross_asset.research.cli --help
```

本机审计复现使用 `D:\量化资产监控系统\.venv\Scripts\python.exe` 与对应 ruff 路径；该路径不是项目运行要求。

仍待真实数据权限、来源 vintage 和连续周度使用周期验证；本轮没有解锁正式研究、交易或服务发布。
