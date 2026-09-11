# CURRENT_STATE

Status: ACTIVE BOOTSTRAP POINTER
Project profile: PERSONAL / INTERNAL WORKBENCH
Canonical dynamic control: GitHub Issue `#35`
Canonical role registry: `docs/project_management/ROLE_REGISTRY.yml`
Canonical operating model: `docs/project_management/MULTI_WINDOW_GITHUB_OPERATING_MODEL.md`

## Purpose

This file is deliberately low-churn. It points a fresh window to current GitHub state without copying mutable task/PR/CI facts into another document.

## Runtime authority order

For mutable state, prefer:

1. actual repository `main` and current GitHub object state;
2. Control Issue `#35`;
3. the active task dispatch / Issue;
4. the current PR/diff/tests/CI when directly relevant;
5. canonical governance documents when a rule needs clarification.

Chat history and old handoff text are non-authoritative when they conflict with current GitHub state.

## Minimum startup read

For ordinary assigned work, read only:

```text
actual main
AGENTS.md
Control Issue #35
own active dispatch / Task Issue
directly relevant PR / test / business-contract evidence
```

Read the role registry, operating model, task index, historical Issues/PRs or research roadmaps only when the current task materially depends on them.

Do not repeat full-history scans or re-check unchanged facts.

## Default workflow

```text
WEB-CONTROL decides the task is worth doing
-> one complete dispatch
-> executor implementation + necessary tests/regression/smoke + PR/fixes where useful
-> one final handoff
-> WEB-CONTROL acceptance / concrete defect return / merge
```

For ordinary work, WEB-CONTROL should normally appear only at the beginning and end of this loop.

The historical `WG0-WG9` collaboration pipeline is not required for ordinary new work. Domain/research Gates remain applicable only where their underlying business/data risk is relevant.

## Default routing

```text
online-capable work -> GPT-DEV
local environment/data/files/Windows/native tooling/real local E2E required -> LOCAL-DEV-A or LOCAL-DEV-B
```

Do not route work locally merely for parallelism if the online executor can finish it more cheaply and simply.

## When extra control is allowed

Extra approval/checking is justified only by a direct material risk such as destructive DB write/restore, Schema migration, irreversible external write, credential/funds handling, unknown-process termination, material public-network exposure, material concurrent overlap, or evidence failure that could materially misstate research conclusions.

Use the smallest control that addresses the actual risk; do not propagate it to unrelated tasks.

## Dispatch rule

`No GitHub dispatch = NO WORK` applies to development windows. A compact Issue/comment is enough; an open PR alone does not self-assign a window.

## Minimum safety floor

```text
UNKNOWN_PROCESS_KILL = FORBIDDEN
DESTRUCTIVE_DB_WRITE = EXPLICIT_ONLY
DB_RESTORE = EXPLICIT_ONLY
SCHEMA_MIGRATION = EXPLICIT_SCOPE_ONLY
UNKNOWN != ZERO
MISSING != ZERO
```

These controls are intentionally narrow and must not be expanded into enterprise-style governance without a concrete project risk.
