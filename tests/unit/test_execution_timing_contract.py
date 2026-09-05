from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

from cross_asset.operations.calendar import MarketCalendar
from cross_asset.operations.execution_timing import (
    ExecutionTimingPolicy,
    load_execution_timing_policy,
    resolve_market_execution,
)


def _write_calendar(tmp_path, *, verified=True, covered_years=None, early_closes=None):
    config = tmp_path / "calendars.yml"
    config.write_text(
        yaml.safe_dump(
            {
                "calendars": {
                    "CN": {
                        "calendar_id": "CN_TEST",
                        "capability_status": "VERIFIED" if verified else "UNVERIFIED",
                        "timezone": "Asia/Shanghai",
                        "source": "fixture",
                        "source_version": "1",
                        "version": "fixture-v1",
                        "regular_close": "15:00",
                        "verified": verified,
                        "evidence": ["fixture"],
                        "reviewer": "test",
                        "approved_at": "2026-01-01T00:00:00+08:00",
                        "covered_years": covered_years or [2026],
                        "holidays": ["2026-09-07"],
                        "early_closes": early_closes or {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return config


def _policy():
    return ExecutionTimingPolicy(
        version="1.0",
        effective_from="next_available_session",
        execution_price_rule="next_available_session_close",
        require_verified_calendar=True,
        calendar_config="unused-in-test",
    )


def test_default_execution_timing_policy_is_frozen_and_fail_closed():
    policy = load_execution_timing_policy()
    assert policy.effective_from == "next_available_session"
    assert policy.execution_price_rule == "next_available_session_close"
    assert policy.require_verified_calendar is True


def test_verified_calendar_resolves_first_open_session_close_after_decision(tmp_path):
    config = _write_calendar(tmp_path)
    decision = datetime(2026, 9, 5, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = resolve_market_execution(
        decision,
        "CN",
        policy=_policy(),
        calendar_config=config,
    )

    assert result.status == "RESOLVED"
    assert result.reason == "next_verified_session_close"
    assert result.decision_at == decision
    assert result.effective_at == datetime(
        2026, 9, 8, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    assert result.execution_price_at == result.effective_at
    assert result.execution_price_rule == "next_available_session_close"
    assert result.calendar_id == "CN_TEST"
    assert result.calendar_version == "fixture-v1"


def test_execution_uses_early_close_and_regular_close_field(tmp_path):
    config = _write_calendar(tmp_path, early_closes={"2026-09-08": "11:30"})
    calendar = MarketCalendar("CN", config)
    assert calendar.close_time.hour == 15

    decision = datetime(2026, 9, 5, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = resolve_market_execution(
        decision,
        "CN",
        policy=_policy(),
        calendar_config=config,
    )

    assert result.status == "RESOLVED"
    assert result.execution_price_at == datetime(
        2026, 9, 8, 11, 30, tzinfo=ZoneInfo("Asia/Shanghai")
    )


def test_unverified_calendar_blocks_instead_of_using_weekend_heuristic(tmp_path):
    config = _write_calendar(tmp_path, verified=False)
    decision = datetime(2026, 9, 5, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = resolve_market_execution(
        decision,
        "CN",
        policy=_policy(),
        calendar_config=config,
    )

    assert result.status == "BLOCKED"
    assert result.reason == "calendar_unverified"
    assert result.effective_at is None
    assert result.execution_price_at is None


def test_calendar_coverage_gap_blocks_without_skipping_unknown_dates(tmp_path):
    config = _write_calendar(tmp_path, covered_years=[2025])
    decision = datetime(2025, 12, 31, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = resolve_market_execution(
        decision,
        "CN",
        policy=_policy(),
        calendar_config=config,
    )

    assert result.status == "BLOCKED"
    assert result.reason == "calendar_coverage_missing"


def test_naive_decision_timestamp_is_rejected(tmp_path):
    config = _write_calendar(tmp_path)
    result = resolve_market_execution(
        datetime.fromisoformat("2026-09-05T12:00:00"),
        "CN",
        policy=_policy(),
        calendar_config=config,
    )

    assert result.status == "BLOCKED"
    assert result.reason == "decision_time_must_be_timezone_aware"
