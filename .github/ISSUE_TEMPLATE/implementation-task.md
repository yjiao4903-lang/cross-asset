---
name: Implementation task
title: "[TASK] "
about: Dispatch one bounded task to a project execution role
labels: ""
assignees: ""
---

## One-shot dispatch

- Task / workstream:
- Owner: <!-- GPT-DEV | LOCAL-DEV-A | LOCAL-DEV-B -->
- Goal:
- Scope:
- Business boundaries / must-not-change:

## Validate

<!-- List only the tests/regression/smoke actually needed to prove this task works. -->

- 

## Risk / dependencies

- High-risk operation: <!-- NONE unless explicit destructive DB write/restore, Schema migration, unknown-process concern, credential/funds/public exposure, etc. -->
- Material dependency/overlap: <!-- NONE or pointer -->
- Data/PIT/source constraint: <!-- N/A or explicit -->

## Return

Complete the assigned scope end-to-end where possible and post one compact final handoff:

```text
HANDOFF_COMPLETE: <task/workstream>
role: <role>
PR: <# or N/A>
head: <sha or N/A>
completed: <short summary>
validation:
  - <evidence>
blockers: NONE | <blocker>
residual_risk: NONE | <short note>
next: READY_FOR_CONTROL
```

Do not split ordinary work into separate analysis/test/review/smoke Gates. Escalate only a genuine scope, architecture, coordination or high-risk decision.
