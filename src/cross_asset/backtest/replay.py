import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from cross_asset.backtest.returns import AssetReturnSpec, portfolio_period_return
from cross_asset.engines.allocation import allocate
from cross_asset.engines.asset_score import score_asset
from cross_asset.engines.macro import build_macro_state
from cross_asset.engines.market import MarketEngine
from cross_asset.engines.style import StyleEngine


@dataclass
class ReplayResult:
    returns: pd.Series
    allocations: pd.DataFrame
    decision_dates: list
    model_version: str = "market_v0.1"
    assumptions: list[str] = field(
        default_factory=lambda: [
            "weekly deterministic calendar",
            "next-period effective",
            "cost is research placeholder",
        ]
    )
    config_hash: str = ""
    data_cutoff: object = None
    fixture: bool = True
    scores: pd.DataFrame = field(default_factory=pd.DataFrame)
    decisions: list[dict] = field(default_factory=list)
    benchmark_metadata: dict = field(default_factory=dict)

    def write_artifacts(self, output_dir="artifacts/backtests"):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        _write_parquet(self.returns.to_frame(), out / "returns.parquet")
        _write_parquet(self.allocations, out / "allocations.parquet")
        _write_parquet(
            self.scores
            if not self.scores.empty
            else pd.DataFrame({"score": [None] * len(self.returns)}, index=self.returns.index),
            out / "scores.parquet",
        )
        (out / "decisions.json").write_text(
            json.dumps(self.decisions, default=str, indent=2), encoding="utf-8"
        )
        (out / "summary.md").write_text(
            "# Backtest Artifacts\n\n"
            "Offline fixture artifacts; not investment performance.\n\n"
            f"- model_version: {self.model_version}\n- config_hash: {self.config_hash}\n"
            f"- data_cutoff: {self.data_cutoff}\n- fixture: {self.fixture}\n"
            f"- assumptions: {', '.join(self.assumptions)}\n",
            encoding="utf-8",
        )
        return out


class HistoricalReplay:
    def __init__(
        self,
        observations,
        strategy,
        *,
        frequency="W-FRI",
        cost_bps=0,
        model_version="market_v0.1",
        config=None,
        fixture=True,
    ):
        self.observations = observations.copy()
        self.strategy = strategy
        self.frequency = frequency
        self.cost_bps = cost_bps
        self.model_version = model_version
        self.fixture = fixture
        self.config_hash = hash_config(
            config
            or {"frequency": frequency, "cost_bps": cost_bps, "model_version": model_version}
        )

    def run(self, start=None, end=None):
        obs = self.observations.assign(
            _available=pd.to_datetime(self.observations["available_at"])
        )
        dates = pd.date_range(
            start or obs._available.min(), end or obs._available.max(), freq=self.frequency
        )
        alloc = []
        score_rows = []
        decision_records = []
        rets = []
        prev = None
        benchmark_metadata = {}
        for decision in dates:
            info = obs[obs._available <= decision]
            raw_allocation = self.strategy(info, decision)
            benchmark_metadata = dict(getattr(raw_allocation, "attrs", {}))
            a = pd.Series(raw_allocation, dtype=float)
            a = a / a.sum() if a.sum() else a
            next_decision = dates[dates > decision][0] if any(dates > decision) else None
            if hasattr(self.strategy, "realized_return"):
                realized = self.strategy.realized_return(obs, a, decision, next_decision)
                ret = float("nan") if realized is None else float(realized)
            elif hasattr(self.strategy, "next_return"):
                ret = float(
                    self.strategy.next_return(obs[obs._available <= decision], a, decision)
                )
            else:
                ret = 0.0
            turnover = float((a - prev).abs().sum()) if prev is not None else 0.0
            rets.append(ret - turnover * self.cost_bps / 10000)
            alloc.append(a)
            score_rows.append(
                {
                    k: getattr(v, "score", v)
                    for k, v in getattr(self.strategy, "last_scores", {}).items()
                }
            )
            if getattr(self.strategy, "last_decision", None):
                d = self.strategy.last_decision
                decision_records.append(
                    {
                        "decision": str(decision),
                        "allocation": dict(a),
                        "scores": {
                            k: getattr(v, "score", None)
                            for k, v in d["asset_scores"].items()
                        },
                        "attribution": d["attribution"],
                        "model_versions": d["model_versions"],
                        "data_cutoff": str(d["data_cutoff"]),
                        "missing_signal_assets": d.get("missing_signal_assets", []),
                    }
                )
            prev = a
        return ReplayResult(
            pd.Series(rets, index=dates, name="return"),
            pd.DataFrame(alloc, index=dates).fillna(0),
            list(dates),
            self.model_version,
            config_hash=self.config_hash,
            data_cutoff=obs._available.max(),
            fixture=self.fixture,
            scores=pd.DataFrame(score_rows, index=dates),
            decisions=decision_records,
            benchmark_metadata=benchmark_metadata,
        )


class FullModelStrategy:
    """PIT-only decision strategy that executes the complete offline model chain."""

    def __init__(
        self,
        assets,
        *,
        strategic_weights=None,
        macro_config=None,
        style_definitions=None,
        asset_series_map=None,
        return_specs=None,
        signal_directions=None,
        critical_assets=None,
    ):
        self.assets = list(assets)
        self.strategic_weights = strategic_weights or {
            asset: 1 / len(self.assets) for asset in self.assets
        }
        default_map = {
            asset: (None if asset == "CASH" else asset) for asset in self.assets
        }
        default_map.update(asset_series_map or {})
        self.asset_series_map = default_map
        self.return_specs = {
            asset: (
                AssetReturnSpec(None, kind="cash")
                if self.asset_series_map.get(asset) is None
                else AssetReturnSpec(self.asset_series_map[asset], kind="price")
            )
            for asset in self.assets
        }
        self.return_specs.update(return_specs or {})
        self.signal_directions = {asset: 1.0 for asset in self.assets}
        self.signal_directions.update(signal_directions or {})
        self.critical_assets = set(
            critical_assets
            or [
                asset
                for asset in self.assets
                if self.asset_series_map.get(asset) is not None
            ]
        )
        self.macro_config = macro_config or {"series": {}, "dimensions": {}}
        self.style_engine = StyleEngine(style_definitions or {})
        self.market_engine = MarketEngine(min_history=1)
        self.last_decision = None

    def __call__(self, info, decision, *, health=True):
        prices = _price_histories(info, self.assets, self.asset_series_map)
        market = self.market_engine.build(prices, as_of=decision)
        macro_rows = info.to_dict("records")
        for row in macro_rows:
            available = pd.Timestamp(row["available_at"])
            row["available_at"] = (
                available.tz_localize("UTC")
                if available.tz is None
                else available.tz_convert("UTC")
            )
        macro = build_macro_state(macro_rows, decision, self.macro_config)
        style = self.style_engine.build({}, data_cutoff=decision)
        scores = {}
        missing_signal_assets = []
        for asset in self.assets:
            market_asset = market.assets.get(asset, {})
            trend = market_asset.get("trend", {}).get("ret_1m")
            if trend is not None and pd.isna(trend):
                trend = None
            if trend is not None:
                trend = float(trend) * float(self.signal_directions.get(asset, 1.0))
            if asset in self.critical_assets and trend is None:
                missing_signal_assets.append(asset)
            scores[asset] = score_asset(asset, {"trend": trend}, data_cutoff=decision)

        upstream_healthy = not (
            health is False
            or str(health).upper() in {"UNHEALTHY", "FAILED", "STALE"}
        )
        effective_health = upstream_healthy and not missing_signal_assets
        allocation = allocate(
            scores,
            self.strategic_weights,
            as_of=decision,
            data_cutoff=decision,
            health=effective_health,
        )
        self.last_decision = {
            "market_state": market,
            "macro_state": macro,
            "style_state": style,
            "asset_scores": scores,
            "allocation": allocation,
            "attribution": allocation.attribution,
            "model_versions": {
                "market": market.model_version,
                "macro": getattr(macro, "model_version", "macro_v0.1"),
                "style": self.style_engine.model_version,
                "asset": "asset_score_v0.1",
                "allocation": allocation.model_version,
            },
            "data_cutoff": decision,
            "missing_signal_assets": missing_signal_assets,
        }
        self.last_scores = scores
        return allocation.weights

    def realized_return(self, all_observations, allocation, decision, next_decision):
        return portfolio_period_return(
            all_observations,
            allocation,
            decision,
            next_decision,
            specs=self.return_specs,
        )


def realized_return(
    observations, allocation, decision, next_decision, return_specs=None
):
    """Compatibility helper using explicit full holding-period boundaries."""

    return portfolio_period_return(
        observations,
        allocation,
        decision,
        next_decision,
        specs=return_specs,
    )


def _price_histories(info, assets, asset_series_map=None):
    if "series_id" not in info or "value" not in info:
        return {asset: pd.Series(dtype=float) for asset in assets}
    mapping = {
        asset: (asset_series_map or {}).get(
            asset, None if asset == "CASH" else asset
        )
        for asset in assets
    }
    series_ids = {sid for sid in mapping.values() if sid is not None}
    rows = info[info["series_id"].isin(series_ids)].copy()
    rows["_date"] = pd.to_datetime(rows["observation_date"])
    return {
        asset: (
            pd.Series(dtype=float)
            if sid is None
            else rows[rows["series_id"] == sid]
            .sort_values("_date")
            .set_index("_date")["value"]
        )
        for asset, sid in mapping.items()
    }


def hash_config(config):
    payload = json.dumps(
        config,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _write_parquet(frame, path):
    """Write parquet through DuckDB so pyarrow is not required."""
    import duckdb

    con = duckdb.connect()
    con.register("_frame", frame.reset_index(names="date"))
    con.execute("COPY _frame TO ? (FORMAT PARQUET)", [str(path)])
    con.close()
