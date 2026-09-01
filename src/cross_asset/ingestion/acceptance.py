"""Read-only CSV and manifest acceptance checks for real-data handoff."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .origin import DataOrigin, OriginEvidence, validate_origin_evidence

MANIFEST_FIELDS = {"series_id", "provider", "source_series_id", "permission_scope", "origin", "observation_definition", "unit", "currency", "timezone", "price_type", "adjustment_type", "frequency", "history_start", "history_end", "observation_date_rule", "available_at_rule", "vintage_rule", "missing_policy", "semantic_equivalence", "template_version", "file_sha256", "reviewer", "approved_at", "reconciliation_notes"}
REQUIRED_COLUMNS = {"observation_date", "value", "available_at"}
_ALIASES = {"template_id": "template_version", "version": "template_version", "file_hash": "file_sha256"}
_CORE_FIELDS = ("series_id", "provider", "source_series_id", "observation_definition", "unit", "currency", "timezone", "price_type", "adjustment_type", "frequency", "observation_date_rule", "available_at_rule", "vintage_rule", "missing_policy")


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8")) if path.suffix.lower() == ".json" else yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("manifest must be a mapping")
    return data


def _entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries = manifest.get("series", manifest.get("records"))
    if entries is None:
        return [manifest]
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
        raise ValueError("manifest series must be a list of mappings")
    return entries


def _parse_dt(value: Any, *, aware: bool = False) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if aware and parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed


def _normalise(entry: dict[str, Any], warnings: list[dict[str, str]]) -> dict[str, Any]:
    result = dict(entry)
    for old, canonical in _ALIASES.items():
        if old in entry:
            if canonical not in result:
                result[canonical] = entry[old]
            warnings.append({"code": "legacy_manifest_field", "message": f"{old} is deprecated; use {canonical}"})
    result["file_hash"] = result.get("file_sha256")
    result["template_id"] = result.get("template_version")
    return result


def _result(path, actual_hash, errors, warnings, gates, row_count=0, unique_count=0, manifest_path=None):
    errors = sorted(errors, key=lambda item: (item.get("code", ""), item.get("message", "")))
    warnings = sorted(warnings, key=lambda item: (item.get("code", ""), item.get("message", "")))
    status = "FAIL" if errors else ("PASS" if all(value == "PASS" for value in gates.values()) else "PARTIAL")
    return {"status": status, "file": str(path), "manifest": str(manifest_path) if manifest_path else None, "sha256": actual_hash, "counts": {"rows": row_count, "unique_observations": unique_count, "errors": len(errors), "warnings": len(warnings)}, "gates": gates, "errors": errors, "warnings": warnings}


def validate_data_file(file: str | Path, manifest: str | Path | None = None) -> dict[str, Any]:
    """Validate a data file without writing observations or changing the DB."""
    path = Path(file)
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    gates = {name: "UNKNOWN" for name in ("TECH", "LEGAL", "PIT", "STABILITY")}
    if not path.is_file():
        return _result(path, None, [{"code": "file_not_found", "message": "data file does not exist"}], warnings, gates)
    manifest_path = Path(manifest) if manifest else None
    if manifest_path is None:
        preferred = [path.with_name(f"{path.stem}.manifest{s}") for s in (".yml", ".yaml", ".json")]
        legacy = [path.with_suffix(s) for s in (".yml", ".yaml", ".json")]
        manifest_path = next((candidate for candidate in preferred if candidate.is_file()), None)
        if manifest_path is None:
            manifest_path = next((candidate for candidate in legacy if candidate.is_file()), None)
            if manifest_path is not None:
                warnings.append({"code": "legacy_manifest_discovery", "message": "legacy same-stem manifest discovered; use *.manifest.yml"})
    data = None
    if manifest_path is None:
        errors.append({"code": "manifest_required", "message": "manifest not found"})
    else:
        try:
            data = _load_manifest(manifest_path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
            errors.append({"code": "manifest_invalid", "message": type(exc).__name__})
    rows: list[dict[str, str]] = []
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
            if missing:
                errors.append({"code": "required_columns_missing", "message": ",".join(missing)})
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        errors.append({"code": "csv_invalid", "message": type(exc).__name__})
    actual_hash = _hash(path)
    entries: list[dict[str, Any]] = []
    if data is not None:
        try:
            entries = [_normalise(entry, warnings) for entry in _entries(data)]
        except ValueError as exc:
            errors.append({"code": "manifest_invalid", "message": str(exc)})
    valid_origins: list[DataOrigin] = []
    for entry in entries:
        missing_fields = sorted(MANIFEST_FIELDS - set(entry))
        if missing_fields:
            errors.append({"code": "manifest_fields_missing", "message": ",".join(missing_fields)})
        if entry.get("file_sha256") != actual_hash:
            errors.append({"code": "file_hash_mismatch", "message": str(entry.get("series_id", "unknown"))})
        for field in _CORE_FIELDS:
            if entry.get(field) in (None, "", "TBD"):
                errors.append({"code": "core_field_invalid", "message": field})
        for field in ("history_start", "history_end"):
            if _parse_dt(entry.get(field)) is None:
                errors.append({"code": "history_invalid", "message": field})
        start, end = _parse_dt(entry.get("history_start")), _parse_dt(entry.get("history_end"))
        if start and end and start > end:
            errors.append({"code": "history_invalid", "message": "history_start_after_end"})
        approved = entry.get("approved_at")
        if approved not in (None, "", "TBD") and _parse_dt(approved, aware=True) is None:
            errors.append({"code": "approved_at_invalid", "message": "approved_at must be timezone-aware ISO"})
        try:
            origin = DataOrigin(str(entry.get("origin", "UNAVAILABLE")).upper())
            valid_origins.append(origin)
            evidence = OriginEvidence(origin, provider=entry.get("provider"), file_hash=entry.get("file_sha256"), template_id=entry.get("template_version"), verified_at=entry.get("verified_at"), raw_file=entry.get("raw_file"), provider_attempt_id=entry.get("provider_attempt_id"), available_at=entry.get("available_at"))
            ok, origin_errors = validate_origin_evidence(evidence)
            if not ok:
                errors.extend({"code": code, "message": "origin evidence invalid"} for code in origin_errors)
        except ValueError:
            errors.append({"code": "origin_invalid", "message": str(entry.get("origin"))})
        if entry.get("semantic_equivalence") is False and (entry.get("fallback") or entry.get("source_switch")):
            errors.append({"code": "semantic_equivalence_invalid", "message": "fallback/source switch requires semantic_equivalence=true"})
        if entry.get("fallback") or entry.get("source_switch"):
            fallback = entry.get("fallback_source")
            if not isinstance(fallback, dict) or not fallback.get("provider") or not fallback.get("source_series_id"):
                errors.append({"code": "fallback_invalid", "message": "fallback_source requires independent provider and source_series_id"})
            if not entry.get("reconciliation_notes"):
                errors.append({"code": "fallback_reconciliation_missing", "message": "fallback/source switch requires reconciliation_notes"})
    duplicate_keys = set()
    for row in rows:
        key = (row.get("series_id"), row.get("source_series_id"), row.get("observation_date"), row.get("available_at"))
        if key in duplicate_keys:
            errors.append({"code": "duplicate_observation", "message": repr(key)})
        duplicate_keys.add(key)
        if not row.get("observation_date") or _parse_dt(row.get("observation_date")) is None or _parse_dt(row.get("available_at"), aware=True) is None:
            errors.append({"code": "observation_invalid", "message": "observation_date/available_at must be parseable timezone-aware ISO"})
        try:
            if not row.get("value", "").strip():
                raise ValueError
            float(row["value"])
        except (KeyError, TypeError, ValueError):
            errors.append({"code": "observation_invalid", "message": "value must be parseable and non-empty"})
    if not errors:
        gates["TECH"] = "PASS" if all(entry.get("semantic_equivalence") is not False and all(entry.get(field) not in (None, "", "TBD") for field in _CORE_FIELDS) for entry in entries) else "UNKNOWN"
        gates["LEGAL"] = "PASS" if all(entry.get("permission_scope") not in (None, "", "TBD") and entry.get("reviewer") not in (None, "", "TBD") and entry.get("approved_at") not in (None, "", "TBD") for entry in entries) else "UNKNOWN"
        gates["PIT"] = "PASS" if all(entry.get(field) not in (None, "", "TBD") for entry in entries for field in ("available_at_rule", "vintage_rule")) else "UNKNOWN"
        manual = DataOrigin.MANUAL in set(valid_origins)
        stable = True
        for entry in entries:
            batches = entry.get("repeatability_evidence")
            valid = isinstance(batches, list) and len(batches) >= 3 and all(isinstance(batch, dict) and all(batch.get(field) not in (None, "", "TBD") for field in ("batch_id", "file_sha256", "exported_at", "reviewer", "approved_at")) for batch in batches)
            distinct = valid and len({batch["batch_id"] for batch in batches}) >= 3 and (len({batch["file_sha256"] for batch in batches}) >= 2 or all(batch.get("reconciliation_evidence") for batch in batches))
            stable = stable and (distinct if manual else batches not in (None, "", "TBD"))
        gates["STABILITY"] = "PASS" if stable else "UNKNOWN"
        if manual and not stable:
            warnings.append({"code": "manual_batches_insufficient", "message": "MANUAL requires three evidenced repeatability batches"})
    result = _result(path, actual_hash, errors, warnings, gates, len(rows), len(duplicate_keys), manifest_path)
    if entries:
        entry = entries[0]
        from cross_asset.pit import classify_pit_grade
        grade, grade_warnings = classify_pit_grade(entry)
        warnings.extend({"code": code, "message": code} for code in grade_warnings)
        result["warnings"] = sorted(warnings, key=lambda item: (item["code"], item["message"]))
        result["counts"]["warnings"] = len(result["warnings"])
        result["registry_candidate"] = {"series_id": entry.get("series_id"), "provider": entry.get("provider"), "source_series_id": entry.get("source_series_id"), "pit_grade": grade.value if grade else None, "origin": entry.get("origin", "UNAVAILABLE"), "permission_scope": entry.get("permission_scope"), "semantic_equivalence": entry.get("semantic_equivalence"), "reviewer": entry.get("reviewer"), "approved_at": entry.get("approved_at")}
    return result


def exit_code(result: dict[str, Any]) -> int:
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}[result["status"]]
