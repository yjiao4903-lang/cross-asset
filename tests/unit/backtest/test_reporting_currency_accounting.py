from dataclasses import asdict

import pandas as pd
import pytest

from cross_asset.backtest.accounting import (
    AssetAccountingSpec,
    FXConversionSpec,
    PortfolioAccountingPolicy,
    load_return_accounting_policy,
    portfolio_reporting_currency_return,
)
from cross_asset.backtest.returns import AssetReturnSpec, portfolio_asset_returns
from cross_asset.research.model_config import load_research_model_config


def _frame(*, fx_quality="ok", fx_end_available="2026-01-09T08:00:00Z"):
    return pd.DataFrame(
        [
            {
                "series_id": "USD_ASSET",
                "observation_date": "2026-01-02",
                "available_at": "2026-01-02T08:00:00Z",
                "value": 100.0,
                "quality": "ok",
            },
            {
                "series_id": "USD_ASSET",
                "observation_date": "2026-01-09",
                "available_at": "2026-01-09T08:00:00Z",
                "value": 110.0,
                "quality": "ok",
            },
            {
                "series_id": "USD_CNY_EXPLICIT",
                "observation_date": "2026-01-02",
                "available_at": "2026-01-02T08:00:00Z",
                "value": 7.0,
                "quality": "ok",
            },
            {
                "series_id": "USD_CNY_EXPLICIT",
                "observation_date": "2026-01-09",
                "available_at": fx_end_available,
                "value": 7.2,
                "quality": fx_quality,
            },
        ]
    )


def _policy(
    *,
    quote_direction="reporting_per_local",
    max_age_hours=24.0,
    fx_mapping_status="RESOLVED",
    fx=True,
    hedge_status="UNHEDGED",
    hedge_return_series_id=None,
    return_type="PRICE_RETURN",
    local_currency="USD",
    futures_roll_semantics=None,
):
    conversion = None
    if fx:
        conversion = FXConversionSpec(
            series_id="USD_CNY_EXPLICIT",
            local_currency="USD",
            reporting_currency="CNY",
            quote_direction=quote_direction,
            max_age_hours=max_age_hours,
        )
    return PortfolioAccountingPolicy(
        version="test-v1",
        reporting_currency="CNY",
        supported_currencies=("CNY", "HKD", "USD"),
        assets={
            "A": AssetAccountingSpec(
                local_currency=local_currency,
                return_type=return_type,
                hedge_status=hedge_status,
                fx_mapping_status=fx_mapping_status,
                fx=conversion,
                hedge_return_series_id=hedge_return_series_id,
                futures_roll_semantics=futures_roll_semantics,
            )
        },
    )


def _result(frame, policy, **kwargs):
    return portfolio_reporting_currency_return(
        frame,
        {"A": 1.0},
        pd.Timestamp("2026-01-02T12:00:00Z"),
        pd.Timestamp("2026-01-09T12:00:00Z"),
        return_specs={"A": AssetReturnSpec("USD_ASSET", "price")},
        policy=policy,
        **kwargs,
    )


def test_unhedged_mixed_currency_return_uses_both_fx_endpoints():
    result = _result(_frame(), _policy())
    assert result.status == "RESOLVED"
    assert result.reporting_currency == "CNY"
    assert result.local_asset_returns["A"] == pytest.approx(0.10)
    assert result.asset_returns["A"] == pytest.approx(1.10 * (7.2 / 7.0) - 1.0)
    assert result.gross_return == pytest.approx(result.asset_returns["A"])
    assert result.performance_semantics == "research_proxy_not_investor_realizable"


def test_inverse_fx_quote_direction_is_explicit_not_guessed():
    frame = _frame()
    frame.loc[frame.series_id == "USD_CNY_EXPLICIT", "value"] = [1 / 7.0, 1 / 7.2]
    result = _result(frame, _policy(quote_direction="local_per_reporting"))
    assert result.status == "RESOLVED"
    assert result.asset_returns["A"] == pytest.approx(1.10 * (7.2 / 7.0) - 1.0)


def test_missing_fx_mapping_fails_closed():
    result = _result(
        _frame(),
        _policy(fx=False, fx_mapping_status="UNRESOLVED"),
    )
    assert result.status == "BLOCKED"
    assert "A:fx_mapping_unresolved" in result.blockers
    assert result.gross_return is None


def test_stale_or_bad_quality_fx_fails_closed():
    stale = _result(_frame(), _policy(max_age_hours=1.0))
    assert stale.status == "BLOCKED"
    assert any("fx_quote_stale" in blocker for blocker in stale.blockers)

    bad_quality = _result(_frame(fx_quality="stale"), _policy())
    assert bad_quality.status == "BLOCKED"
    assert any("fx_quality_blocked:stale" in blocker for blocker in bad_quality.blockers)


def test_fx_and_asset_pricing_boundaries_must_match():
    result = _result(
        _frame(),
        _policy(),
        fx_end_at=pd.Timestamp("2026-01-09T11:59:00Z"),
    )
    assert result.status == "BLOCKED"
    assert result.blockers == ("fx_boundary_mismatch_with_asset_pricing",)


def test_hedged_foreign_asset_requires_explicit_hedge_return_input():
    result = _result(
        _frame(),
        _policy(
            hedge_status="HEDGED",
            fx=False,
            fx_mapping_status="UNRESOLVED",
        ),
    )
    assert result.status == "BLOCKED"
    assert "A:hedge_return_series_missing" in result.blockers


def test_futures_proxy_requires_explicit_roll_semantics():
    frame = pd.DataFrame(
        [
            {
                "series_id": "USD_ASSET",
                "observation_date": "2026-01-02",
                "available_at": "2026-01-02T08:00:00Z",
                "value": 100.0,
            },
            {
                "series_id": "USD_ASSET",
                "observation_date": "2026-01-09",
                "available_at": "2026-01-09T08:00:00Z",
                "value": 101.0,
            },
        ]
    )
    policy = PortfolioAccountingPolicy(
        version="test-v1",
        reporting_currency="CNY",
        supported_currencies=("CNY", "HKD", "USD"),
        assets={
            "A": AssetAccountingSpec(
                local_currency="CNY",
                return_type="FUTURES_CONTINUOUS_ROLL_PROXY",
                fx_mapping_status="NOT_REQUIRED",
                futures_roll_semantics="UNVERIFIED",
            )
        },
    )
    result = _result(frame, policy)
    assert result.status == "BLOCKED"
    assert "A:futures_roll_semantics_unverified" in result.blockers


def test_unsupported_currency_is_rejected_by_policy():
    policy = _policy(
        local_currency="EUR",
        fx=False,
        fx_mapping_status="UNRESOLVED",
    )
    with pytest.raises(ValueError, match="unsupported_asset_currency:EUR"):
        policy.validate()


def test_default_research_policy_is_cny_and_refuses_unresolved_hkd_fx():
    policy = load_return_accounting_policy()
    assert policy.reporting_currency == "CNY"
    assert policy.assets["HK_EQ"].local_currency == "HKD"
    assert policy.assets["HK_EQ"].fx_mapping_status == "UNRESOLVED"
    assert policy.assets["US_EQ"].fx is None
    assert policy.assets["GOLD"].return_type == "UNRESOLVED"
    assert policy.assets["COMMODITY"].futures_roll_semantics == "UNVERIFIED"

    model = load_research_model_config()
    hk_accounting = dict(model.return_specs["HK_EQ"].accounting or {})
    assert hk_accounting["reporting_currency"] == "CNY"
    assert hk_accounting["fx_mapping_status"] == "UNRESOLVED"

    frame = pd.DataFrame(
        [
            {
                "series_id": "CN_EQ_LARGE",
                "observation_date": "2026-01-02",
                "available_at": "2026-01-02T08:00:00Z",
                "value": 100.0,
            },
            {
                "series_id": "CN_EQ_LARGE",
                "observation_date": "2026-01-09",
                "available_at": "2026-01-09T08:00:00Z",
                "value": 101.0,
            },
            {
                "series_id": "HK_EQ",
                "observation_date": "2026-01-02",
                "available_at": "2026-01-02T08:00:00Z",
                "value": 200.0,
            },
            {
                "series_id": "HK_EQ",
                "observation_date": "2026-01-09",
                "available_at": "2026-01-09T08:00:00Z",
                "value": 202.0,
            },
        ]
    )
    assert (
        portfolio_asset_returns(
            frame,
            {"CN_EQ": 0.5, "HK_EQ": 0.5},
            pd.Timestamp("2026-01-02T12:00:00Z"),
            pd.Timestamp("2026-01-09T12:00:00Z"),
            specs=model.return_specs,
        )
        is None
    )


def test_accounting_result_disclosure_is_serializable_mapping():
    result = _result(_frame(), _policy())
    payload = asdict(result)
    assert payload["reporting_currency"] == "CNY"
    assert payload["by_asset"]["A"]["return_type"] == "PRICE_RETURN"
    assert payload["by_asset"]["A"]["hedge_status"] == "UNHEDGED"
