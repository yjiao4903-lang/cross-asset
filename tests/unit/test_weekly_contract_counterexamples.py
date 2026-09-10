from datetime import date, datetime
from pathlib import Path

import pytest

from cross_asset.research.weekly_review import (
    BEIJING,
    Observation,
    build_fact_table,
    run_weekly_review,
    to_beijing,
)

FIXTURE = Path(__file__).resolve().parents[2] / "examples" / "weekly_review_fixture.json"


def _obs(series_id, day, value, available=None, source="fixture"):
    stamp = available or f"{day}T12:00:00+08:00"
    return Observation(series_id, date.fromisoformat(day), value, to_beijing(stamp), source)


def _table(rows, required=None):
    config = {
        "required_series": required
        or [{"series_id": "US_EQ", "asset_id": "US_EQ", "kind": "price", "unit": "index_points"}],
        "lookbacks": {
            "week": {"days": 7, "label": "1w"},
            "month": {"days": 21, "label": "21d_calendar"},
        },
    }
    return build_fact_table(
        rows,
        as_of=date(2026, 9, 9),
        cutoff=datetime(2026, 9, 9, 23, 59, tzinfo=BEIJING),
        config=config,
        week_end_date=date(2026, 9, 4),
    )


def test_current_none_with_valid_history_blocks_without_crashing():
    table = _table([_obs("US_EQ", "2026-08-28", 100), _obs("US_EQ", "2026-09-04", None)])
    assert table["status"] == "DATA_BLOCKED"
    assert table["facts"][0]["value"] is None
    valid_current = _table([_obs("US_EQ", "2026-08-28", None), _obs("US_EQ", "2026-09-04", 101)])
    assert valid_current["facts"][0]["value"] == 101


def test_explicit_cutoff_beyond_asof_is_rejected(tmp_path: Path):
    with pytest.raises((ValueError, RuntimeError)):
        run_weekly_review(
            as_of="2026-09-04",
            observations_json=FIXTURE,
            output=tmp_path / "weekly_counterexample.md",
            review_cutoff="2026-09-06T12:00:00+08:00",
        )


def test_missing_expected_provider_never_becomes_admitted():
    table = _table(
        [_obs("US_EQ", "2026-09-04", 100, source="unverified")],
        required=[
            {
                "series_id": "US_EQ",
                "asset_id": "US_EQ",
                "kind": "price",
                "unit": "index_points",
                "provider": None,
            }
        ],
    )
    fact = table["facts"][0]
    assert fact["source_status"] != "ADMITTED"
