# CURRENT_STATE

Status: ACTIVE BOOTSTRAP POINTER
Canonical dynamic control: GitHub Issue `#35`
Canonical role registry: `docs/project_management/ROLE_REGISTRY.yml`
Canonical operating model: `docs/project_management/MULTI_WINDOW_GITHUB_OPERATING_MODEL.md`

## Purpose

This file is deliberately low-churn. It tells a fresh window how to recover current state without copying mutable PR/CI/dispatch facts into another stale document.

## Runtime authority order

For mutable state, read in this order:
1. actual repository `main` and GitHub object state;
2. Control Issue `#35` current body/comments;
3. active task Issue/REQ and explicit dispatch;
4. current PR head/diff/reviews/CI;
5. repository governance documents.

Chat history, old handoff text and superseded prompt files are non-authoritative.

## Required startup read

```text
actual main
AGENTS.md
docs/CURRENT_STATE.md
docs/project_management/ROLE_REGISTRY.yml
docs/project_management/MULTI_WINDOW_GITHUB_OPERATING_MODEL.md
docs/tasks/INDEX.md
Control Issue #35
own active dispatch
relevant REQ / Issue / PR / CI / Gate evidence
```

## Drift rule

If any canonical governance document, Control Issue dispatch, branch identity or PR role conflicts with another current GitHub source, do not guess. Report `GOVERNANCE_DRIFT`, identify the conflicting pointers and wait for WEB-CONTROL to resolve or update the canonical GitHub record.

## Dispatch rule

`No GitHub dispatch = NO WORK`.

An open PR does not by itself assign ownership to a newly opened window. Legacy/open PRs must be explicitly adopted or reviewed by WEB-CONTROL before a new executor modifies them.

## Production rule

Unless the active dispatch explicitly says otherwise:

```text
production writes: NOT_AUTHORIZED
schema migration: NOT_AUTHORIZED
release: NOT_AUTHORIZED
cutover: NOT_AUTHORIZED
irreversible operation: NOT_AUTHORIZED
```
