"""Strict production CSV ingestion for canonical market observations."""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from cross_asset.settings import get_settings
from cross_asset.storage import init_db

from .raw_archive import ImmutableRawArchive
from .runner import IngestionRunner

REQUIRED_COLUMNS = {
    "series_id",
    "observation_date",
    "value",
    "available_at",
    "source",
    "source_series_id",
}
OPTIONAL_COLUMNS = {"vintage_date", "quality"}
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ProductionCSVError(ValueError):
    """Raised when a production CSV fails validation before any write."""

    def __init__(self, errors: list[dict[str, object]]):
        self.errors = errors
        super().__init__("production CSV validation failed")


def _series_catalog_path() -> Path:
    configured = Path(get_settings().cross_asset_config_dir)
    if configured.is_absolute():
        return configured / "series.yml"
    current = Path.cwd() / configured / "series.yml"
    if current.is_file():
        return current
    return Path(__file__).resolve().parents[3] / configured / "series.yml"


def _known_series() -> set[str]:
    path = _series_catalog_path()
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ProductionCSVError(
            [{"row": None, "code": "series_catalog_unavailable", "message": type(exc).__name__}]
        ) from exc
    entries = payload.get("series") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ProductionCSVError(
            [{"row": None, "code": "series_catalog_invalid", "message": "series must be a list"}]
        )
    return {str(entry["series_id"]) for entry in entries if isinstance(entry, dict) and entry.get("series_id")}


def _error(errors: list[dict[str, object]], row: int, code: str, message: str) -> None:
    errors.append({"row": row, "code": code, "message": message})


def _csv_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _parse_date(value: str, *, row: int, field: str, errors: list[dict[str, object]]) -> date | None:
    if not isinstance(value, str) or not _DATE_PATTERN.fullmatch(value):
        _error(errors, row, "invalid_date", f"{field} must use YYYY-MM-DD")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        _error(errors, row, "invalid_date", f"{field} must use YYYY-MM-DD")
        return None


def _parse_available_at(
    value: str,
    *,
    row: int,
    errors: list[dict[str, object]],
) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        _error(errors, row, "available_at_required", "available_at must be explicit")
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        _error(errors, row, "available_at_invalid", "available_at must be ISO-8601")
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _error(errors, row, "available_at_timezone_required", "available_at must include a timezone")
        return None
    return parsed.astimezone(UTC)


def _parse_rows(path: Path, payload: bytes) -> tuple[list[dict], dict[str, object]]:
    errors: list[dict[str, object]] = []
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProductionCSVError(
            [{"row": None, "code": "csv_encoding_invalid", "message": "expected UTF-8 CSV"}]
        ) from exc

    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        fieldnames = reader.fieldnames or []
        fields = set(fieldnames)
        missing = sorted(REQUIRED_COLUMNS - fields)
        if missing:
            _error(errors, 1, "required_columns_missing", ",".join(missing))
        if not fieldnames:
            _error(errors, 1, "csv_header_missing", "CSV header is required")
        elif len(fields) != len(fieldnames):
            _error(errors, 1, "csv_header_duplicate", "CSV header columns must be unique")
        elif any(not isinstance(field, str) or not field for field in fieldnames):
            _error(errors, 1, "csv_header_invalid", "CSV header columns must be non-empty")
        raw_rows = list(reader)
    except csv.Error as exc:
        raise ProductionCSVError(
            [{"row": None, "code": "csv_invalid", "message": type(exc).__name__}]
        ) from exc

    if not raw_rows:
        _error(errors, 1, "csv_empty", "CSV must contain at least one observation")

    known_series = _known_series()
    canonical: list[dict] = []
    seen: set[tuple] = set()
    sources: set[str] = set()
    for row_number, raw in enumerate(raw_rows, start=2):
        if None in raw:
            _error(errors, row_number, "csv_row_malformed", "row has more fields than the header")

        series_id = _csv_text(raw.get("series_id")).strip()
        if not series_id:
            _error(errors, row_number, "series_id_required", "series_id must be non-empty")
        elif series_id not in known_series:
            _error(errors, row_number, "unknown_series_id", series_id)

        observation_date = _parse_date(
            raw.get("observation_date", ""), row=row_number, field="observation_date", errors=errors
        )
        available_at = _parse_available_at(
            raw.get("available_at", ""), row=row_number, errors=errors
        )

        raw_value = raw.get("value", "")
        try:
            if not isinstance(raw_value, str) or not raw_value.strip():
                raise ValueError
            value = float(raw_value)
            if not math.isfinite(value):
                raise ValueError
        except (TypeError, ValueError):
            _error(errors, row_number, "value_invalid", "value must be finite and numeric")
            value = None

        source = _csv_text(raw.get("source")).strip()
        source_series_id = _csv_text(raw.get("source_series_id")).strip()
        if not source:
            _error(errors, row_number, "source_required", "source must be non-empty")
        elif any(character in source for character in ("/", "\\", ":")):
            _error(errors, row_number, "source_invalid", "source contains an invalid path character")
        else:
            sources.add(source)
        if not source_series_id:
            _error(errors, row_number, "source_series_id_required", "source_series_id must be non-empty")

        vintage_date = None
        vintage_value = _csv_text(raw.get("vintage_date")).strip()
        if vintage_value:
            vintage_date = _parse_date(
                vintage_value, row=row_number, field="vintage_date", errors=errors
            )
        quality = _csv_text(raw.get("quality")).strip() or "ok"

        if all(item is not None for item in (observation_date, available_at, value)):
            key = (series_id, observation_date, available_at, source, source_series_id)
            if key in seen:
                _error(errors, row_number, "duplicate_observation", "duplicate canonical observation")
            seen.add(key)
            canonical.append(
                {
                    "series_id": series_id,
                    "observation_date": observation_date,
                    "available_at": available_at,
                    "value": value,
                    "source": source,
                    "source_series_id": source_series_id,
                    "vintage_date": vintage_date,
                    "quality": quality,
                    "ingested_at": datetime.now(UTC),
                }
            )

    if len(sources) > 1:
        _error(errors, 1, "mixed_source", "one CSV may contain only one source")
    if errors:
        raise ProductionCSVError(errors)

    metadata = {
        "source": next(iter(sources)),
        "series_ids": sorted({row["series_id"] for row in canonical}),
        "rows": len(canonical),
        "date_min": min(row["observation_date"] for row in canonical).isoformat(),
        "date_max": max(row["observation_date"] for row in canonical).isoformat(),
        "file": str(path),
    }
    return canonical, metadata


def ingest_production_csv(
    file: str | Path,
    *,
    database: str | Path | None = None,
    raw_dir: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Validate and optionally ingest one canonical production CSV."""
    path = Path(file)
    try:
        payload = path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise ProductionCSVError(
            [{"row": None, "code": "file_read_failed", "message": type(exc).__name__}]
        ) from exc

    rows, metadata = _parse_rows(path, payload)
    file_sha256 = hashlib.sha256(payload).hexdigest()
    if dry_run:
        return {"status": "VALID", "dry_run": True, "file_sha256": file_sha256, **metadata}

    archive_root = raw_dir if raw_dir is not None else get_settings().raw_dir
    archive = ImmutableRawArchive(archive_root)
    raw_file = archive.write(metadata["source"], "production_csv", payload, extension="csv")
    for row in rows:
        row["raw_file"] = raw_file

    database_path = database if database is not None else get_settings().database_path
    store = init_db(database_path)
    try:
        result = IngestionRunner(store).run(metadata["source"], lambda: rows)
    finally:
        store.close()

    rows_written = int(result["rows_written"])
    # Passing CSV syntax makes rows *candidate* observations only. Formal
    # consumption requires a matching acceptance-registry provenance (Issue #18);
    # the marker below keeps that boundary explicit in the command output.
    return {
        "status": str(result.get("status", "failed")).upper(),
        "consumption_status": "CANDIDATE",
        "dry_run": False,
        "run_id": result["run_id"],
        "source": metadata["source"],
        "rows_input": len(rows),
        "rows_written": rows_written,
        "rows_existing": len(rows) - rows_written,
        "series_ids": metadata["series_ids"],
        "raw_file": raw_file,
        "file_sha256": file_sha256,
        "date_min": metadata["date_min"],
        "date_max": metadata["date_max"],
    }


__all__ = [
    "OPTIONAL_COLUMNS",
    "REQUIRED_COLUMNS",
    "ProductionCSVError",
    "ingest_production_csv",
]
