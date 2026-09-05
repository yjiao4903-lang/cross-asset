from types import SimpleNamespace

import pandas as pd
import pytest

import cross_asset.research.executor as executor
from cross_asset.backtest.returns import AssetReturnSpec
from cross_asset.research.executor import ResearchModelConfig


def test_executor_requests_fx_through_same_formal_observation_query(monkeypatch):
    captured = {}

    def fake_formal_query(
        _connection,
        _decision_time,
        *,
        required_usage_status,
        series_ids,
    ):
        captured["usage"] = required_usage_status
        captured["series_ids"] = tuple(series_ids)
        return pd.DataFrame()

    monkeypatch.setattr(executor, "latest_formal_observations_asof", fake_formal_query)
    accounting = {
        "policy_version": "test-v1",
        "reporting_currency": "CNY",
        "supported_currencies": ["CNY", "USD"],
        "pricing_basis": "decision_to_next_decision_research_proxy",
        "performance_semantics": "research_proxy_not_investor_realizable",
        "local_currency": "USD",
        "return_type": "PRICE_RETURN",
        "hedge_status": "UNHEDGED",
        "fx_mapping_status": "RESOLVED",
        "fx": {
            "series_id": "USD_CNY_APPROVED",
            "local_currency": "USD",
            "reporting_currency": "CNY",
            "quote_direction": "reporting_per_local",
            "max_age_hours": 24.0,
        },
        "hedge_return_series_id": None,
        "futures_roll_semantics": None,
    }
    model = ResearchModelConfig(
        assets=("A",),
        strategic_weights={"A": 1.0},
        return_specs={
            "A": AssetReturnSpec(
                "A_PRICE",
                kind="price",
                accounting=accounting,
            )
        },
        asset_signal_map={"A": {"macro": None}},
        component_weights={"trend": 1.0},
        allocation_config={},
        macro_config={"series": {}, "dimensions": {}},
    )
    protocol = SimpleNamespace(
        execution_blockers=(),
        required_usage_status="RESEARCH_ADMISSIBLE",
    )
    plan = {
        "status": "READY_FOR_OOS",
        "holdout_sealed": True,
        "development_count": 1,
        "folds": [],
    }
    dates = pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"])

    with pytest.raises(ValueError, match="formal_observations_empty"):
        executor.execute_walk_forward(
            object(),
            decision_dates=dates,
            plan=plan,
            protocol=protocol,
            model_config=model,
        )

    assert captured["usage"] == "RESEARCH_ADMISSIBLE"
    assert captured["series_ids"] == ("A_PRICE", "USD_CNY_APPROVED")
