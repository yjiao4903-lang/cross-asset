# Cross-Asset Allocation Decision Engine — 当前权威状态

复核时间：2026-08-31（Asia/Shanghai，UTC+8）

## 结论

离线基础设施、PIT、Provenance、Data Health、Shadow 连续运行和备份/锁门禁已完成。全量测试 **71 passed**，Ruff clean，compileall 通过。真实 Yahoo/FRED/Wind/iFinD 数据仍为 **DATA_BLOCKED**，不代表 live provider 或投资结论已验证。

## 当前事实

- Git 已 `init`，当前无 commit；不存在可声称的 commit code version。
- `config_hash`、`model_runs`、`data_snapshots` 已实现并写入 DuckDB；当前库 introspection：10 张业务表，`observations=0`、`provider_attempts=7`、`model_runs=1`、`data_snapshots=1`。
- Shadow 主路径支持显式 as-of、PIT cutoff、7 日连续 fixture、provider degraded、critical stale→FROZEN→恢复、幂等/retry/跨进程锁及 weekly review。
- `INFRA_FREEZE=TRUE` 仅表示离线基础设施门禁通过；真实数据保持 DATA_BLOCKED。
- `uv` 环境事实：使用 bundled Python 将 `uv 0.12.7` 安装至项目 `.tools`，`PYTHONPATH=.tools python -m uv sync --extra dev` 成功；未改系统 PATH，未安装进 `.venv`。
- v0.8 治理合同已建立：Freeze、Data Acceptance、LIVE_CORE_8 与 Research Protocol；研究配置为 PLANNING_ONLY，owner/reviewer/approved_at 明确 TBD，真实数据仍 DATA_BLOCKED。

## 验证

```text
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp <project-dir>  PASS (66 passed)
.venv\Scripts\ruff.exe check .                                             PASS
.venv\Scripts\python.exe -m compileall -q src                                PASS
cross-asset weekly-shadow-report                                               PASS (weekly_shadow_review.md)
cross-asset backup / verify-backup                                             PASS (isolated smoke)
```

## 待办

真实 provider 权限、稳定网络和 8 canonical series verified snapshot 仍需人工/合规数据窗口；后续研究须在真实数据到位后重新验证覆盖、样本外表现和参数稳健性。
