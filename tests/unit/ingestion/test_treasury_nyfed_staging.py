import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from cross_asset.ingestion.treasury_nyfed_quality import attach_available_at, audit_quality
from cross_asset.ingestion.treasury_nyfed_registry import load_registry
from cross_asset.ingestion.treasury_nyfed_staging import collect_all, collect_dataset, research_transforms


def test_fixture_collect_covers_two_treasury_and_two_nyfed_families():
    report = collect_all(live=False, fetched_at=datetime(2026, 9, 10, 12, tzinfo=ZoneInfo("UTC")))
    ids = {item["manifest"]["dataset_id"] for item in report["datasets"]}
    assert "TREASURY_DTS_OPERATING_CASH" in ids
    assert "TREASURY_DEBT_TO_PENNY" in ids
    assert "NYFED_ONRRP_RESULTS" in ids
    assert "NYFED_SOMA_SUMMARY" in ids
    assert report["production_admission"] is False
    tga = next(item for item in report["datasets"] if item["manifest"]["dataset_id"] == "TREASURY_DTS_OPERATING_CASH")
    assert tga["manifest"]["row_count"] == 3
    assert tga["manifest"]["source_health"] in {"HEALTHY", "DEGRADED"}
    omo = next(
        item for item in report["datasets"] if item["manifest"]["dataset_id"] == "NYFED_OMO_TRANSACTION_HISTORY"
    )
    assert omo["manifest"]["source_health"] == "BLOCKED"
    assert "dataset_unresolved" in omo["manifest"]["blockers"]


def test_schema_drift_and_empty_payload_fail_closed():
    spec = load_registry().get("TREASURY_DTS_OPERATING_CASH")
    empty = audit_quality([], spec=spec)
    assert empty.blockers == ("empty_payload",)
    drifted = attach_available_at([{"record_date": "2026-09-04", "unexpected_field": "1"}], spec)
    report = audit_quality(drifted, spec=spec, fetched_at=datetime(2026, 9, 10, 12, tzinfo=ZoneInfo("UTC")))
    assert "schema_drift" in report.blockers


def test_future_available_at_is_blocked():
    spec = load_registry().get("TREASURY_DTS_OPERATING_CASH")
    rows = attach_available_at(
        [{"record_date": "2026-09-04", "account_type": "Treasury General Account (TGA)", "close_today_bal": "1"}],
        spec,
    )
    report = audit_quality(rows, spec=spec, fetched_at=datetime(2026, 9, 4, 12, tzinfo=ZoneInfo("UTC")))
    assert "future_available_at" in report.blockers


def test_research_transforms_are_causal_and_not_allocation_signals():
    payload = collect_all(live=False, fetched_at=datetime(2026, 9, 10, 12, tzinfo=ZoneInfo("UTC")))
    visible = research_transforms(payload, "2026-09-03T16:00:00-04:00")
    hidden = research_transforms(payload, "2026-09-02T12:00:00-04:00")
    assert visible["allocation_signal"] is False
    assert visible["components"]["net_liquidity"]["allocation_signal"] is False
    assert hidden["components"]["tga_daily_change"] is None


def test_collect_writes_manifest(tmp_path: Path):
    output = tmp_path / "manifest.json"
    report = collect_all(
        dataset_id="TREASURY_AUCTIONS",
        live=False,
        output=str(output),
        fetched_at=datetime(2026, 9, 10, 12, tzinfo=ZoneInfo("UTC")),
    )
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["datasets"][0]["manifest"]["dataset_id"] == "TREASURY_AUCTIONS"
    assert report["datasets"][0]["rows"][0]["available_at"]


def test_unresolved_dataset_does_not_collect_live_rows():
    spec = load_registry().get("NYFED_OMO_TRANSACTION_HISTORY")
    rows, manifest = collect_dataset(spec, live=True)
    assert rows == []
    assert manifest.source_health == "BLOCKED"
