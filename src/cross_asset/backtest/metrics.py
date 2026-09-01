import numpy as np


def performance_metrics(returns, allocations=None, periods_per_year=52):
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
    dd = wealth / wealth.cummax() - 1
    turnover = (
        float(allocations.diff().abs().sum(axis=1).mean())
        if allocations is not None and len(allocations) > 1
        else 0.0
    )
    return {
        "CAGR": cagr,
        "annualized_vol": vol,
        "Sharpe": sharpe,
        "max_drawdown": float(dd.min()) if len(dd) else None,
        "turnover": turnover,
        "average_allocation": allocations.mean().to_dict()
        if allocations is not None and len(allocations)
        else {},
    }


def compare_costs(gross_returns, allocations=None, cost_bps=0, periods_per_year=52):
    """Return gross/net metrics; cost is deliberately a research placeholder."""
    gross = performance_metrics(gross_returns, allocations, periods_per_year)
    if allocations is None or len(allocations) < 2:
        net_returns = gross_returns.copy()
    else:
        turnover = allocations.diff().abs().sum(axis=1).fillna(0)
        net_returns = gross_returns - turnover * float(cost_bps) / 10000
    return {
        "gross": gross,
        "net": performance_metrics(net_returns, allocations, periods_per_year),
        "cost_bps": cost_bps,
    }
