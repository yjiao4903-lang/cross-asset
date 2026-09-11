# Cross-Asset 项目级协作规则

## 1. 项目定位与最高目标

本项目是个人/内部工作台型轻量项目，不按大型企业生产系统治理。

默认优先级：

1. 真实功能跑通；
2. 稳定可用；
3. 维护简单；
4. 用户时间成本与模型成本最优；
5. 只有真实风险需要时才增加额外控制。

任何新增角色、Gate、文档、测试或流程，都必须能明显提高功能正确性、降低实际风险或降低总体开发成本；否则不要增加。

## 2. 固定角色与职责

项目固定逻辑角色只有：`WEB-CONTROL`、`GPT-DEV`、`LOCAL-DEV-A`、`LOCAL-DEV-B`。

- `WEB-CONTROL`：唯一项目主控。负责目标与优先级、任务拆分与派发、业务边界、架构/Schema/Contract 决策、跨任务冲突处理、最终验收，以及高风险/不可逆操作授权。WEB-CONTROL 不是默认主力编码窗口，也不得为了治理完整性主动制造额外流程。
- `GPT-DEV`：默认 ONLINE 执行窗口。普通在线可完成的代码、测试、PR、文档和轻量验证应优先交给 GPT-DEV，并尽量一次做到最终回传。
- `LOCAL-DEV-A`：本地执行窗口 A，仅用于确实依赖本地数据库、本地文件、Windows runtime、Wind/iFind/native tool、进程状态或真实本机环境的工作。不得把普通在线开发默认路由给本地窗口。
- `LOCAL-DEV-B`：本地执行窗口 B，与 LOCAL-DEV-A 适用相同本地环境边界；仅在本地能力、数据或隔离并行确有需要时由 WEB-CONTROL 派发。不得把普通在线开发默认路由给本地窗口。

开发窗口不得自行扩大 Scope、改变架构/Schema/Contract、改变 allocation/strategic weights、Merge、Release 或执行未授权的高风险写入。

## 3. GitHub 是事实源，但启动读取必须最小化

GitHub 是项目协作事实源；聊天窗口是临时执行单元。

新窗口默认只读取完成当前任务所必需的增量信息：

1. actual `main`；
2. 本文件；
3. Control Issue `#35` 当前状态；
4. 自己的 active dispatch / Task Issue；
5. 与本任务直接相关的 PR、测试、CI 或业务文档。

只有存在冲突、跨模块依赖或明确需要时，才继续读取 `docs/CURRENT_STATE.md`、`docs/project_management/ROLE_REGISTRY.yml`、`docs/project_management/MULTI_WINDOW_GITHUB_OPERATING_MODEL.md`、历史 Issue/PR 或研究路线文档。

不得要求新窗口重复全文扫描已经稳定且与本任务无关的历史材料。同一事实已验证且状态未变化时，不重复核验。

`No GitHub dispatch = NO WORK` 仍适用于开发窗口；但 dispatch 可以是紧凑的 Issue/comment，不要求复杂模板。

## 4. 默认任务闭环

普通任务默认采用：

`一次完整派发 -> 实现 + 必要测试 + 必要 smoke -> 一次最终回传 -> WEB-CONTROL 验收/合并`

能一次完成的事情不得人为拆成“分析 -> 实现 -> 单测 -> review -> smoke -> release prep”等连续小任务。

同一执行窗口具备能力时，应连续做到真正需要 WEB-CONTROL 决策的边界。

一个普通任务如果需要用户来回中转超过约 2 次，WEB-CONTROL 应优先判断为流程设计失败，并合并后续步骤；用户不得充当 Agent 之间的消息总线。

## 5. 一次派发的最小充分内容

普通 dispatch 尽量一次包含：

- 目标；
- 允许范围；
- 明确业务边界/不可改项；
- 必要测试与 smoke；
- 失败时如何返回真实状态；
- 是否涉及下述高风险操作；
- 最终返回标记。

不默认要求 baseline SHA、完整 overlap 表、WG0-WG9、单独 Gate 报告、exact-head 证据包或多轮 approval。只有这些信息能解决真实冲突或风险时才补充。

代码任务通常使用独立 branch + PR 以便 diff/回滚；低风险、低冲突的纯文档/治理小改动可由 WEB-CONTROL直接处理。不要把 branch/PR 本身当作审批链。

## 6. 最小充分验收

普通功能只需证明：

- 目标功能可用；
- 直接相关 regression 正常；
- 关键业务语义正确；
- 没有明显破坏核心流程。

默认优先：targeted tests + 直接相关 regression + 必要 smoke。只有跨模块、高风险、平台相关或准备重要合并时，才要求更广的测试。

CI 是证据，不是单独 Gate。CI 不可用但本地/运行时证据已经足够时，可记录残余风险后继续推进。

PR head 在最终合并前必须确认没有意外变化，但不为普通任务单独建立“exact-head evidence Gate”。

研究/数据域已有的 `G0-G5`、`C0-C3` 等业务准入边界，在确实影响研究结论、PIT、数据来源或 production allocation 时继续适用；它们不是多窗口协作审批链。

## 7. 最小安全底线

以下底线用于防止真实数据或本机环境被误伤，不得扩张成企业级安全或发布治理工程：

```text
UNKNOWN_PROCESS_KILL = FORBIDDEN
DESTRUCTIVE_DB_WRITE = EXPLICIT_ONLY
DB_RESTORE = EXPLICIT_ONLY
SCHEMA_MIGRATION = EXPLICIT_SCOPE_ONLY
UNKNOWN != ZERO
MISSING != ZERO
```

涉及凭据时只允许从安全环境/忽略文件读取，不得写入版本控制或公开日志。

任何真实数据、外部来源或 PIT 证据不足时，必须保持真实的 `PARTIAL` / `DATA_BLOCKED` / `UNRESOLVED`，不得用 fixture、默认值、零填充或偶发成功伪造完整性。

## 8. 外部集成与研究实现

- 开发外部集成、复杂依赖或不确定实现时，优先检查官方文档与可复用成熟方案；只有这能实际降低实现/维护成本时才扩大调研。
- 新增数据源、因子、风险模型、资产评分、配置权重或研究输出时，按直接相关的研究/数据准入文档执行，不为无关任务重复加载整套研究材料。
- 同一外部集成问题经过两次有区分度且受控的尝试仍失败后，停止局部反复试错；记录真实阻塞并转向可并行工作。
- `UNKNOWN`、`MISSING`、网络失败、授权不明、PIT 不足和 provider 偶发成功必须保持语义区分。

## 9. 冲突处理

如果 actual `main`、当前 dispatch、目标 PR 或当前业务契约之间存在实质冲突，报告 `GOVERNANCE_DRIFT` 或 `COORDINATION_BLOCKED` 并交由 WEB-CONTROL 处理。

只有真正的文件/逻辑表面重叠才需要协调；不要为历史上曾经相关但当前没有并发修改的工作制造阻塞。
