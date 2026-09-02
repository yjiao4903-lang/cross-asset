import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from cross_asset.engines.macro import build_macro_state
from cross_asset.features.macro import transform_series


def _fixture_rows():
    raw = json.loads(
        Path("tests/fixtures/macro_vintage/jan_vintage.json").read_text(encoding="utf-8")
    )
    return [
        dict(
            row,
            available_at=datetime.fromisoformat(row["available_at"]),
            observation_date=datetime.fromisoformat(row["observation_date"]).date(),
        )
        for row in raw
    ]


def test_macro_vintage_cutoff_hides_future_and_selects_revision():
    rows = _fixture_rows()
    before = build_macro_state(
        rows,
        datetime(2025, 2, 9, tzinfo=UTC),
        {
            "series": {"TEST_MACRO_JAN": {"transform": {"type": "level"}}},
            "dimensions": {"GROWTH": ["TEST_MACRO_JAN"]},
        },
    )
    feb = build_macro_state(
        rows,
        datetime(2025, 2, 20, tzinfo=UTC),
        {
            "series": {"TEST_MACRO_JAN": {"transform": {"type": "level"}}},
            "dimensions": {"GROWTH": ["TEST_MACRO_JAN"]},
        },
    )
    mar = build_macro_state(
        rows,
        datetime(2025, 3, 20, tzinfo=UTC),
        {
            "series": {"TEST_MACRO_JAN": {"transform": {"type": "level"}}},
            "dimensions": {"GROWTH": ["TEST_MACRO_JAN"]},
        },
    )
    assert before.score is None
    # The raw PIT value is retained in contributions; aggregate scores are
    # intentionally clipped to the model's [-2, 2] score contract.
    assert feb["GROWTH"].contributions["TEST_MACRO_JAN"] == 100
    assert mar["GROWTH"].contributions["TEST_MACRO_JAN"] == 102


def test_macro_transform_missing_and_direction():
    assert transform_series([], {"type": "level"}).reason == "missing"
    assert transform_series([{"value": 100}], {"type": "diff"}).reason == "insufficient_history"
    result = transform_series(
        [{"value": 100}, {"value": 102}], {"type": "diff", "direction": "negative"}
    )
    assert result.available and result.value == -2


def test_macro_confidence_drops_with_missing_dimension():
    rows = _fixture_rows()[:1]
    state = build_macro_state(
        rows,
        datetime(2025, 2, 20, tzinfo=UTC),
        {
            "series": {"TEST_MACRO_JAN": {"transform": {"type": "level"}}},
            "dimensions": {"GROWTH": ["TEST_MACRO_JAN", "MISSING"], "POLICY": ["MISSING_POLICY"]},
        },
    )
    assert state["GROWTH"].coverage == 0.5
    assert state["POLICY"].score is None
    assert state.confidence < 1



def test_macro_revisions_do_not_count_as_extra_time_periods():
    rows = [
        {
            "series_id": "X",
            "observation_date": date(2025, 1, 1),
            "available_at": datetime(2025, 2, 1, tzinfo=UTC),
            "value": 100.0,
        },
        {
            "series_id": "X",
            "observation_date": date(2025, 1, 1),
            "available_at": datetime(2025, 3, 1, tzinfo=UTC),
            "value": 102.0,
        },
        {
            "series_id": "X",
            "observation_date": date(2025, 2, 1),
            "available_at": datetime(2025, 3, 10, tzinfo=UTC),
            "value": 105.0,
        },
    ]
    state = build_macro_state(
        rows,
        datetime(2025, 3, 20, tzinfo=UTC),
        {
            "series": {"X": {"transform": {"type": "diff"}}},
            "dimensions": {"GROWTH": ["X"]},
        },
    )
    assert state["GROWTH"].contributions["X"] == 3.0
    assert state["GROWTH"].raw_contributions["X"] == 3.0


def test_macro_dimension_freshness_is_series_local_not_global():
    rows = [
        {
            "series_id": "FRESH",
            "observation_date": date(2025, 1, 9),
            "available_at": datetime(2025, 1, 9, tzinfo=UTC),
            "value": 1.0,
        },
        {
            "series_id": "STALE",
            "observation_date": date(2024, 12, 1),
            "available_at": datetime(2024, 12, 1, tzinfo=UTC),
            "value": 1.0,
        },
    ]
    state = build_macro_state(
        rows,
        datetime(2025, 1, 10, tzinfo=UTC),
        {
            "series": {
                "FRESH": {
                    "stale_after_hours": 168,
                    "transform": {"type": "level"},
                },
                "STALE": {
                    "stale_after_hours": 168,
                    "transform": {"type": "level"},
                },
            },
            "dimensions": {"A": ["FRESH"], "B": ["STALE"]},
        },
    )
    assert state["A"].confidence > 0
    assert state["B"].confidence == 0


def test_macro_causal_normalization_requires_prior_history():
    rows = [
        {
            "series_id": "X",
            "observation_date": (date(2025, 1, 1) + timedelta(days=i)),
            "available_at": datetime(2025, 1, 1, tzinfo=UTC)
            + timedelta(days=i),
            "value": float(i),
        }
        for i in range(15)
    ]
    state = build_macro_state(
        rows,
        datetime(2025, 1, 20, tzinfo=UTC),
        {
            "series": {
                "X": {
                    "transform": {"type": "level"},
                    "normalization": {
                        "method": "causal_zscore",
                        "min_history": 10,
                        "clip": 2.0,
                    },
                }
            },
            "dimensions": {"GROWTH": ["X"]},
        },
    )
    assert state["GROWTH"].score is not None
    assert 0 < state["GROWTH"].score <= 2
    assert state["GROWTH"].raw_contributions["X"] == 14.0
