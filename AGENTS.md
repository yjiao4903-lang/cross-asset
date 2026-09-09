# Cross-Asset 项目级协作规则

## 多窗口治理启动规则

- GitHub 是本项目唯一事实源。任何新窗口开始工作前，必须重新读取 actual `main`、本文件、`docs/CURRENT_STATE.md`、`docs/project_management/ROLE_REGISTRY.yml`、`docs/project_management/MULTI_WINDOW_GITHUB_OPERATING_MODEL.md`、`docs/tasks/INDEX.md`、Control Issue `#35`、自己的 active dispatch，以及相关 REQ / Issue / PR / CI / Gate 证据；不得依赖旧聊天记录判断当前状态。
- 当前固定逻辑身份只有：`WEB-CONTROL`、`GPT-DEV`、`GROK-DEV`、`LOCAL-DEV`。任何开发窗口不得自封 WEB-CONTROL、不得通过“主力执行者”身份获得架构或 merge 权限。
- `No GitHub dispatch = NO WORK`。打开的旧 PR 不等于自动分配给新窗口；任何接管、继续开发、rebase、重构或合并必须有 WEB-CONTROL 的 GitHub 记录。
- 新治理分支必须使用身份前缀：`gpt/`、`grok/`、`local/`、`control/` 或 `governance/`，并在 PR 中填写逻辑 Role / Workstream / baseline / overlap / tests / CI / exact-head / production-impact 契约。
- 多窗口并行默认禁止修改同一生产文件集或同一逻辑表面。发现 material overlap 时，后进入窗口必须返回 `COORDINATION_BLOCKED`，除非 WEB-CONTROL 已在 Issue 中定义安全拆分。
- 协作门禁统一使用 `WG0-WG9`，与研究/因子准入 `G0-G5` 区分。CI 通过只是 Gate 证据，永远不等于 `MERGE_APPROVED`；只有 WEB-CONTROL 可以针对 exact PR head 发布 `MERGE_APPROVED`。
- 如果聊天、旧 prompt、Control Issue、REQ、PR 或实际 main 之间出现冲突，不得自行猜测或静默修正，应报告 `GOVERNANCE_DRIFT` 并由 WEB-CONTROL 先修复 GitHub 事实源。
- 生产写入、Schema Migration、Release、Cutover 和不可逆操作默认 `NOT_AUTHORIZED`；必须由 WEB-CONTROL 显式授权。

## 研究、数据与实现规则

- 开发任何复杂功能前，必须先检索官方文档、成熟开源项目、官方 issue 和高质量社区实践，确认是否已有可复用的库、组件、架构或故障解决方案；先形成“直接复用、适配集成或必要自研”的简短判断，再开始编码，避免重复造轮子。候选方案必须同时审查许可证兼容性、安全风险、维护活跃度、依赖成本、接口稳定性及与本项目数据边界的适配性；不得仅因存在开源实现就未经评估直接引入。
- 涉及数据扩充、因子新增、资产评分、风险模型、配置权重、研究输出或 allocation 演进的开发任务，必须先阅读 `docs/CROSS_ASSET_RESEARCH_ENRICHMENT_ROADMAP_v1_20260909.md`，按其中的 Factor/Series Admission Contract 与 G0-G5 门禁执行；不得跳过研究准入直接将候选数据或因子接入 production allocation。
- 任何新增/替换数据源、要求用户提供数据、接入 Wind/iFind、构建市场/宏观/估值/利率/信用/期货曲线数据时，必须同时阅读 `docs/DATA_AVAILABILITY_AND_SOURCE_STRATEGY_v1_20260909.md`。默认顺序是“官方公共自动源 → 经审计的公共 adapter → Professional Data Bridge → 最小一次性人工 backfill”；在前三级未被有证据地排除前，不得把可自动取得的数据转嫁给用户手工导出。
- Professional Data Bridge 的实现与能力探测必须遵循 `docs/tasks/REQ-PROFESSIONAL-DATA-BRIDGE-W1-20260909.md`；专业源可用只代表 source capability，不代表 PIT verified、accepted、OOS validated 或 production ready。
- 同一外部集成、网络或依赖问题，经过两次有区分度且受控的尝试仍失败后，立即停止局部参数反复试错；不得无限重试、隐藏失败或把偶发成功当作稳定性证据。
- 继续验证前，先检索并记录官方文档、官方 issue/状态页及高质量社区经验，形成已知故障模式、适用条件、替代方案和证据链接；只有新证据支持时才进行一次针对性验证，否则标记阻塞并转向可并行工作。
- 凭据只允许从安全环境/忽略文件读取，任何输出、日志、异常、URL、raw 内容、artifact 和测试断言都必须脱敏；不得把凭据写入命令行参数或版本控制。
- 真实 Live 数据必须保留来源、权限、PIT/available_at 和可复核证据；证据不足时保持 PARTIAL/BLOCKED，整体 `DATA_BLOCKED` 边界不得被绕过，不得伪造 Live、审批或生产就绪结论。
- 网络失败、授权不明、PIT 不足和 provider 偶发成功必须分别记录，不能互相降级掩盖；所有受控运行应保留安全错误和停止原因。
