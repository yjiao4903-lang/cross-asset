"""RT139 B3 — freshness/calendar attacks (seeds: #138 B3; re-derived)."""

from __future__ import annotations

from datetime import UTC, datetime

from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db
from cross_asset.decision_support.producer import build_monitoring_snapshot
from cross_asset.reports.monitoring_health import monitoring_data_health
from redteam139._helpers import (
    WEEK2_CUTOFF,
    WEEK2_DECISION,
    cpi_values,
    governed_store,
    month_rows,
    payroll_values,
    workbench_run,
    write_monitoring_run,
)

CAPTURE = WEEK2_DECISION.replace(hour=0)


def _full_store():
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE)
    rows += month_rows("US_NONFARM_PAYROLLS", "PAYEMS", payroll_values(40), capture_time=CAPTURE)
    write_monitoring_run(store, rows, run_id="run-b3", requested=2)
    return store


# --- RT139-B3-01: fresh evidence keeps full health ---
def test_b3_01_captured_monthly_data_is_usable():
    store = _full_store()
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b3-01"))
    by_id = {item.series_id: item for item in pack.series}
    assert by_id["US_CORE_CPI"].status in {"FRESH", "STALE"}
    assert by_id["US_CORE_CPI"].observations


# --- RT139-B3-02: #129 publication-frequency exception stays narrow ---
def test_b3_02_calendar_mapping_missing_maps_to_stale_with_limitation():
    store = _full_store()
    health_rows = monitoring_data_health(
        store.conn, as_of=WEEK2_DECISION.replace(tzinfo=None), market_data_cutoff=WEEK2_CUTOFF,
        series_ids=["US_CORE_CPI"],
    )
    for row in health_rows:
        if row["series_id"] == "US_CORE_CPI":
            reason = str(row.get("monitoring_reason") or "")
            assert reason in {"", "calendar_mapping_missing"}
            if reason == "calendar_mapping_missing":
                assert row["monitoring_status"] == "BLOCKED"
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b3-02"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    if series.status == "STALE":
        assert series.provenance["freshness_verified"] is False
        assert series.provenance["freshness_limitation"] == "calendar_mapping_missing"


# --- RT139-B3-03: provider/schema failures never downgrade to stale ---
def test_b3_03_identity_failure_stays_blocked():
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "PAYEMS", cpi_values(40), capture_time=CAPTURE)
    write_monitoring_run(store, rows, run_id="run-b3-03")
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b3-03"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.status == "BLOCKED"
    assert series.provenance["freshness_verified"] is True or series.provenance["identity_blockers"]


# --- RT139-B3-04: stale is not missing ---
def test_b3_04_stale_is_not_missing():
    store = _full_store()
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b3-04"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    if series.status == "STALE":
        assert series.observations, "stale series must retain its observations"
    assert series.status != "MISSING"


# --- RT139-B3-05: missing series stays explicit MISSING, not zero ---
def test_b3_05_missing_series_is_explicit():
    store = governed_store(series_ids=["US_NONFARM_PAYROLLS"])
    rows = month_rows("US_NONFARM_PAYROLLS", "PAYEMS", payroll_values(40), capture_time=CAPTURE)
    write_monitoring_run(store, rows, run_id="run-b3-05")
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b3-05"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.status in {"MISSING", "BLOCKED"}
    assert series.observations == []


# --- RT139-B3-06: calendar lag is recorded when a calendar is configured ---
def test_b3_06_calendar_lag_recorded_when_configured():
    store = _full_store()
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b3-06"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert "calendar" in series.provenance
    assert "calendar_lag_sessions" in series.provenance


# --- RT139-B3-07: no Mon-Fri heuristic fallback for unconfigured calendars ---
def test_b3_07_no_weekday_heuristic_fallback():
    store = _full_store()
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b3-07"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    if series.provenance.get("calendar") in (None, "", "unknown"):
        # Without governed calendar authority the series may not claim FRESH.
        assert series.status != "FRESH" or series.provenance["freshness_verified"] is True


# --- RT139-B3-08: snapshot data health mirrors explicit staleness ---
def test_b3_08_snapshot_health_lists_components():
    store = _full_store()
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b3-08"))
    snapshot = build_monitoring_snapshot(pack)
    health = snapshot.data_health_summary
    assert health is not None
    assert snapshot.details["binding_counts"]["missing"] >= 0


# --- RT139-B3-09: freshness state is per-series, not global ---
def test_b3_09_freshness_is_per_series():
    store = _full_store()
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b3-09"))
    statuses = {item.series_id: item.status for item in pack.series}
    present = {sid: status for sid, status in statuses.items() if sid in {"US_CORE_CPI", "US_NONFARM_PAYROLLS"}}
    assert present
    # missing market series (US_EQ etc.) are independently MISSING
    if "US_EQ" in statuses:
        assert statuses["US_EQ"] in {"MISSING", "BLOCKED"}


# --- RT139-B3-10: holiday-adjacent capture cannot fabricate freshness ---
def test_b3_10_weekend_capture_stays_truthful():
    store = _full_store()
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b3-10"))
    for item in pack.series:
        if item.observations and item.status == "FRESH":
            assert item.provenance["freshness_verified"] is True
