# Multi-Window GitHub Operating Model

Date: 2026-09-09
Status: ACTIVE
Canonical control issue: `#35`
Machine-readable role registry: `docs/project_management/ROLE_REGISTRY.yml`

## 1. Operating principle

GitHub is the single source of truth. Chat windows are temporary execution units.

When chat, local notes, old prompts or cached task state conflict with GitHub, GitHub wins. The agent must report `GOVERNANCE_DRIFT` rather than silently choosing one version.

Authority is centralized; execution is distributed.

## 2. Persistent roles

### WEB-CONTROL

The ChatGPT main-control window. Sole project controller.

Owns:
- project roadmap and task decomposition;
- REQ/Issue activation and owner assignment;
- architecture and contract decisions;
- workflow/Gate definitions;
- cross-window coordination;
- final PR review;
- exact-head `MERGE_APPROVED` decisions;
- release, cutover, production writes and irreversible operations.

WEB-CONTROL may make low-risk GitHub governance/documentation changes directly, preferably through a PR. It is not the default production-code executor.

### GPT-DEV

Online GPT development window. Default online implementation executor.

Default routing: `ONLINE_DEFAULT`.

May implement approved scope, test, open PRs, respond to review and provide exact-head evidence. It may not self-expand scope, change architecture/contracts, merge, release or perform production writes without explicit WEB-CONTROL authorization.

### GROK-DEV

Online Grok development window. Peer online executor used for parallel isolated work, independent implementation, red-team/review-only assignments or research-only assignments.

Default routing: `ONLINE_PARALLEL`.

GROK-DEV is not a second controller. A review from GROK-DEV is advisory and never equals `MERGE_APPROVED`.

### LOCAL-DEV

Local PC development window. Peer coding executor for work that genuinely requires the local workstation, local datasets, Wind/iFind/native tools, local filesystem state or workstation-specific validation.

Default routing: `LOCAL_REQUIRED`.

LOCAL-DEV may also be designated `PRIMARY_EXECUTOR` by WEB-CONTROL for a task. That designation changes execution priority, not decision authority.

## 3. Logical identity versus GitHub account identity

The four roles above are logical project identities. If several windows use the same GitHub account/token, GitHub cannot cryptographically prove which model/window authored a commit.

Therefore identity is recorded through four independent signals:
1. Control Issue dispatch owner;
2. branch prefix;
3. Issue/PR `Role` field;
4. PR governance check.

Canonical branch prefixes:
- `control/` or `governance/` — WEB-CONTROL
- `gpt/` — GPT-DEV
- `grok/` — GROK-DEV
- `local/` — LOCAL-DEV

If cryptographic separation is later required, use separate GitHub accounts or scoped tokens for each executor. Do not pretend logical tags provide authentication that they do not provide.

## 4. Startup protocol

Every new window must read, in order:
1. actual `main`;
2. root `AGENTS.md`;
3. `docs/CURRENT_STATE.md`;
4. `docs/project_management/ROLE_REGISTRY.yml`;
5. this operating model;
6. `docs/tasks/INDEX.md`;
7. Control Issue `#35`;
8. its own active dispatch;
9. relevant REQ/Issue/PR/CI/Gate evidence.

Then it must return a `ROLE_READY` block containing:

```text
ROLE_READY
role:
actual_main:
control_issue:
active_workstream:
routing_mode:
assigned_scope:
branch_or_planned_branch:
active_pr_overlap:
known_blockers:
governance_drift:
```

No GitHub dispatch means `NO WORK`.

## 5. Dispatch contract

Every implementation task must state:
- `WORKSTREAM_ID`;
- owner role;
- routing mode;
- source REQ/Issue;
- baseline and current main;
- allowed file/logical surfaces;
- explicit out-of-scope;
- dependency gates;
- acceptance criteria;
- integration owner if needed;
- production/schema/release authorization state.

Default authorization for production writes, schema migration, release, cutover and irreversible operations is `NOT_AUTHORIZED`.

## 6. Non-overlap rule

Before coding, every executor checks open PRs, active dispatches, target files and logical surfaces.

Material overlap with another active executor is `COORDINATION_BLOCKED` unless WEB-CONTROL explicitly defines a safe split.

Default: one owner + one task + one branch + one PR.

## 7. Workflow Gates

To avoid collision with domain/research G0-G5 gates, collaboration governance uses `WG0-WG9`.

- `WG0 DISPATCH` — explicit GitHub dispatch exists.
- `WG1 BASELINE` — current main, task baseline, branch and overlap check recorded.
- `WG2 SCOPE` — allowed/non-scope and dependencies confirmed.
- `WG3 LOCAL_EVIDENCE` — required local tests/lint/evidence pass at exact head.
- `WG4 CI_EXACT_HEAD` — required CI is tied to exact head.
- `WG5 DOMAIN_SAFETY` — applicable data/PIT/schema/contract/production boundaries checked.
- `WG6 HANDOFF` — complete handoff packet posted.
- `WG7 CONTROL_REVIEW` — WEB-CONTROL reviews diff/evidence.
- `WG8 MERGE_APPROVED` — WEB-CONTROL explicitly approves one exact head.
- `WG9 POST_MERGE` — merged main stability/integration verification.

Allowed status vocabulary includes `PASS`, `FAIL`, `NOT_RUN`, `CI_INFRA_BLOCKED`, `DATA_GAP`, `BLOCKED`, `DATA_BLOCKED`, and `COORDINATION_BLOCKED`.

CI success is evidence for a Gate; it is never merge approval.

## 8. Exact-head rule

Every implementation handoff must state branch, head SHA, tests and CI tied to that head. Any new commit invalidates older exact-head evidence unless the relevant check is explicitly content-independent.

`MERGE_APPROVED` must name or otherwise unambiguously bind to the approved PR head. A moved head requires re-review.

## 9. Research and reference separation

Research may be assigned as a task mode (`RESEARCH_ONLY`) to GPT-DEV, GROK-DEV or LOCAL-DEV. It does not create another control authority.

External evidence, experiments and candidate factors remain reference/research material until a formal REQ and applicable admission Gates authorize implementation/production use.

## 10. Handoff contract

```text
HANDOFF_COMPLETE: <WORKSTREAM_ID>
role: <WEB-CONTROL | GPT-DEV | GROK-DEV | LOCAL-DEV>
routing_mode:
branch:
head:
PR:
WG_highest:
scope_completed:
tests:
CI:
data/PIT/source_health:
coordination_status:
known_limitations:
production_impact:
out_of_scope:
integration_touchpoints:
next: <READY_FOR_REVIEW | BLOCKED | CHANGES_REQUIRED>
```

Development is complete at PR + evidence + handoff. Merge/release remain separate decisions.

## 11. Authority summary

- Parallel execution: allowed when scopes do not overlap.
- Architecture authority: WEB-CONTROL only.
- Scope activation/change: WEB-CONTROL only.
- Merge approval: WEB-CONTROL only.
- Production write/release/cutover: explicit WEB-CONTROL authorization only.
- Developer self-merge: prohibited.
- Research conclusion -> production fact: prohibited without explicit admission.

This document supersedes older role naming where it conflicts with the current four-window configuration.
