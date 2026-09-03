"""Strict, small canonicalizer for audited Wind exports.

This module deliberately stops at the canonical production CSV boundary.  It
does not archive files, open DuckDB, or invoke the production importer.
"""

from __future__ import annotations

import csv
import json
import math
import posixpath
import re
import zipfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import yaml

CANONICAL_COLUMNS = (
    "series_id",
    "observation_date",
    "value",
    "available_at",
    "source",
    "source_series_id",
    "vintage_date",
    "quality",
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LABELS = {
    "instrument_name": {"instrument name", "instrument_name", "指标名称", "名称"},
    "frequency": {"frequency", "频率", "数据频率"},
    "unit": {"unit", "单位", "量纲"},
    "source_series_id": {
        "wind code",
        "wind_code",
        "wind code / 指标id",
        "wind代码",
        "指标id",
        "指标 ID",
        "指标ID",
        "代码",
    },
    "source": {"source", "来源", "数据来源", "数据源"},
    "field_name": {"field name", "field_name", "字段", "字段名"},
    "currency": {"currency", "货币"},
}


class WindCanonicalizerError(ValueError):
    """Raised for an unsupported or invalid Wind export."""

    def __init__(self, code: str, message: str, report: dict[str, Any] | None = None):
        self.code = code
        self.report = report or {}
        super().__init__(f"{code}: {message}")


def _norm(value: Any) -> str:
    return re.sub(r"[\s:：_/\\-]+", " ", str(value).strip().lower())


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or not str(value).strip()


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return date(1899, 12, 30) + timedelta(days=float(value))
        except (TypeError, ValueError, OverflowError):
            return None
    text = str(value).strip()
    if not text or not _DATE_RE.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _excel_column(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _load_mapping(path: str | Path) -> dict[str, dict[str, Any]]:
    try:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise WindCanonicalizerError("INVALID_MAPPING", type(exc).__name__) from exc
    if not isinstance(payload, dict):
        raise WindCanonicalizerError("INVALID_MAPPING", "mapping must be an object")
    entries = payload.get("mappings", payload)
    if not isinstance(entries, dict):
        raise WindCanonicalizerError("INVALID_MAPPING", "mappings must be an object")
    result: dict[str, dict[str, Any]] = {}
    for series_id, item in entries.items():
        if series_id in {"version", "description"}:
            continue
        if not isinstance(item, dict):
            raise WindCanonicalizerError("INVALID_MAPPING", f"invalid entry: {series_id}")
        result[str(series_id)] = dict(item)
    return result


def _approved_by_source(mapping: dict[str, dict[str, Any]]) -> dict[str, tuple[str, dict[str, Any]]]:
    result = {}
    for series_id, item in mapping.items():
        source_id = item.get("source_series_id")
        if source_id is None or not str(source_id).strip() or item.get("approved", True) is False:
            continue
        if item.get("available_at_basis", "POLICY_DERIVED") != "POLICY_DERIVED":
            raise WindCanonicalizerError(
                "INVALID_MAPPING",
                f"available_at_basis must be POLICY_DERIVED: {series_id}",
            )
        source_id = str(source_id).strip()
        if source_id in result:
            raise WindCanonicalizerError("INVALID_MAPPING", f"duplicate source_series_id: {source_id}")
        result[source_id] = (series_id, item)
    return result


def _available_at(day: date, rule: str) -> str:
    if rule in {"CN_EQ_EOD_V1", "CN_BOND_10Y_EOD_V1"}:
        local = datetime.combine(day, time(16 if rule == "CN_EQ_EOD_V1" else 18), tzinfo=ZoneInfo("Asia/Shanghai"))
    elif rule == "HK_EQ_EOD_V1":
        local = datetime.combine(day, time(16, 30), tzinfo=ZoneInfo("Asia/Hong_Kong"))
    elif rule in {"US_EQ_EOD_V1", "COMEX_EOD_V1"}:
        local = datetime.combine(day + timedelta(days=1), time(6), tzinfo=ZoneInfo("Asia/Shanghai"))
    else:
        raise WindCanonicalizerError("INVALID_MAPPING", f"unknown PIT rule: {rule}")
    return local.isoformat()


def _numeric(value: Any) -> float:
    if _is_blank(value):
        raise ValueError("blank")
    number = float(str(value).strip())
    if not math.isfinite(number):
        raise ValueError("non-finite")
    return number


def _metadata_from_frame(frame: list[list[Any]]) -> tuple[int, dict[int, dict[str, Any]]]:
    metadata: dict[int, dict[str, Any]] = {}
    data_start = None
    for row_number in range(len(frame)):
        first = frame[row_number][0] if frame[row_number] else None
        if _as_date(first) is not None:
            data_start = row_number
            break
        label = _norm(first) if not _is_blank(first) else ""
        key = next((key for key, aliases in _LABELS.items() if label in {_norm(alias) for alias in aliases}), None)
        if key is None:
            continue
        for column in range(1, max(len(row) for row in frame)):
            value = frame[row_number][column] if column < len(frame[row_number]) else None
            if not _is_blank(value):
                metadata.setdefault(column, {})[key] = str(value).strip()
    if data_start is None or not metadata:
        raise WindCanonicalizerError("INVALID_METADATA", "Pattern D metadata or data start not found")
    for column, values in metadata.items():
        if not values.get("source_series_id"):
            raise WindCanonicalizerError("INVALID_METADATA", f"missing Wind code in column {_excel_column(column + 1)}")
    return data_start, metadata


def _read_xlsx(path: Path) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    try:
        with zipfile.ZipFile(path) as archive:
            shared: list[str] = []
            workbook_ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            rels_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
            workbook_root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            sheets = workbook_root.findall(".//x:sheet", workbook_ns)
            if len(sheets) != 1:
                raise ValueError("Pattern D requires exactly one worksheet")
            relationship_id = sheets[0].attrib.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            relationship = next(
                (
                    item
                    for item in relationships.findall("r:Relationship", rels_ns)
                    if item.attrib.get("Id") == relationship_id
                ),
                None,
            )
            if relationship is None:
                raise ValueError("worksheet relationship is missing")
            target = relationship.attrib.get("Target", "").lstrip("/")
            worksheet_path = posixpath.normpath(
                target if target.startswith("xl/") else posixpath.join("xl", target)
            )
            if not worksheet_path.startswith("xl/"):
                raise ValueError("worksheet relationship escapes workbook")
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for item in root.findall("x:si", ns):
                    shared.append("".join(node.text or "" for node in item.iter() if node.tag.endswith("}t")))
            root = ElementTree.fromstring(archive.read(worksheet_path))
            ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            cells: dict[tuple[int, int], Any] = {}
            max_row = max_col = 0
            for cell in root.findall(".//x:c", ns):
                ref = cell.attrib.get("r", "")
                match = re.fullmatch(r"([A-Z]+)(\d+)", ref)
                if not match:
                    continue
                letters, row_text = match.groups()
                column = 0
                for letter in letters:
                    column = column * 26 + ord(letter) - 64
                row = int(row_text)
                node = cell.find("x:v", ns)
                inline = cell.find("x:is", ns)
                if inline is not None:
                    value = "".join(node.text or "" for node in inline.iter() if node.tag.endswith("}t"))
                elif node is None:
                    value = None
                elif cell.attrib.get("t") == "s":
                    value = shared[int(node.text or 0)]
                else:
                    text = node.text or ""
                    try:
                        value = float(text)
                    except ValueError:
                        value = text
                cells[(row - 1, column - 1)] = value
                max_row, max_col = max(max_row, row), max(max_col, column)
            frame = [[cells.get((row, column)) for column in range(max_col)] for row in range(max_row)]
    except (OSError, KeyError, ValueError, ElementTree.ParseError, zipfile.BadZipFile) as exc:
        raise WindCanonicalizerError("UNSUPPORTED_FORMAT", type(exc).__name__) from exc
    data_start, metadata = _metadata_from_frame(frame)
    raw: list[dict[str, Any]] = []
    for row_number in range(data_start, len(frame)):
        day = _as_date(frame[row_number][0] if frame[row_number] else None)
        if day is None:
            continue
        for column, meta in metadata.items():
            value = frame[row_number][column] if column < len(frame[row_number]) else None
            raw.append({"date": day, "value": value, "column": _excel_column(column + 1), **meta})
    return raw, "WIND_PATTERN_D_V1", list(metadata.values())


def _read_csv(path: Path) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise WindCanonicalizerError("UNSUPPORTED_FORMAT", type(exc).__name__) from exc
    required = {"date", "value", "wind_code"}
    if not rows or not required.issubset(rows[0]):
        raise WindCanonicalizerError("UNSUPPORTED_FORMAT", "simple CSV requires date,value,wind_code")
    raw = []
    for row in rows:
        item = dict(row)
        item["date"] = _as_date(row.get("date"))
        item["source_series_id"] = row.get("wind_code", "").strip()
        item["column"] = row.get("field_name", "value") or "value"
        raw.append(item)
    return raw, "WIND_SIMPLE_CSV_V1", []


def canonicalize_wind_export(
    file: str | Path,
    *,
    mapping: str | Path,
    output: str | Path | None = None,
    report: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Convert an audited Wind export into the production CSV contract."""
    path = Path(file)
    if path.suffix.lower() == ".xlsx":
        raw, format_name, metadata_rows = _read_xlsx(path)
    elif path.suffix.lower() == ".csv":
        raw, format_name, metadata_rows = _read_csv(path)
    else:
        raise WindCanonicalizerError("UNSUPPORTED_FORMAT", path.suffix or "no extension")
    config = _load_mapping(mapping)
    by_source = _approved_by_source(config)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in raw:
        grouped.setdefault(str(item.get("source_series_id", "")).strip(), []).append(item)

    canonical: list[dict[str, Any]] = []
    series_reports: list[dict[str, Any]] = []
    for source_id, items in grouped.items():
        resolved = by_source.get(source_id)
        series_id, rule_config = resolved if resolved else (None, {})
        metadata = items[0]
        entry: dict[str, Any] = {
            "wind_code": source_id,
            "source_series_id": source_id,
            "series_id": series_id,
            "instrument_name": metadata.get("instrument_name"),
            "frequency": metadata.get("frequency"),
            "unit": metadata.get("unit"),
            "field_name": metadata.get("field_name"),
            "currency": metadata.get("currency"),
            "source": metadata.get("source", "wind") or "wind",
            "raw_column": metadata.get("column"),
            "raw_file": str(path),
            "raw_rows": len(items),
            "canonical_rows": 0,
            "omitted_missing_rows": 0,
            "duplicate_rows": 0,
            "date_min": None,
            "date_max": None,
            "available_at_rule": rule_config.get("available_at_rule"),
            "available_at_basis": rule_config.get("available_at_basis", "POLICY_DERIVED"),
            "status": "UNRESOLVED_MAPPING" if resolved is None else "READY",
        }
        if resolved is None:
            dates = [item["date"] for item in items if item.get("date") is not None]
            entry["omitted_missing_rows"] = sum(1 for item in items if _is_blank(item.get("value")))
            if dates:
                entry["date_min"] = min(dates).isoformat()
                entry["date_max"] = max(dates).isoformat()
            series_reports.append(entry)
            continue
        seen: set[date] = set()
        valid: list[dict[str, Any]] = []
        error_status = None
        for item in items:
            day = item.get("date")
            if day is None:
                error_status = "INVALID_METADATA"
                break
            if _is_blank(item.get("value")):
                entry["omitted_missing_rows"] += 1
                continue
            try:
                value = _numeric(item.get("value"))
            except ValueError:
                error_status = "INVALID_VALUE"
                break
            if day in seen:
                entry["duplicate_rows"] += 1
                error_status = "DUPLICATE_OBSERVATION"
                break
            seen.add(day)
            valid.append({"series_id": series_id, "observation_date": day.isoformat(), "value": value,
                          "available_at": _available_at(day, str(rule_config.get("available_at_rule"))),
                          "source": "wind", "source_series_id": source_id, "vintage_date": "", "quality": "ok"})
        if error_status:
            entry["status"] = error_status
        else:
            valid.sort(key=lambda row: row["observation_date"])
            canonical.extend(valid)
            entry["canonical_rows"] = len(valid)
            if valid:
                entry["date_min"] = valid[0]["observation_date"]
                entry["date_max"] = valid[-1]["observation_date"]
        series_reports.append(entry)

    statuses = {entry["status"] for entry in series_reports}
    if any(status in {"INVALID_VALUE", "DUPLICATE_OBSERVATION", "INVALID_METADATA"} for status in statuses):
        file_status = "FAIL"
    elif "UNRESOLVED_MAPPING" in statuses:
        file_status = "PARTIAL"
    else:
        file_status = "READY"
    result = {"status": file_status, "input_file": str(path), "format": format_name,
              "series": series_reports, "raw_rows": len(raw), "canonical_rows": len(canonical),
              "metadata_preserved": True, "metadata_rows": metadata_rows}
    if output is not None and not dry_run and canonical and file_status in {"READY", "PARTIAL"}:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CANONICAL_COLUMNS)
            writer.writeheader()
            writer.writerows(canonical)
        result["output_file"] = str(output_path)
    if report is not None:
        report_path = Path(report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["report_file"] = str(report_path)
    result["dry_run"] = dry_run
    return result


__all__ = ["CANONICAL_COLUMNS", "WindCanonicalizerError", "canonicalize_wind_export"]
