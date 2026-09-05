"""Leakage-safe walk-forward window and transaction ledgers.

This module deliberately does not infer a calendar. Callers must provide the
ordered decision dates that are valid for their data and trading venue.
"""

from collections.abc import Iterable
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

SUPPORTED_COST_BPS = (0, 5, 10, 20, 30)
SUPPORTED_TURNOVER_CONVENTIONS = ("two_sided_notional", "one_way")


@dataclass(frozen=True)
class WalkForwardWindow:
    fold: int
    train_start: object
    train_end: object
    test_start: object
    test_end: object
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    window_type: str = "expanding"

    def to_dict(self):
        return asdict(self)


def build_window_manifest(
    decision_dates: Iterable,
    *,
    train_size: int | None = None,
    test_size: int = 1,
    step: int | None = None,
    window_type: str = "expanding",
    rolling_window: int | None = None,
) -> list[dict]:
    dates = list(decision_dates)
    if not dates:
        return []
    if any(pd.isna(d) for d in dates):
        raise ValueError("decision_dates cannot contain missing values")
    if any(dates[i] >= dates[i + 1] for i in range(len(dates) - 1)):
        raise ValueError("decision_dates must be strictly increasing")
    kind = str(window_type).lower()
    if kind not in {"expanding", "rolling"}:
        raise ValueError("window_type must be 'expanding' or 'rolling'")
    if test_size < 1 or (step is not None and step < 1):
        raise ValueError("test_size and step must be positive")
    if kind == "rolling":
        width = rolling_window if rolling_window is not None else train_size
        if width is None:
            raise ValueError("rolling_window is required for rolling windows")
        train_size = width
    elif train_size is None:
        train_size = 1
    if train_size < 1:
        raise ValueError("train_size must be positive")
    stride = step or test_size
    out = []
    fold = 0
    test_start = train_size
    while test_start < len(dates):
        test_end = min(test_start + test_size, len(dates))
        train_start = 0 if kind == "expanding" else test_start - train_size
        window = WalkForwardWindow(
            fold=fold,
            train_start=dates[train_start],
            train_end=dates[test_start - 1],
            test_start=dates[test_start],
            test_end=dates[test_end - 1],
            train_indices=tuple(range(train_start, test_start)),
            test_indices=tuple(range(test_start, test_end)),
            window_type=kind,
        )
        out.append(window.to_dict())
        fold += 1
        test_start += stride
    return out


def walk_forward_manifest(decision_dates, **kwargs):
    return build_window_manifest(decision_dates, **kwargs)


generate_walk_forward_manifest = build_window_manifest
make_walk_forward_manifest = build_window_manifest


def build_calendar_window_manifest(
    decision_dates: Iterable,
    *,
    train_min_years: int = 5,
    test_window_months: int = 12,
    step_months: int = 3,
    window_type: str = "expanding",
    rolling_years: int | None = None,
) -> list[dict]:
    """Build time-based walk-forward folds from explicit valid decision dates.

    Calendar offsets define research horizons while the returned indices always
    point to dates supplied by the caller; no synthetic trading dates are
    created. Test windows may overlap when the step is shorter than the test
    horizon.
    """

    dates = pd.DatetimeIndex(list(decision_dates))
    if len(dates) == 0:
        return []
    if dates.isna().any():
        raise ValueError("decision_dates cannot contain missing values")
    if any(dates[index] >= dates[index + 1] for index in range(len(dates) - 1)):
        raise ValueError("decision_dates must be strictly increasing")
    if train_min_years < 1 or test_window_months < 1 or step_months < 1:
        raise ValueError("calendar window lengths must be positive")

    kind = str(window_type).lower()
    if kind not in {"expanding", "rolling"}:
        raise ValueError("window_type must be 'expanding' or 'rolling'")
    if kind == "rolling" and (rolling_years is None or rolling_years < 1):
        raise ValueError("rolling_years is required for rolling calendar windows")

    first_test_target = dates[0] + pd.DateOffset(years=train_min_years)
    test_start_index = int(dates.searchsorted(first_test_target, side="left"))
    folds = []
    fold = 0
    while test_start_index < len(dates):
        test_start = dates[test_start_index]
        test_end_target = test_start + pd.DateOffset(months=test_window_months)
        test_end_index = int(dates.searchsorted(test_end_target, side="left"))
        test_end_index = min(max(test_end_index, test_start_index + 1), len(dates))

        if kind == "expanding":
            train_start_index = 0
        else:
            train_target = test_start - pd.DateOffset(years=int(rolling_years))
            train_start_index = int(dates.searchsorted(train_target, side="left"))

        train_indices = tuple(range(train_start_index, test_start_index))
        test_indices = tuple(range(test_start_index, test_end_index))
        if not train_indices:
            raise ValueError("calendar fold has no training observations")
        if not test_indices:
            break

        folds.append(
            WalkForwardWindow(
                fold=fold,
                train_start=dates[train_indices[0]],
                train_end=dates[train_indices[-1]],
                test_start=dates[test_indices[0]],
                test_end=dates[test_indices[-1]],
                train_indices=train_indices,
                test_indices=test_indices,
                window_type=kind,
            ).to_dict()
        )
        fold += 1

        next_target = test_start + pd.DateOffset(months=step_months)
        next_index = int(dates.searchsorted(next_target, side="left"))
        test_start_index = max(test_start_index + 1, next_index)

    return folds


def portfolio_turnover(current, previous, *, convention="two_sided_notional") -> float:
    """Compute turnover under an explicit and reproducible convention."""

    if convention not in SUPPORTED_TURNOVER_CONVENTIONS:
        raise ValueError(f"unsupported turnover convention: {convention}")
    current = pd.Series(current, dtype=float)
    previous = pd.Series(previous, dtype=float)
    keys = current.index.union(previous.index)
    gross_notional = float(
        (current.reindex(keys, fill_value=0.0) - previous.reindex(keys, fill_value=0.0))
        .abs()
        .sum()
    )
    return gross_notional if convention == "two_sided_notional" else gross_notional / 2.0


def drifted_pretrade_weights(previous_target, asset_returns) -> dict[str, float] | None:
    """Advance prior target weights through realized asset returns.

    Every non-zero prior holding needs a finite holding-period return. Missing
    or economically invalid returns fail closed because the next decision's
    actual pre-trade holdings cannot be reconstructed safely.
    """

    target = pd.Series(previous_target, dtype=float)
    returns = pd.Series(asset_returns, dtype=float)
    if target.empty:
        return {}
    grown: dict[str, float] = {}
    for asset, weight in target.items():
        weight = float(weight)
        if abs(weight) <= 1e-15:
            grown[str(asset)] = 0.0
            continue
        if asset not in returns.index:
            return None
        value = float(returns.loc[asset])
        if not np.isfinite(value) or 1.0 + value < 0.0:
            return None
        grown[str(asset)] = weight * (1.0 + value)
    total = float(sum(grown.values()))
    if not np.isfinite(total) or total <= 0.0:
        return None
    return {asset: value / total for asset, value in grown.items()}


def rebalance_turnover(
    current_target,
    previous_target,
    previous_asset_returns,
    *,
    convention="two_sided_notional",
):
    """Return (pre-trade holdings, turnover) using drift-aware accounting."""

    pretrade = drifted_pretrade_weights(previous_target, previous_asset_returns)
    if pretrade is None:
        return None, None
    return pretrade, portfolio_turnover(
        current_target,
        pretrade,
        convention=convention,
    )


def build_turnover_cost_ledger(
    returns,
    allocations=None,
    *,
    asset_returns=None,
    cost_bps: float = 10,
    base_bps: int = 10,
    turnover_convention: str = "two_sided_notional",
    charge_initial_trade: bool = False,
) -> pd.DataFrame:
    """Build an auditable transaction-cost ledger.

    When ``asset_returns`` is supplied, turnover is computed from drifted
    pre-trade holdings. When it is omitted, the legacy target-to-target basis is
    preserved explicitly for backward-compatible non-formal callers and is
    labelled as such in ``turnover_basis``.
    """

    if not isinstance(cost_bps, (int, float)) or cost_bps < 0:
        raise ValueError("cost_bps must be a non-negative number")
    if turnover_convention not in SUPPORTED_TURNOVER_CONVENTIONS:
        raise ValueError(f"unsupported turnover convention: {turnover_convention}")
    gross = pd.Series(returns, dtype=float).copy()
    if allocations is None:
        turnover = pd.Series(0.0, index=gross.index)
        cost = turnover * float(cost_bps) / 10000.0
        return pd.DataFrame(
            {
                "gross_return": gross,
                "turnover": turnover,
                "turnover_basis": "no_allocations",
                "drift_aware": False,
                "pretrade_weights": [None] * len(gross),
                "turnover_convention": turnover_convention,
                "cost_bps": float(cost_bps),
                "cost": cost,
                "net_return": gross - cost,
                "cumulative_cost": cost.cumsum(),
                "base_bps": float(base_bps),
            },
            index=gross.index,
        )

    targets = pd.DataFrame(
        allocations,
        index=allocations.index if hasattr(allocations, "index") else None,
    ).fillna(0.0)
    if len(targets) != len(gross):
        raise ValueError("returns and allocations must have equal length")

    drift_frame = None
    if asset_returns is not None:
        drift_frame = pd.DataFrame(
            asset_returns,
            index=asset_returns.index if hasattr(asset_returns, "index") else None,
        )
        if len(drift_frame) != len(gross):
            raise ValueError("returns and asset_returns must have equal length")
        drift_frame.index = gross.index

    turnovers: list[float] = []
    costs: list[float] = []
    net_returns: list[float] = []
    bases: list[str] = []
    pretrades: list[dict | None] = []
    previous_target = None
    previous_asset_return = None

    for position, (_, current_target) in enumerate(targets.iterrows()):
        gross_return = float(gross.iloc[position]) if pd.notna(gross.iloc[position]) else np.nan
        terminal = position == len(targets) - 1 and pd.isna(gross.iloc[position])
        if terminal:
            pretrade = None
            turnover_value = 0.0
            basis = "terminal_no_trade"
        elif previous_target is None:
            pretrade = {}
            turnover_value = (
                portfolio_turnover(
                    current_target,
                    {},
                    convention=turnover_convention,
                )
                if charge_initial_trade
                else 0.0
            )
            basis = "initial_target_vs_cash" if charge_initial_trade else "initial_trade_not_charged"
        elif drift_frame is None:
            pretrade = dict(previous_target)
            turnover_value = portfolio_turnover(
                current_target,
                previous_target,
                convention=turnover_convention,
            )
            basis = "target_weights_legacy_fallback"
        else:
            pretrade, turnover_value = rebalance_turnover(
                current_target,
                previous_target,
                previous_asset_return,
                convention=turnover_convention,
            )
            basis = "drifted_pretrade_holdings" if turnover_value is not None else "drift_unavailable"

        if turnover_value is None:
            turnover_number = np.nan
            cost_value = np.nan
            net_value = np.nan
        else:
            turnover_number = float(turnover_value)
            cost_value = turnover_number * float(cost_bps) / 10000.0
            net_value = gross_return - cost_value if np.isfinite(gross_return) else np.nan

        turnovers.append(turnover_number)
        costs.append(cost_value)
        net_returns.append(net_value)
        bases.append(basis)
        pretrades.append(pretrade)
        previous_target = current_target.to_dict()
        previous_asset_return = (
            drift_frame.iloc[position].dropna().to_dict()
            if drift_frame is not None
            else None
        )

    cost_series = pd.Series(costs, index=gross.index, dtype=float)
    return pd.DataFrame(
        {
            "gross_return": gross,
            "turnover": pd.Series(turnovers, index=gross.index, dtype=float),
            "turnover_basis": bases,
            "drift_aware": drift_frame is not None,
            "pretrade_weights": pretrades,
            "turnover_convention": turnover_convention,
            "cost_bps": float(cost_bps),
            "cost": cost_series,
            "net_return": pd.Series(net_returns, index=gross.index, dtype=float),
            "cumulative_cost": cost_series.fillna(0.0).cumsum(),
            "base_bps": float(base_bps),
        },
        index=gross.index,
    )


def transaction_cost_ledger(returns, allocations=None, **kwargs):
    return build_turnover_cost_ledger(returns, allocations, **kwargs)


def cost_sensitivity_ledger(
    returns,
    allocations=None,
    *,
    asset_returns=None,
    costs=SUPPORTED_COST_BPS,
    base_bps=10,
    turnover_convention="two_sided_notional",
    charge_initial_trade=False,
):
    costs = tuple(costs)
    unknown = [c for c in costs if c not in SUPPORTED_COST_BPS]
    if unknown:
        raise ValueError(f"unsupported sensitivity costs: {unknown}")
    if base_bps not in costs:
        raise ValueError("base_bps must be included in costs")
    return {
        c: build_turnover_cost_ledger(
            returns,
            allocations,
            asset_returns=asset_returns,
            cost_bps=c,
            base_bps=base_bps,
            turnover_convention=turnover_convention,
            charge_initial_trade=charge_initial_trade,
        )
        for c in costs
    }
