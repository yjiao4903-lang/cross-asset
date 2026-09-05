# Four-Role GitHub Development Operating Model

Date: 2026-09-05
Status: ACTIVE
Project control hub: `yjiao4903-lang/cross-asset`
Related provider repo: `yjiao4903-lang/Marco-economic`

## 1. Purpose

From this development round onward, all project management is GitHub-first. Chat windows are execution roles, not sources of truth.

The project has four persistent roles:

1. **WEB-CONTROL** — web-side development controller
2. **CODEX-DEV** — online development window colocated with WEB-CONTROL; default primary executor
3. **AUX-DEV** — local/offline development window; default parallel/local executor and eligible temporary primary executor
4. **RESEARCH-AUX** — research/evidence auxiliary agent

Old windows may be archived. A fresh window resumes work only from GitHub issues, repository docs, PRs, current branches, and CI state.

### 1.1 Development-window parity and routing

`CODEX-DEV` and `AUX-DEV` are **peer coding authorities under WEB-CONTROL**. Their difference is default task routing and execution environment, not a permanent permission hierarchy.

Default routing policy:

- **Online-first:** work that can be completed efficiently and safely in the online development environment should be routed to `CODEX-DEV` by default.
- **Offline/local routing:** work that requires local filesystem access, native/local tooling, local datasets, workstation-specific state, or another genuinely local execution dependency is routed to `AUX-DEV`.
- **Parallel-efficiency routing:** `AUX-DEV` may also receive isolated work purely to increase throughput when parallel execution is materially useful.
- **Temporary primary promotion:** WEB-CONTROL may explicitly designate `AUX-DEV` as `PRIMARY-EXECUTOR` for a task or development phase. When so designated, AUX-DEV may execute critical-path or high-coupling work within the approved Issue/REQ scope; the old low-coupling-only restriction does not apply to that explicitly assigned task.
- **No self-assignment by authority level:** no development window gains architecture or merge authority merely by being the current primary executor. Architecture, scope, gates and merge authorization remain with WEB-CONTROL.

The project therefore distinguishes **control authority** from **execution priority**:

- Control authority: `WEB-CONTROL`
- Default execution priority: online `CODEX-DEV`
- Local/offline execution: `AUX-DEV`
- Temporary execution priority: whichever development window WEB-CONTROL records as `PRIMARY-EXECUTOR` for that task

## 2. Single source of truth

GitHub is authoritative for requirements, priorities, dependency gates, architecture decisions, task state, acceptance criteria, implementation evidence, branch/commit/PR state, blockers, merge decisions, task routing, current primary executor, and research evidence that affects implementation.

Chat history is non-authoritative. If chat and GitHub conflict, the latest explicit GitHub decision wins unless WEB-CONTROL records a correcting GitHub update.

## 3. WEB-CONTROL

WEB-CONTROL owns architecture, planning, issue decomposition, task routing, acceptance, and merge authorization.

Responsibilities:
- inspect current GitHub state before issuing work
- create/update control issues and requirement documents
- define repository ownership and integration boundaries
- route work between development windows according to online-first / local-required / parallel-efficiency principles
- designate or revoke `PRIMARY-EXECUTOR` status when useful
- split concurrent work to avoid overlapping files/semantics
- set priorities, dependency gates, and acceptance criteria
- review PRs and RESEARCH-AUX findings
- decide `CHANGES_REQUIRED / BLOCKED / MERGE_APPROVED`
- keep the project-control issue current

WEB-CONTROL normally does not implement production code. Small GitHub-management/documentation changes are allowed to establish the source of truth.

## 4. CODEX-DEV — default online primary executor

CODEX-DEV is the default online development window colocated with WEB-CONTROL.

Its default role is **primary execution**, because online development should be preferred when the task does not genuinely require local/offline state.

Default work types:
- architecture-sensitive implementation already specified by an approved Issue/REQ
- cross-module and cross-repository work
- integration and runtime semantics
- allocation/research/runtime implementation under approved gates
- high-regression-risk tasks
- final integration of parallel subpackages
- ordinary implementation work that can be completed online without local-only dependencies

Responsibilities:
- fetch/read current GitHub source of truth before work
- record task baseline vs current main
- inspect active PR/task overlap
- implement only unlocked scope
- create tests/reproducible evidence
- create feature branches and PRs
- never self-merge unless explicitly authorized
- report branch/head/PR/tests/CI/PIT/real-data/blockers

CODEX-DEV has no permanent authority over AUX-DEV. It is the default primary executor by routing policy, not a superior development role.

## 5. AUX-DEV — local/offline peer developer

AUX-DEV is the local/offline coding-capable execution role with GitHub and local-filesystem access.

All tasks that genuinely require local/offline execution should be routed here.

Default work types when operating as an auxiliary/parallel executor:
- isolated source adapters/parsers
- fixtures and test harnesses
- data contracts and raw-archive support
- low-coupling utility modules
- documentation tied directly to implementation
- compatibility/migration helpers
- regression-test expansion
- research-shadow/data-collection plumbing
- small self-contained bug fixes explicitly assigned by WEB-CONTROL
- any work that requires local datasets, local filesystem state, native/local tools or workstation-specific execution

### 5.1 Temporary primary mode

WEB-CONTROL may mark AUX-DEV as `PRIMARY-EXECUTOR` for a task or phase.

In temporary primary mode AUX-DEV may take, when explicitly assigned:
- architecture-sensitive implementation already resolved in the Issue/REQ
- high-coupling changes
- cross-module changes
- critical-path work
- final integration work
- tasks that would normally default to CODEX-DEV

Temporary primary mode does **not** authorize AUX-DEV to independently change architecture, gates, canonical schemas, Integration Contract semantics, allocation semantics, or strategic weights beyond the approved Issue/REQ.

### 5.2 Non-overlap rule

Before coding, every development window must check:
- current open PRs
- active tasks/branches of other development windows
- target files likely to change
- logical/semantic surfaces likely to overlap

If material overlap exists, the later task must stop and mark `COORDINATION_BLOCKED` unless WEB-CONTROL explicitly defines a safe split.

Default rule: development windows should not modify the same production file set or logical surface concurrently unless the Issue explicitly coordinates the split.

### 5.3 Branch and PR rule

Each development window always uses its own feature branch and its own PR unless an Issue explicitly establishes a coordinated shared branch workflow.

A development window must not push commits onto another active window's branch and must not merge its own PR without WEB-CONTROL authorization.

### 5.4 Handoff rule

Development completion means:
- code/tests/docs complete for assigned scope
- PR opened
- implementation update posted
- known integration touchpoints listed

WEB-CONTROL decides whether the PR can merge directly, requires changes, is blocked, or must be consumed/rebased by another executor.

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

### Task-routing level
Every active implementation task should identify:
- owner/executor role
- whether the task is `ONLINE_DEFAULT`, `LOCAL_REQUIRED`, `PARALLEL_EFFICIENCY`, or explicitly `PRIMARY-EXECUTOR`
- allowed files/surfaces
- dependency gate
- completion criteria
- integration owner if different

Existing Issues that only name `CODEX-DEV` or `AUX-DEV` remain valid; the routing semantics in this document apply without requiring immediate mass renaming.

### PR level
Every PR must link its REQ/child Issue and state scope, explicit non-scope, tests, CI, data/PIT status, blockers, compatibility notes, and coordination status.

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

Before implementation every development window must report:
- task baseline SHA
- current `origin/main` SHA
- commits between them
- semantic/file conflicts
- chosen branch name
- active PR overlap check
- routing mode (`ONLINE_DEFAULT / LOCAL_REQUIRED / PARALLEL_EFFICIENCY / PRIMARY-EXECUTOR`)

Default: branch from latest main, not stale task baseline.

## 10. Cross-repository boundary

`Marco-economic` remains the producer for Macro / Fundamental / Structural / Regime data.

`cross-asset` remains the consumer for Market State / Cross-Asset Decision / Allocation / Research.

Integration Contract v1 remains the boundary unless a separate contract-change Issue is approved.

## 11. Merge authority

Development windows open PRs and provide evidence.

WEB-CONTROL decides:
- `CHANGES_REQUIRED`
- `BLOCKED`
- `MERGE_APPROVED`

Passing CI alone is never merge approval.

`PRIMARY-EXECUTOR` status never includes merge authority.

## 12. Standard implementation update

```md
## Implementation update

- Role: CODEX-DEV / AUX-DEV
- Routing mode: ONLINE_DEFAULT / LOCAL_REQUIRED / PARALLEL_EFFICIENCY / PRIMARY-EXECUTOR
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
