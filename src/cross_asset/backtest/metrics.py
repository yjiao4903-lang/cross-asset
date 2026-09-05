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
    *,
    asset_returns=None,
    charge_initial_trade=False,
):
    """Return gross/net metrics and an auditable turnover/cost ledger.

    Supplying asset-level holding returns enables drift-aware rebalancing cost.
    Without them the ledger retains the legacy target-to-target basis and labels
    that fallback explicitly; callers must not describe it as drift-aware.
    """

    gross = performance_metrics(
        gross_returns,
        allocations,
        periods_per_year,
        turnover_convention,
    )
    ledger = build_turnover_cost_ledger(
        gross_returns,
        allocations,
        asset_returns=asset_returns,
        cost_bps=cost_bps,
        turnover_convention=turnover_convention,
        charge_initial_trade=charge_initial_trade,
    )
    net_returns = ledger["net_return"]
    cost_complete = not bool(ledger["cost"].isna().any())
    total_cost = float(ledger["cost"].sum()) if cost_complete else np.nan
    finite_turnover = ledger.loc[ledger["turnover"].notna(), "turnover"]
    average_turnover = float(finite_turnover.mean()) if len(finite_turnover) else np.nan
    drift_aware = bool(asset_returns is not None)

    gross["Cost"] = total_cost
    gross["cost"] = total_cost
    gross["turnover"] = average_turnover
    gross["turnover_basis"] = (
        "drifted_pretrade_holdings" if drift_aware else "target_weights_legacy_fallback"
    )
    gross["drift_aware_turnover"] = drift_aware

    net = performance_metrics(
        net_returns,
        allocations,
        periods_per_year,
        turnover_convention,
    )
    net["Cost"] = total_cost
    net["cost"] = total_cost
    net["turnover"] = average_turnover
    net["turnover_basis"] = gross["turnover_basis"]
    net["drift_aware_turnover"] = drift_aware
    return {
        "gross": gross,
        "net": net,
        "cost_bps": cost_bps,
        "cost_complete": cost_complete,
        "drift_aware_turnover": drift_aware,
        "turnover_basis": gross["turnover_basis"],
        "turnover_convention": turnover_convention,
        "charge_initial_trade": bool(charge_initial_trade),
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
