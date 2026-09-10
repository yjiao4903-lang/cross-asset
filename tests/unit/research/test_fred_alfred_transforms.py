from datetime import date

import pandas as pd
import pytest

from cross_asset.ingestion.fred_alfred_pit import (
    MODE_ALL_REALTIME_PERIODS,
    MODE_REVISED_LATEST,
    FredPITError,
    VintageObservation,
    conservative_available_at,
)
from cross_asset.research.fred_alfred_transforms import (
    annualized_mom,
    causal_series,
    mom,
    rolling_percentile,
    rolling_zscore,
    spread,
    yoy,
)


def _record(obs, value, vintage, *, series="A", mode=MODE_ALL_REALTIME_PERIODS):
    vintage_date = date.fromisoformat(vintage)
    return VintageObservation(
        canonical_series_id=series,
        provider_series_id=series,
        observation_date=date.fromisoformat(obs),
        value=value,
        realtime_start=vintage_date,
        realtime_end=date(9999, 12, 31),
        conservative_available_at=conservative_available_at(vintage_date),
        mode=mode,
        request_vintage=None,
        raw_value=str(value),
    )


def test_yoy_and_mom_use_only_decision_visible_vintages():
    rows = []
    for month in range(1, 13):
        rows.append(_record(f"2020-{month:02d}-01", 100 + month, f"2020-{month:02d}-15"))
    rows.append(_record("2021-01-01", 120, "2021-01-15"))
    rows.append(_record("2020-01-01", 999, "2022-01-01"))
    decision = "2021-02-01T00:00:00Z"
    yoy_result = yoy(rows, decision_time=decision)
    mom_result = mom(rows, decision_time=decision)
    assert yoy_result.iloc[-1] == pytest.approx(120 / 101 - 1)
    assert mom_result.iloc[-1] == pytest.approx(120 / 112 - 1)
    assert causal_series(rows, decision_time=decision).iloc[0] == 101


def test_spread_aligns_only_causal_vintage_snapshots():
    left = [
        _record("2020-01-01", 2.0, "2020-01-02", series="L"),
        _record("2020-02-01", 2.5, "2020-02-02", series="L"),
    ]
    right = [
        _record("2020-01-01", 1.0, "2020-01-02", series="R"),
        _record("2020-02-01", 1.5, "2020-02-02", series="R"),
    ]
    result = spread(left, right, decision_time="2020-03-01T00:00:00Z")
    assert result.tolist() == [1.0, 1.0]


def test_rolling_zscore_and_percentile_are_trailing_only():
    rows = [
        _record(f"2020-0{i}-01", float(i), f"2020-0{i}-02")
        for i in range(1, 6)
    ]
    z = rolling_zscore(
        rows,
        decision_time="2020-06-01T00:00:00Z",
        window=3,
    )
    percentile = rolling_percentile(
        rows,
        decision_time="2020-06-01T00:00:00Z",
        window=3,
    )
    assert pd.isna(z.iloc[1])
    assert z.iloc[-1] > 0
    assert percentile.iloc[-1] == 1.0


def test_annualized_mom_is_explicit_compounding():
    rows = [
        _record("2020-01-01", 100.0, "2020-01-02"),
        _record("2020-02-01", 101.0, "2020-02-02"),
    ]
    result = annualized_mom(
        rows,
        decision_time="2020-03-01T00:00:00Z",
        periods_per_year=12,
    )
    assert result.iloc[-1] == pytest.approx((1.01**12) - 1)


def test_revised_latest_transform_fails_closed():
    rows = [_record("2020-01-01", 100.0, "2026-01-01", mode=MODE_REVISED_LATEST)]
    with pytest.raises(FredPITError, match="revised_latest_forbidden"):
        causal_series(rows, decision_time="2026-01-03T00:00:00Z")
