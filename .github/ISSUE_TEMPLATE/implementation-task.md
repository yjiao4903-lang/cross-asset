---
name: Implementation task
title: "[TASK] "
about: Dispatch a bounded implementation/research/review task to one project role
labels: ""
assignees: ""
---

## Dispatch contract

- WORKSTREAM_ID:
- Owner role: <!-- GPT-DEV | GROK-DEV | LOCAL-DEV -->
- Routing mode: <!-- ONLINE_DEFAULT | ONLINE_PARALLEL | LOCAL_REQUIRED | PRIMARY_EXECUTOR | RESEARCH_ONLY | REVIEW_ONLY | LOCAL_EVIDENCE -->
- Source REQ / parent Issue:
- Task baseline SHA:
- Current main SHA:
- Branch prefix / planned branch:

## Allowed scope

### Files / surfaces

- 

### Logical responsibilities

- 

## Explicit out-of-scope

- 

## Dependencies / unlock conditions

- 

## Acceptance criteria

- [ ] WG0 explicit dispatch recorded
- [ ] WG1 baseline + overlap check recorded
- [ ] WG2 scope/non-scope confirmed
- [ ] Required implementation/evidence complete
- [ ] Required tests/lint complete at exact head
- [ ] Required CI state recorded truthfully
- [ ] Data/PIT/schema/contract safety checked where applicable
- [ ] PR + handoff posted

## Coordination

- Active PR overlap check:
- Integration owner:
- Known blockers:

## Authorization state

- Production writes: NOT_AUTHORIZED
- Schema migration: NOT_AUTHORIZED
- Release: NOT_AUTHORIZED
- Cutover: NOT_AUTHORIZED
- Irreversible operations: NOT_AUTHORIZED

Only WEB-CONTROL may change the authorization state or publish `MERGE_APPROVED`.
