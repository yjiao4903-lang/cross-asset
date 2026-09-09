# 工作包 D：两周个人包与周报附件

状态 `DEVELOPMENT_PRIOR`。本包叠在 PR #58 的账本/情景入口上，不改正式研究准入，不改战略权重。

## 交付

- `weekly_annex.py` 把可选 `claim-ledger` / `scenario` 结果附到周报末尾。缺文件时标记 `SKIPPED`，不阻断事实表。
- `weekly-review` 增加 `--claims-json` 与 `--scenarios-json`。附件不改 `stance`。
- `examples/personal_week_20260828.json` 与 `examples/personal_week_20260904.json` 是用户 Wind/iFinD 工作簿的压缩个人包。vendor 名可通过 `source_aliases` 映射到 `manual`，但 `US_EQ` 仍缺席，因此两周都保持 `DATA_BLOCKED`。

## 验收

同一入口可比较两个周五观察周；上周快照存在时写出相对变化；附件可见；默认仍为不行动。不得把压缩包写成 `RESEARCH_ADMISSIBLE` 或 Live 数据。

## 命令

```text
python -m cross_asset.cli weekly-review \
  --as-of 2026-09-05 \
  --week-end 2026-09-04 \
  --review-cutoff 2026-09-05T12:00:00+08:00 \
  --observations-json examples/personal_week_20260904.json \
  --prior-snapshot artifacts/reports/week_20260828.snapshot.json \
  --claims-json examples/event_claims_fixture.json \
  --scenarios-json examples/scenario_fixture.json \
  --output artifacts/reports/weekly_review.md
```
