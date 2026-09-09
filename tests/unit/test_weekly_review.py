from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cross_asset.research.weekly_review import (
    BEIJING,
    Observation,
    build_fact_table,
    compare_weeks,
    default_review_cutoff,
    latest_on_or_before,
    run_weekly_review,
    to_beijing,
    week_end,
)

FIXTURE = Path(__file__).resolve().parents[2] / "examples" / "weekly_review_fixture.json"
EDT = ZoneInfo("America/New_York")


def _obs(series_id, day, value, available=None):
    stamp = available or f"{day}T16:00:00+08:00"
    return Observation(
        series_id=series_id,
        observation_date=date.fromisoformat(day),
        value=value,
        available_at=to_beijing(stamp),
        source="fixture",
    )


CONFIG = {
    "week_end_weekday": "Friday",
    "review_local_time": "12:00",
    "lookbacks": {
        "week": {"days": 7, "label": "1w"},
        "month": {"days": 21, "label": "1m"},
    },
    "required_series": [
        {"series_id": "US_EQ", "asset_id": "US_EQ", "kind": "price", "unit": "index_points"},
        {"series_id": "CN_BOND_10Y", "asset_id": "CN_BOND", "kind": "yield", "unit": "percent"},
    ],
}


def test_week_end_snaps_back_to_friday():
    assert week_end(date(2026, 9, 9), "Friday") == date(2026, 9, 4)


def test_naive_timestamp_is_beijing():
    parsed = to_beijing("2026-09-05T12:00:00")
    assert parsed.tzinfo == BEIJING
    assert parsed.isoformat() == "2026-09-05T12:00:00+08:00"


def test_default_review_cutoff_is_saturday_noon_beijing():
    cutoff = default_review_cutoff(date(2026, 9, 4))
    assert cutoff == datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING)


def test_us_friday_close_visible_saturday_noon_beijing():
    us_close = datetime(2026, 9, 4, 16, 0, tzinfo=EDT)
    rows = [
        Observation(
            series_id="US_EQ",
            observation_date=date(2026, 9, 4),
            value=5500,
            available_at=to_beijing(us_close),
            source="fred",
        )
    ]
    friday_night = datetime(2026, 9, 4, 23, 59, 59, tzinfo=BEIJING)
    saturday_noon = datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING)
    assert latest_on_or_before(rows, "US_EQ", date(2026, 9, 4), friday_night) is None
    seen = latest_on_or_before(rows, "US_EQ", date(2026, 9, 4), saturday_noon)
    assert seen is not None
    assert seen.value == 5500


def test_future_available_at_is_invisible():
    rows = [_obs("US_EQ", "2026-09-04", 100, "2026-09-08T16:00:00+08:00")]
    assert (
        latest_on_or_before(rows, "US_EQ", date(2026, 9, 4), datetime(2026, 9, 4, 16, 0, tzinfo=BEIJING))
        is None
    )


def test_missing_level_blocks_and_does_not_fill():
    rows = [_obs("US_EQ", "2026-09-04", 100)]
    table = build_fact_table(
        rows,
        as_of=date(2026, 9, 9),
        cutoff=datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING),
        config=CONFIG,
    )
    assert table["status"] == "DATA_BLOCKED"
    assert "CN_BOND_10Y" in table["missing_levels"]
    bond = next(item for item in table["facts"] if item["series_id"] == "CN_BOND_10Y")
    assert bond["value"] is None
    assert bond["changes"]["1w"]["value"] is None


def test_price_and_yield_changes_use_dated_lookback():
    rows = [
        _obs("US_EQ", "2026-08-14", 90),
        _obs("US_EQ", "2026-08-28", 95),
        _obs("US_EQ", "2026-09-04", 100, "2026-09-05T12:00:00+08:00"),
        _obs("CN_BOND_10Y", "2026-08-14", 1.80),
        _obs("CN_BOND_10Y", "2026-08-28", 1.84),
        _obs("CN_BOND_10Y", "2026-09-04", 1.90),
    ]
    table = build_fact_table(
        rows,
        as_of=date(2026, 9, 9),
        cutoff=datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING),
        config=CONFIG,
    )
    assert table["status"] == "READY"
    equity = next(item for item in table["facts"] if item["series_id"] == "US_EQ")
    bond = next(item for item in table["facts"] if item["series_id"] == "CN_BOND_10Y")
    assert equity["changes"]["1w"]["value"] == round(100 / 95 - 1, 6)
    assert bond["changes"]["1w"]["value"] == round((1.90 - 1.84) * 100, 4)


def test_compare_weeks_and_cli_fixture(tmp_path: Path):
    current = {
        "week_end": "2026-09-04",
        "facts": [
            {"series_id": "US_EQ", "label": "US_EQ", "kind": "price", "value": 110, "period": "2026-09-04"}
        ],
    }
    prior = {
        "week_end": "2026-08-28",
        "facts": [
            {"series_id": "US_EQ", "label": "US_EQ", "kind": "price", "value": 100, "period": "2026-08-28"}
        ],
    }
    delta = compare_weeks(current, prior)
    assert delta[0]["value"] == 0.1

    result = run_weekly_review(
        as_of="2026-09-09",
        observations_json=FIXTURE,
        output=tmp_path / "weekly.md",
        snapshot_output=tmp_path / "weekly.snapshot.json",
        config_path="config/weekly_review.yml",
    )
    assert result["status"] == "READY"
    assert result["week_end"] == "2026-09-04"
    assert result["timezone"] == "Asia/Shanghai"
    assert "+08:00" in result["data_cutoff"]
    text = Path(result["brief_output"]).read_text(encoding="utf-8")
    assert "相对上周" in text
    assert "不行动" in text
    assert "未提供上周快照" in text
    assert "北京时间" in text
    assert "宏观四格" in text
    assert "胜率 / 赔率" in text
    assert result["stance"]["decision"] == "不行动"
    boxes = {item["label"]: item["value"] for item in result["macro_boxes"]}
    assert boxes["增长"] == "扩张"
    assert boxes["通胀"] == "分化"
    assert boxes["流动性"] == "松"
    snapshot = Path(result["snapshot_output"]).read_text(encoding="utf-8")
    assert "CN_EQ_LARGE" in snapshot
    assert "Asia/Shanghai" in snapshot
    assert "scorecard" in snapshot


def test_missing_config_and_explicit_none_do_not_fallback(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        __import__("cross_asset.research.weekly_review", fromlist=["load_weekly_config"]).load_weekly_config(
            tmp_path / "missing.yml"
        )
    rows = [
        _obs("US_EQ", "2026-08-28", 100),
        _obs("US_EQ", "2026-09-04", None, "2026-09-05T12:00:00+08:00"),
    ]
    table = build_fact_table(
        rows,
        as_of=date(2026, 9, 4),
        cutoff=datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING),
        config=CONFIG,
    )
    assert table["status"] == "DATA_BLOCKED"
    assert table["missing_levels"] == ["US_EQ", "CN_BOND_10Y"]


def test_explicit_week_end_and_review_cutoff_keep_saturday_close_visible():
    rows = [_obs("US_EQ", "2026-09-04", 5500, "2026-09-05T12:00:00+08:00")]
    table = build_fact_table(
        rows,
        as_of=date(2026, 9, 4),
        cutoff=datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING),
        config=CONFIG,
        week_end_date=date(2026, 9, 4),
    )
    assert table["facts"][0]["value"] == 5500
