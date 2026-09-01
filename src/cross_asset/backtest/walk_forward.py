"""Leakage-safe walk-forward window and transaction ledgers.

This module deliberately does not infer a calendar.  Callers must provide the
ordered decision dates that are valid for their data and trading venue.
"""

from collections.abc import Iterable
from dataclasses import asdict, dataclass

import pandas as pd

SUPPORTED_COST_BPS = (0, 5, 10, 20, 30)


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
    """Build ordered train/test windows from explicit decision dates.

    The first test block starts after ``train_size`` observations.  When
    omitted, expanding starts at the second date (one date of history), while
    rolling requires ``rolling_window``.  No dates are generated or filled.
    """
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
    """Compatibility alias for :func:`build_window_manifest`."""
    return build_window_manifest(decision_dates, **kwargs)


# Descriptive aliases kept intentionally small so callers can use the name
# used by their protocol without creating a second implementation.
generate_walk_forward_manifest = build_window_manifest
make_walk_forward_manifest = build_window_manifest


def build_turnover_cost_ledger(
    returns, allocations=None, *, cost_bps: float = 10, base_bps: int = 10
) -> pd.DataFrame:
    """Return one row per period with turnover, cost and gross/net returns."""
    if not isinstance(cost_bps, (int, float)) or cost_bps < 0:
        raise ValueError("cost_bps must be a non-negative number")
    gross = pd.Series(returns, dtype=float).copy()
    if allocations is None:
        turnover = pd.Series(0.0, index=gross.index)
    else:
        a = pd.DataFrame(
            allocations, index=allocations.index if hasattr(allocations, "index") else None
        ).fillna(0.0)
        if len(a) != len(gross):
            raise ValueError("returns and allocations must have equal length")
        turnover = a.diff().abs().sum(axis=1).fillna(0.0)
        turnover.index = gross.index
    cost = turnover * float(cost_bps) / 10000.0
    return pd.DataFrame(
        {
            "gross_return": gross,
            "turnover": turnover,
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


def cost_sensitivity_ledger(returns, allocations=None, *, costs=SUPPORTED_COST_BPS, base_bps=10):
    """Build ledgers for the fixed research sensitivity grid.

    ``base_bps`` is metadata identifying the reference case; it does not alter
    the supplied cost grid or tune allocations.
    """
    costs = tuple(costs)
    unknown = [c for c in costs if c not in SUPPORTED_COST_BPS]
    if unknown:
        raise ValueError(f"unsupported sensitivity costs: {unknown}")
    if base_bps not in costs:
        raise ValueError("base_bps must be included in costs")
    return {
        c: build_turnover_cost_ledger(returns, allocations, cost_bps=c, base_bps=base_bps)
        for c in costs
    }
