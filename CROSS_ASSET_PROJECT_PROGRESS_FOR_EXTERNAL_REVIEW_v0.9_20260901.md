# Cross-Asset 项目进度与下一阶段计划（外部审核版 v0.9）

审计日期：2026-09-01（Asia/Shanghai）  
结论先行：离线工程基础设施和研究合同已形成，FRED 已取得受控 raw/attempt/Registry 证据；但项目仍 `DATA_BLOCKED`，没有可用于正式 PIT 回测的 observations，也不能据此声称真实 Live、投资有效性或生产就绪。

## 1. 执行摘要

已核验事实：DuckDB 当前 observations 为 0；provider attempts 为 45；data acceptance registry 为 15；最近 FRED ALFRED 宏观批次 model run 为 `partial` 且 `data_snapshot_id=NULL`。公开 CSV 与 ALFRED 响应都只作证据 raw，未写正式 observations。

当前判断：

- 离线 Storage/PIT/as-of、治理、验收、provenance、备份锁、Shadow/Replay 与 benchmark 接口可作为工程基础，具体门禁仍应以各自测试和报告为准。
- FRED public CSV：priority 8 条完成两轮下载和 hash 重复性核对；5 条既有宏观序列完成一次 ALFRED `output_type=4` 受控请求。两者均缺少可证明的首次发布时间/盘中 `available_at`，因此不能解冻 PIT。
- FRED、Yahoo、Wind/iFinD、中国市场数据的授权、稳定性、长期历史和语义等仍未全部验证。
- Git 已初始化但当前无 commit/tag；这是可追溯性风险，不是业务数据通过证据。

## 2. 目标与边界

目标是构建一套可审计的跨资产决策/历史重放基础：数据具有 source/origin/raw hash、PIT available_at、as-of 查询、质量和 provenance；模型链为 Market→Macro→Style→Asset→Allocation，并支持 benchmark、回放和 Shadow。

明确边界：工程接口、fixture/simulated、公开下载样本和研究设计不等于真实数据可用；不作投资收益、预测能力、授权完整性或生产 SLA 结论。

## 3. 分阶段完成矩阵

| 阶段/能力 | 当前状态 | 证据与边界 |
|---|---|---|
| P0 Storage/PIT/Replay | DONE（离线） | DuckDB schema、事务、as-of、golden/replay 测试；真实数据未验证 |
| P0 Market/Macro/Style/Asset/Allocation | DONE（fixture/离线） | 状态与模型链测试；不代表真实数据或 OOS 有效 |
| 基础设施 Freeze | TRUE（仅离线） | [INFRA_FREEZE_REPORT](artifacts/sprint_a/INFRA_FREEZE_REPORT.md)；不覆盖 DATA_READY |
| Origin/Acceptance | DONE（合同/候选登记） | [DATA_ACCEPTANCE_GATE](docs/DATA_ACCEPTANCE_GATE.md)；审批字段 TBD，PASS 仍受四门约束 |
| PIT Grade A/B/C/D | DONE（规则/Registry） | A/B 可作为 PASS 候选，C warning，D research-only；未知不升级 |
| Calendar/Coverage | PARTIAL | 默认日历 UNVERIFIED；权威假期/早收盘覆盖仍缺 |
| Model modes/benchmarks | READY（接口） | MACRO_ONLY/RISK_ONLY 语义隔离已测；参数未校准、无 OOS 验证 |
| Backup/restore/lock/provenance | DONE（离线） | 现有冻结报告与 DB schema；尚无生产运行压力证据 |
| Shadow continuity | DONE（模拟） | 7 日连续模拟、degraded/frozen/recovery 等测试记录；非真实市场验证 |
| Provider Live | PARTIAL/BLOCKED | FRED 有受控 evidence raw；Yahoo/Wind/iFinD/中国数据仍未完成授权/PIT/SLA 验证 |
| UI | MISSING/后置 | 不在本阶段放行范围 |

## 4. FRED 数据全景

### 4.1 Public CSV

本轮 priority 白名单为 EFFR、DGS2、DGS5、DGS30、CPILFESL、PCEPI、T10YIE、T5YIE。每条从 2024-01-01 请求至 2026-09-01，首次与一次重复下载 hash 全部一致；频率和实际区间因序列而异：日/工作日序列约 694–695 行，月度序列 31 行。逐条 rows、日期、路径和 SHA-256 见 [fred_priority_batch_20260901.json](artifacts/data_capability/fred_priority_batch_20260901.json)。

该批次在主库对应 16 条 provider attempts、8 条 PARTIAL Registry、model run `fred_priority_batch_20260901`（partial，snapshot NULL）。raw 只证明下载/内容稳定性；没有首次 release timestamp，因此未写 observations。

### 4.2 鉴权 ALFRED/API

CPIAUCSL 定向验证使用固定 realtime 边界，返回 31 行和日期级 `realtime_start/end`，raw hash 及合同见 [fred_alfred_cpi_targeted_retry_20260901.json](artifacts/data_capability/fred_alfred_cpi_targeted_retry_20260901.json)。此前未带 realtime 边界的 CPI 请求返回 HTTP 400；其后唯一批准复测成功，不再进行参数试错。

随后对 CPIAUCSL、PCEPILFE、UNRATE、ICSA、INDPRO 各进行一次 ALFRED `output_type=4` 请求，均为 PARTIAL，行数分别为 31、31、31、138、31；见 [fred_alfred_macro_first_release_batch_20260901.json](artifacts/data_capability/fred_alfred_macro_first_release_batch_20260901.json)。该批次在主库新增 5 条 attempts、5 条 PARTIAL/D Registry，model run `fred_alfred_macro_first_release_batch_20260901` 为 partial、snapshot NULL。

ALFRED 日期级 realtime 不是盘中首次发布时间；因此当前仍不允许将其写成 `available_at`，也不允许正式研究消费。

## 5. DATA_BLOCKED 与 INFRA_FREEZE 的含义

`INFRA_FREEZE=TRUE` 只表示离线基础设施门禁（schema、PIT 过滤逻辑、raw、provenance、模拟链、备份/锁等）有报告和测试证据。它不表示 provider、数据授权、PIT release lineage、模型预测或生产环境已准备。

`DATA_BLOCKED` 表示至少一个正式数据接纳门未通过：当前 observations=0，FRED Registry 为 PARTIAL/D，审批字段未完成，且真实系列的 release timestamp、法律范围、日历和长期稳定性尚未闭合。

## 6. 测试与静态检查

- 最近可复核全量记录：**100 passed**，项目内新 basetemp；全量 Ruff 通过，compileall 通过。
- 当前窗口最近 FRED 定向回归：**8 passed**；Ruff 和相关 compileall 通过。
- 早期 [TEST_BASELINE](artifacts/current_state/TEST_BASELINE.md) 仍记载 98 passed/2026-08-31，与之后 100 passed 不一致；本报告采用较新的命令结果，但建议主窗口重新运行一次全量并更新 canonical baseline。
- 静态通过不等于真实网络、并发、备份恢复、渲染或投资结果通过；上述强门仍需专门运行证据。

## 7. 风险、阻塞与技术债

1. PIT：FRED realtime/vintage 仅日期级，缺首次发布时间或可批准的 conservative lag；不能安全生成 `available_at`。
2. 法律：API key/公开可下载不自动授予保存、研究、再分发权限；reviewer/approved_at 仍 TBD。
3. 数据覆盖：Yahoo、Wind、iFinD、交易所和中国宏观/债券数据缺真实 entitlement、语义、历史深度和稳定性闭环。
4. Calendar：US/CN/HK/FX 权威日历和 covered years 仍未完成，coverage 不能静默按工作日推算。
5. Git/追溯：仓库已 init 但无 commit/tag；source tree 可计算但无发布锚点。
6. 运行时：旧临时审计目录存在权限/清理风险；网络链路曾出现超时，不能以偶发成功推断 SLA。
7. 模型：benchmark 参数未校准，暂无真实 OOS、成本敏感性和基准对照结果。
8. 当前状态文档仍含早期测试数字和过时 FRED 描述，需由主窗口统一刷新，避免多个 canonical 文件漂移。

## 8. 下一阶段五轮计划

| 轮次/优先级 | 目标与输入 | 交付物/验收门 | 依赖与禁止结论 |
|---|---|---|---|
| 1. Data Unblock / P0 | 用户授权、FRED/PIT/日历证据、Wind/iFinD/交易所导出 | 每条 manifest 四门证据、3 批 manual repeatability、reviewer/approved_at、可重建 available_at；失败保持 BLOCKED | 依赖权限和人工证据；不得把网页可下载写成 DATA_READY |
| 2. Real Backfill / P0 | 通过门禁的真实历史 raw 与 vintage | content-addressed raw、observations、PIT as-of、coverage、reconciliation、snapshot；重复采集 hash/row 稳定 | 依赖轮次 1；不得用 fixture 混入 LIVE |
| 3. Real Shadow / P1 | 真实 8 核心及宏观数据、冻结参数、日历 | 连续运行、health/fallback/freeze、provider attempts、manifest/provenance；异常可重放 | 依赖 PIT/授权/日历；不交易、不调参、不改变 strategic weights |
| 4. OOS Validation / P1 | 真实 backfill、冻结 research protocol（5Y train/12M test/3M step/last 20% holdout） | challenger 结果、成本敏感性、缺失剥离、统计不确定性、独立 review；结果可复算 | 依赖真实数据和预注册协议；不得把模拟或 in-sample 说成有效性 |
| 5. Production Readiness / P2 | 通过 OOS 的版本化代码/配置/数据 | 发布 commit/tag、备份恢复演练、监控/SLA、权限审计、回滚和人工审批 | 依赖前四轮全通过；不得以 INFRA_FREEZE 单独宣布生产就绪 |

## 9. 外部审核问题清单

- 每个系列的首次 release/available_at 证据是否能由第三方复核？realtime 日期如何避免被误用为盘中时间？
- FRED/Yahoo/商业源的保存、研究、再分发权限边界分别是什么？审批人和日期在哪里？
- Registry 的 PARTIAL/D 是否始终阻止正式 observations 和 OOS？
- Calendar 的来源、版本、覆盖年、节假日和早收盘是否足够支持 coverage？
- 真实 backfill 如何保证 raw、PIT、snapshot、model run、artifact 的 hash 链一致？
- MACRO_ONLY/RISK_ONLY 的参数、映射和 OOS 结果是否预注册并独立复核？
- 100 passed 与旧 baseline 数字冲突时，哪一份是唯一 canonical 测试证据？
- 无 Git commit/tag 时如何审计代码版本和发布回滚？

## 10. 最终放行判断

工程基础设施：可称为离线冻结候选，依据 [INFRA_FREEZE_REPORT](artifacts/sprint_a/INFRA_FREEZE_REPORT.md)。  
真实数据与模型：**不放行**，状态必须保持 `DATA_BLOCKED`。当前证据不足以支持真实 Live、正式 PIT 回测、投资有效性或生产就绪结论。

