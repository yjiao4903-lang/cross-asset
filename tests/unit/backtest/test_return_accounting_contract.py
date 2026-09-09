import pandas as pd
import pytest

from cross_asset.backtest.accounting import (
    AssetAccountingSpec,
    FXConversionSpec,
    PortfolioAccountingPolicy,
    embedded_accounting_disclosure,
    embedded_accounting_required_series_ids,
    portfolio_reporting_currency_return,
)
from cross_asset.backtest.returns import AssetReturnSpec


def _embedded_spec(*, fx=None, hedge_series=None):
    accounting = {
        "policy_version": "test-v1",
        "reporting_currency": "CNY",
        "supported_currencies": ["CNY", "USD"],
        "pricing_basis": "decision_to_next_decision_research_proxy",
        "performance_semantics": "research_proxy_not_investor_realizable",
        "local_currency": "USD",
        "return_type": "PRICE_RETURN",
        "hedge_status": "UNHEDGED",
        "fx_mapping_status": "RESOLVED" if fx else "UNRESOLVED",
        "fx": fx,
        "hedge_return_series_id": hedge_series,
        "futures_roll_semantics": None,
    }
    return AssetReturnSpec("USD_ASSET", kind="price", accounting=accounting)


def test_embedded_policy_declares_fx_and_hedge_formal_query_dependencies():
    fx = {
        "series_id": "USD_CNY_APPROVED",
        "local_currency": "USD",
        "reporting_currency": "CNY",
        "quote_direction": "reporting_per_local",
        "max_age_hours": 24.0,
    }
    specs = {"A": _embedded_spec(fx=fx, hedge_series="USD_CNY_HEDGE_RETURN")}
    assert embedded_accounting_required_series_ids(specs) == {
        "USD_CNY_APPROVED",
        "USD_CNY_HEDGE_RETURN",
    }
    disclosure = embedded_accounting_disclosure(specs)
    assert disclosure is not None
    assert disclosure["reporting_currency"] == "CNY"
    assert disclosure["performance_semantics"] == "research_proxy_not_investor_realizable"
    assert disclosure["assets"]["A"]["fx"]["series_id"] == "USD_CNY_APPROVED"


def test_policy_rejects_investor_realizable_relabeling():
    policy = PortfolioAccountingPolicy(
        version="test-v1",
        reporting_currency="CNY",
        supported_currencies=("CNY",),
        assets={
            "CASH": AssetAccountingSpec(
                local_currency="CNY",
                return_type="CASH_RATE",
                fx_mapping_status="NOT_REQUIRED",
            )
        },
        performance_semantics="investor_realizable",
    )
    with pytest.raises(ValueError, match="realizable_performance_claim_not_authorized"):
        policy.validate()


def test_cash_return_stays_in_reporting_currency_without_fx():
    policy = PortfolioAccountingPolicy(
        version="test-v1",
        reporting_currency="CNY",
        supported_currencies=("CNY",),
        assets={
            "CASH": AssetAccountingSpec(
                local_currency="CNY",
                return_type="CASH_RATE",
                fx_mapping_status="NOT_REQUIRED",
            )
        },
    )
    result = portfolio_reporting_currency_return(
        pd.DataFrame(),
        {"CASH": 1.0},
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-08T00:00:00Z"),
        return_specs={
            "CASH": AssetReturnSpec(None, kind="cash", annual_rate=0.0365)
        },
        policy=policy,
    )
    assert result.status == "RESOLVED"
    assert result.by_asset["CASH"]["conversion"] == "not_required"
    assert result.asset_returns["CASH"] == pytest.approx(0.0365 * 7 / 365.25)


def test_future_fx_available_at_cannot_leak_into_earlier_boundary():
    observations = pd.DataFrame(
        [
            {
                "series_id": "USD_ASSET",
                "observation_date": "2026-01-01",
                "available_at": "2026-01-01T08:00:00Z",
                "value": 100.0,
                "quality": "ok",
            },
            {
                "series_id": "USD_ASSET",
                "observation_date": "2026-01-08",
                "available_at": "2026-01-08T08:00:00Z",
                "value": 101.0,
                "quality": "ok",
            },
            {
                "series_id": "USD_CNY_APPROVED",
                "observation_date": "2026-01-01",
                "available_at": "2026-01-01T08:00:00Z",
                "value": 7.0,
                "quality": "ok",
            },
            {
                "series_id": "USD_CNY_APPROVED",
                "observation_date": "2026-01-08",
                "available_at": "2026-01-08T13:00:00Z",
                "value": 7.1,
                "quality": "ok",
            },
        ]
    )
    policy = PortfolioAccountingPolicy(
        version="test-v1",
        reporting_currency="CNY",
        supported_currencies=("CNY", "USD"),
        assets={
            "A": AssetAccountingSpec(
                local_currency="USD",
                return_type="PRICE_RETURN",
                fx_mapping_status="RESOLVED",
                fx=FXConversionSpec(
                    series_id="USD_CNY_APPROVED",
                    local_currency="USD",
                    reporting_currency="CNY",
                    quote_direction="reporting_per_local",
                    max_age_hours=24.0,
                ),
            )
        },
    )
    result = portfolio_reporting_currency_return(
        observations,
        {"A": 1.0},
        pd.Timestamp("2026-01-01T12:00:00Z"),
        pd.Timestamp("2026-01-08T12:00:00Z"),
        return_specs={"A": AssetReturnSpec("USD_ASSET", kind="price")},
        policy=policy,
    )
    assert result.status == "BLOCKED"
    assert any(
        blocker in {"A:fx_quote_stale", "A:fx_quote_unavailable_at_boundary"}
        for blocker in result.blockers
    )
