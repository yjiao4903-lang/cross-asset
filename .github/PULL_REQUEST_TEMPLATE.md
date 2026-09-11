## Task

- Role: <!-- WEB-CONTROL | GPT-DEV | LOCAL-DEV-A | LOCAL-DEV-B -->
- Task / Issue: <!-- #number or compact workstream id -->
- Goal: <!-- business outcome this PR delivers -->

## Completed

<!-- What changed. Keep this concise and outcome-oriented. -->

## Boundaries

- Out of scope: <!-- material items intentionally not changed -->
- Architecture / Schema / Contract / allocation impact: <!-- NONE or explicit -->
- High-risk operation: <!-- NONE, or reference explicit WEB-CONTROL authorization -->
- Coordination/overlap: <!-- NONE, or only material active overlap -->

## Validation

- Targeted tests / regression: <!-- command + result, or N/A -->
- Smoke / runtime validation: <!-- result when useful, or N/A -->
- CI: <!-- optional supporting evidence; CI is not a separate Gate -->
- Data/PIT/source status: <!-- N/A or truthful PARTIAL / DATA_BLOCKED / etc. -->

## Handoff

```text
HANDOFF_COMPLETE: <task/workstream>
head: <current PR head>
blockers: NONE | <blocker>
residual_risk: NONE | <short note>
next: READY_FOR_CONTROL
```

WEB-CONTROL reviews the current diff/head and decides acceptance/merge. No WG0-WG9 or separate exact-head evidence packet is required for ordinary work.
