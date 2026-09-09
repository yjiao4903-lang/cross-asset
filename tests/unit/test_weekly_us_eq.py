from datetime import date

from cross_asset.research.weekly_us_eq import (
    build_us_eq_observations,
    conservative_available_at,
    parse_fred_sp500_csv,
)


CSV = """observation_date,SP500
2026-08-14,7785.76
2026-08-28,7711.76
2026-09-04,7718.60
2026-09-07,
"""


def test_parse_skips_blank_and_stamps_next_noon_beijing():
    rows = parse_fred_sp500_csv(CSV)
    assert [row["observation_date"] for row in rows] == [
        "2026-08-14",
        "2026-08-28",
        "2026-09-04",
    ]
    assert rows[-1]["value"] == 7718.60
    assert rows[-1]["source"] == "fred"
    assert rows[-1]["available_at"] == "2026-09-05T12:00:00+08:00"
    stamp = conservative_available_at(date(2026, 8, 28))
    assert stamp.isoformat() == "2026-08-29T12:00:00+08:00"


def test_build_from_text_stays_personal():
    payload = build_us_eq_observations(
        start="2026-08-01",
        end="2026-09-05",
        csv_text=CSV,
    )
    assert payload["status"] == "PERSONAL_WEEKLY"
    assert payload["research_admissible"] is False
    assert payload["transport"] == "public_csv"
    assert len(payload["observations"]) == 3
