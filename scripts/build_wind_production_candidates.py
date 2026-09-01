"""Build auditable Wind production-admission candidates from evidence staging."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from cross_asset.ingestion.acceptance import validate_data_file
from cross_asset.storage import init_db
from cross_asset.storage.acceptance_registry import (
    candidate_registry_record,
    upsert_data_acceptance,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "production_admission" / "wind_candidates"
DB = ROOT / "data" / "db" / "cross_asset.duckdb"

CONTRACTS = {
    "CN_EQ_LARGE": {"definition": "CSI 300 total-return index level", "unit": "index_points", "currency": "CNY", "price_type": "total_return_index", "adjustment": "cash dividends reinvested by index methodology", "timezone": "Asia/Shanghai"},
    "CN_EQ_SMALL": {"definition": "CSI 1000 total-return index level", "unit": "index_points", "currency": "CNY", "price_type": "total_return_index", "adjustment": "cash dividends reinvested by index methodology", "timezone": "Asia/Shanghai"},
    "HK_EQ": {"definition": "Hang Seng Index level", "unit": "index_points", "currency": "HKD", "price_type": "price_index", "adjustment": "unadjusted index level", "timezone": "Asia/Hong_Kong"},
    "CN_BOND_10Y": {"definition": "China government bond 10-year yield", "unit": "yield_percent", "currency": "CNY", "price_type": "yield", "adjustment": "none", "timezone": "Asia/Shanghai"},
    "CN_DR007": {"definition": "DR007 weighted repo rate", "unit": "yield_percent", "currency": "CNY", "price_type": "rate", "adjustment": "none", "timezone": "Asia/Shanghai"},
    "CN_CPI": {"definition": "China CPI year-over-year", "unit": "percent", "currency": "CNY", "price_type": "macro_rate", "adjustment": "source-defined", "timezone": "Asia/Shanghai"},
    "CN_PPI": {"definition": "China PPI year-over-year", "unit": "percent", "currency": "CNY", "price_type": "macro_rate", "adjustment": "source-defined", "timezone": "Asia/Shanghai"},
    "CN_M1": {"definition": "China M1 year-over-year growth", "unit": "percent", "currency": "CNY", "price_type": "macro_rate", "adjustment": "source-defined", "timezone": "Asia/Shanghai"},
    "CN_M2": {"definition": "China M2 year-over-year growth", "unit": "percent", "currency": "CNY", "price_type": "macro_rate", "adjustment": "source-defined", "timezone": "Asia/Shanghai"},
}

SOURCES = [
    "https://www.stats.gov.cn/sj/fbrc/bnxxfb/",
    "https://www.chinamoney.com.cn/chinese/bkfrr/",
    "https://www.hsi.com.hk/",
    "https://www.csindex.com.cn/",
]


def available_at(observation_date, frequency: str, timezone: str) -> datetime:
    lag = 1 if frequency == "daily" else 45
    return datetime.combine(observation_date + timedelta(days=lag), time.min, ZoneInfo(timezone)).astimezone(UTC)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    store = init_db(DB)
    results = []
    try:
        for series_id, contract in CONTRACTS.items():
            rows = store.conn.execute(
                """SELECT source_series_id, observation_date, value, frequency
                   FROM wind_evidence_staging
                   WHERE canonical_candidate=?
                   ORDER BY observation_date""",
                [series_id],
            ).fetchall()
            if not rows:
                continue
            source_ids = sorted({row[0] for row in rows})
            if len(source_ids) != 1:
                raise ValueError(f"multiple_source_ids:{series_id}")
            source_id = source_ids[0]
            frequency = "daily" if str(rows[0][3]).lower() in {"daily", "day", "日"} else "monthly"
            csv_path = OUTPUT / f"{series_id}.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["series_id", "source_series_id", "observation_date", "available_at", "value"])
                writer.writeheader()
                for _, obs_date, value, _ in rows:
                    writer.writerow({"series_id": series_id, "source_series_id": source_id, "observation_date": obs_date.isoformat(), "available_at": available_at(obs_date, frequency, contract["timezone"]).isoformat(), "value": format(float(value), ".15g")})
            file_hash = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            manifest = {
                "series_id": series_id,
                "provider": "wind_manual",
                "source_series_id": source_id,
                "permission_scope": "LOCAL_INTERNAL_USE_PENDING_USER_WIND_LICENSE_CONFIRMATION",
                "origin": "MANUAL",
                "observation_definition": contract["definition"],
                "unit": contract["unit"],
                "currency": contract["currency"],
                "timezone": contract["timezone"],
                "price_type": contract["price_type"],
                "adjustment_type": contract["adjustment"],
                "frequency": frequency,
                "history_start": rows[0][1].isoformat(),
                "history_end": rows[-1][1].isoformat(),
                "observation_date_rule": "source observation/trading date retained exactly",
                "available_at_rule": "documented conservative lag: daily T+1 calendar day 00:00 local; monthly observation date +45 calendar days 00:00 Asia/Shanghai",
                "vintage_rule": "no true vintage history; conservative lag and source revision lineage pending",
                "missing_policy": "missing remains unavailable; no zero fill or forward fill",
                "semantic_equivalence": True,
                "template_version": "wind_canonical_v1.0",
                "file_sha256": file_hash,
                "reviewer": None,
                "approved_at": None,
                "reconciliation_notes": "Exact Wind source ID retained; canonical mapping reviewed against workbook label and project contract. Production use awaits permission, repeatability and independent approval.",
                "available_at": "CONSERVATIVE_POLICY_APPLIED_NOT_ACTUAL_RELEASE",
                "pit_grade": "C",
                "raw_file": str(csv_path.relative_to(ROOT)),
                "repeatability_evidence": [],
                "evidence_urls": SOURCES,
            }
            manifest_path = OUTPUT / f"{series_id}.manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result = validate_data_file(csv_path, manifest_path)
            result_path = OUTPUT / f"{series_id}.validation.json"
            result_path.write_text(json.dumps(result, ensure_ascii=False, default=str, indent=2) + "\n", encoding="utf-8")
            if result["status"] != "FAIL":
                saved = upsert_data_acceptance(store, candidate_registry_record(result))
            else:
                saved = None
            results.append({"series_id": series_id, "rows": len(rows), "source_series_id": source_id, "status": result["status"], "gates": result["gates"], "pit_grade": (result.get("registry_candidate") or {}).get("pit_grade"), "registry": saved is not None, "validation": str(result_path.relative_to(ROOT))})
        summary = {"generated_at": datetime.now(UTC).isoformat(), "status": "PRODUCTION_ADMISSION_PARTIAL", "series": results, "remaining_human_gates": ["confirm Wind license permission_scope for local storage/internal research", "name independent reviewer and provide timezone-aware approved_at", "provide two additional fixed-template exports at later acquisition dates for three-batch stability"], "automatic_promotion": False}
        (OUTPUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, default=str, indent=2) + "\n", encoding="utf-8")
    finally:
        store.close()


if __name__ == "__main__":
    main()
