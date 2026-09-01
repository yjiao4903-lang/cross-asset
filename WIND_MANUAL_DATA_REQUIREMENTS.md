# Wind 人工取数需求（MVP）

本文档是本地跨资产引擎的人工导入操作单。Wind 仅用于补足中国市场、宏观与风格数据；它不是模型逻辑，也不要求用户提供账号密码、Token 或截图。当前 Yahoo/FRED 已覆盖的序列不需要重复导出：`US_EQ`、`HK_EQ`、`GOLD`、`COPPER`、`OIL`、`DXY`、`USDCNH` 可优先使用已验证的 Yahoo 数据；`US_GOV_10Y`、`US_REAL_10Y` 的核心宏观来源优先 FRED。`US_GOV_10Y` 的 Yahoo `^TNX` 只能作 auxiliary，默认 `semantic_equivalence=false`，不能替代 FRED。

## 1. 取数优先级

- **P0 Live Gate/中国桥**：`CN_EQ_LARGE`、`CN_EQ_SMALL`、`HK_EQ`、`CN_BOND_10Y`。
- **P1 中国宏观 PIT**：`CN_PMI`、`CN_CPI`、`CN_PPI`、`CN_M1`、`CN_M2`、`CN_SOCIAL_FINANCING`、`CN_DR007`。
- **P2 风格增强**：可合法定义 SIZE/GROWTH/CYCLICAL/TECH 的指数对；优先日频、价格口径一致、长期稳定的指数。

## 2. 单序列需求

Wind 代码只有在终端核对过后才能填写。下表中的“候选代码”均为搜索提示，不是未经核验的事实代码。

| canonical id | 中文名 | Wind 代码/候选 | 类型/频率 | 首次区间 | 单位/币种 | 口径、时区 | PIT/版本 | critical/用途 |
|---|---|---|---|---|---|---|---|---|
| CN_EQ_LARGE | 中国大盘权益 | 需在Wind终端确认；关键词：沪深300、中证大盘、large cap index | 指数日频 | 2010-01-01至今 | index points / CNY | 价格指数或全收益必须明确；Asia/Shanghai；不默认复权 | observation_date=交易日；available_at=收盘后可用时间；如无精确时间，采用保守次日 00:00；vintage按导出版本 | P0；中国权益桥 |
| CN_EQ_SMALL | 中国小盘权益 | 需在Wind终端确认；关键词：中证1000、中证小盘、small cap index | 指数日频 | 2010-01-01至今 | index points / CNY | 必须与 CN_EQ_LARGE 明确同口径 | 同上；保留 vintage_date/is_final | P0；SIZE |
| HK_EQ | 港股权益 | 已有 Yahoo 主源；Wind 仅 backup，代码需终端确认；关键词：恒生指数/港股宽基 | 指数日频 | 2010-01-01至今 | index points / HKD | 仅在与主源语义等价时才可人工替换 | 交易日、收盘发布时间 | P0 backup；默认 semantic_equivalence=false |
| CN_BOND_10Y | 中国10年国债 | 需在Wind终端确认；关键词：中债国债10年到期收益率、10Y CGB yield | 收益率日频 | 2010-01-01至今 | percent / CNY | 到期收益率/估值收益率须写清；Asia/Shanghai | available_at 为发布/收盘可用时点；保留修订版本 | P0；中国债券桥 |
| CN_PMI | 中国制造业PMI | 需在Wind终端确认；关键词：中国制造业采购经理指数 PMI | 宏观月频 | 2005-01-01至今 | index / CNY | 公告值，不是收盘值 | observation_date=统计月份末；available_at=国家统计局公告时间，未知则次月1日后保守 lag；vintage/revision 必须保留 | P1；Macro |
| CN_CPI | 中国CPI | 需在Wind终端确认；关键词：居民消费价格指数 CPI 当月同比 | 宏观月频 | 2005-01-01至今 | percent / CNY | 同比/环比需分开 | 以正式公告时间为 available_at，不得填月份末 | P1；Macro |
| CN_PPI | 中国PPI | 需在Wind终端确认；关键词：工业生产者出厂价格指数 PPI 当月同比 | 宏观月频 | 2005-01-01至今 | percent / CNY | 同比/环比需分开 | 同 CN_CPI | P1；Macro |
| CN_M1 | 中国M1 | 需在Wind终端确认；关键词：M1同比/余额 | 宏观月频 | 2005-01-01至今 | percent 或 CNY bn / CNY | 增速或余额必须明确 | 以央行/统计公告发布时间为 available_at；保留 revision | P1；流动性 |
| CN_M2 | 中国M2 | 需在Wind终端确认；关键词：M2同比/余额 | 宏观月频 | 2005-01-01至今 | percent 或 CNY bn / CNY | 与 M1 采用同类口径 | 同上 | P1；流动性 |
| CN_SOCIAL_FINANCING | 社会融资规模 | 需在Wind终端确认；关键词：社会融资规模存量/增量 | 宏观月频 | 2010-01-01至今 | CNY bn / CNY | 存量与增量不可混用 | 公告时间；保留 revision | P1；信用 |
| CN_DR007 | 银行间质押式回购7天利率 | 需在Wind终端确认；关键词：DR007、存款类机构质押式回购 | 利率日频 | 2015-01-01至今 | percent / CNY | 加权利率口径确认 | observation_date=交易日；available_at=收盘/发布后；必要时保守次日 | P1；流动性 |
| CN_GROWTH_LHS/RHS | 成长/价值指数对 | 需在Wind终端确认；关键词：中证成长、中证价值、成长价值风格指数 | 指数日频 | 2010-01-01至今 | index points / CNY | 需同一编制机构、价格或全收益一致 | 交易日收盘后 | P2；GROWTH；代码未确认前 UNAVAILABLE |
| CN_CYCLICAL_LHS/RHS | 周期/防御指数对 | 需在Wind终端确认；关键词：周期、防御、行业风格指数 | 指数日频 | 2010-01-01至今 | index points / CNY | 明确成分与指数口径 | 同上 | P2；CYCLICAL；未确认前 UNAVAILABLE |
| CN_TECH_LHS/RHS | 科技/红利指数对 | 需在Wind终端确认；关键词：科技、红利、科技红利指数 | 指数日频 | 2010-01-01至今 | index points / CNY | 明确成分、价格/全收益 | 同上 | P2；TECH；未确认前 UNAVAILABLE |

## 3. Excel 导出模板

文件可为 `.xlsx` 或 `.csv`，每行一条观察。统一必填列：

```text
series_id,source_series_id,observation_date,available_at,value,unit,currency,timezone,vintage_date,is_final,source
```

Market daily 模板：上述必填列；`observation_date` 为交易日，`available_at` 为收盘后实际可用时刻；可选 `adjustment、price_type、notes`。

Macro monthly/release 模板：上述必填列；另外建议 `release_time、release_agency、revision_no、release_lag_days`。`observation_date` 是统计期，不是公告日；`available_at` 必须是公告发布时间，未知时使用保守 lag 并标注 `quality=pIT_conservative_lag`。

Style daily 模板：上述必填列；另外建议 `axis、side`，其中 `side=lhs/rhs`；两边必须有同一交易日、同一价格/全收益口径。

`available_at` 绝不能用 `observation_date` 代替。宏观数据若只有月份而没有公告时间，必须明确标记保守滞后，不能假装精确 PIT。`vintage_date` 不可随意留空；若 Wind 导出的是当前修订值，应标 `is_final` 并在 notes 说明无法重建历史 vintage。

## 4. Wind 操作步骤

1. 在 Wind 终端搜索关键词，先核对名称、编制机构、价格/全收益、币种、频率和修订规则。
2. 打开历史数据/时间序列导出，设置完整起止日期与日历，不要只导出屏幕可见区间。
3. 核对首行、末行、缺失值、单位和小数位；收益率与指数点不要混在同一文件。
4. 导出后补齐统一必填列；从公告或资料记录 `available_at`，不要复制 `observation_date`。
5. 将文件放入 `data/manual_inbox/`，不要改写历史归档文件。
6. 交付前计算 SHA-256，并保留 Wind 代码、口径、导出时间和权限说明在伴随 notes 中。

## 5. 文件命名、版本和幂等

建议命名：`{template_id}_v{version}_{YYYYMMDD}.xlsx`，例如 `market_daily_v1_20260831.xlsx`、`macro_release_v1_20260831.xlsx`、`style_daily_v1_20260831.xlsx`。模板必须有 `template_id`、`version`、required columns 和 mapping。导入器应按 `file_sha256` 幂等：相同文件重复导入不得产生重复 observations；成功后移至 `data/manual_archive/`，原始文件不可覆盖。

## 6. 首次批次与验收

建议顺序：先交 P0 四条（各至少 10 年），再交 P1 宏观（至少 15 年，能提供公告时间最好），最后交 P2 风格（至少 10 年）。导出前检查代码/口径/日期/单位/时区；导出后检查必填列、重复日期、NaN、未来 available_at、时间单调性、SHA-256、source_series_id 和语义等价声明。

常见错误：把公告月末当可用时间；把全收益当价格指数；把收益率当价格；用不同机构的成长/价值指数直接相除；把 Wind 当前修订值当历史 vintage；把 `^TNX` 当 FRED `DGS10` 的等价替代；同一文件改名后重复导入。

示例（仅展示格式，数值为占位符，不是真实数据）：

```csv
series_id,source_series_id,observation_date,available_at,value,unit,currency,timezone,vintage_date,is_final,source
CN_EQ_LARGE,WIND_CODE_TO_CONFIRM,2025-01-02,2025-01-02T15:30:00+08:00,<VALUE>,index_points,CNY,Asia/Shanghai,2025-01-02,false,wind_manual
CN_EQ_SMALL,WIND_CODE_TO_CONFIRM,2025-01-02,2025-01-02T15:30:00+08:00,<VALUE>,index_points,CNY,Asia/Shanghai,2025-01-02,false,wind_manual
CN_BOND_10Y,WIND_CODE_TO_CONFIRM,2025-01-02,2025-01-03T00:00:00+08:00,<VALUE>,yield_percent,CNY,Asia/Shanghai,2025-01-02,true,wind_manual
CN_PMI,WIND_CODE_TO_CONFIRM,2024-12-31,2025-01-01T09:30:00+08:00,<VALUE>,index,CNY,Asia/Shanghai,2025-01-01,true,wind_manual
CN_GROWTH_LHS,WIND_CODE_TO_CONFIRM,2025-01-02,2025-01-02T15:30:00+08:00,<VALUE>,index_points,CNY,Asia/Shanghai,2025-01-02,false,wind_manual
```

## 7. 最小交付清单

- `market_daily_v1_YYYYMMDD.xlsx`：CN_EQ_LARGE、CN_EQ_SMALL、HK_EQ、CN_BOND_10Y（P0）。
- `macro_release_v1_YYYYMMDD.xlsx`：CN_PMI、CN_CPI、CN_PPI、CN_M1、CN_M2、CN_SOCIAL_FINANCING、CN_DR007（P1）。
- `style_daily_v1_YYYYMMDD.xlsx`：经终端确认的三组风格指数对（P2，可后交）。
- 每个文件的 `template_id/version`、Wind 代码与口径 notes、导出时间、SHA-256。
- 不需要提供 Wind 凭据；Yahoo/FRED 已覆盖序列无需重复提供。
