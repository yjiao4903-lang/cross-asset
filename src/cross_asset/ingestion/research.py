"""Strict research admission and formal observation writes."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("observation_date_invalid") from exc


def _parse_aware_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError) as exc:
            raise ValueError("available_at_invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("available_at_timezone_required")
    return parsed.astimezone(UTC)


def _raw_hash_matches(record: dict) -> bool:
    path = Path(record["raw_file"])
    if not path.is_file():
        return False
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    return actual == record.get("raw_hash")


def validate_research_admission(
    record: dict,
    *,
    policies: dict[str, dict],
    require_payload: bool = False,
) -> list[str]:
    errors = []
    if record.get("usage_status") != "RESEARCH_ADMISSIBLE":
        errors.append("usage_status_requires_research_admissible")
    policy = policies.get(record.get("series_id"), {})
    if not policy.get("enabled", False):
        errors.append("available_at_policy_disabled")
    if record.get("reviewer") in (None, "", "TBD") or record.get("approved_at") in (
        None,
        "",
        "TBD",
    ):
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
    if require_payload:
        if not record.get("raw_file"):
            errors.append("raw_file_required")
        if not record.get("provider") or not record.get("source_series_id"):
            errors.append("provider_and_source_series_required")
        observations = record.get("observations")
        if not isinstance(observations, list) or not observations:
            errors.append("canonical_observations_required")
    return sorted(set(errors))


def _registry_errors(record: dict, store) -> list[str]:
    rows = store.conn.execute(
        """SELECT status,usage_status,reviewer,approved_at,pit_grade
           FROM data_acceptance_registry
           WHERE series_id=? AND provider=? AND source_series_id=?
           ORDER BY updated_at DESC""",
        [
            record.get("series_id"),
            record.get("provider"),
            record.get("source_series_id"),
        ],
    ).fetchall()
    if not rows:
        return ["acceptance_registry_record_required"]
    status, usage, reviewer, approved_at, pit_grade = rows[0]
    errors = []
    if status != "PASS":
        errors.append("acceptance_registry_pass_required")
    if usage != "RESEARCH_ADMISSIBLE":
        errors.append("acceptance_registry_research_admissible_required")
    if reviewer in (None, "", "TBD") or approved_at is None:
        errors.append("acceptance_registry_approval_required")
    if pit_grade not in {"A", "B", "C"}:
        errors.append("acceptance_registry_pit_grade_required")
    return errors


def _canonical_rows(record: dict) -> list[dict]:
    rows = []
    seen = set()
    ingested_at = datetime.now(UTC).replace(tzinfo=None)
    for item in record["observations"]:
        if not isinstance(item, dict):
            raise TypeError("observation_must_be_mapping")
        if item.get("series_id") not in (None, record["series_id"]):
            raise ValueError("observation_series_id_mismatch")
        if item.get("source_series_id") not in (None, record["source_series_id"]):
            raise ValueError("observation_source_series_id_mismatch")
        observation_date = _parse_date(item.get("observation_date"))
        available_aware = _parse_aware_datetime(item.get("available_at"))
        if available_aware.date() < observation_date:
            raise ValueError("available_at_before_observation_date")
        try:
            value = float(item["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("observation_value_invalid") from exc
        if not math.isfinite(value):
            raise ValueError("observation_value_must_be_finite")
        vintage = item.get("vintage_date")
        vintage_date = None if vintage in (None, "") else _parse_date(vintage)
        available_at = available_aware.replace(tzinfo=None)
        key = (
            record["series_id"],
            observation_date,
            available_at,
            record["provider"],
            record["source_series_id"],
        )
        if key in seen:
            raise ValueError("duplicate_canonical_observation")
        seen.add(key)
        rows.append(
            {
                "series_id": record["series_id"],
                "observation_date": observation_date,
                "available_at": available_at,
                "value": value,
                "source": record["provider"],
                "source_series_id": record["source_series_id"],
                "vintage_date": vintage_date,
                "ingested_at": ingested_at,
                "quality": item.get("quality", "ok"),
                "raw_file": str(record["raw_file"]),
            }
        )
    return rows


def _batch_run_id(records: list[dict]) -> str:
    identity = [
        {
            "series_id": record["series_id"],
            "provider": record["provider"],
            "source_series_id": record["source_series_id"],
            "raw_hash": record["raw_hash"],
            "source_contract": record["source_contract"],
        }
        for record in records
    ]
    body = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return f"research-admission-{hashlib.sha256(body).hexdigest()[:24]}"


def ingest_research_data(
    records: list[dict],
    *,
    policies: dict[str, dict],
    store=None,
    dry_run: bool = False,
) -> dict:
    """Validate and, only after registry PASS, write formal observations idempotently."""

    strict_payload = dry_run or store is not None
    validation = {
        record.get("series_id", "UNKNOWN"): validate_research_admission(
            record,
            policies=policies,
            require_payload=strict_payload,
        )
        for record in records
    }
    errors = {key: value for key, value in validation.items() if value}
    if errors:
        return {"status": "REJECTED", "written": 0, "errors": errors}
    if not strict_payload:
        return {
            "status": "ADMISSIBLE",
            "written": 0,
            "candidate_rows": 0,
            "errors": {},
        }

    canonical = []
    for record in records:
        series_id = record["series_id"]
        row_errors = []
        if not _raw_hash_matches(record):
            row_errors.append("raw_hash_mismatch_or_file_missing")
        if store is not None:
            row_errors.extend(_registry_errors(record, store))
        try:
            canonical.extend(_canonical_rows(record))
        except ValueError as exc:
            row_errors.append(str(exc))
        if row_errors:
            errors[series_id] = sorted(set(row_errors))
    if errors:
        return {"status": "REJECTED", "written": 0, "errors": errors}

    if dry_run or store is None:
        return {
            "status": "ADMISSIBLE",
            "written": 0,
            "candidate_rows": len(canonical),
            "errors": {},
        }

    run_id = _batch_run_id(records)
    store.start_run(
        "research_admission",
        run_id,
        requested_series=len(records),
    )
    try:
        written = store.insert_observations(canonical, run_id=run_id)
        store.finish_run(
            run_id,
            "success",
            success_series=len(records),
            failed_series=0,
            rows_written=written,
        )
    except Exception as exc:
        store.finish_run(
            run_id,
            "failed",
            success_series=0,
            failed_series=len(records),
            rows_written=0,
            error_summary=type(exc).__name__,
        )
        raise
    return {
        "status": "ADMITTED",
        "run_id": run_id,
        "written": written,
        "candidate_rows": len(canonical),
        "reused": written == 0,
        "errors": {},
    }


__all__ = ["ingest_research_data", "validate_research_admission"]
