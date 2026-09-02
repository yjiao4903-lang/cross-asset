"""Leakage-safe walk-forward window and transaction ledgers.

This module deliberately does not infer a calendar. Callers must provide the
ordered decision dates that are valid for their data and trading venue.
"""

from collections.abc import Iterable
from dataclasses import asdict, dataclass

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


build_research_window_manifest = build_calendar_window_manifest


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


def build_turnover_cost_ledger(
    returns,
    allocations=None,
    *,
    cost_bps: float = 10,
    base_bps: int = 10,
    turnover_convention: str = "two_sided_notional",
) -> pd.DataFrame:
    if not isinstance(cost_bps, (int, float)) or cost_bps < 0:
        raise ValueError("cost_bps must be a non-negative number")
    if turnover_convention not in SUPPORTED_TURNOVER_CONVENTIONS:
        raise ValueError(f"unsupported turnover convention: {turnover_convention}")
    gross = pd.Series(returns, dtype=float).copy()
    if allocations is None:
        turnover = pd.Series(0.0, index=gross.index)
    else:
        a = pd.DataFrame(
            allocations, index=allocations.index if hasattr(allocations, "index") else None
        ).fillna(0.0)
        if len(a) != len(gross):
            raise ValueError("returns and allocations must have equal length")
        multiplier = 1.0 if turnover_convention == "two_sided_notional" else 0.5
        turnover = a.diff().abs().sum(axis=1).fillna(0.0) * multiplier
        turnover.index = gross.index
    cost = turnover * float(cost_bps) / 10000.0
    return pd.DataFrame(
        {
            "gross_return": gross,
            "turnover": turnover,
            "turnover_convention": turnover_convention,
            "cost_bps": float(cost_bps),
            "cost": cost,
            "net_return": gross - cost,
            "cumulative_cost": cost.cumsum(),
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
    costs=SUPPORTED_COST_BPS,
    base_bps=10,
    turnover_convention="two_sided_notional",
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
            cost_bps=c,
            base_bps=base_bps,
            turnover_convention=turnover_convention,
        )
        for c in costs
    }
