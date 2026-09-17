"""Fail-closed freshness interface tests (Issue #18; calendar reuse is #125)."""

from datetime import date

from cross_asset.engines.freshness import (
    evaluate_series_freshness,
    load_series_calendar_mapping,
)

CUTOFF = date(2026, 8, 31)  # a Monday


def _evaluate(mapping=None, *, latest=CUTOFF, cutoff=CUTOFF, config=None):
    return evaluate_series_freshness(
        "A",
        latest_observation_date=latest,
        market_data_cutoff=cutoff,
        calendar_config=config or "config/calendars.yml",
        series_calendar_config="series_calendars-unused.yml",
        mapping=mapping,
    )


def test_missing_calendar_mapping_fails_closed():
    result = _evaluate(mapping=None)
    assert not result.healthy
    assert result.status == "BLOCKED"
    assert result.reason == "calendar_mapping_missing"


def test_unverified_calendar_fails_closed():
    result = _evaluate(mapping={"A": {"calendar": "CN", "max_lag_sessions": 3}})
    assert not result.healthy
    assert result.reason == "calendar_unverified"


def test_missing_max_lag_fails_closed():
    result = _evaluate(mapping={"A": {"calendar": "CN"}})
    assert not result.healthy
    assert result.reason == "max_lag_sessions_not_configured"


def test_missing_observation_fails_closed():
    result = _evaluate(mapping={"A": {"calendar": "CN", "max_lag_sessions": 3}}, latest=None)
    assert not result.healthy
    assert result.reason == "no_formal_observation"


def test_verified_calendar_ok_within_lag_and_stale_beyond(tmp_path):
    config = tmp_path / "calendars.yml"
    config.write_text(
        "calendars:\n"
        "  TEST:\n"
        "    calendar_id: TEST\n"
        "    capability_status: VERIFIED\n"
        "    timezone: UTC\n"
        "    source: test\n"
        "    source_version: '1'\n"
        "    version: '1'\n"
        "    covered_years: [2026]\n"
        "    open_time: '00:00'\n"
        "    close_time: '23:59'\n"
        "    regular_close: '23:59'\n"
        "    holidays: []\n"
        "    early_closes: {}\n"
        "    verified: true\n"
        "    evidence: [test]\n"
        "    reviewer: test\n"
        "    approved_at: '2026-01-01T00:00:00+00:00'\n",
        encoding="utf-8",
    )
    mapping = {"A": {"calendar": "TEST", "max_lag_sessions": 2}}

    fresh = _evaluate(mapping, latest=CUTOFF, config=config)
    assert fresh.healthy
    assert fresh.lag_sessions == 0

    # One open session back from the Monday cutoff is the previous Friday.
    friday = date(2026, 8, 28)
    within = _evaluate(mapping, latest=friday, config=config)
    assert within.healthy
    assert within.lag_sessions == 1

    beyond = _evaluate(mapping, latest=date(2026, 8, 26), config=config)
    assert not beyond.healthy
    assert beyond.status == "STALE"
    assert beyond.reason == "calendar_lag_exceeds_max_lag_sessions"


def test_uncovered_year_fails_closed(tmp_path):
    config = tmp_path / "calendars.yml"
    config.write_text(
        "calendars:\n"
        "  TEST:\n"
        "    calendar_id: TEST\n"
        "    capability_status: VERIFIED\n"
        "    timezone: UTC\n"
        "    source: test\n"
        "    source_version: '1'\n"
        "    version: '1'\n"
        "    covered_years: [2025]\n"
        "    open_time: '00:00'\n"
        "    close_time: '23:59'\n"
        "    regular_close: '23:59'\n"
        "    holidays: []\n"
        "    early_closes: {}\n"
        "    verified: true\n"
        "    evidence: [test]\n"
        "    reviewer: test\n"
        "    approved_at: '2026-01-01T00:00:00+00:00'\n",
        encoding="utf-8",
    )
    result = _evaluate(
        {"A": {"calendar": "TEST", "max_lag_sessions": 3}}, config=config
    )
    assert not result.healthy
    assert result.reason == "calendar_coverage_missing"


def test_default_mapping_activates_only_evidence_backed_exchange_series():
    mapping = load_series_calendar_mapping()
    assert set(mapping) == {"US_EQ", "HK_EQ"}
    assert mapping["US_EQ"] == {
        "calendar": "XNYS",
        "calendar_source": "exchange_adapter",
        "max_lag_sessions": 1,
    }
    assert mapping["HK_EQ"] == {
        "calendar": "XHKG",
        "calendar_source": "exchange_adapter",
        "max_lag_sessions": 1,
    }


def test_upstream_exchange_series_can_be_ok_or_stale():
    mapping = {
        "A": {
            "calendar": "XNYS",
            "calendar_source": "exchange_adapter",
            "max_lag_sessions": 1,
        }
    }
    fresh = _evaluate(mapping, latest=date(2025, 12, 24), cutoff=date(2025, 12, 26))
    assert fresh.status == "OK"
    assert fresh.calendar == "XNYS"
    assert fresh.lag_sessions == 1

    stale = _evaluate(mapping, latest=date(2025, 12, 23), cutoff=date(2025, 12, 26))
    assert stale.status == "STALE"
    assert stale.lag_sessions == 2


def test_real_exchange_holiday_is_not_counted_as_open_session():
    mapping = {
        "A": {
            "calendar": "XNYS",
            "calendar_source": "exchange_adapter",
            "max_lag_sessions": 0,
        }
    }
    # Christmas Day is a real XNYS holiday. A 12/24 observation remains at
    # zero open-session lag through 12/25; no generic Mon-Fri approximation.
    holiday = _evaluate(mapping, latest=date(2025, 12, 24), cutoff=date(2025, 12, 25))
    assert holiday.status == "OK"
    assert holiday.lag_sessions == 0
    assert holiday.expected_session == date(2025, 12, 24)


def test_unmapped_and_unsupported_special_calendars_stay_blocked():
    unmapped = evaluate_series_freshness(
        "US_GOV_10Y",
        latest_observation_date=date(2025, 12, 24),
        market_data_cutoff=date(2025, 12, 26),
    )
    assert unmapped.status == "BLOCKED"
    assert unmapped.reason == "calendar_mapping_missing"

    unsupported = _evaluate(
        {
            "A": {
                "calendar": "US_TREASURY_SPECIAL",
                "calendar_source": "exchange_adapter",
                "max_lag_sessions": 1,
            }
        },
        latest=date(2025, 12, 24),
        cutoff=date(2025, 12, 26),
    )
    assert unsupported.status == "BLOCKED"
    assert unsupported.reason == "calendar_unavailable"
