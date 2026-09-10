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
one complete dispatch
-> implementation + necessary tests/regression/smoke
-> one final handoff
-> WEB-CONTROL acceptance / concrete fixes / merge
```

The historical `WG0-WG9` collaboration pipeline is not required for ordinary new work. Domain/research Gates remain applicable only where their underlying business/data risk is relevant.

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
