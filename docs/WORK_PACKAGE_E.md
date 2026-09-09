# 工作包 E：附件接线与两周对照

状态 `DEVELOPMENT_PRIOR`。叠在工作包 D / PR #59 上，补完未接线入口，不改正式研究准入。

## 交付

- `run_weekly_review` 与 `weekly-review` CLI 接受 `--claims-json` / `--scenarios-json`。缺文件 `SKIPPED`，不改 `stance`。
- `weekly_compare.py` 对照上周快照的四格与评分；只记录翻转，不产生交易。
- 个人包补齐 `examples/personal_week_20260828.json`。
- `source_aliases` 允许 Wind/iFinD 手工摘录名映射到 `manual`。`US_EQ` 仍要求 `fred`，本包不编造美股价格。

## 不做

- 不拉 Live FRED，不写 RESEARCH_ADMISSIBLE，不改战略权重，不合并到 `main`（仍须 #57 → #58 → 本分支）。
