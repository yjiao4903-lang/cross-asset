from datetime import date, datetime
from pathlib import Path

from cross_asset.research.weekly_review import (
    Observation,
    build_fact_table,
    compare_weeks,
    latest_on_or_before,
    run_weekly_review,
    week_end,
)

FIXTURE = Path(__file__).resolve().parents[2] / "examples" / "weekly_review_fixture.json"


def _obs(series_id, day, value, available=None):
    return Observation(
        series_id=series_id,
        observation_date=date.fromisoformat(day),
        value=value,
        available_at=datetime.fromisoformat((available or day) + "T16:00:00"),
        source="fixture",
    )


CONFIG = {
    "week_end_weekday": "Friday",
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


def test_future_available_at_is_invisible():
    rows = [_obs("US_EQ", "2026-09-04", 100, "2026-09-08")]
    assert (
        latest_on_or_before(rows, "US_EQ", date(2026, 9, 4), datetime(2026, 9, 4, 16, 0, 0))
        is None
    )


def test_missing_level_blocks_and_does_not_fill():
    rows = [_obs("US_EQ", "2026-09-04", 100)]
    table = build_fact_table(
        rows,
        as_of=date(2026, 9, 9),
        cutoff=datetime(2026, 9, 9, 23, 59, 59),
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
        _obs("US_EQ", "2026-09-04", 100),
        _obs("CN_BOND_10Y", "2026-08-14", 1.80),
        _obs("CN_BOND_10Y", "2026-08-28", 1.84),
        _obs("CN_BOND_10Y", "2026-09-04", 1.90),
    ]
    table = build_fact_table(
        rows,
        as_of=date(2026, 9, 9),
        cutoff=datetime(2026, 9, 9, 23, 59, 59),
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
    text = Path(result["brief_output"]).read_text(encoding="utf-8")
    assert "相对上周" in text
    assert "不行动" in text
    assert "未提供上周快照" in text
    snapshot = Path(result["snapshot_output"]).read_text(encoding="utf-8")
    assert "CN_EQ_LARGE" in snapshot
