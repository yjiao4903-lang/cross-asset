from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

from cross_asset.backtest.returns import AssetReturnSpec
from cross_asset.operations.execution_timing import (
    ExecutionTimingPolicy,
    portfolio_execution_timing_disclosure,
)


def _calendar(tmp_path, *, verified=True):
    path = tmp_path / "calendars.yml"
    path.write_text(
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
                        "covered_years": [2026],
                        "holidays": [],
                        "early_closes": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _policy():
    return ExecutionTimingPolicy(
        version="1.0",
        effective_from="next_available_session",
        execution_price_rule="next_available_session_close",
        require_verified_calendar=True,
        calendar_config="unused-in-test",
    )


def _specs():
    return {
        "CN_EQ": AssetReturnSpec("CN_EQ", kind="price"),
        "CASH": AssetReturnSpec(None, kind="cash"),
    }


def test_disclosure_resolves_non_cash_and_marks_cash_not_applicable(tmp_path):
    decision = datetime(2026, 9, 5, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = portfolio_execution_timing_disclosure(
        decision,
        _specs(),
        {"CN_EQ": "CN"},
        policy=_policy(),
        calendar_config=_calendar(tmp_path),
    )

    assert result["status"] == "RESOLVED"
    assert result["blockers"] == []
    assert result["by_asset"]["CN_EQ"]["status"] == "RESOLVED"
    assert result["by_asset"]["CN_EQ"]["effective_at"] == datetime(
        2026, 9, 7, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    assert result["by_asset"]["CN_EQ"]["execution_price_at"] == result["by_asset"][
        "CN_EQ"
    ]["effective_at"]
    assert result["by_asset"]["CASH"]["status"] == "NOT_APPLICABLE"
    assert result["return_timing_basis"] == "decision_to_next_decision_research_proxy"
    assert result["performance_semantics"] == "research_proxy_not_investor_realizable"


def test_disclosure_blocks_when_market_mapping_is_missing():
    decision = datetime(2026, 9, 5, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = portfolio_execution_timing_disclosure(decision, _specs(), {})

    assert result["status"] == "BLOCKED"
    assert result["by_asset"]["CN_EQ"]["reason"] == "market_mapping_missing"
    assert result["by_asset"]["CN_EQ"]["effective_at"] is None
    assert result["by_asset"]["CN_EQ"]["execution_price_at"] is None
    assert result["blockers"] == ["CN_EQ:market_mapping_missing"]


def test_disclosure_propagates_unverified_calendar_block(tmp_path):
    decision = datetime(2026, 9, 5, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = portfolio_execution_timing_disclosure(
        decision,
        _specs(),
        {"CN_EQ": "CN"},
        policy=_policy(),
        calendar_config=_calendar(tmp_path, verified=False),
    )

    assert result["status"] == "BLOCKED"
    assert result["by_asset"]["CN_EQ"]["reason"] == "calendar_unverified"
    assert result["blockers"] == ["CN_EQ:calendar_unverified"]
