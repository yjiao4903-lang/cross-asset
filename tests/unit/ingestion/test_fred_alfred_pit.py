from datetime import UTC, datetime

import pytest

from cross_asset.ingestion.fred_alfred_pit import (
    MODE_ALL_REALTIME_PERIODS,
    MODE_HISTORICAL_ASOF,
    MODE_INITIAL_RELEASE,
    MODE_REVISED_LATEST,
    FredPITError,
    parse_observations,
    snapshot_asof,
)


def _row(value, realtime_start, realtime_end="9999-12-31", obs_date="2020-01-01"):
    return {
        "date": obs_date,
        "value": str(value),
        "realtime_start": realtime_start,
        "realtime_end": realtime_end,
    }


def test_revisions_are_preserved_and_asof_selects_latest_visible_version():
    payload = {
        "observations": [
            _row(100, "2020-02-01", "2020-03-14"),
            _row(101, "2020-03-15", "9999-12-31"),
        ]
    }
    rows = parse_observations(
        canonical_series_id="US_CPI_HEADLINE",
        provider_series_id="CPIAUCSL",
        payload=payload,
        mode=MODE_ALL_REALTIME_PERIODS,
    )
    assert [row.value for row in rows] == [100.0, 101.0]
    early = snapshot_asof(rows, datetime(2020, 3, 1, tzinfo=UTC))
    late = snapshot_asof(rows, datetime(2020, 3, 20, tzinfo=UTC))
    assert early[0].value == 100.0
    assert late[0].value == 101.0


def test_initial_release_accepts_official_shape_without_realtime_end():
    payload = {
        "output_type": 4,
        "observations": [
            {
                "realtime_start": "2020-02-13",
                "date": "2020-01-01",
                "value": "258.678",
            }
        ],
    }
    rows = parse_observations(
        canonical_series_id="US_CPI_HEADLINE",
        provider_series_id="CPIAUCSL",
        payload=payload,
        mode=MODE_INITIAL_RELEASE,
    )
    assert rows[0].realtime_start.isoformat() == "2020-02-13"
    assert rows[0].realtime_end is None
    assert rows[0].to_dict()["realtime_end"] is None
    assert snapshot_asof(rows, "2020-02-14T23:59:59Z") == []
    assert snapshot_asof(rows, "2020-02-15T00:00:00Z")[0].value == 258.678


def test_missing_realtime_end_still_fails_closed_outside_initial_release():
    with pytest.raises(FredPITError, match="fred_invalid_realtime_end"):
        parse_observations(
            canonical_series_id="US_CPI_HEADLINE",
            provider_series_id="CPIAUCSL",
            payload={
                "observations": [
                    {
                        "realtime_start": "2020-02-13",
                        "date": "2020-01-01",
                        "value": "258.678",
                    }
                ]
            },
            mode=MODE_ALL_REALTIME_PERIODS,
        )


def test_vintage_is_not_visible_until_two_utc_days_later_under_c0_policy():
    rows = parse_observations(
        canonical_series_id="US_CPI_HEADLINE",
        provider_series_id="CPIAUCSL",
        payload={"observations": [_row(100, "2020-02-01")]},
        mode=MODE_ALL_REALTIME_PERIODS,
    )
    assert snapshot_asof(rows, "2020-02-01T23:59:59Z") == []
    assert snapshot_asof(rows, "2020-02-02T00:00:00Z") == []
    assert snapshot_asof(rows, "2020-02-03T00:00:00Z")[0].value == 100.0


def test_future_vintage_in_historical_asof_payload_fails_closed():
    with pytest.raises(FredPITError, match="future_vintage_leakage"):
        parse_observations(
            canonical_series_id="US_CPI_HEADLINE",
            provider_series_id="CPIAUCSL",
            payload={"observations": [_row(100, "2020-04-01")]},
            mode=MODE_HISTORICAL_ASOF,
            request_vintage="2020-03-01",
        )


def test_request_vintage_after_decision_fails_closed():
    rows = parse_observations(
        canonical_series_id="US_CPI_HEADLINE",
        provider_series_id="CPIAUCSL",
        payload={"observations": [_row(100, "2020-03-01")]},
        mode=MODE_HISTORICAL_ASOF,
        request_vintage="2020-03-15",
    )
    with pytest.raises(FredPITError, match="future_vintage_leakage"):
        snapshot_asof(rows, "2020-03-10T12:00:00Z")


def test_revised_latest_is_explicitly_forbidden_for_historical_decisions():
    rows = parse_observations(
        canonical_series_id="US_CPI_HEADLINE",
        provider_series_id="CPIAUCSL",
        payload={"observations": [_row(101, "2026-01-01")]},
        mode=MODE_REVISED_LATEST,
    )
    with pytest.raises(FredPITError, match="revised_latest_forbidden"):
        snapshot_asof(rows, "2026-01-03T00:00:00Z")


def test_missing_values_remain_missing_not_imputed():
    rows = parse_observations(
        canonical_series_id="US_CPI_HEADLINE",
        provider_series_id="CPIAUCSL",
        payload={"observations": [_row(".", "2020-02-01")]},
        mode=MODE_ALL_REALTIME_PERIODS,
    )
    assert rows[0].value is None
