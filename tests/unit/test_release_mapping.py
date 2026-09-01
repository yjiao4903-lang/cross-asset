from datetime import UTC, datetime

from cross_asset.pit.release_mapping import map_alfred_rows, release_date_eod


def test_release_date_eod_respects_new_york_dst():
    winter = release_date_eod("2026-01-09")
    summer = release_date_eod("2026-07-10")
    assert winter.hour == 4 and summer.hour == 3


def test_mapping_is_dry_run_and_decision_time_aware():
    rows = [{"date": "2025-01-31", "realtime_start": "2025-02-10", "value": "100"}]
    result = map_alfred_rows(rows, decision_time=datetime(2025, 2, 15, 4, tzinfo=UTC))
    assert result["matched"] == 1 and result["rows"][0]["eligible_next_decision"] is True
    assert result["rows"][0]["admitted"] is False
