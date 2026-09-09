from datetime import date, datetime

import pytest

from cross_asset.research.weekly_depth import build_location
from cross_asset.research.weekly_layers import build_scorecard, decide_stance, overlay_levels
from cross_asset.research.weekly_review import (
    BEIJING,
    Observation,
    build_fact_table,
    run_weekly_review,
    to_beijing,
)

FIXTURE = "examples/weekly_review_fixture.json"


def _obs(series_id, day, value, available=None, source="fixture"):
    stamp = available or f"{day}T12:00:00+08:00"
    return Observation(series_id, date.fromisoformat(day), value, to_beijing(stamp), source)


def _table(rows, required=None):
    config = {"required_series": required or [{"series_id": "US_EQ", "asset_id": "US_EQ", "kind": "price", "unit": "index_points"}], "lookbacks": {"week": {"days": 7, "label": "1w"}, "month": {"days": 21, "label": "1m"}}}
    return build_fact_table(rows, as_of=date(2026, 9, 9), cutoff=datetime(2026, 9, 9, 23, 59, tzinfo=BEIJING), config=config, week_end_date=date(2026, 9, 4))


def test_twenty_revisions_of_one_period_do_not_count_as_year_percentile():
    rows = [_obs("CN_EQ_LARGE", "2026-09-04", 100 + i, f"2026-09-04T{9+i%10:02d}:00:00+08:00") for i in range(20)]
    table = {"week_end": "2026-09-04", "facts": [{"series_id": "CN_EQ_LARGE", "value": 119, "changes": {}}]}
    result = build_location(rows, table, {}, cutoff=datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING))
    item = next(row for row in result if row["series_id"] == "CN_EQ_LARGE")
    assert item["percentile_1y"] is None and item["n_unique_periods"] == 1


def test_current_none_with_valid_history_blocks_without_crashing():
    table = _table([_obs("US_EQ", "2026-08-28", 100), _obs("US_EQ", "2026-09-04", None)])
    assert table["status"] == "DATA_BLOCKED"
    assert table["facts"][0]["value"] is None
    valid_current = _table([_obs("US_EQ", "2026-08-28", None), _obs("US_EQ", "2026-09-04", 101)])
    assert valid_current["facts"][0]["value"] == 101


def test_year_old_overlay_is_stale_and_cannot_drive_direction():
    rows = [_obs("CN_PMI", "2024-01-31", 55)]
    overlay = overlay_levels(rows, week_end_date=date(2026, 9, 4), cutoff=datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING), specs=[{"series_id": "CN_PMI"}])
    assert overlay["CN_PMI"]["status"] == "STALE" and overlay["CN_PMI"]["value"] is None


def test_blocked_core_cannot_emit_deterministic_observation_lean():
    table = {"status": "DATA_BLOCKED", "facts": [{"series_id": "US_EQ", "value": 110, "changes": {"1w": {"value": 0.02}, "1m": {"value": 0.1}}}]}
    scorecard = build_scorecard(table, {"US_GOV_10Y": {"change_1w": -10}}, [{"label": "增长", "value": None}, {"label": "流动性", "value": None}])
    stance = decide_stance(scorecard)
    assert table["status"] == "DATA_BLOCKED" and stance["leans"] == [] and stance["decision"] == "不行动"


def test_explicit_cutoff_beyond_asof_is_rejected():
    with pytest.raises((ValueError, RuntimeError)):
        run_weekly_review(as_of="2026-09-04", observations_json=FIXTURE, output="D:/CROSS/weekly_counterexample.md", review_cutoff="2026-09-06T12:00:00+08:00")


def test_missing_expected_provider_never_becomes_admitted():
    table = _table([_obs("US_EQ", "2026-09-04", 100, source="unverified")], required=[{"series_id": "US_EQ", "asset_id": "US_EQ", "kind": "price", "unit": "index_points", "provider": None}])
    fact = table["facts"][0]
    assert fact["source_status"] != "ADMITTED"
