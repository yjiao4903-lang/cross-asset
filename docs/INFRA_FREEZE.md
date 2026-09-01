# Offline Infrastructure Freeze Contract

Version: 0.1  
Owner: TBD  
Reviewer: TBD  
Approved at: TBD

## Scope

`INFRA_FREEZE=TRUE` freezes the verified offline contracts: Storage/PIT, immutable raw archive, ingestion idempotency, provenance, origin gates, engine interfaces, backup/restore verification, cross-process lock, and simulated Shadow control flow. It does **not** mean real data, research validity, investment effectiveness, or production readiness.

## No-change rule

Do not refactor a frozen contract for elegance or tuning. A change is allowed only for a reproducible PIT invariant bug, raw corruption, replay lookahead, provider semantic/security defect, data-integrity defect, or critical production safety issue.

## Unfreeze and approval

Any unfreeze request must record `change_id`, `reason`, `affected_contracts`, `risk`, `rollback_plan`, `tests`, `owner`, `reviewer`, `approved_at`, and `effective_at`. Owner/Reviewer/Approved at remain `TBD` until explicitly assigned; no implied approval is valid. After change, run the full QA gate and update the freeze report. Real provider access remains separately governed by the Data Acceptance Gate.
