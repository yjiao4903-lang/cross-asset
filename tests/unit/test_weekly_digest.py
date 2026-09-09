from datetime import date

from cross_asset.research.weekly_digest import (
    build_weekly_digest,
    upcoming_events,
)


def test_upcoming_events_keep_next_two_weeks_only():
    events = [
        {"date": "2026-09-04", "label": "too_early"},
        {"date": "2026-09-11", "label": "CPI"},
        {"date": "2026-10-01", "label": "too_late"},
    ]
    out = upcoming_events(events, date(2026, 9, 4))
    assert [item["label"] for item in out] == ["CPI"]


def test_digest_uses_this_week_numbers():
    table = {
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
    digest = build_weekly_digest(
        table=table,
        boxes=[
            {"label": "增长", "value": "走弱"},
            {"label": "流动性", "value": "松"},
        ],
        scorecard=[{"label": "CN_BOND", "win": "升", "odds": "差"}],
        stance={"decision": "不行动"},
        reviews=[
            {
                "house": "personal_journal",
                "checks": [
                    {
                        "label": "海外约束",
                        "computed": "中性",
                        "stated": "外部紧",
                        "status": "对照冲突",
                    }
                ],
            }
        ],
        depth={
            "transmission": [
                {"label": "增长复合体", "status": "断裂"},
                {"label": "国内利率传导", "status": "接通"},
                {"label": "黄金-利率对冲", "status": "断裂"},
            ],
            "priced": [{"claim": "弱增长", "state": "残差"}],
        },
    )
    text = digest["markdown"]
    assert "A股一周-1.33%" in digest["happened"]
    assert "1.68" in digest["constraint"]
    assert "不能把宽松直接写成加久期" in digest["constraint"]
    assert "外部紧" in text
    assert "FOMC" in text
    assert "不行动" in text
