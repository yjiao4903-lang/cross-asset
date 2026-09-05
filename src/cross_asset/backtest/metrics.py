import numpy as np

from .path_metrics import max_drawdown_from_returns
from .walk_forward import build_turnover_cost_ledger, portfolio_turnover


def performance_metrics(
    returns,
    allocations=None,
    periods_per_year=52,
    turnover_convention="two_sided_notional",
):
    r = returns.dropna().astype(float)
    wealth = (1 + r).cumprod()
    years = len(r) / periods_per_year
    cagr = float(wealth.iloc[-1] ** (1 / years) - 1) if len(r) and years else None
    vol = float(r.std(ddof=1) * np.sqrt(periods_per_year)) if len(r) > 1 else None
    sharpe = (
        float(r.mean() / r.std(ddof=1) * np.sqrt(periods_per_year))
        if len(r) > 1 and r.std(ddof=1)
        else None
    )
    max_drawdown = max_drawdown_from_returns(r)
    month_periods = max(1, round(periods_per_year / 12))
    worst_1m = (
        float(
            (
                (1 + r).rolling(month_periods, min_periods=month_periods).apply(np.prod, raw=True)
                - 1
            ).min()
        )
        if len(r) >= month_periods
        else None
    )
    recovery = _recovery_periods(wealth)
    turnover = 0.0
    if allocations is not None and len(allocations) > 1:
        values = [
            portfolio_turnover(
                allocations.iloc[i],
                allocations.iloc[i - 1],
                convention=turnover_convention,
            )
            for i in range(1, len(allocations))
        ]
        turnover = float(np.mean(values)) if values else 0.0
    return {
        "CAGR": cagr,
        "annualized_vol": vol,
        "Sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "turnover": turnover,
        "turnover_convention": turnover_convention,
        "Worst1M": worst_1m,
        "worst_1m": worst_1m,
        "Recovery": recovery,
        "recovery_periods": recovery,
        "Cost": 0.0,
        "cost": 0.0,
        "average_allocation": allocations.mean().to_dict()
        if allocations is not None and len(allocations)
        else {},
    }


def compare_costs(
    gross_returns,
    allocations=None,
    cost_bps=0,
    periods_per_year=52,
    turnover_convention="two_sided_notional",
):
    """Return gross/net metrics and a reproducible turnover/cost ledger."""

    gross = performance_metrics(
        gross_returns,
        allocations,
        periods_per_year,
        turnover_convention,
    )
    ledger = build_turnover_cost_ledger(
        gross_returns,
        allocations,
        cost_bps=cost_bps,
        turnover_convention=turnover_convention,
    )
    net_returns = ledger["net_return"]
    gross["Cost"] = float(ledger["cost"].sum())
    gross["cost"] = gross["Cost"]
    net = performance_metrics(
        net_returns,
        allocations,
        periods_per_year,
        turnover_convention,
    )
    net["Cost"] = float(ledger["cost"].sum())
    net["cost"] = net["Cost"]
    return {
        "gross": gross,
        "net": net,
        "cost_bps": cost_bps,
        "turnover_convention": turnover_convention,
        "ledger": ledger,
    }


def _recovery_periods(wealth):
    """Maximum observations needed to recover a prior running high-water mark."""

    if len(wealth) == 0:
        return None
    peak = -np.inf
    peak_at = 0
    durations = []
    for i, value in enumerate(wealth):
        value = float(value)
        if value >= peak:
            peak, peak_at = value, i
        else:
            recovered = next(
                (j for j in range(i + 1, len(wealth)) if wealth.iloc[j] >= peak),
                None,
            )
            durations.append(
                (recovered - peak_at)
                if recovered is not None
                else (len(wealth) - 1 - peak_at)
            )
    return int(max(durations, default=0))
