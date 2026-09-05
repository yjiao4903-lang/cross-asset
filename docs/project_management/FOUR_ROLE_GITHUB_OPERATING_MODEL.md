# Four-Role GitHub Development Operating Model

Date: 2026-09-05
Status: ACTIVE
Project control hub: `yjiao4903-lang/cross-asset`
Related provider repo: `yjiao4903-lang/Marco-economic`

## 1. Purpose

From this development round onward, all project management is GitHub-first. Chat windows are execution roles, not sources of truth.

The project has four persistent roles:

1. **WEB-CONTROL** — web-side development controller
2. **CODEX-DEV** — local primary development window
3. **AUX-DEV** — auxiliary development window
4. **RESEARCH-AUX** — research/evidence auxiliary agent

Old windows may be archived. A fresh window resumes work only from GitHub issues, repository docs, PRs, current branches, and CI state.

## 2. Single source of truth

GitHub is authoritative for requirements, priorities, dependency gates, architecture decisions, task state, acceptance criteria, implementation evidence, branch/commit/PR state, blockers, merge decisions, and research evidence that affects implementation.

Chat history is non-authoritative. If chat and GitHub conflict, the latest explicit GitHub decision wins unless WEB-CONTROL records a correcting GitHub update.

## 3. WEB-CONTROL

WEB-CONTROL owns architecture, planning, issue decomposition, acceptance, and merge authorization.

Responsibilities:
- inspect current GitHub state before issuing work
- create/update control issues and requirement documents
- define repository ownership and integration boundaries
- split work between CODEX-DEV and AUX-DEV to avoid overlapping files/semantics
- set priorities, dependency gates, and acceptance criteria
- review PRs and RESEARCH-AUX findings
- decide `CHANGES_REQUIRED / BLOCKED / MERGE_APPROVED`
- keep the project-control issue current

WEB-CONTROL normally does not implement production code. Small GitHub-management/documentation changes are allowed to establish the source of truth.

## 4. CODEX-DEV — primary developer

CODEX-DEV is the primary coding authority for high-coupling and critical-path work.

Capabilities assumed:
- local filesystem access
- full repository access
- tests/local runtime
- Git branches/commits
- GitHub issues and PRs

Default work types:
- architecture-sensitive changes
- cross-module changes
- integration-contract work
- allocation/research/runtime semantics
- database/state migrations
- final integration of multiple subpackages
- tasks with high regression risk

Responsibilities:
- fetch latest `origin/main`
- read repository rules and assigned REQ
- record task baseline vs current main
- implement only unlocked scope
- create tests/reproducible evidence
- create feature branches and PRs
- never self-merge unless explicitly authorized
- report branch/head/PR/tests/CI/PIT/real-data/blockers

CODEX-DEV may work across both repositories.

## 5. AUX-DEV — auxiliary developer

AUX-DEV is a second coding-capable execution role with GitHub and local-filesystem access.

Its purpose is to increase parallel throughput without creating a second architecture authority.

Best-fit work types:
- isolated source adapters/parsers
- fixtures and test harnesses
- data contracts and raw-archive support
- low-coupling utility modules
- documentation tied directly to implementation
- compatibility/migration helpers
- regression-test expansion
- research-shadow/data-collection plumbing
- small self-contained bug fixes explicitly assigned by WEB-CONTROL

AUX-DEV must not independently take:
- Integration Contract schema changes
- allocation semantics or strategic-weight changes
- large cross-repository refactors
- database canonical-schema redesign
- tasks already owned by CODEX-DEV
- architectural decisions not present in the assigned Issue/REQ

### 5.1 Non-overlap rule

Before coding, AUX-DEV must check:
- current open PRs
- CODEX-DEV active branch/task
- target files likely to change

If material overlap exists, AUX-DEV must stop and mark `COORDINATION_BLOCKED` rather than editing the same logical surface.

Default rule: CODEX-DEV and AUX-DEV should not modify the same production file set concurrently unless the Issue explicitly coordinates the split.

### 5.2 Branch and PR rule

AUX-DEV always uses its own feature branch and its own PR.

It must not push commits onto CODEX-DEV's branch and must not merge its own PR.

### 5.3 Handoff rule

AUX-DEV completion means:
- code/tests/docs complete for assigned scope
- PR opened
- implementation update posted
- known integration touchpoints listed

WEB-CONTROL decides whether the PR can merge directly or must first be consumed/rebased by CODEX-DEV.

## 6. RESEARCH-AUX

RESEARCH-AUX is a research/evidence role, not a coding authority.

Responsibilities:
- verify external data sources, documentation, release calendars, PIT semantics, historical availability, licensing/access constraints, and failure modes
- compare official sources and approved fallbacks
- red-team proposed data definitions and transformations
- produce evidence suitable for GitHub issues/docs

Prohibited:
- production code changes
- allocation/factor weight changes
- schema changes
- independent architecture decisions
- declaring production readiness without repository acceptance

## 7. Project-control hierarchy

### Project level
The canonical project-control issue lives in `yjiao4903-lang/cross-asset` and links all active work across repositories.

### Repository level
Each implementation package must have a repository-local REQ issue and, for non-trivial work, a `docs/tasks/REQ-*.md` document.

### Subtask level
Parallel AUX-DEV work should have its own child Issue or an explicit subsection in the parent Issue identifying:
- owner role = AUX-DEV
- allowed files/surfaces
- dependency gate
- completion criteria
- integration owner

### PR level
Every PR must link its REQ/child Issue and state scope, explicit non-scope, tests, CI, data/PIT status, blockers, and compatibility notes.

## 8. Task lifecycle

`PROPOSED -> READY -> IN_PROGRESS -> PR_OPEN -> REVIEW -> MERGE_APPROVED -> MERGED -> VERIFIED`

Alternative states:
- `BLOCKED`
- `DATA_BLOCKED`
- `COORDINATION_BLOCKED`
- `RESEARCH_SHADOW`
- `DEFERRED`
- `REJECTED`

## 9. Baseline protocol

Before implementation both CODEX-DEV and AUX-DEV must report:
- task baseline SHA
- current `origin/main` SHA
- commits between them
- semantic/file conflicts
- chosen branch name
- active PR overlap check

Default: branch from latest main, not stale task baseline.

## 10. Cross-repository boundary

`Marco-economic` remains the producer for Macro / Fundamental / Structural / Regime data.

`cross-asset` remains the consumer for Market State / Cross-Asset Decision / Allocation / Research.

Integration Contract v1 remains the boundary unless a separate contract-change Issue is approved.

## 11. Merge authority

CODEX-DEV and AUX-DEV open PRs and provide evidence.

WEB-CONTROL decides:
- `CHANGES_REQUIRED`
- `BLOCKED`
- `MERGE_APPROVED`

Passing CI alone is never merge approval.

## 12. Standard implementation update

```md
## Implementation update

- Role: CODEX-DEV / AUX-DEV
- Task baseline:
- Current origin/main:
- Active-PR overlap check:
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
- Coordination blockers:
- Known blockers:
- Out-of-scope findings:
- Integration touchpoints:
- Merge recommendation:
```

## 13. Standard research update

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
