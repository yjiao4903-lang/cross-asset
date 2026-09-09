from cross_asset.research.weekly_views import (
    build_narratives,
    compare_sell_side,
    render_view_markdown,
)


def test_sell_side_conflict_does_not_require_boxes_on_house():
    boxes = [
        {"label": "增长", "value": "扩张"},
        {"label": "通胀", "value": "分化"},
        {"label": "流动性", "value": "松"},
        {"label": "海外约束", "value": "中性"},
    ]
    reviews = compare_sell_side(
        boxes,
        [
            {
                "house": "fixture",
                "theme": "demo",
                "boxes": {"增长": "走弱", "通胀": "分化", "流动性": "松"},
            }
        ],
    )
    assert reviews[0]["agreement"] == "存在对照冲突"
    by_label = {row["label"]: row["status"] for row in reviews[0]["checks"]}
    assert by_label["增长"] == "对照冲突"
    assert by_label["通胀"] == "同意"
    assert by_label["海外约束"] == "卖方未填"


def test_empty_sell_side_is_not_a_block():
    boxes = [{"label": "增长", "value": "STALE"}]
    assert compare_sell_side(boxes, []) == []


def test_active_narrative_and_markdown():
    boxes = [
        {"label": "增长", "value": "走弱"},
        {"label": "通胀", "value": "回落或低位"},
        {"label": "流动性", "value": "松"},
        {"label": "海外约束", "value": "外部紧"},
    ]
    relatives = [
        {"label": "铜vsA股一周", "value": "背离"},
        {"label": "黄金vs美债一周", "value": "符合"},
        {"label": "A相对H一周", "value": 0.02},
    ]
    scorecard = [{"label": "CN_EQ", "win": "升", "odds": "消耗"}]
    stories = build_narratives(boxes, relatives, scorecard)
    active = {item["label"] for item in stories if item["active"]}
    assert "弱增长 + 松流动性" in active
    assert "外部约束收紧" in active
    assert "相对价格背离" in active
    assert "胜率与赔率打架" in active
    text = render_view_markdown([], stories)
    assert "竞争叙事" in text
    assert "弱增长 + 松流动性" in text
