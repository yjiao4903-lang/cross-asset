from datetime import date

import yaml

from cross_asset.operations.calendar import MarketCalendar, last_common_session
from cross_asset.reports.coverage import generate_coverage_report
from cross_asset.storage import init_db


def test_calendar_holiday_timezone_and_unknown_range(tmp_path):
    config = tmp_path / "calendars.yml"
    config.write_text(yaml.safe_dump({"calendars": {"US": {"capability_status": "VERIFIED", "timezone": "America/New_York", "source": "test", "version": "1", "covered_years": [2025], "open_time": "09:30", "close_time": "16:00", "holidays": ["2025-01-20"]}, "CN": {"capability_status": "VERIFIED", "timezone": "Asia/Shanghai", "source": "test", "version": "1", "covered_years": [2025], "open_time": "09:30", "close_time": "15:00", "holidays": ["2025-01-29"]}}}), encoding="utf-8")
    us, cn = MarketCalendar("US", config), MarketCalendar("CN", config)
    assert us.session_status(date(2025, 1, 20)) == "CLOSED"
    assert us.last_available_session(date(2025, 1, 20)) == date(2025, 1, 17)
    assert us.session_status(date(2035, 1, 2)) == "UNKNOWN"
    assert last_common_session(date(2025, 1, 21), [us, cn]) == date(2025, 1, 21)


def test_coverage_empty_is_data_blocked_and_catalog_unknown(tmp_path):
    db = init_db(":memory:")
    db.conn.execute("INSERT INTO series_catalog VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ["S", "S", "x", "x", "daily", "u", "USD", "UTC", False, "C", 24, True, "2025-01-01", "2025-01-01"])
    result = generate_coverage_report(db.conn, as_of="2025-01-02T00:00:00+00:00")
    assert result["status"] in {"DATA_BLOCKED", "EMPTY"} and result["series"][0]["n_obs"] == 0
    assert result["series"][0]["acceptance_status"] == "UNKNOWN"


def test_coverage_filters_available_at_and_is_sorted():
    db = init_db(":memory:")
    db.conn.execute("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)", ["B", date(2025, 1, 2), "2025-01-03 00:00:00", 2.0, "fixture", "B", None, "2025-01-03", "ok", None, "r"])
    db.conn.execute("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)", ["A", date(2025, 1, 1), "2025-01-01 00:00:00", 1.0, "fixture", "A", None, "2025-01-01", "ok", None, "r"])
    result = generate_coverage_report(db.conn, as_of="2025-01-02T00:00:00+00:00")
    assert [item["series"] for item in result["series"]] == ["A"]
