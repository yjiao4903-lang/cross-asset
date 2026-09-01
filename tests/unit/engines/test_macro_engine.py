import json
from datetime import UTC, datetime
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
