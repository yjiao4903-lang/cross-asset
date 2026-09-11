"""Provider-neutral manual source-file intake -> existing research-admission.

Lane B transport adapter:

    USER_MANUAL_DATA_EXPORT
      -> IMMUTABLE_RAW_FILE          (byte-preserving, archived before parsing)
      -> SHA256 / SIDECAR            (raw hash + semantic-manifest hash bound)
      -> SEMANTIC_VALIDATION         (explicit, fail-closed, no inference)
      -> CANONICAL_IMPORT            (public shape consumed by ingest_research_data)
      -> RESEARCH_ADMISSIBLE         (existing gates only, never self-approve)
      -> SANCTIONED_QUERY            (existing approved-observation read path)

This is an *adapter* into existing primitives. It does not build a parallel
ingestion/admission system. It:

- never mints approvals; ``usage_status``/reviewer/approved_at/PIT grade are
  carried only from an existing acceptance-registry PASS, and only in the
  explicit ``write`` path;
- reuses the existing read-only DATA_ACCEPTANCE_GATE (``validate_data_file``);
- treats a rule name such as ``market_close`` as documentation only - an
  explicit timezone-aware ``available_at`` is required per row (no inference);
- distinguishes ZERO from MISSING: a numeric 0 is a valid value, never treated
  as a blank; None/blank/non-finite are explicit exclusions, never zero.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from .raw_archive import ImmutableRawArchive

# --------------------------------------------------------------------------- #
# Manifest contract.
# --------------------------------------------------------------------------- #
# Fields a semantic manifest must declare per series (explicit, no inference).
_REQUIRED_SERIES_FIELDS = {
    "series_id",
    "provider",  # professional source identity, NOT collapsed to "manual"
    "source_series_id",
    "instrument_identity",
    "field",
    "unit",
    "currency",
    "price_type",
    "instrument_type",
    "frequency",
    "timezone",
    "observation_date_rule",
    "available_at_rule",  # DOCUMENTATION ONLY - never a resolved timestamp
    "vintage_rule",
    "missing_policy",
}

_MISSING_SENTINELS = (None, "", "TBD", "UNKNOWN", "UNAVAILABLE")
# Canonical FX quote-direction contracts. Anything else (or an unresolved
# sentinel) is treated as unresolved fail-closed; arbitrary non-empty strings
# are never accepted as "resolved".
_FX_QUOTE_DIRECTION_CANONICAL = ("QUOTE_PER_BASE", "BASE_PER_QUOTE")


def _resolved(value) -> bool:
    """True only when a declared value is a non-empty, non-sentinel string.

    ``None``/``""``/``TBD``/``UNKNOWN``/``UNAVAILABLE`` are unresolved. A numeric
    zero (e.g. a genuine 0) is NOT a missing sentinel, so it remains usable.
    """
    if value is None:
        return False
    if not isinstance(value, str):
        value = str(value)
    text = value.strip()
    return bool(text) and text not in _MISSING_SENTINELS


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# Raw-file handling: byte-preserving immutable copy + hashes, BEFORE parsing.
# --------------------------------------------------------------------------- #
def stage_manual_raw(
    source_path: str | Path,
    *,
    source_provider: str,
    dataset: str,
    archive: ImmutableRawArchive,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    """Copy original source bytes into the immutable archive and return identity.

    The exact original bytes are preserved (never re-encoded by CSV/XLSX
    parsing) and hashed. Returns raw path + the SHA-256 of the archived bytes.
    """
    source_path = Path(source_path)
    original_bytes = source_path.read_bytes()
    extension = source_path.suffix.strip(".") or "bin"
    captured_at = captured_at or datetime.now(UTC)
    raw_file = archive.write(
        source_provider,
        dataset,
        original_bytes,
        captured_at=captured_at,
        extension=extension,
    )
    raw_sha256 = sha256_bytes(original_bytes)
    return {"raw_file": raw_file, "raw_sha256": raw_sha256}


# --------------------------------------------------------------------------- #
# Sidecar / provenance manifest.
# --------------------------------------------------------------------------- #
def write_sidecar(
    *,
    raw_file: str,
    raw_sha256: str,
    semantic_manifest: dict[str, Any],
    semantic_manifest_sha256: str,
    source_path: str | Path,
    source_label: str,
    worksheet: str | None,
    ingested_at: datetime | None = None,
) -> dict[str, Any]:
    source_path = Path(source_path)
    ingested_at = ingested_at or datetime.now(UTC)
    assert ingested_at.tzinfo is not None, "ingested_at must be timezone-aware"
    return {
        "source_path": str(source_path),
        "source_label": source_label,
        "worksheet": worksheet,
        "raw_file": raw_file,
        "raw_sha256": raw_sha256,
        "semantic_manifest_sha256": semantic_manifest_sha256,
        "ingested_at": ingested_at.astimezone(UTC).isoformat(),
        "origin": "MANUAL",
    }


def collect_sidecar_record(
    *,
    source_label: str,
    raw_file: str,
    raw_sha256: str,
    semantic_manifest_sha256: str,
    export_timestamp: str | None = None,
    worksheet: str | None = None,
    provider: str | None = None,
    source_series_id: str | None = None,
) -> dict[str, Any]:
    """Sidecar metadata for the provenance manifest (source facts only)."""
    return {
        "source_label": source_label,
        "export_timestamp": export_timestamp,
        "source_series_id": source_series_id,
        "provider": provider,
        "worksheet": worksheet,
        "raw_file": raw_file,
        "raw_sha256": raw_sha256,
        "semantic_manifest_sha256": semantic_manifest_sha256,
        "ingested_at": datetime.now(UTC).isoformat(),
        "origin": "MANUAL",
    }


# --------------------------------------------------------------------------- #
# Tabular read (CSV / XLSX). Parsing happens AFTER archiving.
# --------------------------------------------------------------------------- #
def normalize_cell_value(value: Any) -> Any:
    """Normalize a raw cell to a plain comparable form.

    Excel/OOXML native ``datetime``/``date`` cells are converted to ISO strings
    so downstream parsing is type-safe (never ``.strip()`` on a datetime).
    Numbers (including 0), strings and None are preserved as-is.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def read_manual_tabular(
    path: str | Path,
    *,
    file_format: str | None = None,
    worksheet: str | None = None,
) -> dict[str, Any]:
    """Return declared columns and normalized rows for CSV or one XLSX sheet.

    ``worksheet`` is required for XLSX; workbook sheet selection is never an
    inferred semantic and must agree with the semantic manifest. CSV is the
    normative interchange format.
    """
    path = Path(path)
    fmt = (file_format or path.suffix.lstrip(".")).strip().lower()
    if fmt == "csv":
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            columns = list(reader.fieldnames or [])
            rows = [
                {key: normalize_cell_value(value) for key, value in row.items()}
                for row in reader
            ]
        return {"format": "csv", "worksheet": None, "columns": columns, "rows": rows}
    if fmt in {"xlsx", "xlsm"}:
        from openpyxl import load_workbook

        if not worksheet:
            raise ValueError("xlsx_worksheet_required")
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            if worksheet not in workbook.sheetnames:
                raise ValueError("xlsx_worksheet_not_found")
            sheet = workbook[worksheet]
            value_rows = list(sheet.iter_rows(values_only=True))
        finally:
            workbook.close()
        if not value_rows:
            return {"format": "xlsx", "worksheet": worksheet, "columns": [], "rows": []}
        headers = [str(normalize_cell_value(cell)) if cell is not None else "" for cell in value_rows[0]]
        rows = [
            {header: normalize_cell_value(cell) for header, cell in zip(headers, row)}
            for row in value_rows[1:]
        ]
        return {"format": "xlsx", "worksheet": worksheet, "columns": headers, "rows": rows}
    raise ValueError(f"unsupported_manual_format:{fmt}")


# --------------------------------------------------------------------------- #
# Shared value / row evaluation. Validator and candidate builder MUST agree.
# --------------------------------------------------------------------------- #
def parse_observation_value(value: Any) -> tuple[str, float | None]:
    """Parse a cell into ``(verdict, value)``.

    Verdicts: ``ok`` | ``missing`` | ``nonfinite`` | ``invalid``.
    A numeric zero (int/float ``0``) is a valid ``ok`` value and is NEVER
    treated as missing. None / blank string are ``missing``; inf/nan are
    ``nonfinite``; unparseable text is ``invalid``.
    """
    if value is None:
        return ("missing", None)
    if isinstance(value, str) and not value.strip():
        return ("missing", None)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return ("invalid", None)
    if not math.isfinite(parsed):
        return ("nonfinite", None)
    return ("ok", parsed)


def _date_text(value: Any) -> str:
    """Normalize any cell to a YYYY-MM-DD observation date string.

    Handles Excel-native ``datetime``/``date`` objects and ISO strings (which may
    carry a time component) without ever calling ``.strip()`` on a raw datetime
    and without guessing a material timezone.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):  # datetime is a subclass; handled above
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip()
        try:
            return datetime.fromisoformat(text).date().isoformat()
        except ValueError:
            return text
    return str(value).strip()


def _aware_iso_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value).strip()


def evaluate_row(row: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a single data row against its semantic manifest entry.

    Returns a verdict mapping with keys:
      - ``verdict``: ``ok`` | ``excluded`` | ``error``
      - ``reason``/``code``: explicit reason when not ok
      - ``observation``: canonical observation dict when ok

    Value MISSING vs ZERO is handled by ``parse_observation_value``. A rule name
    such as ``market_close`` never resolves ``available_at``; an explicit
    timezone-aware timestamp (or a deterministic rule that is actually
    implemented and verified) is required, otherwise the row is an ``error``.
    """
    series_id = str(row.get("series_id", "")).strip()
    # Source-identity binding: a row may name the professional source.
    row_source = str(row.get("source_series_id", "") or "").strip()
    manifest_source = str(entry.get("source_series_id") or "").strip()
    if row_source and row_source != manifest_source:
        return {
            "verdict": "error",
            "code": "row_source_identity_conflict",
            "series_id": series_id,
            "source_series_id": row_source,
            "manifest_source_series_id": manifest_source,
        }

    value_verdict, numeric = parse_observation_value(row.get("value"))
    if value_verdict == "missing":
        return {
            "verdict": "excluded",
            "reason": "missing_value_not_zerofilled",
            "series_id": series_id,
            "observation_date": row.get("observation_date"),
            "value": row.get("value"),
        }
    if value_verdict == "nonfinite":
        return {
            "verdict": "excluded",
            "reason": "value_nonfinite_not_zerofilled",
            "series_id": series_id,
            "observation_date": row.get("observation_date"),
            "value": row.get("value"),
        }
    if value_verdict == "invalid":
        return {
            "verdict": "excluded",
            "reason": "value_not_numeric_not_zerofilled",
            "series_id": series_id,
            "observation_date": row.get("observation_date"),
            "value": row.get("value"),
        }

    obs_date_text = _date_text(row.get("observation_date"))
    if not obs_date_text:
        return {"verdict": "error", "code": "observation_date_missing", "series_id": series_id}
    try:
        date.fromisoformat(obs_date_text)
    except ValueError:
        return {"verdict": "error", "code": "observation_date_invalid", "series_id": series_id}

    avail_text = _aware_iso_text(row.get("available_at"))
    if not avail_text:
        return {
            "verdict": "error",
            "code": "pit_available_at_unresolved",
            "series_id": series_id,
            "observation_date": obs_date_text,
        }
    try:
        avail_dt = datetime.fromisoformat(avail_text)
    except ValueError:
        return {"verdict": "error", "code": "available_at_invalid", "series_id": series_id}
    if avail_dt.tzinfo is None:
        return {"verdict": "error", "code": "available_at_timezone_required", "series_id": series_id}
    avail = avail_dt.astimezone(UTC)
    if avail.date() < date.fromisoformat(obs_date_text):
        return {"verdict": "error", "code": "available_at_before_observation_date", "series_id": series_id}

    return {
        "verdict": "ok",
        "series_id": series_id,
        "observation": {
            "series_id": series_id,
            "source_series_id": str(entry.get("source_series_id") or ""),
            "observation_date": obs_date_text,
            "available_at": avail.isoformat(),
            "value": numeric,  # float; preserves numeric zero
            "quality": "ok",
        },
    }


# --------------------------------------------------------------------------- #
# Explicit semantic manifest validation (fail-closed, no inference).
# --------------------------------------------------------------------------- #
def _conditional_semantics_errors(entry: dict[str, Any]) -> list[dict[str, str]]:
    """Material-semantics gates keyed off the DECLARED instrument/field semantics.

    These never guess from ``source_series_id``, filename or column names. If a
    series declares a semantic that needs a disambiguating contract and that
    contract is unresolved (missing or an unresolved sentinel) or - for FX quote
    direction - not a canonical value, the manifest is rejected fail-closed.
    """
    errors: list[dict[str, str]] = []
    series_id = str(entry.get("series_id") or "unknown")
    instrument_type = str(entry.get("instrument_type") or "").strip().lower()
    field = str(entry.get("field") or "").strip().lower()
    price_type = str(entry.get("price_type") or "").strip().lower()

    # FX: explicit base/quote currency AND a canonical quote direction are
    # required. Unresolved sentinels and non-canonical direction values BLOCK.
    if instrument_type in {"fx", "fx_spot", "fx_forward"}:
        base_ok = _resolved(entry.get("base_currency"))
        quote_ok = _resolved(entry.get("quote_currency"))
        qd = entry.get("quote_direction")
        qd_ok = _resolved(qd) and str(qd).strip().upper() in _FX_QUOTE_DIRECTION_CANONICAL
        if not (base_ok and quote_ok and qd_ok):
            errors.append({"code": "FX_QUOTE_DIRECTION_UNRESOLVED", "message": series_id})

    # Continuous futures: roll/adjustment semantics must be explicitly resolved
    # (never TBD/UNKNOWN/UNAVAILABLE).
    if instrument_type in {"futures_continuous", "continuous_futures"}:
        required = (
            "continuous_contract_identity",
            "roll_method",
            "roll_semantics",
            "adjustment_semantics",
        )
        if not all(_resolved(entry.get(f)) for f in required):
            errors.append({"code": "FUTURES_ROLL_SEMANTICS_UNRESOLVED", "message": series_id})

    # Returns/index: a series declared as a return must state a resolved return type.
    is_return = (
        "return" in field
        or "return" in price_type
        or price_type in {"total_return_index", "excess_return_index", "net_return_index"}
    )
    if is_return and not _resolved(entry.get("return_type")):
        errors.append({"code": "RETURN_TYPE_UNRESOLVED", "message": series_id})
    return errors


def _provider_identity_errors(entry: dict[str, Any], top_level_provider: str) -> list[dict[str, str]]:
    provider = str(entry.get("provider") or "").strip()
    if top_level_provider and provider and provider != top_level_provider:
        return [
            {
                "code": "PROVIDER_IDENTITY_CONFLICT",
                "message": f"{entry.get('series_id', 'unknown')}: {provider} != file provider {top_level_provider}",
            }
        ]
    return []


def validate_semantic_manifest(manifest: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    series = manifest.get("series", manifest.get("records", [manifest]))
    if not isinstance(series, list) or not series:
        return [{"code": "semantic_series_required", "message": "manifest declares no series"}]
    top_level_provider = str(manifest.get("provider") or "").strip()
    # The file/top-level provider is REQUIRED - it is never inferred, and there
    # is no fallback to "manual". This is the authoritative provenance provider.
    if not _resolved(manifest.get("provider")):
        errors.append({"code": "provider_unresolved", "message": "file/top-level provider required"})
    for entry in series:
        if not isinstance(entry, dict):
            errors.append({"code": "semantic_series_invalid", "message": "series entry must be a mapping"})
            continue
        missing = sorted(_REQUIRED_SERIES_FIELDS - set(entry))
        if missing:
            errors.append(
                {
                    "code": "semantic_fields_missing",
                    "message": f"{entry.get('series_id', 'unknown')}:{' ,'.join(missing)}",
                }
            )
        for field in _REQUIRED_SERIES_FIELDS:
            if entry.get(field) in _MISSING_SENTINELS:
                errors.append(
                    {
                        "code": "semantic_field_unresolved",
                        "message": f"{entry.get('series_id', 'unknown')}:{field}",
                    }
                )
        errors.extend(_provider_identity_errors(entry, top_level_provider))
        errors.extend(_conditional_semantics_errors(entry))
    return sorted(errors, key=lambda item: (item["code"], item["message"]))


def _manifest_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries = manifest.get("series", manifest.get("records", [manifest]))
    return entries if isinstance(entries, list) else []


def validate_rows_against_semantics(
    rows: list[dict[str, Any]],
    semantic_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Validate each row against the explicit manifest using ``evaluate_row``.

    Returns per-row errors and explicit exclusions (never zero-filled or
    silently dropped). MISSING is distinct from ZERO.
    """
    report: dict[str, Any] = {"errors": [], "excluded": [], "rows": 0, "admitted_rows": 0}
    fields = {entry.get("series_id"): entry for entry in _manifest_entries(semantic_manifest)}
    for row in rows:
        series_id = str(row.get("series_id", "")).strip()
        entry = fields.get(series_id)
        if entry is None:
            report["errors"].append(
                {"code": "row_series_identity_unresolved", "series_id": series_id or "UNKNOWN"}
            )
            continue
        verdict = evaluate_row(row, entry)
        if verdict["verdict"] == "ok":
            report["rows"] += 1
            report["admitted_rows"] += 1
        elif verdict["verdict"] == "error":
            report["errors"].append({key: verdict[key] for key in ("code", "series_id") if key in verdict})
        else:
            report["excluded"].append(
                {key: verdict[key] for key in ("reason", "series_id", "observation_date", "value") if key in verdict}
            )
    return report


# --------------------------------------------------------------------------- #
# Canonical candidate conversion -> public admission-record shape.
# --------------------------------------------------------------------------- #
def approval_contract_sha256(*, raw_sha256: str, semantic_digest: str) -> str:
    """Combined approval contract hash = raw-data identity + semantic-contract identity.

    Reuses the existing acceptance-registry ``manifest_hash`` field to bind an
    approval to BOTH the exact raw bytes AND the material semantic contract. A
    PASS minted for the same raw bytes under different semantics is therefore
    rejected. No schema migration. ``manifest_hash == raw_sha256`` alone is NOT
    sufficient (same bytes + changed semantics would silently reuse an old PASS).
    """
    return sha256_bytes(f"{raw_sha256}::{semantic_digest}".encode())


def build_candidate_records_from_rows(
    *,
    raw_file: str,
    raw_sha256: str,
    semantic_manifest: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build candidates in the ``ingest_research_data`` record shape.

    Candidates are deliberately NOT approved: they carry no ``usage_status``,
    no ``reviewer``/``approved_at`` and no PIT grade. Only after a matching
    existing acceptance-registry PASS (whose ``manifest_hash`` equals the
    combined ``contract_hash``) is verified may the caller enrich the record
    before handing it to ``ingest_research_data()``. ``source_contract`` binds
    raw + semantic-manifest identity so the same raw bytes under different
    semantics differ, and ``contract_hash`` is the combined raw+semantic hash
    used to match an existing approval.
    """
    records: list[dict[str, Any]] = []
    fields = {entry.get("series_id"): entry for entry in _manifest_entries(semantic_manifest)}
    for entry in fields.values():
        series_id = entry.get("series_id")
        provider = entry.get("provider")
        source_series_id = entry.get("source_series_id")
        semantic_digest = sha256_bytes(
            json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        source_contract = f"manual:{provider}:{source_series_id}:{semantic_digest[:16]}"
        contract_hash = approval_contract_sha256(raw_sha256=raw_sha256, semantic_digest=semantic_digest)
        observations = [
            verdict["observation"]
            for row in rows
            if (verdict := evaluate_row(row, entry)).get("verdict") == "ok"
        ]
        records.append(
            {
                "series_id": series_id,
                "provider": provider,
                "source_series_id": source_series_id,
                "origin": "MANUAL",
                "raw_file": raw_file,
                "raw_hash": raw_sha256,
                "source_contract": source_contract,
                "contract_hash": contract_hash,
                # No usage_status / reviewer / approved_at / pit_grade here:
                # staging state must remain non-approved.
                "observations": observations,
            }
        )
    return records


# --------------------------------------------------------------------------- #
# Existing acceptance-registry PASS matching with manifest_hash binding.
# --------------------------------------------------------------------------- #
def _load_policies(policy_payload: str | None) -> dict[str, dict]:
    if not policy_payload:
        return {}
    path = Path(policy_payload)
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw) if path.suffix.lower() == ".json" else yaml.safe_load(raw)
    return data if isinstance(data, dict) else {}


def _registry_pass_reviewer(
    store, record: dict[str, Any], expected_manifest_hash: str
) -> dict[str, Any] | None:
    """Return an existing acceptance-registry PASS that matches the current
    semantic/data contract.

    The PASS must reside on the same identity triple and its ``manifest_hash``
    must equal the current combined contract hash (raw-data identity AND
    semantic-contract identity, see ``approval_contract_sha256``). Otherwise a
    materially different semantic/data contract could reuse an old approval - which
    is not allowed. An old PASS minted against ``raw_sha256`` only (or against
    different semantics) for the same bytes is rejected. No schema migration is
    performed.
    """
    from cross_asset.storage.acceptance_registry import query_data_acceptance

    rows = query_data_acceptance(
        store,
        series_id=record.get("series_id"),
        provider=record.get("provider"),
        source_series_id=record.get("source_series_id"),
        usage_status="RESEARCH_ADMISSIBLE",
    )
    for row in rows:
        if (
            row.get("status") == "PASS"
            and row.get("usage_status") == "RESEARCH_ADMISSIBLE"
            and row.get("reviewer") not in (None, "", "TBD")
            and row.get("approved_at") is not None
            and row.get("manifest_hash") == expected_manifest_hash
        ):
            return row
    return None


# --------------------------------------------------------------------------- #
# Reconnect to the existing read-only DATA_ACCEPTANCE_GATE.
# --------------------------------------------------------------------------- #
def run_data_acceptance_gate(
    *,
    parsed_ok_rows: list[dict[str, Any]],
    semantic_manifest: dict[str, Any],
    raw_sha256: str,
    contract_hash: str,
    first_obs_date: str | None,
    last_obs_date: str | None,
    reviewer: str | None,
    approved_at: str | None,
) -> dict[str, Any]:
    """Run the existing ``validate_data_file`` gate for the staged pack.

    The authoritative acceptance checker is reused; PARTIAL (e.g. MANUAL
    three-batch STABILITY) and FAIL are surfaced faithfully. This does not
    create a parallel admission gate.

    The returned result carries ``sha256`` = the combined approval contract hash
    (raw-data identity + semantic-contract identity). Feeding this result through
    the existing ``register-data-acceptance -> candidate_registry_record ->
    upsert_data_acceptance`` boundary therefore persists that exact combined
    contract hash as the registry ``manifest_hash``, so a later ``--write`` lookup
    matches only the identical contract (no schema migration, backward
    compatible: ``candidate_registry_record`` keeps reading ``result["sha256"]``).
    """
    from .acceptance import validate_data_file

    columns = ["series_id", "source_series_id", "observation_date", "available_at", "value"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        csv_path = tmp_dir / "projection.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for row in parsed_ok_rows:
                writer.writerow(
                    {
                        "series_id": row.get("series_id", ""),
                        "source_series_id": row.get("source_series_id", ""),
                        "observation_date": row.get("observation_date", ""),
                        "available_at": row.get("available_at", ""),
                        "value": row.get("value", ""),
                    }
                )
        projection_sha = compute_sha256(csv_path)
        entry = _manifest_entries(semantic_manifest)[0]
        # The authoritative MANUAL gate requires manifest-level provenance: origin
        # evidence needs file_hash / template_id / available_at. We carry the latest
        # explicit per-row available_at as the series as-of - never a guessed tz.
        manifest_available_at = (
            max((obs.get("available_at", "") for obs in parsed_ok_rows if obs.get("available_at")), default=None)
        )
        acceptance_manifest = {
            "series_id": entry.get("series_id"),
            "provider": entry.get("provider"),
            "source_series_id": entry.get("source_series_id"),
            "permission_scope": entry.get("permission_scope"),
            "origin": "MANUAL",
            "observation_definition": entry.get("instrument_identity"),
            "unit": entry.get("unit"),
            "currency": entry.get("currency"),
            "timezone": entry.get("timezone"),
            "price_type": entry.get("price_type"),
            "adjustment_type": "raw",
            "frequency": entry.get("frequency"),
            "history_start": first_obs_date,
            "history_end": last_obs_date,
            "observation_date_rule": entry.get("observation_date_rule"),
            "available_at_rule": entry.get("available_at_rule"),
            "vintage_rule": entry.get("vintage_rule"),
            "missing_policy": entry.get("missing_policy"),
            "semantic_equivalence": True,
            "template_version": "manual_export_v1",
            "file_sha256": projection_sha,
            "available_at": manifest_available_at,
            # Forward the MANUAL admission evidence the authoritative gate
            # actually requires (MANUAL three-batch STABILITY, LEGAL approval and
            # PIT grade). These come from the semantic manifest entry ONLY when
            # declared; explicit ``reviewer``/``approved_at`` params (if given)
            # take precedence. Without this evidence the gate stays PARTIAL and
            # can never mint a PASS - it is never upgraded downstream.
            "reviewer": reviewer if reviewer is not None else entry.get("reviewer"),
            "approved_at": approved_at if approved_at is not None else entry.get("approved_at"),
            "repeatability_evidence": entry.get("repeatability_evidence"),
            "pit_grade": entry.get("pit_grade"),
            "reconciliation_notes": "",
        }
        manifest_path = tmp_dir / "projection.manifest.json"
        manifest_path.write_text(json.dumps(acceptance_manifest, sort_keys=True), encoding="utf-8")
        result = validate_data_file(csv_path, manifest_path)
    result = dict(result)
    # The contract identity for manual intake is the combined raw+semantic hash,
    # not the ephemeral projection file hash. Registering this result persists
    # the combined contract hash as the registry manifest_hash.
    result["sha256"] = contract_hash
    return result


def build_manual_registration_result(
    *,
    gate_result: dict[str, Any],
    contract_hash: str,
    series_id: str,
    provider: str,
    source_series_id: str,
    reviewer: str,
    approved_at: datetime | str,
) -> dict[str, Any]:
    """Assemble an explicit-registrar payload for the combined contract.

    This helper NEVER upgrades the authoritative DATA_ACCEPTANCE_GATE. It leaves
    ``status`` / ``TECH`` / ``LEGAL`` / ``PIT`` / ``STABILITY`` / ``pit_grade``
    exactly as produced by ``validate_data_file`` - a genuine PARTIAL/UNKNOWN/FAIL
    (e.g. missing MANUAL three-batch STABILITY) remains so. It only:

      - binds the combined raw+semantic contract hash via ``sha256``;
      - carries the explicit ``reviewer``/``approved_at`` metadata;
      - when (and only when) the authoritative gate is a genuine PASS (all four
        gates PASS) marks the record ``RESEARCH_ADMISSIBLE`` so the real
        registration primitive may persist it.

    If the gate is not a genuine PASS it fails closed by raising, so a formal
    ``RESEARCH_ADMISSIBLE PASS`` can never be minted from insufficient evidence.
    It is never invoked inside the manual-intake write path, so there is no
    self-approval. Durability still goes through the existing
    ``register-data-acceptance -> candidate_registry_record -> upsert_data_acceptance``
    path (this only builds the payload).
    """
    status = gate_result.get("status")
    gates = gate_result.get("gates") or {}
    if status != "PASS" or not all(
        gates.get(name) == "PASS" for name in ("TECH", "LEGAL", "PIT", "STABILITY")
    ):
        raise ValueError("manual_registration_requires_authoritative_pass")
    result = dict(gate_result)
    result["sha256"] = contract_hash
    candidate = dict(result.get("registry_candidate") or {})
    candidate.update(
        {
            "series_id": series_id,
            "provider": provider,
            "source_series_id": source_series_id,
            "usage_status": "RESEARCH_ADMISSIBLE",
            "origin": candidate.get("origin") or "MANUAL",
            "reviewer": reviewer,
            "approved_at": approved_at,
        }
    )
    result["registry_candidate"] = candidate
    return result


def _worksheet_identity(semantic_manifest: dict[str, Any], worksheet_param: str | None) -> tuple[str | None, list[dict[str, str]]]:
    """Resolve the worksheet/table identity for a single-read pack.

    The semantic manifest must explicitly declare worksheet identity (no
    inferred sheet selection). A provided ``worksheet`` param must agree with
    the manifest; mismatch is blocked.
    """
    declared = sorted(
        {
            str(e["worksheet"]).strip()
            for e in _manifest_entries(semantic_manifest)
            if str(e.get("worksheet") or "").strip()
        }
    )
    errors: list[dict[str, str]] = []
    if len(declared) > 1:
        errors.append({"code": "multi_worksheet_not_single_read", "message": ",".join(declared)})
    if worksheet_param and declared and worksheet_param not in declared:
        errors.append(
            {
                "code": "worksheet_mismatch",
                "message": f"manifest declares {declared[0] if declared else 'none'} but requested {worksheet_param}",
            }
        )
    effective = worksheet_param or (declared[0] if declared else None)
    return effective, errors


# --------------------------------------------------------------------------- #
# Pipeline entry point.
# --------------------------------------------------------------------------- #
def ingest_manual_pack(
    *,
    source_file: str | Path,
    manifest_path: str | Path,
    raw_archive: ImmutableRawArchive,
    sidecar_dir: str | Path | None = None,
    worksheet: str | None = None,
    source_label: str = "manual_export",
    export_timestamp: str | None = None,
    policies_payload: str | None = None,
    database: str | None = None,
    write: bool = False,
) -> dict[str, Any]:
    """Run the Lane-B pipeline: archive -> hash -> sidecar -> validate -> stage.

    Default is archive/validate/stage only (no DB write). A formal DB write
    requires the explicit ``write=True`` flag AND an existing acceptance-registry
    PASS whose ``manifest_hash`` matches the current raw data (and an enabled
    policy); otherwise the run fails closed and never mints its own approval.
    """
    source_path = Path(source_file)
    if not source_path.is_file():
        return {"status": "BLOCKED", "errors": [{"code": "source_file_not_found", "message": str(source_path)}]}

    manifest_file = Path(manifest_path)
    try:
        manifest_text = manifest_file.read_text(encoding="utf-8")
    except OSError as exc:
        return {"status": "BLOCKED", "errors": [{"code": "manifest_not_found", "message": str(exc)}]}
    semantic = json.loads(manifest_text) if manifest_file.suffix.lower() == ".json" else yaml.safe_load(manifest_text)
    if not isinstance(semantic, dict):
        return {"status": "BLOCKED", "errors": [{"code": "semantic_manifest_invalid", "message": "manifest must be a mapping"}]}

    fmt = source_path.suffix.lstrip(".").strip().lower()
    if fmt in {"xlsx", "xlsm", "csv"}:
        pass
    else:
        return {"status": "BLOCKED", "errors": [{"code": "unsupported_manual_format", "message": fmt}]}

    effective_worksheet, sheet_errors = _worksheet_identity(semantic, worksheet)

    # Raw file archived/hashed BEFORE parsing (byte-preserving).
    staged = stage_manual_raw(
        source_path,
        # No fallback to "manual": the top-level provider is authoritative and
        # required (validated separately); if absent the pack is BLOCKED and never
        # enters formal provenance under a fabricated provider.
        source_provider=str(semantic.get("provider") or "UNRESOLVED_PROVIDER"),
        dataset=str(semantic.get("dataset", "manual")),
        archive=raw_archive,
    )
    raw_file = staged["raw_file"]
    raw_sha256 = staged["raw_sha256"]

    semantic_manifest_sha256 = sha256_bytes(manifest_text.encode("utf-8"))
    sidecar = collect_sidecar_record(
        source_label=source_label,
        raw_file=raw_file,
        raw_sha256=raw_sha256,
        semantic_manifest_sha256=semantic_manifest_sha256,
        export_timestamp=export_timestamp,
        worksheet=effective_worksheet,
        provider=semantic.get("provider"),
        source_series_id=(
            semantic.get("series", [{}])[0].get("source_series_id")
            if isinstance(semantic.get("series"), list) and semantic.get("series")
            else None
        ),
    )
    sidecar_path = None
    if sidecar_dir:
        sidecar_dir = Path(sidecar_dir)
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        sidecar_path = sidecar_dir / f"{source_path.stem}.sidecar.json"
        sidecar_path.write_text(
            json.dumps(sidecar, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    semantic_errors = validate_semantic_manifest(semantic)
    blockers: list[dict[str, Any]] = []
    blockers.extend(semantic_errors)
    blockers.extend(sheet_errors)

    parsed = None
    row_report: dict[str, Any] = {"rows": 0, "admitted_rows": 0, "errors": [], "excluded": []}
    candidates: list[dict[str, Any]] = []
    if not semantic_errors and not sheet_errors:
        try:
            parsed = read_manual_tabular(source_path, worksheet=effective_worksheet)
        except ValueError as exc:
            blockers.append({"code": str(exc), "message": "tabular read failed"})
        if parsed is not None:
            row_report = validate_rows_against_semantics(parsed["rows"], semantic)
            blockers.extend(row_report["errors"])
            candidates = build_candidate_records_from_rows(
                raw_file=raw_file,
                raw_sha256=raw_sha256,
                semantic_manifest=semantic,
                rows=parsed["rows"],
            )

    for rec in candidates:
        if rec.get("source_series_id") in (None, "", "UNKNOWN", "TBD"):
            blockers.append({"code": "source_series_id_unverified", "message": rec.get("series_id")})

    # Phase-1 scope is one file / one formal series. The Data-acceptance
    # projection is single-series; a multi-series pack fails closed rather than
    # having the gate use only the first manifest entry for all series.
    if len(_manifest_entries(semantic)) > 1:
        blockers.append(
            {
                "code": "MULTI_SERIES_MANUAL_PACK_UNSUPPORTED",
                "message": "one file must carry exactly one formal series",
            }
        )

    # Surface the authoritative DATA_ACCEPTANCE_GATE for the staged pack.
    ok_rows = [
        obs
        for rec in candidates
        for obs in rec.get("observations", [])
    ]
    obs_dates = [obs.get("observation_date") for obs in ok_rows if obs.get("observation_date")]
    first_obs = min(obs_dates) if obs_dates else None
    last_obs = max(obs_dates) if obs_dates else None
    acceptance_gate: dict[str, Any] | None = None
    gate_contract_hash = candidates[0]["contract_hash"] if len(candidates) == 1 else None
    if parsed is not None and not blockers and gate_contract_hash is not None:
        acceptance_gate = run_data_acceptance_gate(
            parsed_ok_rows=ok_rows,
            semantic_manifest=semantic,
            raw_sha256=raw_sha256,
            contract_hash=gate_contract_hash,
            first_obs_date=first_obs,
            last_obs_date=last_obs,
            reviewer=None,
            approved_at=None,
        )

    report: dict[str, Any] = {
        "status": "STAGED",
        "source_file": str(source_path),
        "raw_file": raw_file,
        "raw_sha256": raw_sha256,
        "semantic_manifest_sha256": semantic_manifest_sha256,
        "worksheet": effective_worksheet,
        "sidecar_path": str(sidecar_path) if sidecar_path else None,
        "semantic_manifest": semantic,
        "semantic_errors": semantic_errors,
        "row_validation": row_report,
        "data_acceptance_gate": acceptance_gate,
        "candidate_series": [
            {"series_id": rec["series_id"], "provider": rec["provider"], "source_series_id": rec["source_series_id"], "contract_hash": rec["contract_hash"], "observations": len(rec["observations"])}
            for rec in candidates
        ],
        "blockers": blockers,
        "write_requested": write,
        "admit_result": None,
        "sanctioned_query": None,
    }

    admission: dict[str, Any] | None = None
    if write and not blockers:
        from cross_asset.ingestion.research import ingest_research_data
        from cross_asset.storage import init_db

        policies = _load_policies(policies_payload)
        store = init_db(database)
        try:
            valid_records: list[dict[str, Any]] = []
            for rec in candidates:
                pass_row = _registry_pass_reviewer(store, rec, expected_manifest_hash=rec["contract_hash"])
                if pass_row is None:
                    blockers.append(
                        {"code": "research_admission_not_satisfied", "message": rec.get("series_id")}
                    )
                    continue
                # Enrich the record with the accepted contract ONLY after the
                # existing PASS (with matching manifest_hash) is verified.
                enriched = dict(rec)
                enriched["usage_status"] = "RESEARCH_ADMISSIBLE"
                enriched["reviewer"] = pass_row["reviewer"]
                enriched["approved_at"] = pass_row["approved_at"]
                enriched["pit_grade"] = pass_row.get("pit_grade")
                valid_records.append(enriched)
            if blockers:
                admission = {"status": "REJECTED", "written": 0, "errors": {b["code"]: b for b in blockers}}
            else:
                admission = ingest_research_data(
                    valid_records,
                    policies=policies,
                    store=store,
                    dry_run=False,
                )
        finally:
            store.close()
        report["admit_result"] = admission
        if admission and admission.get("status") == "ADMITTED":
            report["status"] = "ADMITTED"
        else:
            report["status"] = "BLOCKED"
    elif blockers:
        report["status"] = "BLOCKED"

    # Sanctioned-query smoke against the formal read path (existing primitives).
    if write and not blockers and report["status"] == "ADMITTED":
        db_store = init_db(database)
        try:
            from cross_asset.storage.queries import approved_observations_asof

            samples = []
            for rec in candidates:
                decision_time = max(
                    (datetime.fromisoformat(obs["available_at"]).astimezone(UTC) for obs in rec["observations"]),
                    default=datetime(2099, 1, 1, tzinfo=UTC),
                )
                rows = approved_observations_asof(
                    db_store.conn,
                    decision_time,
                    series_id=rec["series_id"],
                    required_usage_status="RESEARCH_ADMISSIBLE",
                ).fetchall()
                samples.append(
                    {
                        "series_id": rec["series_id"],
                        "provider": rec["provider"],
                        "source_series_id": rec["source_series_id"],
                        "visible_rows": len(rows),
                    }
                )
            report["sanctioned_query"] = samples
        finally:
            db_store.close()

    return report


__all__ = [
    "approval_contract_sha256",
    "build_candidate_records_from_rows",
    "build_manual_registration_result",
    "collect_sidecar_record",
    "compute_sha256",
    "evaluate_row",
    "ingest_manual_pack",
    "normalize_cell_value",
    "parse_observation_value",
    "read_manual_tabular",
    "run_data_acceptance_gate",
    "sha256_bytes",
    "stage_manual_raw",
    "validate_rows_against_semantics",
    "validate_semantic_manifest",
    "write_sidecar",
]