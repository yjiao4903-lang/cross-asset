# 工作包 E：附件接线、两周对照与 FRED US_EQ

状态 `DEVELOPMENT_PRIOR`。不改正式研究准入。

## 交付

- `run_weekly_review` 接受 `--claims-json` / `--scenarios-json`。
- `weekly_compare.py` 对照上周四格与评分。
- `weekly_us_eq.py` 读 FRED 公共 `fredgraph.csv`（系列 `SP500`），不需要 `FRED_API_KEY`。
- `available_at` 用次日 12:00 北京时间。不写 Live，不写 RESEARCH_ADMISSIBLE。
- 个人包已写入 2026-08-14 / 08-28 / 09-04 收盘。

## 不做

- 不把 FRED 正式 API 开进生产门禁
- 不改战略权重
- 不合并到 `main`（仍须 #57 → #58 → 本分支）
