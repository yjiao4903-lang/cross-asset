from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from cross_asset.features.drawdown import drawdown_features
from cross_asset.features.trend import trend_features
from cross_asset.features.volatility import volatility_features


@dataclass
class MarketState:
    as_of: Any
    model_version: str = "market_v0.1"
    assets: dict[str, dict[str, Any]] = field(default_factory=dict)
    unavailable: list[str] = field(default_factory=list)


class MarketEngine:
    """Deterministic aggregator; receives PIT-clipped price series only."""

    def __init__(self, min_history: int = 21, model_version: str = "market_v0.1"):
        self.min_history, self.model_version = min_history, model_version

    def build(self, prices: dict[str, pd.Series], *, as_of=None) -> MarketState:
        assets = {}
        unavailable = []
        for asset, series in prices.items():
            s = series.dropna().astype(float)
            if len(s) < self.min_history:
                unavailable.append(asset)
                continue
            trend = trend_features(s)
            vol = volatility_features(s)
            dd = drawdown_features(s)
            assets[asset] = {
                "as_of": as_of or s.index[-1],
                "data_cutoff": s.index[-1],
                "trend": trend.iloc[-1].dropna().to_dict(),
                "volatility": vol.iloc[-1].dropna().to_dict(),
                "drawdown": dd.iloc[-1].dropna().to_dict(),
                "available": True,
            }
        return MarketState(
            as_of=as_of, model_version=self.model_version, assets=assets, unavailable=unavailable
        )
