"""B3 — freshness/calendar attacks (ADVERSARIAL-E2E-VALIDATION-V1)."""

from __future__ import annotations

from datetime import date

import pytest
import yaml

from cross_asset.engines.freshness import (
    evaluate_freshness,
    evaluate_series_freshness,
    load_series_calendar_mapping,
)

from _helpers import (
    CAPTURE,
    governed_store,
    month_rows,
    workbench_run,
    write_monitoring_run,
)

from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db


# --- B3-01: valid exchange calendar -------------------------------------------


def test_adv_b3_01_supported_exchange_calendar_is_fresh_within_lag():
    result = evaluate_series_freshness(
        "US_EQ",
        latest_observation_date=date(2026, 9, 11),
        market_data_cutoff=date(2026, 9, 14),
    )
    assert result.status == "OK"
    assert result.calendar == "XNYS"
    assert result.lag_sessions == 1


# --- B3-02: holiday boundary ---------------------------------------------------


def test_adv_b3_02_holiday_is_not_counted_as_a_missing_session():
    # 2026-11-26 is US Thanksgiving (XNYS closed).
    thanksgiving = evaluate_series_freshness(
        "US_EQ",
        latest_observation_date=date(2026, 11, 24),
        market_data_cutoff=date(2026, 11, 26),
    )
    assert thanksgiving.status == "OK"
    assert thanksgiving.lag_sessions == 1

    # The following Monday has two open sessions after the observation.
    later = evaluate_series_freshness(
        "US_EQ",
        latest_observation_date=date(2026, 11, 24),
        market_data_cutoff=date(2026, 11, 27),
    )
    assert later.status == "STALE"
    assert later.lag_sessions == 2


# --- B3-03/04: unsupported calendar / missing mapping --------------------------


@pytest.mark.parametrize(
    "series_id",
    ["CN_EQ_LARGE", "COPPER", "GOLD", "US_CORE_CPI", "US_NONFARM_PAYROLLS"],
)
def test_adv_b3_03_unmapped_series_is_blocked_never_fresh(series_id):
    result = evaluate_series_freshness(
        series_id,
        latest_observation_date=date(2026, 9, 11),
        market_data_cutoff=date(2026, 9, 11),
    )
    assert result.status == "BLOCKED"
    assert result.reason == "calendar_mapping_missing"
    assert result.healthy is False


def test_adv_b3_04_no_observation_is_blocked_with_its_own_reason():
    result = evaluate_series_freshness(
        "US_EQ",
        latest_observation_date=None,
        market_data_cutoff=date(2026, 9, 14),
    )
    assert result.status == "BLOCKED"
    assert result.reason == "no_formal_observation"


# --- B3-05: cutoff outside provider calendar coverage --------------------------


def test_adv_b3_05_cutoff_outside_calendar_coverage_is_blocked():
    far_future = evaluate_series_freshness(
        "US_EQ",
        latest_observation_date=date(2026, 9, 11),
        market_data_cutoff=date(2035, 1, 2),
    )
    assert far_future.status == "BLOCKED"
    assert far_future.reason == "calendar_coverage_missing"

    before_coverage = evaluate_series_freshness(
        "US_EQ",
        latest_observation_date=date(1990, 1, 2),
        market_data_cutoff=date(2026, 9, 14),
    )
    assert before_coverage.status == "BLOCKED"
    assert before_coverage.reason == "calendar_coverage_missing"


# --- B3-06: stale vs missing vs blocked vs unknown stay distinct ---------------


def test_adv_b3_06_health_states_are_not_collapsed():
    results = evaluate_freshness(
        ["US_EQ", "CN_EQ_LARGE", "HK_EQ"],
        latest_observation_dates={
            "US_EQ": date(2026, 9, 11),
            "CN_EQ_LARGE": date(2026, 9, 11),
            "HK_EQ": None,
        },
        market_data_cutoff=date(2026, 9, 14),
    )
    assert results["US_EQ"].status == "OK"
    assert results["CN_EQ_LARGE"].status == "BLOCKED"
    assert results["CN_EQ_LARGE"].reason == "calendar_mapping_missing"
    assert results["HK_EQ"].status == "BLOCKED"
    assert results["HK_EQ"].reason == "no_formal_observation"


# --- B3-07: no Mon-Fri / elapsed-hour heuristic --------------------------------


def test_adv_b3_07_no_weekday_heuristic_in_the_freshness_path():
    source = open("src/cross_asset/engines/freshness.py", encoding="utf-8").read()
    assert "weekday" not in source
    assert "isoweekday" not in source
    # An unmapped series is BLOCKED even when the observation equals the cutoff.
    result = evaluate_series_freshness(
        "CN_EQ_LARGE",
        latest_observation_date=date(2026, 9, 14),
        market_data_cutoff=date(2026, 9, 14),
    )
    assert result.status == "BLOCKED"


# --- B3-08: invalid lag configuration fails closed -----------------------------


@pytest.mark.parametrize(
    "entry",
    [
        {"calendar": "XNYS", "calendar_source": "exchange_adapter"},
        {"calendar": "XNYS", "calendar_source": "exchange_adapter", "max_lag_sessions": -1},
        {"calendar": "XNYS", "calendar_source": "exchange_adapter", "max_lag_sessions": "x"},
        {"calendar": None, "calendar_source": "exchange_adapter", "max_lag_sessions": 1},
        {"calendar": "XNYS", "calendar_source": "vendor_magic", "max_lag_sessions": 1},
    ],
)
def test_adv_b3_08_invalid_calendar_entries_fail_closed(entry, tmp_path):
    path = tmp_path / "series_calendars.yml"
    path.write_text(
        yaml.safe_dump({"series_calendars": {"US_EQ": entry}}), encoding="utf-8"
    )
    result = evaluate_series_freshness(
        "US_EQ",
        latest_observation_date=date(2026, 9, 11),
        market_data_cutoff=date(2026, 9, 14),
        series_calendar_config=path,
    )
    assert result.status == "BLOCKED"


# --- B3-09: publication series without a governed publication calendar ---------


def test_adv_b3_09_unverified_project_calendar_is_blocked(tmp_path):
    """A configured but unverified project calendar must never report fresh."""

    entry = {
        "calendar": "US",
        "calendar_source": "config",
        "max_lag_sessions": 1,
    }
    path = tmp_path / "series_calendars.yml"
    path.write_text(
        yaml.safe_dump({"series_calendars": {"US_NONFARM_PAYROLLS": entry}}),
        encoding="utf-8",
    )
    result = evaluate_series_freshness(
        "US_NONFARM_PAYROLLS",
        latest_observation_date=date(2026, 9, 11),
        market_data_cutoff=date(2026, 9, 14),
        series_calendar_config=path,
    )
    assert result.status == "BLOCKED"
    assert result.reason == "calendar_unverified"


# --- B3-10: narrow #129 exception only downgrades the one governed reason ------


def test_adv_b3_10_adapter_only_downgrades_the_governed_missing_calendar_reason(
    governed_store,
):
    store = governed_store(("US_CORE_CPI", "US_EQ"))
    try:
        write_monitoring_run(
            store,
            month_rows("US_CORE_CPI", "CPILFESL", [200 + i for i in range(48)]),
            run_id="monitoring-fred-adv-b3-10",
        )
        store.record_quality_event(
            {
                "event_id": "adv-b3-10",
                "detected_at": CAPTURE.replace(tzinfo=None),
                "series_id": "US_EQ",
                "severity": "ERROR",
                "event_type": "MONITORING_SCHEMA_ERROR",
                "message": "synthetic schema failure",
                "provider": "fred",
                "run_id": "monitoring-fred-adv-b3-10",
            }
        )
        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-b3-10"))
        by_series = {item.series_id: item for item in bundle.series}
        # calendar_mapping_missing -> STALE, reduced confidence, explicitly unverified.
        cpi = by_series["US_CORE_CPI"]
        assert cpi.status == "STALE"
        assert cpi.provenance["freshness_verified"] is False
        assert cpi.provenance["monitoring_status"] == "BLOCKED"
        # A schema/identity failure stays BLOCKED; it is never downgraded.
        eq = by_series["US_EQ"]
        assert eq.status == "BLOCKED"
        assert eq.provenance["freshness_verified"] is True
    finally:
        store.close()


# --- B3-11: calendar mapping file is the only freshness authority --------------


def test_adv_b3_11_mapping_loader_is_explicit_and_fail_closed(tmp_path):
    assert load_series_calendar_mapping("does/not/exist.yml") == {}
    mapping = load_series_calendar_mapping("config/series_calendars.yml")
    assert set(mapping) == {"US_EQ", "HK_EQ"}
    assert all(
        entry["calendar_source"] == "exchange_adapter" for entry in mapping.values()
    )
