"""Persistent, auditable data acceptance registry."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from cross_asset.domain.usage import validate_usage_status
from cross_asset.pit import validate_pit_grade

from ._time import utc_naive


def candidate_registry_record(result: dict[str, Any]) -> dict[str, Any]:
    """Build a candidate only; this function never writes to DuckDB."""
    candidate = result.get("registry_candidate") or {}
    usage_status = candidate.get("usage_status", "EVIDENCE_ONLY")
    return {
        "series_id": candidate.get("series_id", "UNKNOWN"),
        "provider": candidate.get("provider", "UNKNOWN"),
        "source_series_id": candidate.get("source_series_id", "UNKNOWN"),
        "status": result.get("status", "FAIL"),
        "usage_status": usage_status,
        "tech_gate": result.get("gates", {}).get("TECH", "UNKNOWN"),
        "legal_gate": result.get("gates", {}).get("LEGAL", "UNKNOWN"),
        "pit_gate": result.get("gates", {}).get("PIT", "UNKNOWN"),
        "stability_gate": result.get("gates", {}).get("STABILITY", "UNKNOWN"),
        "pit_grade": candidate.get("pit_grade"),
        "origin": candidate.get("origin", "UNAVAILABLE"),
        "permission_scope": candidate.get("permission_scope"),
        "semantic_equivalence": candidate.get("semantic_equivalence"),
        "manifest_hash": result.get("sha256"),
        "reviewer": candidate.get("reviewer"),
        "approved_at": candidate.get("approved_at"),
        "evidence_json": json.dumps(
            {
                "errors": result.get("errors", []),
                "warnings": result.get("warnings", []),
            },
            sort_keys=True,
        ),
        "updated_at": datetime.now(UTC).replace(tzinfo=None),
    }


def validate_registry_record(record: dict[str, Any]) -> list[str]:
    errors = []
    try:
        validate_usage_status(record.get("usage_status"))
    except ValueError as exc:
        errors.append(str(exc))
    if record.get("status") == "FAIL":
        return ["fail_cannot_be_registered"]
    gates = {
        name: record.get(f"{name.lower()}_gate", "UNKNOWN")
        for name in ("TECH", "LEGAL", "PIT", "STABILITY")
    }
    ok, grade_errors = validate_pit_grade(
        record.get("pit_grade"), str(record.get("status", "")), gates
    )
    errors.extend(grade_errors if not ok else [])
    if record.get("status") == "PASS" and (
        record.get("reviewer") in (None, "", "TBD")
        or record.get("approved_at") in (None, "", "TBD")
    ):
        errors.append("pass_requires_reviewer_approval")
    if record.get("status") not in {"PASS", "PARTIAL"}:
        errors.append("status_invalid")
    return errors


def upsert_data_acceptance(store, record: dict[str, Any]) -> dict[str, Any]:
    record = dict(record)
    record["usage_status"] = validate_usage_status(record.get("usage_status"))
    errors = validate_registry_record(record)
    if errors:
        raise ValueError(";".join(sorted(set(errors))))

    fields = [
        "series_id",
        "provider",
        "source_series_id",
        "status",
        "tech_gate",
        "legal_gate",
        "pit_gate",
        "stability_gate",
        "pit_grade",
        "origin",
        "permission_scope",
        "semantic_equivalence",
        "manifest_hash",
        "reviewer",
        "approved_at",
        "evidence_json",
        "updated_at",
        "usage_status",
    ]
    values = [
        utc_naive(record.get(field))
        if field in {"approved_at", "updated_at"}
        else record.get(field)
        for field in fields
    ]
    key_fields = {"series_id", "provider", "source_series_id", "usage_status"}
    update_fields = [field for field in fields if field not in key_fields]
    store.conn.execute(
        f"INSERT INTO data_acceptance_registry ({','.join(fields)}) "
        f"VALUES ({','.join('?' for _ in fields)}) "
        "ON CONFLICT(series_id,provider,source_series_id,usage_status) DO UPDATE SET "
        + ",".join(f"{field}=excluded.{field}" for field in update_fields),
        values,
    )
    rows = query_data_acceptance(
        store,
        record["series_id"],
        record["provider"],
        record["source_series_id"],
        usage_status=record["usage_status"],
    )
    return rows[0]


def query_data_acceptance(
    store,
    series_id: str | None = None,
    provider: str | None = None,
    source_series_id: str | None = None,
    usage_status: str | None = None,
) -> list[dict[str, Any]]:
    predicates, params = [], []
    if usage_status is not None:
        usage_status = validate_usage_status(usage_status)
    for field, value in (
        ("series_id", series_id),
        ("provider", provider),
        ("source_series_id", source_series_id),
        ("usage_status", usage_status),
    ):
        if value is not None:
            predicates.append(f"{field}=?")
            params.append(value)
    where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
    rows = store.conn.execute(
        f"SELECT * FROM data_acceptance_registry {where} "
        "ORDER BY series_id,provider,source_series_id,usage_status",
        params,
    ).fetchall()
    columns = [
        item[0]
        for item in store.conn.execute("DESCRIBE data_acceptance_registry").fetchall()
    ]
    return [dict(zip(columns, row)) for row in rows]
