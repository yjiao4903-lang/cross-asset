"""Transactional staging for Wind exports; never writes formal observations."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

WIND_CANONICAL = {
    "M0000612": "CN_CPI",
    "M0017126": "CN_PMI",
    "M0001227": "CN_PPI",
    "M0001383": "CN_M1",
    "M0001385": "CN_M2",
    "M1006337": "CN_DR007",
    "M1001654": "CN_BOND_10Y",
}


def _parse_date(value: str) -> date:
    year, month, day = (int(part) for part in value.split("/"))
    return date(year, month, day)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_wind_csv(store, path: str | Path) -> dict[str, Any]:
    """Load a wide Wind CSV into evidence staging in one transaction.

    The export lacks release timestamps and vintage lineage, so every staged
    row remains PIT_BLOCKED and ``available_at``/``vintage_date`` are NULL.
    """
    source_path = Path(path)
    payload = source_path.read_bytes()
    source_hash = hashlib.sha256(payload).hexdigest()
    rows = list(csv.reader(payload.decode("gb18030").splitlines()))
    if len(rows) < 8 or any(len(row) != len(rows[4]) for row in rows[:7]):
        raise ValueError("wind CSV metadata/header is incomplete")
    names, frequencies, units, source_ids, sources = rows[1], rows[2], rows[3], rows[4], rows[6]
    ingested_at = datetime.now(UTC).replace(tzinfo=None)
    candidates = []
    for index in range(1, len(source_ids)):
        source_id = source_ids[index].strip()
        if not source_id:
            continue
        candidate = WIND_CANONICAL.get(source_id)
        for row in rows[7:]:
            if not row or not row[0].strip() or index >= len(row) or not row[index].strip():
                continue
            try:
                obs_date = _parse_date(row[0].strip())
                value = float(row[index].strip())
            except (ValueError, TypeError):
                raise ValueError(f"invalid Wind CSV value for {source_id}") from None
            country = "China" if row[0] and (names[index].startswith("中国") or sources[index] in {"国家统计局", "中国人民银行", "中国货币网", "中证指数公司"}) else "United States"
            quality_status = "SEMANTIC_UNIT_REVIEW_REQUIRED" if source_id == "M0017126" else "PIT_BLOCKED"
            metadata = {"wind_indicator_id": source_id, "source_file": source_path.name, "source_label": sources[index], "pit_reason": "release timestamp and vintage lineage absent"}
            if source_id == "M0017126":
                metadata["semantic_reason"] = "file unit % conflicts with canonical index contract"
            candidates.append((source_hash, source_id, candidate, names[index], country, frequencies[index], units[index], "wind_manual", obs_date, value, None, None, quality_status, "MANUAL", json.dumps(metadata, ensure_ascii=False, sort_keys=True), ingested_at))
    with store.atomic():
        before = store.conn.execute("SELECT count(*) FROM wind_evidence_staging WHERE source_file_sha256=?", [source_hash]).fetchone()[0]
        columns = ["source_file_sha256", "source_series_id", "canonical_candidate", "indicator_name", "country", "frequency", "unit", "source", "observation_date", "value", "available_at", "vintage_date", "quality_status", "origin", "metadata_json", "ingested_at"]
        frame = pd.DataFrame(candidates, columns=columns)
        store.conn.register("_wind_stage_frame", frame)
        store.conn.execute("INSERT INTO wind_evidence_staging SELECT * FROM _wind_stage_frame ON CONFLICT DO NOTHING")
        store.conn.unregister("_wind_stage_frame")
        after = store.conn.execute("SELECT count(*) FROM wind_evidence_staging WHERE source_file_sha256=?", [source_hash]).fetchone()[0]
        if hasattr(store, "record_provider_attempt"):
            store.record_provider_attempt({
                "attempt_id": f"wind-manual-{source_hash[:24]}",
                "provider": "wind_manual",
                "series_id": "*",
                "started_at": ingested_at,
                "finished_at": ingested_at,
                "status": "PARTIAL",
                "schema_error": "available_at_missing",
                "error_message": "staged as evidence; PIT release evidence is unavailable",
            })
    per_series = {}
    for row in candidates:
        per_series.setdefault(row[1], {"rows": 0, "date_min": row[8].isoformat(), "date_max": row[8].isoformat(), "null_available_at": 0, "duplicate_rows": 0})
        item = per_series[row[1]]
        item["rows"] += 1
        item["date_min"] = min(item["date_min"], row[8].isoformat())
        item["date_max"] = max(item["date_max"], row[8].isoformat())
        item["null_available_at"] += 1
    return {"source_file_sha256": source_hash, "source_path": str(source_path), "candidate_rows": len(candidates), "new_rows": max(0, after - before), "staged_rows": after, "series": per_series, "status": "EVIDENCE_ONLY", "formal_observations_written": 0}


__all__ = ["WIND_CANONICAL", "stage_wind_csv"]


def stage_wind_xlsx(store, path: str | Path) -> dict[str, Any]:
    """Stage the supplied Wind index workbook using stdlib XLSX XML parsing."""
    source_path = Path(path)
    payload = source_path.read_bytes()
    source_hash = hashlib.sha256(payload).hexdigest()
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(source_path) as archive:
        shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings = ["".join(t.text or "" for t in item.iterfind(".//m:t", ns)) for item in shared_root.findall("m:si", ns)]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    parsed = []
    for row in sheet.findall(".//m:sheetData/m:row", ns):
        values = {}
        for cell in row.findall("m:c", ns):
            value = cell.find("m:v", ns)
            if value is None:
                continue
            raw = value.text or ""
            values[cell.attrib["r"][:-len(re.search(r"\d+$", cell.attrib["r"]).group())]] = strings[int(raw)] if cell.attrib.get("t") == "s" else raw
        parsed.append(values)
    header = parsed[0]
    columns = []
    for col in (chr(code) for code in range(ord("B"), ord("T") + 1)):
        label = str(header.get(col, ""))
        match = re.search(r"\[([^]]+)\]", label)
        if not match:
            continue
        source_id = match.group(1).lstrip("'")
        comparable = "(可比)" in label
        columns.append((col, source_id + ("__COMPARABLE" if comparable else ""), label, source_id, comparable))
    ingested_at = datetime.now(UTC).replace(tzinfo=None)
    candidates = []
    for row in parsed[1:]:
        raw_date = row.get("A")
        if raw_date is None:
            continue
        try:
            serial = float(raw_date)
            obs_date = date(1899, 12, 30) + timedelta(days=serial)
        except (TypeError, ValueError, OverflowError):
            continue
        for col, staging_id, label, source_id, comparable in columns:
            raw_value = row.get(col)
            if raw_value in (None, ""):
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                raise ValueError(f"invalid Wind XLSX value for {staging_id}") from None
            canonical = {"H00300": "CN_EQ_LARGE", "H00852": "CN_EQ_SMALL", "HSI": "HK_EQ"}.get(source_id) if not comparable else None
            country = "Hong Kong" if source_id == "HSI" else "China"
            metadata = {"wind_source_id": source_id, "comparable": comparable, "source_file": source_path.name, "pit_reason": "workbook has observation date only; no available_at/vintage"}
            candidates.append((source_hash, staging_id, canonical, label, country, "daily", "index_points", "wind_manual", obs_date, value, None, None, "PIT_BLOCKED", "MANUAL", json.dumps(metadata, ensure_ascii=False, sort_keys=True), ingested_at))
    columns_db = ["source_file_sha256", "source_series_id", "canonical_candidate", "indicator_name", "country", "frequency", "unit", "source", "observation_date", "value", "available_at", "vintage_date", "quality_status", "origin", "metadata_json", "ingested_at"]
    with store.atomic():
        before = store.conn.execute("SELECT count(*) FROM wind_evidence_staging WHERE source_file_sha256=?", [source_hash]).fetchone()[0]
        store.conn.register("_wind_xlsx_frame", pd.DataFrame(candidates, columns=columns_db))
        store.conn.execute("INSERT INTO wind_evidence_staging SELECT * FROM _wind_xlsx_frame ON CONFLICT DO NOTHING")
        store.conn.unregister("_wind_xlsx_frame")
        after = store.conn.execute("SELECT count(*) FROM wind_evidence_staging WHERE source_file_sha256=?", [source_hash]).fetchone()[0]
    return {"source_file_sha256": source_hash, "source_path": str(source_path), "candidate_rows": len(candidates), "new_rows": max(0, after - before), "staged_rows": after, "source_series": [item[1] for item in columns], "status": "EVIDENCE_ONLY", "formal_observations_written": 0}


__all__ = ["WIND_CANONICAL", "stage_wind_csv", "stage_wind_xlsx"]
