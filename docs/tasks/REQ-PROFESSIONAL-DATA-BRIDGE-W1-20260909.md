# REQ-PROFESSIONAL-DATA-BRIDGE-W1 — Professional Data Bridge

**Repository**：`yjiao4903-lang/cross-asset`  
**Priority**：W1 / P0 infrastructure for research enrichment  
**Task baseline date**：2026-09-09  
**Status**：`IMPLEMENTATION_REQUIREMENT`  
**Must read first**：`AGENTS.md`、`docs/DATA_AVAILABILITY_AND_SOURCE_STRATEGY_v1_20260909.md`、`docs/CROSS_ASSET_RESEARCH_ENRICHMENT_ROADMAP_v1_20260909.md`、`docs/DATA_ACCEPTANCE_GATE.md`。

---

## 1. Goal

建立本地 Professional Data Bridge，使 Cross-Asset 可以在**不要求用户长期手工导 Excel**的前提下调用已合法授权的 Wind / iFind 数据能力，并只把专业数据用于公开免费源无法可靠覆盖的高价值研究缺口。

首轮目标不是“接入所有 Wind/iFind 数据”，而是回答：

```text
当前本机到底有哪些专业数据能力？
哪些 P0 研究序列可以自动取得？
哪些确实需要一次性用户操作？
```

---

## 2. Required CLI

新增只读 capability probe：

```text
cross-asset probe-professional-data
```

建议参数：

```text
--provider auto|wind|ifind
--output <json>
--no-network   # 如 vendor SDK 支持本地 capability-only 检查
```

CLI 必须 fail closed，不得因为 SDK import 成功就宣称数据可用。

---

## 3. Capability contract

至少输出：

```json
{
  "generated_at": "<ISO>",
  "providers": {
    "wind": {
      "sdk_available": false,
      "authenticated": false,
      "usable": false,
      "safe_status": "NOT_AVAILABLE"
    },
    "ifind": {
      "sdk_available": false,
      "authenticated": false,
      "usable": false,
      "safe_status": "NOT_AVAILABLE"
    }
  },
  "capabilities": {
    "cn_rates": false,
    "cn_credit": false,
    "valuation": false,
    "consensus": false,
    "global_futures_curve": false,
    "index_constituents": false
  },
  "credential_exposure": false,
  "recommendation": "PUBLIC_ONLY|PROFESSIONAL_READY|MANUAL_BACKFILL_NEEDED"
}
```

不得输出：

- username
- password
- token
- session identifier
- vendor account id
- entitlement raw payload
- 含敏感信息的 exception string

---

## 4. Provider adapters

建议新增：

```text
src/cross_asset/providers/professional/
  __init__.py
  base.py
  wind.py
  ifind.py
  capability.py
```

若现有 provider 目录结构更适合小范围扩展，可适配现有结构，但必须保持 provider-specific code 与 canonical model 分离。

### 4.1 Wind

允许使用 vendor-supported WindPy / local authenticated terminal/session。

首轮只验证：

- SDK import
- session start/status
- minimal metadata/data probe
- entitlement-safe capability inference

禁止首轮大量拉数。

### 4.2 iFind

允许使用 vendor-supported iFinDPy / official Data API。

凭据只能从本地安全配置读取。

若账号只有终端权限但没有 Data API entitlement，必须明确：

```text
sdk_available = true
authenticated = false/partial
usable = false
recommendation = MANUAL_BACKFILL_NEEDED or PUBLIC_ONLY
```

禁止把网页登录能力当成 API capability。

---

## 5. First capability groups

### P0-A — CN Rates

Probe 能否取得：

- CGB 1Y / 2Y / 5Y / 10Y / 30Y
- CDB 5Y / 10Y
- DR007
- NCD representative series

### P0-B — CN Credit

Probe 能否取得：

- AAA 3Y / 5Y
- AA+ 3Y / 5Y
- stable spread components

### P0-C — Valuation

Probe 能否取得长期历史：

- CN broad index PE / PB / dividend yield
- HK broad valuation
- forward PE / consensus EPS if licensed

### P1 — Commodity structure

Probe Gold / Copper / Oil front/2nd/3rd settlement/OI capability。

### P2 — Optional

- consensus revisions
- selected option indices
- institutional flow / ETF flow if licensed

---

## 6. Capability != production approval

Probe success 只意味着：

```text
SOURCE CAPABILITY EXISTS
```

不意味着：

```text
PIT VERIFIED
SEMANTICS VERIFIED
ACCEPTED
LIVE READY
OOS VALIDATED
PRODUCTION ACTIVE
```

任何正式 series 必须继续走现有 acceptance / provenance / PIT / research admission。

---

## 7. Credential rules

必须遵守：

- `.env` / OS credential store / vendor-native session only；
- `.env.example` 只能放变量名，不放真实值；
- 不把密码放 CLI argument；
- 不在 logging / traceback / artifact 输出 credential；
- test fixtures 只使用 fake credential；
- CI 不应依赖真实专业账号。

若 vendor SDK 异常会返回敏感字段，adapter 必须 sanitize。

---

## 8. Manual fallback

只有 capability probe 确认专业 API 不可用时，才生成用户操作清单。

用户操作必须自动压缩为最小 pack：

```text
Pack A: cn_rates_credit_valuation
Pack B: derivatives_structure
```

程序应生成：

```text
artifacts/professional_data/manual_backfill_requirements.json
```

内容应只列真正缺失且高优先级的数据，不重复请求已可由 public source 自动取得的 PMI/CPI/PPI/M1/M2/TSF/两融等。

---

## 9. Public-source precedence

Professional Bridge 不得覆盖已有稳定官方公共源，仅因“Wind 更方便”就将其替换。

默认：

```text
Official public source
    > professional source as validation/backup
```

以下例外可让 professional 成为 primary：

- public history insufficient
- public semantics unstable/incomplete
- entitlement-restricted market data legitimately available locally
- valuation/consensus/curve data where professional DB is materially superior

例外必须写入 source mapping notes。

---

## 10. Acceptance tests

必须覆盖：

1. no SDK installed；
2. SDK installed but not authenticated；
3. authenticated but entitlement missing；
4. provider timeout/network failure；
5. successful safe probe；
6. exception contains fake credential -> output sanitized；
7. repeated probe is idempotent；
8. public-only environment remains fully usable；
9. fixture cannot promote professional series to live acceptance；
10. manual fallback contains only unresolved professional gaps。

---

## 11. Recommended PR split

### PR A — capability contracts and CLI

Branch：`feature/professional-data-capability`

- base contracts
- safe status
- CLI
- tests

### PR B — Wind adapter

Branch：`feature/professional-data-wind`

### PR C — iFind adapter

Branch：`feature/professional-data-ifind`

### PR D — P0 source mappings

Only after capability + semantics/PIT evidence。

禁止把 capability probe、P0 大量拉数、allocation wiring 塞入同一个 PR。

---

## 12. Definition of done for W1

W1 完成意味着：

- 用户可运行一个命令知道专业数据能力；
- credential 不泄漏；
- 系统知道哪些数据由 public 自动解决；
- 系统知道哪些关键数据专业接口可取；
- API 不可用时只产生最小人工 backfill 清单；
- 没有任何候选专业数据绕过 acceptance / PIT / research gate。

W1 **不意味着**任何新因子已经进入 production allocation。
