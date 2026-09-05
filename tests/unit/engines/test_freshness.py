"""Fail-closed freshness interface tests (Issue #18; real calendars are #21)."""

from datetime import date

from cross_asset.engines.freshness import evaluate_series_freshness

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
