# Three-Role GitHub Development Operating Model

Date: 2026-09-05
Status: ACTIVE
Project control hub: `yjiao4903-lang/cross-asset`
Related provider repo: `yjiao4903-lang/Marco-economic`

## 1. Purpose

From this development round onward, all project management is GitHub-first. Chat windows are execution roles, not sources of truth.

The project has exactly three persistent roles:

1. **WEB-CONTROL** — web-side development controller
2. **CODEX-DEV** — local primary Codex development window
3. **RESEARCH-AUX** — research/evidence auxiliary agent

Old windows may be archived. A new window can resume work only by reading GitHub issues, repository docs, PRs, and current branches.

## 2. Single source of truth

GitHub is authoritative for:

- requirements
- priorities
- dependency gates
- architecture decisions
- task state
- acceptance criteria
- implementation evidence
- branch/commit/PR state
- blockers
- merge decisions
- research evidence that affects implementation

Chat history is non-authoritative. If chat and GitHub conflict, the latest explicit GitHub decision wins unless WEB-CONTROL creates a correcting GitHub update.

## 3. Role: WEB-CONTROL

WEB-CONTROL owns architecture, planning, issue decomposition, acceptance, and merge authorization.

Responsibilities:

- inspect current GitHub state before issuing work
- create/update control issues and requirement documents
- define repository ownership and integration boundaries
- set priorities, dependency gates, and acceptance criteria
- review CODEX-DEV PRs and RESEARCH-AUX findings
- decide GO / CHANGES_REQUIRED / BLOCKED / MERGE_APPROVED
- keep the project control issue current
- prevent scope drift and duplicate capability across repositories

WEB-CONTROL normally does **not** implement production code. Small GitHub management/documentation changes are allowed when needed to establish the task source of truth.

WEB-CONTROL must not treat chat-only completion claims as accepted work.

## 4. Role: CODEX-DEV

CODEX-DEV is the only primary coding authority for the development round.

Capabilities assumed:

- local filesystem access
- full repository access
- tests and local runtime
- Git branches/commits
- GitHub issues and PRs

Responsibilities:

- start from the current GitHub control issue
- fetch latest `origin/main` before each task
- read repository rules (`AGENTS.md` where present)
- read the assigned REQ issue and requirement docs
- record task baseline vs current main
- implement only unlocked scope
- create tests and reproducible evidence
- create feature branches and PRs
- never self-merge unless the control issue explicitly authorizes it
- update the issue with branch, head SHA, PR, tests, CI, real-data/PIT status, blockers, and merge recommendation

CODEX-DEV may work across both repositories, but only one active implementation package should be treated as the primary task at a time unless the control issue explicitly allows parallel branches.

## 5. Role: RESEARCH-AUX

RESEARCH-AUX is a research/evidence role, not a coding authority.

Responsibilities:

- verify external data sources, documentation, release calendars, PIT semantics, historical availability, licensing/access constraints, and failure modes
- compare official sources and approved fallbacks
- red-team proposed data definitions and transformations
- produce concise evidence that can be attached to a GitHub issue or committed as a research memo

Prohibited:

- production code changes
- allocation/factor weight changes
- schema changes
- independent architecture decisions
- declaring a source production-ready without repository acceptance
- broad research expansion unless assigned by WEB-CONTROL

If RESEARCH-AUX cannot write GitHub directly, it must return a ready-to-paste Markdown update. The task is not considered closed until WEB-CONTROL or CODEX-DEV records that evidence in GitHub.

## 6. Project control hierarchy

### Project level

The canonical project control issue lives in `yjiao4903-lang/cross-asset` and links all active work across repositories.

### Repository level

Each implementation package must have a repository-local REQ issue and, for non-trivial work, a `docs/tasks/REQ-*.md` document.

### PR level

Every PR must link its REQ issue and state:

- scope implemented
- scope explicitly not implemented
- tests
- CI
- data/PIT status
- blockers
- migration/compatibility notes

## 7. Required task lifecycle

`PROPOSED -> READY -> IN_PROGRESS -> PR_OPEN -> REVIEW -> MERGE_APPROVED -> MERGED -> VERIFIED`

Alternative terminal/holding states:

- `BLOCKED`
- `DATA_BLOCKED`
- `RESEARCH_SHADOW`
- `DEFERRED`
- `REJECTED`

A chat message saying 'done' does not change task state.

## 8. Baseline protocol

Before implementation CODEX-DEV must report:

- task baseline SHA stated in the REQ
- current `origin/main` SHA
- commits between them
- semantic conflicts, if any
- chosen branch name

Default rule: branch from latest main, not stale task baseline.

## 9. Cross-repository boundary

`Marco-economic` remains the producer for Macro / Fundamental / Structural / Regime data.

`cross-asset` remains the consumer for Market State / Cross-Asset Decision / Allocation / Research.

The Integration Contract v1 remains the boundary unless a separate contract-change issue is approved.

Do not create duplicate canonical macro ownership in Cross for convenience.

## 10. Merge authority

CODEX-DEV opens PRs and provides evidence.

WEB-CONTROL decides:

- `CHANGES_REQUIRED`
- `BLOCKED`
- `MERGE_APPROVED`

No development window should infer merge approval from passing CI alone.

## 11. Standard implementation update

```md
## Implementation update

- Task baseline:
- Current origin/main:
- Branch:
- Head:
- PR:
- Scope completed:
- Files changed:
- Tests:
- CI:
- Real-data status:
- PIT/available_at status:
- Source-health status:
- Known blockers:
- Out-of-scope findings:
- Merge recommendation:
```

## 12. Standard research update

```md
## Research evidence update

- Research task:
- Sources checked:
- Official-source evidence:
- Historical availability:
- Release/PIT semantics:
- Access/licensing constraints:
- Failure modes:
- Recommended production source:
- Recommended fallback:
- Confidence:
- Open questions:
- Implementation implications:
```
