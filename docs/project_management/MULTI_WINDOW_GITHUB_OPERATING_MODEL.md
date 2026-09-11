# Multi-Window GitHub Operating Model

Date: 2026-09-11
Status: ACTIVE
Profile: PERSONAL / INTERNAL WORKBENCH
Canonical control issue: `#35`
Machine-readable role registry: `docs/project_management/ROLE_REGISTRY.yml`

## 1. Operating objective

This project is optimized for:

1. working functionality;
2. stable day-to-day use;
3. simple maintenance;
4. minimum user coordination cost;
5. minimum model/process cost consistent with correctness.

GitHub is the collaboration source of truth, but GitHub process is a coordination mechanism, not an enterprise approval system.

Every extra role, Gate, test, document or workflow must clearly improve correctness, reduce real risk or reduce total development cost. Otherwise it should not be added.

## 2. Persistent roles

### WEB-CONTROL

WEB-CONTROL is the sole project controller. Its purpose is to reduce coordination cost and protect the few decisions that truly require central authority.

WEB-CONTROL owns:

- roadmap and priority;
- deciding whether work should be done at all;
- compact task decomposition and dispatch;
- business scope and out-of-scope boundaries;
- architecture / Schema / Contract decisions;
- allocation / strategic-weight decision authority;
- cross-window overlap/conflict resolution;
- final acceptance and merge decisions;
- explicit authorization for destructive or irreversible operations.

WEB-CONTROL is not the default implementation window. It should not turn normal development into a sequence of approvals, reviews or reporting steps. For ordinary work, its expected involvement is one dispatch and one final acceptance decision.

If a normal task requires the user to relay context/status between windows more than about two times, WEB-CONTROL should treat that as a workflow-design failure and consolidate the remaining steps.

### GPT-DEV

GPT-DEV is the default online implementation executor.

For normal online-capable work it should receive one complete task packet and continue through implementation, directly relevant tests, smoke/validation where useful, PR creation where useful, review fixes and final handoff without asking WEB-CONTROL for intermediate permission unless a genuine scope/architecture/risk decision appears.

### LOCAL-DEV-A

LOCAL-DEV-A is a local execution identity reserved for tasks that genuinely depend on a local workstation or local environment, including local databases/files, user-supplied manual source files, Windows runtime, approved local/native tooling, process state, credentials/environment or real local E2E validation.

It is not a generic fallback for online-capable development. WEB-CONTROL dispatches it when the required local capability is available on that execution host.

### LOCAL-DEV-B

LOCAL-DEV-B is a second local execution identity with the same local-only boundary. It exists so WEB-CONTROL can isolate or parallelize genuinely local work when host/data/tool availability makes that useful.

Professional data terminals, if used by the user, are user-side manual export sources only; they are not project automated acquisition/runtime dependencies. The manual path remains `USER_MANUAL_DATA_EXPORT -> IMMUTABLE_RAW_FILE -> ...`. Existing FRED/ALFRED automated routes continue independently.

It does not create a second project controller or runtime authority. The PC-A / PC-B runtime and data-ingress boundary remains governed separately by `docs/OPERATING_MODEL_PC_A_PC_B.md`.

## 3. Startup protocol: minimum necessary reads

A new execution window should read only what is needed to safely start the assigned task:

1. actual `main`;
2. root `AGENTS.md`;
3. Control Issue `#35` current state;
4. its active task/dispatch;
5. directly relevant PR/diff/test/CI/business contract.

Read `docs/CURRENT_STATE.md`, this document, the role registry, task index, old Issues/PRs or research roadmaps only when the current task actually needs them.

Do not repeat full-history scans. Do not re-verify stable facts whose state has not changed.

A compact startup response is sufficient:

```text
ROLE_READY
role: <role>
main: <sha>
task: <issue/workstream>
status: READY | BLOCKED
material_overlap: NONE | <pointer>
```

No separate startup Gate is created by this block.

## 4. Default routing

WEB-CONTROL should route work in this order:

1. GPT-DEV for work that can be completed online;
2. LOCAL-DEV-A or LOCAL-DEV-B only when local environment, local data/files, user-supplied manual source files or approved local/native tooling is materially required; choose the local identity based on host capability, isolation and useful parallelism.

Neither local role is a generic second-choice coding window. Ordinary code, documentation, PR work and tests should remain online whenever possible.

## 5. Default task loop

The normal closed loop is:

```text
WEB-CONTROL one-shot dispatch
    -> executor implements
    -> executor runs necessary tests/regression/smoke
    -> executor opens/updates PR if useful
    -> executor posts one final handoff
    -> WEB-CONTROL accepts / requests concrete fixes / merges
```

Do not split the same ordinary task into separate analysis, implementation, unit-test, review, smoke and release-prep assignments when one executor can carry them through.

A second handoff/review cycle is justified only by a real defect, missing evidence or changed scope.

## 6. Compact dispatch contract

For ordinary implementation work, one dispatch should contain:

```text
TASK: <stable id or issue>
OWNER: <GPT-DEV | LOCAL-DEV-A | LOCAL-DEV-B>
GOAL: <business outcome>
SCOPE: <allowed files/logical surface or behavior>
BOUNDARIES: <must-not-change items>
VALIDATE: <necessary targeted tests/regression/smoke>
RISK: <NONE or explicit high-risk authorization state>
RETURN: HANDOFF_COMPLETE
```

Add dependencies, baseline SHA, overlap details, research/data Gates or integration sequencing only when they materially affect correctness.

An Issue/comment is sufficient dispatch evidence. No large task form is required.

`No GitHub dispatch = NO WORK` remains useful for preventing accidental self-assignment by development windows.

## 7. Branch and PR policy

Branch + PR are useful for implementation changes because they provide reviewable diff, isolation and rollback. They are not an approval chain.

Default guidance:

- normal code change: one task -> one branch -> one PR when practical;
- small low-risk docs/governance edits: WEB-CONTROL may update directly when overlap and rollback risk are trivial;
- do not create extra PRs solely to represent internal phases;
- an old/open PR does not automatically assign ownership to a window.

Branch prefixes remain useful logical identity hints:

- `control/` or `governance/` — WEB-CONTROL
- `gpt/` — GPT-DEV
- `local-a/` — LOCAL-DEV-A
- `local-b/` — LOCAL-DEV-B

They are coordination metadata, not security authentication.

## 8. Testing and acceptance: minimum sufficient evidence

Ordinary functionality is accepted when there is sufficient evidence that:

- the target behavior works;
- directly related regressions pass;
- key business semantics are correct;
- core flow is not obviously broken.

Use the smallest test set that provides this evidence. Broader/full-suite/platform validation is appropriate when the change is cross-cutting, platform-sensitive, economically material, hard to roll back or otherwise high risk.

CI is useful automated evidence, not a collaboration Gate. CI failure must be understood when it is relevant. CI unavailability does not automatically block progress if local/runtime evidence is sufficient; record the residual risk instead.

For PR merges, WEB-CONTROL should verify it is reviewing the current head/diff. This is a basic stale-review check, not a standalone exact-head evidence workflow.

## 9. Domain/research Gates are not collaboration Gates

Existing research/data controls such as `G0-G5` and `C0-C3` may still apply where the business problem requires them—for example PIT safety, source admission, factor admission, research validity or production allocation semantics.

They must not be reused as generic multi-window approval steps.

The old mandatory collaboration sequence `WG0-WG9` is retired for ordinary work. Historical Issues/PRs may continue to contain WG labels as historical evidence; no migration is required.

## 10. Handoff contract

A normal final return should be compact:

```text
HANDOFF_COMPLETE: <task/workstream>
role: <role>
PR: <# or N/A>
head: <sha if PR/code change; otherwise N/A>
completed: <short summary>
validation:
  - <targeted test / regression / smoke result>
blockers: NONE | <truthful blocker>
residual_risk: NONE | <short note>
next: READY_FOR_CONTROL
```

Do not repeat unchanged background, old SHAs, full historical evidence or already-linked information.

## 11. User is not the message bus

Agents should hand off through GitHub Issue/PR comments or compact repository records whenever possible.

WEB-CONTROL should write the next executor's task so the user does not need to copy/paste the same context, SHA, tests or status between windows.

A fresh executor should retrieve only the incremental GitHub context needed for its assignment.

## 12. Minimum safety floor

The following rules are retained because they prevent real local/data damage:

```text
UNKNOWN_PROCESS_KILL = FORBIDDEN
DESTRUCTIVE_DB_WRITE = EXPLICIT_ONLY
DB_RESTORE = EXPLICIT_ONLY
SCHEMA_MIGRATION = EXPLICIT_SCOPE_ONLY
UNKNOWN != ZERO
MISSING != ZERO
```

These rules do not imply enterprise IAM, zero-trust, SIEM/SOC, SAST/DAST, HA, service mesh, complex release systems or mandatory branch-protection programs.

Credentials must not be committed or leaked. Real-data/PIT/source uncertainty must remain explicit rather than being converted into success by defaults, zero-fill or fixtures.

## 13. When extra control is justified

WEB-CONTROL may add a targeted extra check only when the task contains a real direct risk, such as:

- destructive database mutation or restore;
- Schema migration;
- irreversible external/production write;
- credential/funds handling;
- unknown process termination;
- clear public-network exposure;
- materially overlapping concurrent changes;
- economically material allocation/contract changes;
- evidence where a false success would materially mislead research conclusions.

The control should be the smallest one that mitigates that risk and should disappear from unrelated tasks.

## 14. Authority summary

- Project/architecture/scope authority: WEB-CONTROL only.
- Default implementation: GPT-DEV online.
- Local execution: LOCAL-DEV-A / LOCAL-DEV-B only when genuinely local; WEB-CONTROL chooses the appropriate local identity.
- Normal task process: one dispatch, end-to-end execution, one final handoff, one control acceptance.
- Developer self-merge: not allowed unless WEB-CONTROL explicitly changes project policy.
- Destructive DB write / restore / Schema migration: only under the minimum safety rules above.
- Enterprise-grade governance: not a default project objective.
