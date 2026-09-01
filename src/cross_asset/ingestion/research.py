"""Strict local admission; validation precedes every write."""
from __future__ import annotations

import hashlib
from pathlib import Path


def validate_research_admission(record: dict, *, policies: dict[str, dict]) -> list[str]:
    errors = []
    if record.get("usage_status") != "RESEARCH_ADMISSIBLE":
        errors.append("usage_status_requires_research_admissible")
    policy = policies.get(record.get("series_id"), {})
    if not policy.get("enabled", False):
        errors.append("available_at_policy_disabled")
    if record.get("reviewer") in (None, "", "TBD") or record.get("approved_at") in (None, "", "TBD"):
        errors.append("reviewer_approval_required")
    if record.get("origin") in (None, "", "UNAVAILABLE"):
        errors.append("origin_required")
    if record.get("pit_grade") not in {"A", "B", "C"}:
        errors.append("pit_grade_a_b_c_required")
    if not record.get("raw_hash") or not record.get("source_contract"):
        errors.append("raw_hash_and_source_contract_required")
    if record.get("pit_grade") == "C" and not record.get("conservative_lag"):
        errors.append("grade_c_conservative_warning_required")
    if record.get("usage_status") == "LIVE_VERIFIED":
        errors.append("live_verified_requires_explicit_separate_gate")
    return sorted(set(errors))


def ingest_research_data(records: list[dict], *, policies: dict[str, dict], store=None) -> dict:
    errors = {r.get("series_id", "UNKNOWN"): validate_research_admission(r, policies=policies) for r in records}
    errors = {k: v for k, v in errors.items() if v}
    if errors:
        return {"status": "REJECTED", "written": 0, "errors": errors}
    if store:
        with store.atomic():
            for record in records:
                path = Path(record["raw_file"])
                if hashlib.sha256(path.read_bytes()).hexdigest() != record["raw_hash"]:
                    raise ValueError("raw_hash_mismatch")
    return {"status": "ADMISSIBLE", "written": 0, "errors": {}}
