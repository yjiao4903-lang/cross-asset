"""Personal-weekly US_EQ from the public FRED SP500 CSV.

This path does not use FRED_API_KEY and does not grant
RESEARCH_ADMISSIBLE or Live admission. available_at is the
conservative next-day 12:00 Beijing rule.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")
PUBLIC_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SERIES_CODE = "SP500"
CANONICAL = "US_EQ"


def conservative_available_at(observation_date: date) -> datetime:
    nxt = observation_date + timedelta(days=1)
    return datetime.combine(nxt, time(12, 0), tzinfo=BEIJING)


def parse_fred_sp500_csv(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        day = (raw.get("observation_date") or raw.get("DATE") or "").strip()
        value = (raw.get(SERIES_CODE) or raw.get("value") or "").strip()
        if not day or value in {"", "."}:
            continue
        obs_date = date.fromisoformat(day[:10])
        available = conservative_available_at(obs_date)
        rows.append(
            {
                "series_id": CANONICAL,
                "observation_date": obs_date.isoformat(),
                "value": float(value),
                "available_at": available.isoformat(),
                "source": "fred",
            }
        )
    return rows


def fetch_fred_sp500_csv(
    *,
    start: str,
    end: str,
    timeout: int = 8,
) -> str:
    query = f"id={SERIES_CODE}&cosd={start}&coed={end}"
    url = f"{PUBLIC_CSV}?{query}"
    request = Request(url, headers={"User-Agent": "cross-asset-personal-weekly/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8-sig")


def build_us_eq_observations(
    *,
    start: str,
    end: str,
    csv_text: str | None = None,
) -> dict[str, Any]:
    text = csv_text if csv_text is not None else fetch_fred_sp500_csv(
        start=start, end=end
    )
    rows = parse_fred_sp500_csv(text)
    return {
        "status": "PERSONAL_WEEKLY",
        "usage": "PERSONAL_WEEKLY",
        "provider": "fred",
        "source_series_id": SERIES_CODE,
        "transport": "public_csv",
        "research_admissible": False,
        "observations": rows,
    }


__all__ = [
    "build_us_eq_observations",
    "conservative_available_at",
    "fetch_fred_sp500_csv",
    "parse_fred_sp500_csv",
]
