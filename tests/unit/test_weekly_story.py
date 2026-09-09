from cross_asset.research.weekly_story import build_weekly_story, rank_moves


def _table():
    return {
        "week_end": "2026-09-04",
        "facts": [
            {
                "series_id": "CN_EQ_LARGE",
                "value": 4548.05,
                "changes": {"1w": {"value": -0.013263}},
            },
            {
                "series_id": "HK_EQ",
                "value": 25650.87,
                "changes": {"1w": {"value": 0.002583}},
            },
            {
                "series_id": "US_EQ",
                "value": 7718.6,
                "changes": {"1w": {"value": 0.000887}},
            },
            {
                "series_id": "CN_BOND_10Y",
                "value": 1.68,
                "changes": {"1w": {"value": -1.7}},
            },
            {
                "series_id": "GOLD",
                "value": 4510.0,
                "changes": {"1w": {"value": 0.012618}},
            },
            {
                "series_id": "COPPER",
                "value": 6.577,
                "changes": {"1w": {"value": 0.004659}},
            },
        ],
    }


def test_rank_puts_a_share_and_gold_ahead_of_us():
    ranked = rank_moves(_table())
    names = [item["name"] for item in ranked]
    assert names[0] in {"A股", "黄金"}
    assert names[-1] == "美股"


def test_story_leads_with_ah_split_not_six_name_list():
    story = build_weekly_story(
        table=_table(),
        boxes=[
            {"label": "增长", "value": "走弱"},
            {"label": "流动性", "value": "松"},
        ],
        scorecard=[
            {"label": "CN_EQ", "win": "降", "odds": "改善"},
            {"label": "CN_BOND", "win": "升", "odds": "差"},
        ],
        stance={"decision": "不行动"},
        depth={
            "transmission": [
                {"label": "增长复合体", "status": "断裂"},
                {"label": "国内利率传导", "status": "接通"},
                {"label": "黄金-利率对冲", "status": "断裂"},
                {"label": "A-H 同步", "status": "断裂"},
            ],
            "priced": [
                {"claim": "弱增长", "state": "残差"},
                {"claim": "黄金利率对冲", "state": "残差"},
            ],
            "falsifiers": [
                {
                    "kills": "A-H 分化",
                    "next_week": "两岸一周收益重新同号。",
                }
            ],
        },
    )
    text = story["markdown"]
    assert story["thesis"]["id"] == "ah_split"
    assert "A/H拆开" in story["headline"]
    assert "A股一周" not in story["headline"]
    assert "持仓腿在做什么" in text
    assert "为什么仍不行动" in text
    assert "不行动" in text
    assert "A-H 分化" in text
