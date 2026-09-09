from datetime import date, datetime
from zoneinfo import ZoneInfo

from cross_asset.research.weekly_layers import build_macro_boxes, build_weekly_layers, decide_stance
from cross_asset.research.weekly_review import Observation, build_fact_table, to_beijing

BEIJING = ZoneInfo("Asia/Shanghai")


def _obs(series_id, day, value, available=None):
    stamp = available or f"{day}T16:00:00+08:00"
    return Observation(
        series_id=series_id,
        observation_date=date.fromisoformat(day),
        value=value,
        available_at=to_beijing(stamp),
        source="fixture",
    )


def test_missing_overlay_is_stale_not_blocked():
    boxes = build_macro_boxes({})
    states = {item["label"]: item["value"] for item in boxes}
    assert states["增长"] == "STALE"
    assert states["通胀"] == "STALE"


def test_layers_do_not_override_hold():
    stance = decide_stance(
        [
            {"label": "CN_EQ", "win": "升", "odds": "消耗"},
            {"label": "CN_BOND", "win": "降", "odds": "差"},
        ]
    )
    assert stance["decision"] == "不行动"


def test_build_layers_on_partial_facts():
    config = {
        "week_end_weekday": "Friday",
        "lookbacks": {"week": {"days": 7, "label": "1w"}, "month": {"days": 21, "label": "1m"}},
        "required_series": [
            {"series_id": "CN_EQ_LARGE", "asset_id": "CN_EQ", "kind": "price", "unit": "index_points"},
            {"series_id": "HK_EQ", "asset_id": "HK_EQ", "kind": "price", "unit": "index_points"},
            {"series_id": "US_EQ", "asset_id": "US_EQ", "kind": "price", "unit": "index_points"},
            {"series_id": "CN_BOND_10Y", "asset_id": "CN_BOND", "kind": "yield", "unit": "percent"},
            {"series_id": "GOLD", "asset_id": "GOLD", "kind": "price", "unit": "price"},
            {"series_id": "COPPER", "asset_id": "COMMODITY", "kind": "price", "unit": "price"},
        ],
    }
    rows = [
        _obs("CN_EQ_LARGE", "2026-08-28", 100),
        _obs("CN_EQ_LARGE", "2026-09-04", 99),
        _obs("HK_EQ", "2026-08-28", 100),
        _obs("HK_EQ", "2026-09-04", 101),
        _obs("US_EQ", "2026-08-28", 100, "2026-08-29T12:00:00+08:00"),
        _obs("US_EQ", "2026-09-04", 100, "2026-09-05T12:00:00+08:00"),
        _obs("CN_BOND_10Y", "2026-08-28", 1.70),
        _obs("CN_BOND_10Y", "2026-09-04", 1.68),
        _obs("GOLD", "2026-08-28", 100, "2026-08-29T12:00:00+08:00"),
        _obs("GOLD", "2026-09-04", 102, "2026-09-05T12:00:00+08:00"),
        _obs("COPPER", "2026-08-28", 6.0, "2026-08-29T12:00:00+08:00"),
        _obs("COPPER", "2026-09-04", 6.1, "2026-09-05T12:00:00+08:00"),
        _obs("CN_PMI", "2026-08-31", 49.8, "2026-08-31T09:00:00+08:00"),
    ]
    table = build_fact_table(
        rows,
        as_of=date(2026, 9, 5),
        cutoff=datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING),
        config=config,
    )
    layers = build_weekly_layers(rows, table, cutoff=datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING))
    boxes = {item["label"]: item["value"] for item in layers["macro_boxes"]}
    assert boxes["增长"] in {"走弱", "走弱偏平"}
    assert layers["stance"]["decision"] == "不行动"
    assert "宏观四格" in layers["markdown"]
    assert "竞争叙事" in layers["markdown"]
