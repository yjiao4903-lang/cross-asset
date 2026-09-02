import copy

import pandas as pd
import pytest

from cross_asset.backtest.returns import (
    AssetReturnSpec,
    period_asset_return,
    portfolio_period_return,
)
from cross_asset.backtest.walk_forward import portfolio_turnover
from cross_asset.sprint2.config import load_sprint2_config, validate_sprint2_config


def test_price_return_uses_full_holding_period_not_first_future_observation():
    frame = pd.DataFrame(
        [
            {"series_id": "A", "observation_date": "2026-01-02", "value": 100.0},
            {"series_id": "A", "observation_date": "2026-01-05", "value": 101.0},
            {"series_id": "A", "observation_date": "2026-01-09", "value": 110.0},
        ]
    )
    result = period_asset_return(
        frame,
        decision="2026-01-02",
        next_decision="2026-01-09",
        spec=AssetReturnSpec("A", "price"),
    )
    assert result == pytest.approx(0.10)


def test_yield_duration_proxy_does_not_treat_yield_as_price():
    frame = pd.DataFrame(
        [
            {"series_id": "CN10Y", "observation_date": "2026-01-02", "value": 3.0},
            {"series_id": "CN10Y", "observation_date": "2026-01-09", "value": 2.9},
        ]
    )
    result = period_asset_return(
        frame,
        decision="2026-01-02",
        next_decision="2026-01-09",
        spec=AssetReturnSpec(
            "CN10Y",
            "yield_duration_proxy",
            duration_years=8.0,
            yield_scale=100.0,
        ),
    )
    expected = -8.0 * (0.029 - 0.03) + 0.03 * 7 / 365.25
    assert result == pytest.approx(expected)
    assert result > 0


def test_missing_nonzero_asset_makes_portfolio_period_unavailable():
    frame = pd.DataFrame(
        [{"series_id": "A", "observation_date": "2026-01-02", "value": 100.0}]
    )
    result = portfolio_period_return(
        frame,
        {"A": 0.5, "B": 0.5},
        "2026-01-02",
        "2026-01-09",
        specs={"A": AssetReturnSpec("A"), "B": AssetReturnSpec("B")},
    )
    assert result is None


def test_cash_return_is_explicit_and_date_based():
    result = period_asset_return(
        pd.DataFrame(),
        decision="2026-01-02",
        next_decision="2026-01-09",
        spec=AssetReturnSpec(None, "cash", annual_rate=0.0365),
    )
    assert result == pytest.approx(0.0365 * 7 / 365.25)


def test_turnover_convention_is_explicit():
    current = {"A": 0.5, "B": 0.5}
    previous = {"A": 1.0, "B": 0.0}
    assert portfolio_turnover(current, previous) == pytest.approx(1.0)
    assert portfolio_turnover(
        current, previous, convention="one_way"
    ) == pytest.approx(0.5)
    with pytest.raises(ValueError, match="unsupported turnover convention"):
        portfolio_turnover(current, previous, convention="unknown")


def test_sprint2_return_model_and_turnover_are_frozen():
    raw = load_sprint2_config()
    protocol, _ = validate_sprint2_config(raw)
    assert protocol.turnover_convention == "two_sided_notional"
    assert protocol.charge_initial_trade is False
    assert protocol.signal_model_version == "full_model_v0.2"
    assert protocol.return_model["CN_EQ"]["series_id"] == "CN_EQ_LARGE"
    assert protocol.return_model["CN_BOND"]["kind"] == "yield_duration_proxy"

    changed = copy.deepcopy(raw)
    changed["protocol"]["return_model"]["CN_BOND"]["duration_years"] = 7.5
    with pytest.raises(ValueError, match="return_model_is_frozen"):
        validate_sprint2_config(changed)

    changed = copy.deepcopy(raw)
    changed["protocol"]["turnover_convention"] = "one_way"
    with pytest.raises(ValueError, match="turnover_convention_is_frozen"):
        validate_sprint2_config(changed)


def test_full_model_freezes_when_critical_signal_is_missing():
    from cross_asset.backtest.replay import FullModelStrategy

    frame = pd.DataFrame(
        [
            {
                "series_id": "OTHER",
                "observation_date": "2026-01-02",
                "available_at": "2026-01-02",
                "value": 100.0,
            }
        ]
    )
    strategy = FullModelStrategy(
        ["CN_EQ", "CASH"],
        strategic_weights={"CN_EQ": 0.5, "CASH": 0.5},
        asset_series_map={"CN_EQ": "CN_EQ_LARGE", "CASH": None},
    )
    weights = strategy(frame, pd.Timestamp("2026-01-02"))
    assert strategy.last_decision["allocation"].status == "FROZEN"
    assert strategy.last_decision["missing_signal_assets"] == ["CN_EQ"]
    assert weights == {"CN_EQ": 0.5, "CASH": 0.5}


def test_full_model_uses_yield_return_index_for_bond_signal():
    from cross_asset.backtest.replay import FullModelStrategy

    rows = []
    for i in range(22):
        day = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        rows.append(
            {
                "series_id": "CN10Y",
                "observation_date": day,
                "available_at": day,
                "value": 3.0 - i * 0.005,
            }
        )
    strategy = FullModelStrategy(
        ["CN_BOND", "CASH"],
        strategic_weights={"CN_BOND": 0.5, "CASH": 0.5},
        asset_series_map={"CN_BOND": "CN10Y", "CASH": None},
        return_specs={
            "CN_BOND": AssetReturnSpec(
                "CN10Y",
                "yield_duration_proxy",
                duration_years=8.0,
                yield_scale=100.0,
            ),
            "CASH": AssetReturnSpec(None, "cash"),
        },
    )
    strategy(pd.DataFrame(rows), pd.Timestamp("2026-01-22"))
    assert strategy.last_decision["allocation"].status == "ACTIVE"
    assert strategy.last_decision["asset_scores"]["CN_BOND"].score > 0



def test_realized_return_ignores_revision_not_available_by_next_decision():
    frame = pd.DataFrame(
        [
            {
                "series_id": "A",
                "observation_date": "2026-01-02",
                "available_at": "2026-01-02T00:00:00Z",
                "value": 100.0,
            },
            {
                "series_id": "A",
                "observation_date": "2026-01-09",
                "available_at": "2026-01-09T00:00:00Z",
                "value": 110.0,
            },
            {
                "series_id": "A",
                "observation_date": "2026-01-09",
                "available_at": "2026-01-12T00:00:00Z",
                "value": 120.0,
            },
        ]
    )
    result = period_asset_return(
        frame,
        decision="2026-01-02",
        next_decision="2026-01-09",
        spec=AssetReturnSpec("A", "price"),
    )
    assert result == pytest.approx(0.10)


def test_terminal_decision_has_no_realized_holding_period():
    frame = pd.DataFrame(
        [{"series_id": "A", "observation_date": "2026-01-02", "value": 100.0}]
    )
    assert (
        period_asset_return(
            frame,
            decision="2026-01-02",
            next_decision=None,
            spec=AssetReturnSpec("A", "price"),
        )
        is None
    )



def test_full_model_freeze_reuses_last_active_allocation():
    from cross_asset.backtest.replay import FullModelStrategy

    strategy = FullModelStrategy(
        ["A", "B", "CASH"],
        strategic_weights={"A": 0.4, "B": 0.3, "CASH": 0.3},
        asset_series_map={"A": None, "B": None, "CASH": None},
        critical_assets=[],
    )
    components = {
        "A": {"trend": {"score": 2.0, "confidence": 1.0}},
        "B": {"trend": {"score": -2.0, "confidence": 1.0}},
        "CASH": {},
    }
    first = strategy(
        pd.DataFrame(columns=["series_id", "observation_date", "available_at", "value"]),
        pd.Timestamp("2026-01-02"),
        component_inputs=components,
    )
    assert strategy.last_decision["allocation"].status == "ACTIVE"
    assert first != {"A": 0.4, "B": 0.3, "CASH": 0.3}

    frozen = strategy(
        pd.DataFrame(columns=["series_id", "observation_date", "available_at", "value"]),
        pd.Timestamp("2026-01-09"),
        health=False,
        component_inputs=components,
    )
    assert strategy.last_decision["allocation"].status == "FROZEN"
    assert frozen == pytest.approx(first)


def test_full_model_does_not_invent_unavailable_components():
    from cross_asset.backtest.replay import FullModelStrategy

    strategy = FullModelStrategy(
        ["A"],
        strategic_weights={"A": 1.0},
        asset_series_map={"A": None},
        critical_assets=[],
        allocation_config={"constraints": {"max_weight": 1.0}},
    )
    strategy(
        pd.DataFrame(columns=["series_id", "observation_date", "available_at", "value"]),
        pd.Timestamp("2026-01-02"),
        component_inputs={"A": {"trend": {"score": 0.5, "confidence": 1.0}}},
    )
    score = strategy.last_decision["asset_scores"]["A"]
    assert score.contributions["trend"] is not None
    for name in ("macro", "valuation", "carry", "risk", "structure"):
        assert score.contributions[name] is None
