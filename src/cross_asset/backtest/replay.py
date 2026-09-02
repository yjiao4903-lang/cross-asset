from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from cross_asset.backtest.returns import (
    AssetReturnSpec,
    portfolio_period_return,
    return_index_from_series,
)
from cross_asset.backtest.walk_forward import portfolio_turnover
from cross_asset.engines.allocation import allocate
from cross_asset.engines.asset_score import COMPONENT_WEIGHTS, score_asset
from cross_asset.engines.macro import build_macro_state
from cross_asset.engines.market import MarketEngine
from cross_asset.engines.style import StyleEngine


@dataclass
class ReplayResult:
    returns: pd.Series
    allocations: pd.DataFrame
    decision_dates: list
    model_version: str = "full_model_v0.2"
    assumptions: list[str] = field(
        default_factory=lambda: [
            "weekly deterministic calendar",
            "next-period effective",
            "terminal decision has no realized return",
            "initial allocation trade cost disabled unless explicitly requested",
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
        turnover_convention="two_sided_notional",
        charge_initial_trade=False,
        model_version="full_model_v0.2",
        config=None,
        fixture=True,
    ):
        self.observations = observations.copy()
        self.strategy = strategy
        self.frequency = frequency
        self.cost_bps = cost_bps
        self.turnover_convention = turnover_convention
        self.charge_initial_trade = bool(charge_initial_trade)
        self.model_version = model_version
        self.fixture = fixture
        self.config_hash = hash_config(
            config
            or {
                "frequency": frequency,
                "cost_bps": cost_bps,
                "turnover_convention": turnover_convention,
                "charge_initial_trade": self.charge_initial_trade,
                "model_version": model_version,
            }
        )

    def run(self, start=None, end=None):
        obs = self.observations.assign(
            _available=pd.to_datetime(self.observations["available_at"])
        )
        dates = pd.date_range(
            start or obs._available.min(),
            end or obs._available.max(),
            freq=self.frequency,
        )
        allocations = []
        score_rows = []
        decision_records = []
        returns = []
        previous = None
        benchmark_metadata = {}
        for index, decision in enumerate(dates):
            info = obs[obs._available <= decision]
            raw_allocation = self.strategy(info, decision)
            benchmark_metadata = dict(getattr(raw_allocation, "attrs", {}))
            allocation = pd.Series(raw_allocation, dtype=float)
            allocation = allocation / allocation.sum() if allocation.sum() else allocation
            next_decision = dates[index + 1] if index + 1 < len(dates) else None

            if next_decision is None:
                gross_return = float("nan")
            elif hasattr(self.strategy, "realized_return"):
                realized = self.strategy.realized_return(
                    obs,
                    allocation,
                    decision,
                    next_decision,
                )
                gross_return = float("nan") if realized is None else float(realized)
            elif hasattr(self.strategy, "next_return"):
                gross_return = float(
                    self.strategy.next_return(
                        obs[obs._available <= decision],
                        allocation,
                        decision,
                    )
                )
            else:
                gross_return = 0.0

            if next_decision is None:
                turnover = 0.0
            elif previous is None:
                turnover = (
                    portfolio_turnover(
                        allocation,
                        {},
                        convention=self.turnover_convention,
                    )
                    if self.charge_initial_trade
                    else 0.0
                )
            else:
                turnover = portfolio_turnover(
                    allocation,
                    previous,
                    convention=self.turnover_convention,
                )
            returns.append(gross_return - turnover * self.cost_bps / 10000)
            allocations.append(allocation)
            score_rows.append(
                {
                    key: getattr(value, "score", value)
                    for key, value in getattr(self.strategy, "last_scores", {}).items()
                }
            )
            if getattr(self.strategy, "last_decision", None):
                state = self.strategy.last_decision
                decision_records.append(
                    {
                        "decision": str(decision),
                        "allocation": dict(allocation),
                        "scores": {
                            key: getattr(value, "score", None)
                            for key, value in state["asset_scores"].items()
                        },
                        "attribution": state["attribution"],
                        "signal_components": state.get("signal_components", {}),
                        "model_versions": state["model_versions"],
                        "data_cutoff": str(state["data_cutoff"]),
                        "missing_signal_assets": state.get("missing_signal_assets", []),
                        "turnover": turnover,
                    }
                )
            previous = allocation

        return ReplayResult(
            pd.Series(returns, index=dates, name="return"),
            pd.DataFrame(allocations, index=dates).fillna(0),
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
    """PIT-only decision strategy with explicit normalized signal components."""

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
        asset_signal_map=None,
        component_weights=None,
        allocation_config=None,
        critical_assets=None,
        market_engine=None,
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
        self.asset_signal_map = {
            asset: dict((asset_signal_map or {}).get(asset, {}))
            for asset in self.assets
        }
        self.component_weights = dict(component_weights or COMPONENT_WEIGHTS)
        self.allocation_config = dict(allocation_config or {})
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
        self.market_engine = market_engine or MarketEngine(min_history=21)
        self.last_decision = None
        self.last_scores = {}
        self.previous_valid_weight = None

    def reset_state(self):
        self.previous_valid_weight = None
        self.last_decision = None
        self.last_scores = {}

    def __call__(self, info, decision, *, health=True, component_inputs=None):
        market_histories = _market_histories(
            info,
            self.assets,
            self.asset_series_map,
            self.return_specs,
        )
        market = self.market_engine.build(market_histories, as_of=decision)

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

        explicit_components = component_inputs or {}
        scores = {}
        signal_components = {}
        missing_signal_assets = []
        for asset in self.assets:
            market_asset = market.assets.get(asset, {})
            signals = market_asset.get("signals", {})
            trend = signals.get("trend")
            if (
                trend is not None
                and self.return_specs[asset].kind == "price"
                and float(self.signal_directions.get(asset, 1.0)) != 1.0
            ):
                trend = _scaled_signal(
                    trend,
                    float(self.signal_directions[asset]),
                )
            risk = signals.get("risk")
            macro_dimension = self.asset_signal_map.get(asset, {}).get("macro")
            macro_signal = (
                macro.dimensions.get(macro_dimension)
                if macro_dimension is not None
                else None
            )
            components = {
                "macro": macro_signal,
                "trend": trend,
                "risk": risk,
                "valuation": None,
                "carry": None,
                "structure": None,
            }
            components.update(explicit_components.get(asset, {}))
            trend_score = _signal_score(components.get("trend"))
            if asset in self.critical_assets and trend_score is None:
                missing_signal_assets.append(asset)

            scores[asset] = score_asset(
                asset,
                components,
                component_weights=self.component_weights,
                data_cutoff=decision,
            )
            signal_components[asset] = {
                name: _signal_audit(value) for name, value in components.items()
            }

        upstream_healthy = not (
            health is False
            or str(health).upper() in {"UNHEALTHY", "FAILED", "STALE"}
        )
        effective_health = upstream_healthy and not missing_signal_assets
        constraints = self.allocation_config.get("constraints", self.allocation_config)
        allocation = allocate(
            scores,
            self.strategic_weights,
            max_tilt=float(
                constraints.get(
                    "max_tactical_tilt",
                    constraints.get("max_tilt", 0.10),
                )
            ),
            min_weight=float(constraints.get("min_weight", 0.0)),
            max_weight=float(constraints.get("max_weight", 0.5)),
            previous_valid_weight=self.previous_valid_weight,
            as_of=decision,
            data_cutoff=decision,
            health=effective_health,
        )
        if allocation.status == "ACTIVE":
            self.previous_valid_weight = dict(allocation.weights)

        self.last_decision = {
            "market_state": market,
            "macro_state": macro,
            "style_state": style,
            "asset_scores": scores,
            "signal_components": signal_components,
            "allocation": allocation,
            "attribution": allocation.attribution,
            "model_versions": {
                "market": market.model_version,
                "macro": getattr(macro, "model_version", "macro_v0.2"),
                "style": self.style_engine.model_version,
                "asset": "asset_score_v0.2",
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


def _scaled_signal(value, scale):
    if isinstance(value, dict):
        out = dict(value)
        if out.get("score") is not None:
            out["score"] = float(out["score"]) * scale
        if isinstance(out.get("components"), dict):
            out["components"] = {
                key: None if component is None else float(component) * scale
                for key, component in out["components"].items()
            }
        return out
    return value


def _signal_score(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("score", value.get("value"))
    return getattr(value, "score", getattr(value, "value", value))


def _signal_audit(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {"score": value, "confidence": 1.0}


def realized_return(
    observations,
    allocation,
    decision,
    next_decision,
    return_specs=None,
):
    """Compatibility helper using explicit full holding-period boundaries."""

    return portfolio_period_return(
        observations,
        allocation,
        decision,
        next_decision,
        specs=return_specs,
    )


def _market_histories(info, assets, asset_series_map=None, return_specs=None):
    if "series_id" not in info or "value" not in info:
        return {asset: pd.Series(dtype=float) for asset in assets}
    mapping = {
        asset: (asset_series_map or {}).get(
            asset,
            None if asset == "CASH" else asset,
        )
        for asset in assets
    }
    series_ids = {series_id for series_id in mapping.values() if series_id is not None}
    rows = info[info["series_id"].isin(series_ids)].copy()
    rows["_date"] = pd.to_datetime(rows["observation_date"])
    histories = {}
    for asset, series_id in mapping.items():
        if series_id is None:
            histories[asset] = pd.Series(dtype=float)
            continue
        raw = (
            rows[rows["series_id"] == series_id]
            .sort_values(["_date", "available_at"])
            .drop_duplicates("_date", keep="last")
            .set_index("_date")["value"]
        )
        spec = (return_specs or {}).get(asset, AssetReturnSpec(series_id, kind="price"))
        histories[asset] = return_index_from_series(raw, spec)
    return histories


def _price_histories(info, assets, asset_series_map=None):
    """Backward-compatible alias for legacy callers."""

    return _market_histories(info, assets, asset_series_map)


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
