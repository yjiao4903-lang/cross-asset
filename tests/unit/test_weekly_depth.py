from datetime import date, datetime
from zoneinfo import ZoneInfo

from cross_asset.research.weekly_depth import (
    build_falsifiers,
    build_priced_residual,
    build_transmission,
)
from cross_asset.research.weekly_layers import build_weekly_layers
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


def test_growth_link_breaks_when_legs_disagree():
    table = {
        "facts": [
            {"series_id": "COPPER", "changes": {"1w": {"value": 0.02}}},
            {"series_id": "CN_EQ_LARGE", "changes": {"1w": {"value": -0.02}}},
            {"series_id": "CN_BOND_10Y", "changes": {"1w": {"value": -4.0}}},
            {"series_id": "GOLD", "changes": {"1w": {"value": 0.02}}},
            {"series_id": "HK_EQ", "changes": {"1w": {"value": 0.01}}},
        ]
    }
    overlay = {
        "CN_PMI": {"value": 49.5},
        "CN_DR007": {"change_1w": -3.0},
        "US_GOV_10Y": {"change_1w": 4.0},
        "CN_BOND_2Y": {"value": 1.3, "change_1w": -2.0},
        "US_GOV_2Y": {"value": 4.2, "change_1w": 1.0},
    }
    links = {
        item["label"]: item["status"]
        for item in build_transmission(table, overlay)
    }
    assert links["增长复合体"] == "断裂"
    assert links["国内利率传导"] == "接通"
    assert links["黄金-利率对冲"] == "断裂"
    assert links["A-H 同步"] == "断裂"
    assert links["外部利率→A股"] == "无脉冲"


def test_priced_residual_and_falsifier():
    boxes = [
        {"label": "增长", "value": "走弱"},
        {"label": "流动性", "value": "松"},
    ]
    links = [
        {"label": "增长复合体", "status": "断裂"},
        {"label": "国内利率传导", "status": "接通"},
        {"label": "黄金-利率对冲", "status": "断裂"},
        {"label": "A-H 同步", "status": "断裂"},
    ]
    table = {
        "facts": [
            {"series_id": "CN_EQ_LARGE", "changes": {"1w": {"value": -0.01}}},
            {"series_id": "GOLD", "changes": {"1w": {"value": 0.01}}},
        ]
    }
    priced = {
        item["claim"]: item["state"]
        for item in build_priced_residual(boxes, links, table)
    }
    assert priced["弱增长"] == "残差"
    assert priced["国内宽松"] == "已定价"
    assert priced["黄金利率对冲"] == "残差"
    kills = build_falsifiers(
        boxes,
        links,
        [{"label": "弱增长 + 松流动性", "active": True}],
    )
    assert any("PMI" in item["next_week"] for item in kills)


def test_layers_append_depth_headings():
    config = {
        "week_end_weekday": "Friday",
        "lookbacks": {
            "week": {"days": 7, "label": "1w"},
            "month": {"days": 21, "label": "1m"},
        },
        "required_series": [
            {
                "series_id": "CN_EQ_LARGE",
                "asset_id": "CN_EQ",
                "kind": "price",
                "unit": "index_points",
            },
            {
                "series_id": "HK_EQ",
                "asset_id": "HK_EQ",
                "kind": "price",
                "unit": "index_points",
            },
            {
                "series_id": "US_EQ",
                "asset_id": "US_EQ",
                "kind": "price",
                "unit": "index_points",
            },
            {
                "series_id": "CN_BOND_10Y",
                "asset_id": "CN_BOND",
                "kind": "yield",
                "unit": "percent",
            },
            {"series_id": "GOLD", "asset_id": "GOLD", "kind": "price", "unit": "price"},
            {
                "series_id": "COPPER",
                "asset_id": "COMMODITY",
                "kind": "price",
                "unit": "price",
            },
        ],
    }
    rows = [
        _obs("CN_EQ_LARGE", "2026-08-28", 100),
        _obs("CN_EQ_LARGE", "2026-09-04", 98),
        _obs("HK_EQ", "2026-08-28", 100),
        _obs("HK_EQ", "2026-09-04", 102),
        _obs("US_EQ", "2026-08-28", 100, "2026-08-29T12:00:00+08:00"),
        _obs("US_EQ", "2026-09-04", 101, "2026-09-05T12:00:00+08:00"),
        _obs("CN_BOND_10Y", "2026-08-28", 1.70),
        _obs("CN_BOND_10Y", "2026-09-04", 1.68),
        _obs("GOLD", "2026-08-28", 100, "2026-08-29T12:00:00+08:00"),
        _obs("GOLD", "2026-09-04", 103, "2026-09-05T12:00:00+08:00"),
        _obs("COPPER", "2026-08-28", 6.0, "2026-08-29T12:00:00+08:00"),
        _obs("COPPER", "2026-09-04", 5.9, "2026-09-05T12:00:00+08:00"),
        _obs("CN_PMI", "2026-08-31", 49.5, "2026-08-31T09:00:00+08:00"),
        _obs("CN_DR007", "2026-08-28", 1.50),
        _obs("CN_DR007", "2026-09-04", 1.45),
        _obs("US_GOV_10Y", "2026-08-28", 4.60, "2026-08-29T12:00:00+08:00"),
        _obs("US_GOV_10Y", "2026-09-04", 4.70, "2026-09-05T12:00:00+08:00"),
    ]
    table = build_fact_table(
        rows,
        as_of=date(2026, 9, 5),
        cutoff=datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING),
        config=config,
    )
    layers = build_weekly_layers(
        rows,
        table,
        cutoff=datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING),
    )
    assert layers["stance"]["decision"] == "不行动"
    assert "传导图" in layers["markdown"]
    assert "已定价 / 残差" in layers["markdown"]
    assert "下周证伪" in layers["markdown"]
    assert layers["depth"]["transmission"]
    gold = next(
        item
        for item in layers["depth"]["transmission"]
        if item["label"] == "黄金-利率对冲"
    )
    assert gold["status"] == "断裂"
