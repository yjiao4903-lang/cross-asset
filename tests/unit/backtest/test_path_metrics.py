import pandas as pd
import pytest

from cross_asset.backtest.metrics import performance_metrics
from cross_asset.backtest.path_metrics import (
    max_drawdown_from_returns,
    nav_path_from_returns,
)
from cross_asset.research.evaluation import paired_oos_metrics


def test_nav_path_starts_at_one_and_first_loss_counts_as_drawdown():
    returns = pd.Series([-0.20, 0.10])

    nav = nav_path_from_returns(returns)
    assert nav.tolist() == pytest.approx([1.0, 0.80, 0.88])
    assert max_drawdown_from_returns(returns) == pytest.approx(-0.20)

    backtest = performance_metrics(returns)
    research = paired_oos_metrics(returns, pd.Series([0.0, 0.0]))
    assert backtest["max_drawdown"] == pytest.approx(-0.20)
    assert research["model_max_drawdown"] == pytest.approx(-0.20)
    assert research["benchmark_max_drawdown"] == pytest.approx(0.0)


def test_consecutive_losses_compound_from_initial_nav():
    returns = pd.Series([-0.10, -0.10])
    assert max_drawdown_from_returns(returns) == pytest.approx(-0.19)
    assert performance_metrics(returns)["max_drawdown"] == pytest.approx(-0.19)


def test_partial_recovery_does_not_erase_prior_trough():
    returns = pd.Series([-0.20, 0.10, 0.05])
    assert nav_path_from_returns(returns).tolist() == pytest.approx(
        [1.0, 0.80, 0.88, 0.924]
    )
    assert max_drawdown_from_returns(returns) == pytest.approx(-0.20)
    assert performance_metrics(returns)["max_drawdown"] == pytest.approx(-0.20)


def test_empty_or_all_missing_returns_have_no_drawdown():
    empty = pd.Series(dtype=float)
    missing = pd.Series([float("nan"), float("nan")])

    assert max_drawdown_from_returns(empty) is None
    assert max_drawdown_from_returns(missing) is None
    assert performance_metrics(empty)["max_drawdown"] is None
    assert performance_metrics(missing)["max_drawdown"] is None

    paired = paired_oos_metrics(missing, missing)
    assert paired["observations"] == 0
    assert paired["model_max_drawdown"] is None
    assert paired["benchmark_max_drawdown"] is None
