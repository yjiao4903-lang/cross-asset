"""Offline research-admission candidate review; never writes registry or observations."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

SERIES = {"CPIAUCSL": "US_CPI", "PCEPILFE": "US_CORE_PCE", "UNRATE": "US_UNEMPLOYMENT", "ICSA": "US_INITIAL_CLAIMS", "INDPRO": "US_INDUSTRIAL_PRODUCTION"}


def build_candidates(batch_path="artifacts/data_capability/fred_alfred_macro_first_release_batch_20260901.json", raw_root="data/raw/fred", policy_path="config/fred_available_at_policies.yml"):
    batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    policies = {item.get("series_id"): item for item in __import__("yaml").safe_load(Path(policy_path).read_text(encoding="utf-8")).get("policies", [])}
    records = []
    for code, canonical in sorted(SERIES.items()):
        entry = batch.get("series", {}).get(next((k for k, v in batch.get("series", {}).items() if v.get("source_series_id") == code), ""), {})
        raw_path = entry.get("raw_path")
        errors = []
        rows = []
        actual_hash = None
        if not raw_path or not Path(raw_path).exists():
            errors.append("raw_missing")
        else:
            actual_hash = hashlib.sha256(Path(raw_path).read_bytes()).hexdigest()
            payload = json.loads(Path(raw_path).read_text(encoding="utf-8"))
            rows = payload.get("observations", [])
            if entry.get("row_count") != len(rows): errors.append("row_count_mismatch")
        dates = [r.get("date") for r in rows]
        vintages = [r.get("realtime_start") for r in rows]
        if len(dates) != len(set(dates)): errors.append("duplicate_observation_date")
        if any(not value for value in vintages): errors.append("missing_vintage")
        policy = policies.get(code, {})
        blockers = ["policy_disabled", "calendar_unverified", "legal_gate_unknown", "reviewer_approval_missing", "first_release_timestamp_unproven"]
        records.append({"series_id": canonical, "source_series_id": code, "provider": "fred", "source_contract": "ALFRED_API_output_type_4", "raw_path": raw_path, "raw_sha256_artifact": batch.get("raw_sha256", {}).get(code), "raw_sha256_actual": actual_hash, "row_count": len(rows), "observation_date_range": [min(dates), max(dates)] if dates else [None, None], "vintage_date_range": [min(vintages), max(vintages)] if vintages else [None, None], "policy_id": policy.get("policy", "release_date_eod"), "policy_version": "0.1", "candidate_available_at_rule": "release_date_eod America/New_York", "pit_grade_candidate": "C", "conservative_warning": True, "usage_target": "RESEARCH_ADMISSIBLE", "legal_status": "UNKNOWN", "calendar_status": "UNKNOWN", "reviewer": None, "approved_at": None, "status": "FAIL" if errors else "BLOCKED", "errors": sorted(errors), "blockers": blockers})
    return {"generated_at": datetime.now(UTC).isoformat(), "status": "BLOCKED", "enabled": False, "registry_written": False, "observations_written": False, "series": records}


def write_candidate_artifacts(result, json_path, md_path):
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(json_path).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    lines = ["# FRED Macro Research Admission Candidates", "", "状态：BLOCKED；仅候选，不写 Registry/observations。", "", "| Series | Rows | Raw hash match | Policy | Status | Blockers |", "|---|---:|---|---|---|---|"]
    lines += [f"| {r['series_id']} | {r['row_count']} | {'YES' if r['raw_sha256_artifact'] == r['raw_sha256_actual'] else 'NO'} | {r['policy_id']} | {r['status']} | {', '.join(r['blockers'])} |" for r in result["series"]]
    Path(md_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
