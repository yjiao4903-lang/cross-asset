from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from cross_asset.features.drawdown import drawdown_features
from cross_asset.features.normalization import latest_causal_zscore
from cross_asset.features.trend import (
    DEFAULT_TREND_PERIODS,
    multi_horizon_trend_signal,
    trend_features,
)
from cross_asset.features.volatility import volatility_features


@dataclass
class MarketState:
    as_of: Any
    model_version: str = "market_v0.2"
    assets: dict[str, dict[str, Any]] = field(default_factory=dict)
    unavailable: list[str] = field(default_factory=list)


class MarketEngine:
    """Deterministic market-state engine for PIT-clipped return-index histories."""

    def __init__(
        self,
        min_history: int = 21,
        model_version: str = "market_v0.2",
        *,
        trend_periods: dict[str, int] | None = None,
        trend_weights: dict[str, float] | None = None,
        risk_min_history: int = 60,
        risk_window: int | None = 252,
    ):
        self.min_history = int(min_history)
        self.model_version = model_version
        self.trend_periods = trend_periods or dict(DEFAULT_TREND_PERIODS)
        self.trend_weights = trend_weights
        self.risk_min_history = int(risk_min_history)
        self.risk_window = risk_window

    def build(self, prices: dict[str, pd.Series], *, as_of=None) -> MarketState:
        assets = {}
        unavailable = []
        for asset, series in prices.items():
            s = pd.Series(series, copy=True, dtype=float).dropna()
            if not s.index.is_monotonic_increasing:
                s = s.sort_index()
            if len(s) < self.min_history:
                unavailable.append(asset)
                continue

            trend = trend_features(s, self.trend_periods)
            vol = volatility_features(s)
            dd = drawdown_features(s)
            trend_signal = multi_horizon_trend_signal(
                s,
                periods=self.trend_periods,
                weights=self.trend_weights,
            )
            risk_z = (
                latest_causal_zscore(
                    vol["vol_20d"],
                    min_history=self.risk_min_history,
                    window=self.risk_window,
                    clip=2.0,
                )
                if "vol_20d" in vol
                else None
            )
            risk_signal = {
                "score": None if risk_z is None else -float(risk_z),
                "confidence": 0.0 if risk_z is None else 1.0,
                "raw_value": None
                if "vol_20d" not in vol or pd.isna(vol["vol_20d"].iloc[-1])
                else float(vol["vol_20d"].iloc[-1]),
                "reason": None if risk_z is not None else "insufficient_volatility_history",
                "model_version": "risk_signal_v0.2",
            }
            assets[asset] = {
                "as_of": as_of or s.index[-1],
                "data_cutoff": s.index[-1],
                "trend": trend.iloc[-1].dropna().to_dict(),
                "volatility": vol.iloc[-1].dropna().to_dict(),
                "drawdown": dd.iloc[-1].dropna().to_dict(),
                "signals": {
                    "trend": asdict(trend_signal),
                    "risk": risk_signal,
                },
                "available": True,
            }
        return MarketState(
            as_of=as_of,
            model_version=self.model_version,
            assets=assets,
            unavailable=unavailable,
        )
