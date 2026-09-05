# REQ-CA-EXTDATA-W1 — Cross Market Stress & Positioning Data Pack

**Repository**：`yjiao4903-lang/cross-asset`  
**建议 Issue**：`REQ-CA-EXTDATA-W1: market stress and positioning data pack after audit gates`  
**优先级**：W1，但受现有稳定性门禁约束  
**任务编制时已知 main**：`bec52fe84f7a6480cb5dc1ef5b4d10d1634c6167`  
**必须先读**：根目录 `AGENTS.md`、Issue #22、#18、#19；如涉及 run/report wiring，再读 #20。

## 1. 核心目标

补齐 Cross 当前主要基于 realized volatility 的风险体系中三个独立信息维度：

1. **Market Stress**
   - VIX level
   - VIX term structure
   - HY credit stress
   - BAA long-history shadow proxy

2. **US Positioning**
   - CFTC Disaggregated
   - CFTC TFF

3. **China Leverage Positioning**
   - 融资融券余额/变化/分位
   - CFFEX 暂留 P1

这些信号默认只允许：

```text
WARNING
RISK_FILTER
DIAGNOSTIC
CROWDING
```

禁止直接转成：

```text
LONG
SHORT
BUY
SELL
directional alpha
```

## 2. 与当前 #18/#19/#22 的依赖

### Gate C0 — 现在允许

无需等待 #18/#19 完成即可做：

- requirements/audit docs；
- source identity；
- canonical definition；
- parser；
- raw snapshot fixture；
- PIT/release policy；
- shadow archive layout；
- source health contract；
- tests；
- research-only transform。

C0 不允许：

- 正式 factor 权重；
- allocation multiplier；
- production ACTIVE/FROZEN wiring；
- 绕过 approved-observations query；
- 宣称 live-ready。

### Gate C1 — #18 完成后

才允许：

- production ingestion；
- acceptance registry；
- approved-observations consumption；
- source health/freshness；
- production data path。

### Gate C2 — #19 完成后

才允许：

- risk filter 与 AllocationResult 的正式交互；
- positioning 仍不得直接生成方向。

### Gate C3 — #20 运行对象稳定后

才允许：

- report/explain/run artifact 展示；
- 同 run_id 可追溯。

门禁未满足时：
- 可合并 C0 基础能力；
- production wiring 必须 disabled/shadow；
- fixture 不能满足 real-data gate。

## 3. 子包 CA-W1A — Risk Stress Pack

### 3.1 `RISK_VIX_LEVEL`

原始 VIX close。

### 3.2 `RISK_VIX_TS`

正式唯一公式：

```text
RISK_VIX_TS = VIX / VIX3M
```

语义：

```text
< 1 : normal contango
≈ 1 : flat
> 1 : backwardation / stress
```

禁止继续沿用研究报告中错误/混用的 `<0.95 = backwardation` 表述。

本轮不先写死 1.05/1.10 等生产阈值；阈值属于后续 calibration/research。

### 3.3 `RISK_HY_OAS`

当前 HY OAS stress series。

要求：
- source identity 明确；
- 现有免费历史截断风险必须保留本地 raw archive；
- 不能假设 FRED 永久提供完整历史。

### 3.4 `RISK_BAA10Y`

Moody's Baa − 10Y Treasury 的 long-history **shadow proxy**。

必须明确：

```text
RISK_BAA10Y != RISK_HY_OAS
```

禁止：
- 历史拼接；
- 共享绝对 bp 阈值；
- 把 BAA 当作 HY OAS 完全同义 fallback。

允许：
- direction confirmation；
- rolling percentile shadow；
- source-health divergence warning。

### 3.5 第一阶段输出

```text
risk_state
stress_level
warning
data_health
source_status
```

不直接生成 asset direction。

### 3.6 必测边界

- VIX3M 缺失；
- VIX/VIX3M publication cutoff 不一致；
- denominator <= 0；
- HY OAS 截断；
- BAA 与 HY 方向背离；
- stale；
- unapproved；
- `available_at > decision_time`。

## 4. 子包 CA-W1B — CFTC Positioning Pipeline

### 4.1 第一批市场

**Disaggregated Futures+Options**
- Gold
- Copper

**TFF Futures+Options**
- S&P 500
- US Treasury 10Y

contract/report mapping 必须集中配置，不能散落模型代码。

### 4.2 PIT 时间语义

```text
observation = Tuesday
publication = Friday 15:30 ET
available_at >= actual publication
```

回测禁止 Tuesday–Friday 提前使用。

### 4.3 原始字段

至少保存：

- market / contract identity
- report date
- report type
- participant category
- long
- short
- spreading（如有）
- open interest
- source file/year
- publication time
- available_at
- ingested_at
- raw/source hash

### 4.4 派生

允许：

- net position
- % open interest
- rolling percentile
- causal z-score

建议：
- rolling percentile 3Y；
- z-score 只使用当时已知历史。

禁止：

- 极端多头 => 自动 short；
- 极端空头 => 自动 long。

### 4.5 测试

- 周二 observation / 周五 publication；
- holiday publication shift；
- yearly ZIP schema 差异；
- contract rename / mapping；
- duplicate report；
- revised/republished raw file；
- missing participant category；
- stale data；
- future leakage。

## 5. 子包 CA-W1C — China Leverage Positioning

### 5.1 第一阶段只实现两融

建议 canonical：`POS_CN_RZRQ`

基础数据：

- 融资余额；
- 融券余额（若口径持续稳定）；
- 两融余额合计；
- observation date；
- publication/available_at；
- provider identity。

优先派生：

1. 日变化；
2. 20D change；
3. 60D change；
4. rolling percentile。

若 free-float market cap denominator 能稳定、PIT 地获得，再追加 `RZRQ / free-float market cap`；否则不要硬拼 denominator。

### 5.2 CFFEX

CFFEX 前 20 会员继续 P1：

- 不作为本轮 PR 必须项；
- 遇到高反爬、口径复杂或稳定性差时不扩大 scope；
- 不允许 CFFEX 阻塞两融主 PR。

### 5.3 北向

明确 Reject：

- 不重新建立 Northbound net-buy production factor；
- 历史可研究；
- 不用第三方聚合伪造官方已经停止披露的前瞻序列。

## 6. 数据准入

必须复用 #18 最终形成的 approved-observations 规则。

每条正式 source 至少绑定：

```text
series_id
provider
source_series_id / contract identity
usage
registry_status
PIT grade
quality
available_at
reviewer / approved_at（若 #18 最终 gate 要求）
```

#18 未完成前：

```text
production usage = disabled/shadow
```

允许：
- fixture；
- parser；
- raw archive；
- source contract；
- research transform。

## 7. Shadow Archive

所有外部 P0/P1 source 应有最小 raw archive，优先复用仓库已有目录模式。

建议逻辑：

```text
data/raw_external/<provider>/<series>/<date>/...
```

至少记录：fetch time、URL/endpoint identity、source status、raw SHA-256、parser version、row count、min/max observation date、warning、failure reason。

禁止保存 token / credential。

## 8. Source Health

至少输出：

```text
last_success_at
latest_observation
latest_available_at
freshness
source_status
parser_status
coverage_status
```

状态建议：

```text
HEALTHY
STALE
PARTIAL
FAILED
UNAPPROVED
DATA_BLOCKED
```

一次 fetch success 不能作为“源稳定”的证据。

## 9. 与现有 risk/factor 的关系

当前 risk 主要依赖 realized `vol_20d`。

本轮新增应保持正交：

```text
Realized Vol
    +
Implied Vol Term Structure
    +
Credit Stress
    +
Positioning / Crowding
```

第一阶段输出独立状态，不设计复杂 composite optimizer。

## 10. 禁止事项

- 不改 strategic weights；
- 不改 `max_tactical_tilt`；
- 不趁本任务重构 Allocation；
- 不引入 GEX / CTA / MOVE 商业黑盒；
- 不把 BAA 和 HY OAS 拼接；
- 不用 AUM change 代替 flow；
- 不重新引入北向净买入生产依赖；
- 不静默用 Yahoo/社区镜像替代 Tier-1；
- 不宣称 CFTC/两融可以直接预测方向；
- 不使用未来发布时间；
- 不让 fixture 满足 real-data gate。

## 11. 推荐 PR 拆分

### PR A — Risk Stress

Branch：`feature/extdata-w1-risk-stress`  
Title：`feat: add external market stress data pack`

### PR B — CFTC

Branch：`feature/extdata-w1-cftc-positioning`  
Title：`feat: add CFTC positioning pipeline`

### PR C — China Leverage

Branch：`feature/extdata-w1-cn-leverage`  
Title：`feat: add China leverage positioning input`

禁止三个包塞入一个 PR。

## 12. PR/Issue 验收

每个 PR 必须：

- 回链 REQ Issue；
- 标明 #18/#19 gate；
- 明确当前做到 C0/C1/C2/C3 哪层；
- tests + CI；
- real source 是否验证；
- raw archive 是否存在；
- PIT 是否验证；
- source health 是否验证；
- fixture/live 分离；
- 不 merge，由 WEB-CONTROL 验收。

Issue 回传：

```md
## Implementation update

- Task baseline:
- Current origin/main:
- Gate reached: C0/C1/C2/C3
- Branch:
- Head:
- PR:
- Scope completed:
- Tests:
- CI:
- Real-data status:
- PIT status:
- Source-health status:
- Known blockers:
- Out-of-scope findings:
- Merge recommendation:
```
