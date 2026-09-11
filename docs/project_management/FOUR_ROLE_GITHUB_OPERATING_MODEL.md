# Four-Role GitHub Development Operating Model

Status: SUPERSEDED
Superseded on: 2026-09-10

This document is retained only as a historical pointer.

The active four-window model is:

- `WEB-CONTROL`
- `GPT-DEV`
- `LOCAL-DEV-A`
- `LOCAL-DEV-B`

Current canonical rules:

- `AGENTS.md`
- `docs/CURRENT_STATE.md`
- `docs/project_management/ROLE_REGISTRY.yml`
- `docs/project_management/MULTI_WINDOW_GITHUB_OPERATING_MODEL.md`
- Control Issue `#35`

The previous `CODEX-DEV / AUX-DEV / RESEARCH-AUX` naming, mandatory lifecycle/baseline reporting, and heavy task-routing requirements in older versions are no longer active governance.

For ordinary work, use the lightweight closed loop:

```text
one complete dispatch
-> implementation + necessary tests/regression/smoke
-> one final handoff
-> WEB-CONTROL acceptance / merge
```

Do not reconstruct the superseded process from historical Issues or prompts.
