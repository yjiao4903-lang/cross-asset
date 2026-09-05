"""Formal walk-forward executor for admitted observations.

The executor never evaluates the sealed final holdout. Each fold receives a
fresh strategy instance so state and allocation history cannot leak across
folds. Overlapping fold outputs are stitched separately after execution.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from cross_asset.backtest.replay import FullModelStrategy
from cross_asset.backtest.returns import (
    AssetReturnSpec,
    portfolio_asset_returns,
    portfolio_period_return,
    return_index_from_series,
)
from cross_asset.engines.allocation import allocate
from cross_asset.engines.asset_score import score_asset
from cross_asset.engines.macro import build_macro_state
from cross_asset.engines.market import MarketEngine
from cross_asset.storage import latest_formal_observations_asof


@dataclass(frozen=True)
class ResearchModelConfig:
    assets: tuple[str, ...]
    strategic_weights: dict[str, float]
    return_specs: dict[str, AssetReturnSpec]
    asset_signal_map: dict[str, dict]
    component_weights: dict[str, float]
    allocation_config: dict
    macro_config: dict


class _StaticStrategy:
    def __init__(self, config: ResearchModelConfig):
        self.weights = dict(config.strategic_weights)
        self.return_specs = config.return_specs
        self.last_status = "ACTIVE"

    def __call__(self, _info, _decision):
        return self.weights

    def realized_return(self, observations, allocation, decision, next_decision):
        return portfolio_period_return(
            observations,
            allocation,
            decision,
            next_decision,
            specs=self.return_specs,
        )


class _ComponentOnlyStrategy:
    def __init__(self, component: str, config: ResearchModelConfig):
        if component not in {"trend", "risk", "macro"}:
            raise ValueError("component_strategy_invalid")
        self.component = component
        self.config = config
        self.market_engine = MarketEngine(min_history=21)
        self.previous_valid_weight = None
        self.last_status = "FROZEN"

    def _market_signals(self, info, decision):
        histories = _market_histories(
            info,
            self.config.assets,
            self.config.return_specs,
        )
        state = self.market_engine.build(histories, as_of=decision)
        return {
            asset: (
                state.assets.get(asset, {})
                .get("signals", {})
                .get(self.component)
            )
            for asset in self.config.assets
        }

    def _macro_signals(self, info, decision):
        rows = info.to_dict("records")
        for row in rows:
            available = pd.Timestamp(row["available_at"])
            row["available_at"] = (
                available.tz_localize("UTC")
                if available.tz is None
                else available.tz_convert("UTC")
            )
        state = build_macro_state(rows, decision, self.config.macro_config)
        return {
            asset: (
                state.dimensions.get(
                    self.config.asset_signal_map.get(asset, {}).get("macro")
                )
                if self.config.asset_signal_map.get(asset, {}).get("macro")
                else None
            )
            for asset in self.config.assets
        }

    def __call__(self, info, decision):
        signals = (
            self._macro_signals(info, decision)
            if self.component == "macro"
            else self._market_signals(info, decision)
        )
        scores = {
            asset: score_asset(
                asset,
                {self.component: signals.get(asset)},
                component_weights={self.component: 1.0},
                data_cutoff=decision,
            )
            for asset in self.config.assets
        }
        critical = [
            asset
            for asset in self.config.assets
            if self.config.return_specs[asset].kind != "cash"
            and scores[asset].score is None
        ]
        constraints = self.config.allocation_config.get(
            "constraints",
            self.config.allocation_config,
        )
        result = allocate(
            scores,
            self.config.strategic_weights,
            max_tilt=float(constraints.get("max_tactical_tilt", 0.10)),
            min_weight=float(constraints.get("min_weight", 0.0)),
            max_weight=float(constraints.get("max_weight", 0.5)),
            health=not critical,
            previous_valid_weight=self.previous_valid_weight,
            as_of=decision,
            data_cutoff=decision,
            model_version=f"{self.component}_only_allocation_v0.1",
        )
        if result.status == "ACTIVE":
            self.previous_valid_weight = dict(result.weights)
        self.last_status = result.status
        return result.weights

    def realized_return(self, observations, allocation, decision, next_decision):
        return portfolio_period_return(
            observations,
            allocation,
            decision,
            next_decision,
            specs=self.config.return_specs,
        )


def _market_histories(info, assets, return_specs):
    histories = {}
    for asset in assets:
        spec = return_specs[asset]
        if spec.series_id is None:
            histories[asset] = pd.Series(dtype=float)
            continue
        rows = info[info["series_id"] == spec.series_id].copy()
        if rows.empty:
            histories[asset] = pd.Series(dtype=float)
            continue
        rows["_date"] = pd.to_datetime(rows["observation_date"])
        raw = (
            rows.sort_values(["_date", "available_at"])
            .drop_duplicates("_date", keep="last")
            .set_index("_date")["value"]
        )
        histories[asset] = return_index_from_series(raw, spec)
    return histories


def _strategy(name: str, config: ResearchModelConfig):
    name = name.upper()
    if name == "STATIC":
        return _StaticStrategy(config)
    if name == "TREND_ONLY":
        return _ComponentOnlyStrategy("trend", config)
    if name == "RISK_ONLY":
        return _ComponentOnlyStrategy("risk", config)
    if name == "MACRO_ONLY":
        return _ComponentOnlyStrategy("macro", config)
    if name == "FULL_MODEL":
        return FullModelStrategy(
            config.assets,
            strategic_weights=config.strategic_weights,
            macro_config=config.macro_config,
            asset_series_map={
                asset: spec.series_id for asset, spec in config.return_specs.items()
            },
            return_specs=config.return_specs,
            asset_signal_map=config.asset_signal_map,
            component_weights=config.component_weights,
            allocation_config=config.allocation_config,
        )
    raise ValueError(f"unknown_research_benchmark:{name}")


def _status(strategy) -> str:
    if isinstance(strategy, FullModelStrategy):
        return strategy.last_decision["allocation"].status
    return getattr(strategy, "last_status", "ACTIVE")


def execute_walk_forward(
    connection,
    *,
    decision_dates,
    plan: dict,
    protocol,
    model_config: ResearchModelConfig,
) -> pd.DataFrame:
    """Execute only the development walk-forward folds from a sealed plan."""

    if plan.get("status") != "READY_FOR_OOS":
        raise ValueError("research_plan_not_ready")
    if plan.get("holdout_sealed") is not True:
        raise ValueError("formal_walk_forward_requires_sealed_holdout")
    if protocol.execution_blockers:
        raise ValueError("research_protocol_not_executable")

    dates = pd.DatetimeIndex(pd.to_datetime(list(decision_dates), utc=True))
    development_count = int(plan["development_count"])
    development = dates[:development_count]
    if len(development) != development_count:
        raise ValueError("development_decision_dates_incomplete")
    if len(dates) <= development_count:
        raise ValueError("sealed_holdout_dates_missing_from_input")

    series_ids = sorted(
        {
            spec.series_id
            for spec in model_config.return_specs.values()
            if spec.series_id is not None
        }
        | set(model_config.macro_config.get("series", {}))
    )
    observations = latest_formal_observations_asof(
        connection,
        dates.max().to_pydatetime(),
        required_usage_status=protocol.required_usage_status,
        series_ids=series_ids,
    )
    if observations.empty:
        raise ValueError("formal_observations_empty")
    observations["_available"] = pd.to_datetime(observations["available_at"], utc=True)
    observations["_observation_date"] = pd.to_datetime(
        observations["observation_date"],
        utc=True,
    )

    rows = []
    for fold in plan["folds"]:
        fold_number = int(fold["fold"])
        test_indices = list(fold["test_indices"])
        test_dates = development[test_indices]
        if len(test_dates) == 0:
            continue
        train_start = pd.Timestamp(fold["train_start"])
        for benchmark in protocol.benchmarks:
            strategy = _strategy(benchmark, model_config)
            fold_observations = observations
            if fold.get("window_type") == "rolling":
                fold_observations = observations[
                    observations["_observation_date"] >= train_start
                ]
            clean_fold_observations = fold_observations.drop(
                columns=["_available", "_observation_date"]
            )
            for index, decision in enumerate(test_dates):
                info = fold_observations[
                    fold_observations["_available"] <= decision
                ].drop(columns=["_available", "_observation_date"])
                weights = dict(strategy(info, decision))
                next_decision = (
                    test_dates[index + 1]
                    if index + 1 < len(test_dates)
                    else None
                )
                asset_returns = portfolio_asset_returns(
                    clean_fold_observations,
                    weights,
                    decision,
                    next_decision,
                    specs=model_config.return_specs,
                )
                gross_return = (
                    None
                    if asset_returns is None
                    else sum(
                        float(weights[asset]) * value
                        for asset, value in asset_returns.items()
                    )
                )
                rows.append(
                    {
                        "fold": fold_number,
                        "decision_date": decision,
                        "benchmark": benchmark,
                        "gross_return": gross_return,
                        "asset_returns": asset_returns,
                        "allocation_status": _status(strategy),
                        "weights": weights,
                        "train_start": fold["train_start"],
                        "train_end": fold["train_end"],
                        "test_start": fold["test_start"],
                        "test_end": fold["test_end"],
                    }
                )
    return pd.DataFrame(rows)


__all__ = ["ResearchModelConfig", "execute_walk_forward"]
