# Task Index

Status: ACTIVE
Dynamic activation/ownership authority: Control Issue `#35`

This index catalogs task contracts. Presence here does not mean a task is currently dispatched.

| Task contract | Scope | Activation source |
|---|---|---|
| `REQ-CROSS-MARKET-STATE-W1-20260905.md` | Cross market-state W1 | linked Issue + Control Issue #35 |
| `REQ-PROFESSIONAL-DATA-BRIDGE-W1-20260909.md` | professional data bridge capability/evidence | linked Issue + Control Issue #35 |

## Rules

1. Formal implementation should have a GitHub Issue and, for non-trivial work, a `docs/tasks/REQ-*.md` contract.
2. Each active task must have one explicit owner role: `GPT-DEV`, `GROK-DEV`, or `LOCAL-DEV` unless WEB-CONTROL is performing governance-only work.
3. Task activation, owner changes, dependency unlocks and deactivation are recorded in Control Issue #35 or the linked task Issue.
4. A task document may remain in this index after completion for traceability; completion state comes from GitHub, not filename age.
5. Future requirement candidates should remain reference-only until WEB-CONTROL creates/activates a formal REQ.
