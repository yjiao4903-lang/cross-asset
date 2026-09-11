from datetime import date, datetime

from cross_asset.research.weekly_review import (
    BEIJING,
    Observation,
    build_fact_table,
    compare_weeks,
    to_beijing,
)


def _obs(day: str, value: float, *, available: str | None = None, source: str = "manual") -> Observation:
    return Observation(
        series_id="US_EQ",
        observation_date=date.fromisoformat(day),
        value=value,
        available_at=to_beijing(available or f"{day}T16:00:00+08:00"),
        source=source,
    )


def _config() -> dict:
    return {
        "week_end_weekday": "Friday",
        "require_provider_match": True,
        "lookbacks": {
            "week": {"days": 7, "label": "1w", "max_slippage_days": 3},
        },
        "required_series": [
            {
                "series_id": "US_EQ",
                "asset_id": "US_EQ",
                "kind": "price",
                "unit": "index_points",
                "provider": "manual",
                "usage": "PERSONAL_WEEKLY",
            }
        ],
    }


def _table(rows: list[Observation]) -> dict:
    return build_fact_table(
        rows,
        as_of=date(2026, 9, 9),
        cutoff=datetime(2026, 9, 5, 12, 0, tzinfo=BEIJING),
        config=_config(),
        week_end_date=date(2026, 9, 4),
    )


def test_prior_within_slippage_computes_and_discloses_dates():
    table = _table([_obs("2026-08-27", 100.0), _obs("2026-09-04", 110.0)])
    change = table["facts"][0]["changes"]["1w"]

    assert table["status"] == "READY"
    assert change["value"] == 0.1
    assert change["target_date"] == "2026-08-28"
    assert change["actual_prior_date"] == "2026-08-27"
    assert change["slippage_days"] == 1
    assert change["max_slippage_days"] == 3
    assert change["status"] == "COMPARABLE"
    assert change["reason"] is None
    assert table["facts"][0]["source_status"] == "PROVIDER_MATCHED"
    assert table["facts"][0]["source_status"] != "ADMITTED"


def test_prior_beyond_slippage_is_partial_and_never_fake_return():
    table = _table([_obs("2026-08-24", 100.0), _obs("2026-09-04", 110.0)])
    change = table["facts"][0]["changes"]["1w"]

    assert table["status"] == "PARTIAL"
    assert change["value"] is None
    assert change["actual_prior_date"] == "2026-08-24"
    assert change["slippage_days"] == 4
    assert change["status"] == "NON_COMPARABLE"
    assert change["reason"] == "LOOKBACK_SLIPPAGE_EXCEEDED"
    assert any("LOOKBACK_SLIPPAGE_EXCEEDED" in item for item in table["missing_lookbacks"])


def test_future_available_at_prior_cannot_leak_into_lookback():
    table = _table(
        [
            _obs("2026-08-28", 100.0, available="2026-09-06T12:00:00+08:00"),
            _obs("2026-09-04", 110.0),
        ]
    )
    change = table["facts"][0]["changes"]["1w"]

    assert table["status"] == "PARTIAL"
    assert change["value"] is None
    assert change["actual_prior_date"] is None
    assert change["reason"] == "PRIOR_OBSERVATION_MISSING"


def test_provider_mismatch_stays_unverified_and_blocks_required_match():
    table = _table([_obs("2026-08-28", 100.0, source="other"), _obs("2026-09-04", 110.0, source="other")])

    assert table["status"] == "DATA_BLOCKED"
    assert table["facts"][0]["source_status"] == "UNVERIFIED"
    assert table["unverified_sources"] == ["US_EQ"]


def test_non_adjacent_snapshots_are_not_presented_as_prior_week():
    current = {
        "week_end": "2026-09-04",
        "facts": [{"series_id": "US_EQ", "label": "US_EQ", "kind": "price", "value": 110, "period": "2026-09-04"}],
    }
    stale = {
        "week_end": "2026-08-21",
        "facts": [{"series_id": "US_EQ", "label": "US_EQ", "kind": "price", "value": 100, "period": "2026-08-21"}],
    }

    result = compare_weeks(current, stale)
    assert result == [
        {
            "label": "snapshot_comparability",
            "value": "NON_ADJACENT_SNAPSHOT",
            "unit": "status",
            "period": "2026-08-21 -> 2026-09-04",
            "source": "weekly_review",
        }
    ]
    assert "prior week" not in result[0]["label"]
