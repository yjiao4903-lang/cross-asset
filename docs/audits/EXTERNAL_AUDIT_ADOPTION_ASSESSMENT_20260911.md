# Cross-Asset 外部审计吸收评估与后续开发基线

- **Document type**: WEB-CONTROL audit adoption record
- **Assessment date**: 2026-09-11
- **Repository**: `yjiao4903-lang/cross-asset`
- **Frozen assessment baseline**: `94bea2ca3c393a25b181fc8a85848d12a90192aa`
- **Authority**: WEB-CONTROL
- **Status**: `ADOPTED_AS_PLANNING_REFERENCE`
- **Execution effect**: 本文不是开发 dispatch，不自动激活任何 Issue / OOS / holdout，也不授权 production write。

## 1. 目的

本文把 2026-09-11 外部详细审计的结论，结合 WEB-CONTROL 对当前 `main` 的源码复核，固化为后续开发与评估的长期参考。

采用原则：

> 默认最大程度吸收审计建议；只有在建议会破坏既有研究冻结、重复建设 admission/provenance 架构、或者迫使项目猜测真实数据语义时才调整。

当前总体判断：外部审计的方向与项目目标高度一致，绝大多数建议应吸收。项目的主要瓶颈已经从“基础研究设施缺失”转向：

1. 真实数据到用户输出的最后一公里；
2. PERSONAL_WEEKLY 用户可见状态的真实性；
3. 周度比较的时间与来源可比性；
4. research proxy 与真实可投资收益/持仓之间的差距；
5. Formal OOS 前的可计算性与语义完整性。

本项目仍定位为个人/内部研究工作台，不升级为大型企业生产平台。

---

## 2. 当前控制结论

```text
SCIENTIFIC_CRITICAL_PATH = REAL_DATA_FIRST
PRODUCT_CORRECTNESS_PATH = WEEKLY_TRUST_FIXES_REQUIRED
FORMAL_OOS = BLOCKED
HOLDOUT = SEALED
INFRASTRUCTURE_EXPANSION = NOT_JUSTIFIED
NO_PROXY_SUBSTITUTION = TRUE
NO_GUESSED_SOURCE_SEMANTICS = TRUE
```

两条产品/研究线并行但不可互相提升状态：

```text
PERSONAL_WEEKLY
real/public inputs
-> comparability/source validation
-> Weekly Fact Pack
-> claims/scenarios
-> human decision
-> later evaluation

FORMAL_RESEARCH
immutable raw
-> semantic contract
-> RESEARCH_ADMISSIBLE
-> PIT/accounting/readiness
-> frozen OOS
-> benchmark/cost/uncertainty
```

两条线可以共享 canonical identity、provenance、PIT primitives、sanctioned query 与数据合同，但 PERSONAL_WEEKLY 的成功不能自动构成 formal research admission；formal research gate 也不应阻塞普通周度研究产品迭代。

---

## 3. 审计建议的吸收决策

### A01 — Weekly lookback 可无限向历史回找

**Decision: ACCEPT / P0**

当前 `weekly_core` 的 prior lookup 只要求 `observation_date <= target_date`，没有 prior-date 最大偏移约束，可能把过旧数据标成 `1w` 或 `21d` 比较。

必须修复：

- lookback slippage 必须有可配置上限；
- 保存并输出 `target_date`、`actual_prior_date`、`slippage_days`；
- 不要求精确 7 个自然日，允许节假日/市场休市，但禁止无限回溯；
- 超出容忍范围时返回 `PARTIAL` / `NON_COMPARABLE`，不得用 0 或旧值伪装；
- `compare_weeks()` 必须验证 snapshot 是否真实相邻，否则不得表述为 “vs prior week”；
- prior observation 同样必须满足 `available_at <= decision/as_of`。

这是当前最高优先级的用户可见 correctness 问题之一。

### A02 — Weekly `source_status=ADMITTED` 过度声明

**Decision: ACCEPT / P0**

当前 weekly path 的 `ADMITTED` 实际只表达 provider 字符串匹配，不能与 formal `RESEARCH_ADMISSIBLE` 混同。

建议状态层级：

```text
UNVERIFIED
PROVIDER_MATCHED
CONTRACT_MATCHED
FORMAL_ADMITTED   # 仅当真实来自 formal admitted source 时
```

至少应立即把现有 provider-string-only 的 `ADMITTED` 改为 `PROVIDER_MATCHED`。

Weekly observation/input contract 应逐步补充：

- `provider`
- `source_series_id`
- `unit`
- `available_at`
- `evidence_ref`（可选但推荐）

不得建立第二套 weekly admission registry。应复用现有 series catalog、acceptance registry、manual intake sidecar 与 sanctioned query。

### A03 — Placeholder/no-op CLI 成功退出

**Decision: ACCEPT / P1**

命令应明确分为：

```text
IMPLEMENTED
FIXTURE_ONLY
NOT_IMPLEMENTED / RESERVED
```

要求：

- `NOT_IMPLEMENTED` / reserved 命令必须非零退出；
- fixture/offline 命令可以成功，但必须清楚声明 fixture / research-validity-not-claimed；
- 不为了消灭 placeholder 而实现所有未需要功能；
- README/CLI help 应区分真实入口、fixture、reserved command。

### A04 — ALFRED chunk helper 未进入标准 full-vintage collector

**Decision: ACCEPT_WITH_PRIORITY_ADJUSTMENT / P7**

该问题是真实的长期可重复性缺口，但不是当前最前面的科学阻塞。

后续应把 chunk orchestration 接入标准 collector，并支持：

- bounded vintage chunks；
- resume/cache reuse；
- chunk raw manifest；
- merge/dedup；
- chunk boundary 无重无漏 regression；
- 可从 durable entrypoint 重建 B07 类型证据。

不得因此否定已经接受的 B07 真实 evidence，也不得重开已冻结结果。

### A05 — PIT coverage 不等于模型输入可计算性

**Decision: ACCEPT_WITH_RESEARCH_GUARD / P6**

新增独立 diagnostic/preflight，而不是修改已经冻结的 B07 coverage 定义。

未来 readiness 至少区分：

```text
ADMISSION_READY
PIT_COVERAGE_READY
ACCOUNTING_SEMANTICS_READY
MODEL_INPUT_COMPUTABILITY_READY
```

`MODEL_INPUT_COMPUTABILITY` 可检查：

- latest observation period；
- required lag availability；
- normalization/z-score history；
- return start/end endpoints；
- FX endpoints；
- component-level computability；
- exact transform prerequisites。

所有新的 formal gating 语义必须在看 OOS 结果前冻结。

### A06 — Macro unit semantics helper 未被正式引擎强制执行

**Decision: ACCEPT / P6**

已有 unit-semantics primitive 应在 model config / macro definition validation 层变成可执行 guard。

要求：

- `raw_unit` / `derived_unit` / transform 不一致或 unresolved 时 fail closed；
- CN_CPI / CN_PPI / CN_M1 / CN_M2 等目前 unresolved 的定义不得因为导入真实文件而自动变 READY；
- 不建立新的平行 metadata 系统；
- 优先在 model config load/validation 处集中校验，再让 macro engine 只消费已验证定义。

---

## 4. 其他审计建议：默认吸收

以下方向直接进入产品/研究路线，不再单独争论其必要性：

1. PERSONAL_WEEKLY 最终不得要求用户长期手工维护 `observations.json`；应从真实 intake / sanctioned storage 自动形成 weekly input。
2. `compare_weeks()` 除时间邻接外，应验证 unit/provider/source-series 可比性。
3. research brief 中重复的 `computed_signals` 展示应清理。
4. bootstrap/README/CLI 的“成功”必须与真实可执行状态一致。
5. claim ledger、scenario、weekly facts 最终应连成可复盘的研究包。
6. 软件默认 `HOLD` 与“人工投资决定”必须分开表示。
7. 每个观点应能够追踪：当时已知事实、判断、证据、替代解释、后续是否被证伪。
8. 真实周复盘应衡量研究工作流质量，不用短期收益给产品做伪策略验证。
9. 真实 manual data 继续复用现有 Lane B：immutable raw + hash/sidecar + semantic validation + canonical import + admission + sanctioned query。
10. 专业终端保持用户侧人工导出来源，不重新建设 Wind/WindPy/终端自动化依赖。
11. 真实 holdings 后续只做最小上下文，不直接扩展成券商、P&L、VaR、自动交易平台。
12. 旧 PR 的处理原则为 `extract value, not resurrect branch`。
13. 老文档只做必要状态矫正，不重造文档治理系统。
14. 暂停扩大复杂 ML、更多因子族、自动交易、微服务、企业权限、大型 UI。
15. 复杂模型必须与 STATIC / TREND_ONLY / MACRO_ONLY / RISK_ONLY 等简单基线比较；简单模型若更稳健，保留简单模型是合法研究结论。

---

## 5. 明确不直接采用的方向

### 5.1 不重定义已经冻结的 B07 coverage

coverage 与 computability 必须成为两个指标。

禁止为了修 A05 事后改变原 coverage 的定义，以免造成研究协议漂移。

### 5.2 不建设第二套 PERSONAL_WEEKLY admission framework

PERSONAL_WEEKLY 可以有更丰富 provenance，但必须复用现有正式数据基础。

禁止出现另一套 weekly approval table / weekly registry / weekly provenance DB。

### 5.3 不为了周报完整度猜测真实数据语义

以下问题在证据不足时必须保持 `UNRESOLVED` / `PARTIAL`：

- GOLD 是 spot 还是 futures；
- COPPER 的连续合约、roll、adjustment；
- exact DXY 的真实来源与定义；
- CN CPI/PPI/M1/M2 原始单位、同比/环比/水平值语义；
- FX quote direction / fixing / close / timezone。

不允许 proxy substitution 或 silent fallback。

### 5.4 暂不建设完整 holdings/P&L/risk-budget/trading stack

真实持仓有长期价值，但当前只需要最小上下文。完整交易平台会显著偏离当前瓶颈。

### 5.5 暂不优先做自动故事排序

facts contract 与 comparability 尚未完全可信前，story ranking / narrative ranking 优先级低于事实正确性。

---

## 6. 吸收审计后的正式路线

### P0 — Weekly Trust Contract

目标：修 A01/A02 与 cross-week comparability。

预期结果：

- bounded lookback slippage；
- actual prior date disclosure；
- non-adjacent snapshot detection；
- provider/source-series/unit comparability；
- truthful source status；
- stale/non-comparable -> PARTIAL，而不是 fake READY。

### P1 — Surface Truthfulness Cleanup

目标：所有用户可见入口不再“假成功”。

范围：

- CLI exit semantics；
- fixture-only labels；
- README/bootstrap truthfulness；
- research brief duplicate cleanup；
- 小范围 stale docs 修正。

### P2 — #93 Real Data Admission

目标：用户真实文件逐条进入既有 Lane B，不重造框架。

建议顺序：

1. `CN_EQ_LARGE`, `HK_EQ`, `US_EQ`, `CN_BOND_10Y`；
2. USD/CNY, HKD/CNY；
3. GOLD, COPPER；
4. CN_PMI, CN_CPI, CN_PPI, CN_M1, CN_M2, CN_DR007；
5. exact DXY。

### P3 — Weekly Input Adapter

目标：真实 admitted/manual outputs -> weekly facts，减少手工 `observations.json`。

控制原则：先看到第一批真实 intake/sidecar/candidate 的实际形状，再固定 adapter；可先定义接口，但不要基于 fixtures 过早造复杂抽象。

### P4 — Weekly Research Packet

建议目标结构：

```text
weekly/YYYY-MM-DD/
    facts.snapshot.json
    brief.md
    scenarios.json
    scenarios.md
    decision.json
    manifest.json
```

claim ledger 可以继续保持全局 JSONL，由 manifest 引用 claim/evaluation/evidence IDs。

产品核心：

> what was known -> what was believed -> what was decided -> why -> later evaluation

### P5 — Real Data Expansion

补齐 FX、GOLD/COPPER、CN macro、DXY，并保持每条 source identity / available_at / unit / accounting semantics 明确。

### P6 — Pre-OOS Semantic Hardening

目标：

- model-input computability diagnostic；
- macro unit guard；
- return/accounting endpoint checks；
- FX timing/quote checks；
- GOLD/COPPER return/roll semantics readiness。

### P7 — Public Data Reproducibility

目标：ALFRED chunk/resume/full-vintage durable collector。

### P8 — Combined Readiness Rebuild

只使用 accepted code/config + immutable evidence，新建 combined readiness snapshot，不复用旧状态宣称 READY。

### P9 — Formal OOS #81

仅当既有 #81 条件全部满足后激活；holdout 在此之前持续 sealed。

---

## 7. 下一阶段设计要求

在真正派发 P0/P1 开发前，WEB-CONTROL 应把首批 work package 固化到以下粒度：

- goal；
- exact scope；
- files likely touched；
- contract changes；
- negative/positive test cases；
- user-visible behavior；
- explicit non-goals；
- acceptance criteria；
- interaction with #93/#81；
- whether real data is required。

普通工作继续遵循轻量协作：一次完整派发 -> 实现/测试/smoke/PR -> WEB-CONTROL 最终验收。

---

## 8. 真实周度使用的观察指标

真实周度运行用于评估产品工作流，不作为策略有效性 Gate。

建议记录：

- weekly data-prep minutes；
- manual copy/JSON steps；
- facts with evidence/provenance %；
- PARTIAL/BLOCKED 数量与原因；
- claim due/evaluated ratio；
- manual correction count；
- one-command regeneration success；
- source/semantic mismatch count；
- non-adjacent/non-comparable lookback count。

四周是推荐观察窗口，不是硬 Gate；发现明确问题可更早修正。

---

## 9. 当前研究不变量

```text
UNKNOWN_PROCESS_KILL = FORBIDDEN
DESTRUCTIVE_DB_WRITE = EXPLICIT_ONLY
DB_RESTORE = EXPLICIT_ONLY
SCHEMA_MIGRATION = EXPLICIT_SCOPE_ONLY
UNKNOWN != ZERO
MISSING != ZERO
NO_PROXY_SUBSTITUTION = TRUE
NO_SILENT_SOURCE_FALLBACK = TRUE
NO_ADMISSION_RELAXATION = TRUE
NO_GUESSED_SOURCE_SEMANTICS = TRUE
NO_OUTCOME_DRIVEN_TUNING = TRUE
NO_CROSS_WINDOW_DUCKDB_SYNC = TRUE
```

任何新建议、外部开源项目、数据源或宏观模型，必须先通过这些原则过滤。

---

## 10. 本文的使用方式

后续外部评审、GPT-DEV 任务设计、LOCAL real-data work、以及新功能路线判断，可以引用本文作为“2026-09-11 审计吸收基线”。

如未来 actual main 已显著变化，应新建增量评估文档，不应静默改写本文的历史判断。

本文不授权任何开发窗口自行开工；仍遵循 `No GitHub dispatch = NO WORK`。
