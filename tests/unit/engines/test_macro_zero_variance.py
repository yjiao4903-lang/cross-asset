from datetime import UTC, date, datetime, timedelta

from cross_asset.engines.macro import build_macro_state


def _rows(values):
    start = date(2026, 1, 1)
    return [
        {
            "series_id": "X",
            "observation_date": start + timedelta(days=index),
            "available_at": datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
            "value": value,
        }
        for index, value in enumerate(values)
    ]


def _config():
    return {
        "series": {
            "X": {
                "raw_unit": "index",
                "derived_unit": "index",
                "transform": {"type": "level", "direction": "positive"},
                "normalization": {
                    "method": "causal_zscore",
                    "min_history": 10,
                    "clip": 2.0,
                },
            }
        },
        "dimensions": {"GROWTH": ["X"]},
    }


def test_macro_consumer_does_not_call_flat_continuation_neutral():
    rows = _rows([5.0] * 11)
    state = build_macro_state(
        rows,
        rows[-1]["available_at"] + timedelta(hours=1),
        _config(),
    )
    dimension = state["GROWTH"]
    assert dimension.raw_contributions["X"] == 5.0
    assert dimension.contributions["X"] is None
    assert dimension.score is None
    assert dimension.coverage == 0.0


def test_macro_consumer_surfaces_zero_variance_jump_as_directional_anomaly():
    rows = _rows([5.0] * 10 + [7.0])
    state = build_macro_state(
        rows,
        rows[-1]["available_at"] + timedelta(hours=1),
        _config(),
    )
    dimension = state["GROWTH"]
    assert dimension.raw_contributions["X"] == 7.0
    assert dimension.contributions["X"] == 2.0
    assert dimension.score == 2.0
    assert dimension.coverage == 1.0
