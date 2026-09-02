"""Preliminary, no-tuning Sprint 2 historical orchestrator."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from cross_asset.backtest.benchmarks import make_benchmark
from cross_asset.backtest.metrics import performance_metrics
from cross_asset.backtest.replay import FullModelStrategy
from cross_asset.backtest.returns import (
    AssetReturnSpec,
    portfolio_period_return,
    return_index_from_series,
)
from cross_asset.backtest.walk_forward import portfolio_turnover
from cross_asset.engines.allocation import allocate
from cross_asset.engines.asset_score import score_asset
from cross_asset.engines.macro import build_macro_state
from cross_asset.engines.market import MarketEngine
from cross_asset.ingestion.evidence_shadow import load_wind_engineering_frame
from cross_asset.operations.exchange_calendar import CalendarBlockedError, cn_hk_calendar
from cross_asset.sprint2.artifact import protocol_hash, sha256_file, sha256_frame, write_artifacts
from cross_asset.sprint2.config import config_hash, load_sprint2_config, validate_sprint2_config


class Sprint2BlockedError(RuntimeError):
    status = "BLOCKED"


def _strategic_weights() -> dict[str, float]:
    frozen = {"CN_EQ": 0.25, "HK_EQ": 0.10, "CN_BOND": 0.20, "CASH": 0.10}
    total = sum(frozen.values())
    return {asset: weight / total for asset, weight in frozen.items()}


def _return_specs(protocol_obj) -> dict[str, AssetReturnSpec]:
    return {
        asset: AssetReturnSpec(**definition)
        for asset, definition in protocol_obj.return_model.items()
    }


def _series_mapping(protocol_obj) -> dict[str, str | None]:
    return {
        asset: definition.get("series_id")
        for asset, definition in protocol_obj.return_model.items()
    }

def _macro_config() -> dict:
    return {
        "series": {
            "CN_CPI": {
                "transform": {"type": "yoy", "direction": "negative"},
                "normalization": {"method": "causal_zscore", "min_history": 12, "clip": 2.0},
            },
            "CN_PPI": {
                "transform": {"type": "yoy", "direction": "negative"},
                "normalization": {"method": "causal_zscore", "min_history": 12, "clip": 2.0},
            },
            "CN_M1": {
                "transform": {"type": "yoy", "direction": "positive"},
                "normalization": {"method": "causal_zscore", "min_history": 12, "clip": 2.0},
            },
            "CN_M2": {
                "transform": {"type": "yoy", "direction": "positive"},
                "normalization": {"method": "causal_zscore", "min_history": 12, "clip": 2.0},
            },
            "CN_DR007": {
                "transform": {"type": "level", "direction": "negative"},
                "normalization": {
                    "method": "causal_zscore",
                    "min_history": 20,
                    "window": 120,
                    "clip": 2.0,
                },
            },
        },
        "dimensions": {
            "INFLATION": ["CN_CPI", "CN_PPI"],
            "LIQUIDITY": ["CN_DR007", "CN_M1", "CN_M2"],
        },
    }


def _asset_signal_map() -> dict[str, dict[str, str | None]]:
    return {
        "CN_EQ": {"macro": "INFLATION"},
        "HK_EQ": {"macro": "INFLATION"},
        "CN_BOND": {"macro": "LIQUIDITY"},
        "CASH": {"macro": None},
    }


def _market_histories(
    frame: pd.DataFrame,
    assets: tuple[str, ...],
    series_mapping: dict[str, str | None],
    return_specs: dict[str, AssetReturnSpec],
) -> dict[str, pd.Series]:
    histories = {}
    for asset in assets:
        series_id = series_mapping.get(asset)
        if series_id is None:
            histories[asset] = pd.Series(dtype=float)
            continue
        rows = frame[frame.series_id == series_id].copy()
        if rows.empty:
            histories[asset] = pd.Series(dtype=float)
            continue
        rows["_date"] = pd.to_datetime(rows["observation_date"])
        raw = (
            rows.sort_values(["_date", "available_at"])
            .drop_duplicates("_date", keep="last")
            .set_index("_date")["value"]
        )
        histories[asset] = return_index_from_series(raw, return_specs[asset])
    return histories



def _weights(
    benchmark: str,
    frame: pd.DataFrame,
    assets: tuple[str, ...],
    *,
    decision,
    series_mapping: dict[str, str | None],
    return_specs: dict[str, AssetReturnSpec],
    full_strategy: FullModelStrategy | None = None,
) -> tuple[dict[str, float], bool, str | None]:
    strategic = _strategic_weights()
    if benchmark == "FULL_MODEL":
        if full_strategy is None:
            raise ValueError("full_strategy_required")
        weights = full_strategy(frame, pd.Timestamp(decision))
        allocation = full_strategy.last_decision["allocation"]
        available = allocation.status == "ACTIVE"
        reason = (
            None
            if available
            else ";".join(allocation.warnings) or "full_model_inputs_unavailable"
        )
        return dict(weights), available, reason

    histories = _market_histories(
        frame,
        assets,
        series_mapping,
        return_specs,
    )
    market = MarketEngine(min_history=21).build(histories, as_of=decision)
    trend = {
        asset: (
            market.assets.get(asset, {})
            .get("signals", {})
            .get("trend", {})
            .get("score")
        )
        for asset in assets
    }

    if benchmark == "RISK_ONLY":
        volatility = {}
        for asset in assets:
            if asset == "CASH":
                continue
            history = histories.get(asset, pd.Series(dtype=float))
            returns = history.astype(float).pct_change(fill_method=None).dropna().tail(60)
            if len(returns) < 20 or not float(returns.std(ddof=1)):
                return {}, False, "volatility_history_unavailable"
            volatility[asset] = float(returns.std(ddof=1))
        cash_weight = strategic["CASH"]
        inverse = {asset: 1.0 / value for asset, value in volatility.items()}
        scale = (1.0 - cash_weight) / sum(inverse.values())
        weights = {asset: value * scale for asset, value in inverse.items()}
        weights["CASH"] = cash_weight
        return weights, True, None

    info = {"weights": strategic if benchmark == "STATIC" else {}}
    if benchmark == "TREND_ONLY":
        positive = {
            asset: max(float(trend.get(asset) or 0.0), 0.0)
            for asset in assets
        }
        if sum(positive.values()) > 0:
            info["weights"] = {
                asset: positive[asset] / sum(positive.values())
                for asset in assets
            }
        else:
            info["weights"] = {
                asset: 1.0 if asset == "CASH" else 0.0
                for asset in assets
            }
    series = make_benchmark(
        benchmark,
        assets,
        strategic_weights=strategic,
    )(info, None)
    unavailable = bool(series.attrs.get("unavailable", False))
    return (
        {str(key): float(value) for key, value in series.items()},
        not unavailable,
        series.attrs.get("reason"),
    )

def _realized_return(
    frame: pd.DataFrame,
    weights: dict[str, float],
    decision,
    next_decision,
    *,
    return_specs: dict[str, AssetReturnSpec],
) -> float | None:
    return portfolio_period_return(
        frame,
        weights,
        decision,
        next_decision,
        specs=return_specs,
    )


def _macro_only_weights(
    frame: pd.DataFrame,
    decision,
) -> tuple[dict[str, float], bool, str | None]:
    macro_config = _macro_config()
    macro_series = tuple(macro_config["series"])
    rows = frame[frame.series_id.isin(macro_series)].to_dict("records")
    state = build_macro_state(
        rows,
        pd.Timestamp(decision).to_pydatetime(),
        macro_config,
    )
    liquidity = state.dimensions.get("LIQUIDITY")
    liquidity_score = liquidity.score if liquidity is not None else None
    components = {
        "CN_EQ": state.score,
        "HK_EQ": state.score,
        "CN_BOND": liquidity_score,
    }
    scores = {
        asset: score_asset(asset, {"macro": value}, data_cutoff=decision)
        for asset, value in components.items()
    }
    scores["CASH"] = score_asset(
        "CASH",
        {"risk": 0.0},
        data_cutoff=decision,
    )
    result = allocate(
        scores,
        _strategic_weights(),
        max_tilt=0.10,
        min_weight=0.0,
        max_weight=0.5,
        health=all(score.score is not None for score in scores.values()),
        as_of=decision,
        data_cutoff=decision,
        model_version="macro_only_allocation_v0.2",
    )
    available = result.status == "ACTIVE"
    reason = (
        None
        if available
        else ";".join(result.warnings) or "macro_inputs_unavailable"
    )
    return dict(result.weights), available, reason

def run_preliminary(
    connection: Any,
    *,
    output_dir: str | Path,
    calendar_adapter: Any | None = None,
    start: date | None = None,
    end: date | None = None,
    protocol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = protocol or load_sprint2_config()
    protocol_obj, _ = validate_sprint2_config(raw)
    return_specs = _return_specs(protocol_obj)
    series_mapping = _series_mapping(protocol_obj)
    frame = load_wind_engineering_frame(
        connection, decision_time=pd.Timestamp("2100-01-01", tz="UTC")
    )
    formal_observations = int(
        connection.execute("SELECT count(*) FROM observations").fetchone()[0]
    )
    if formal_observations != 0:
        raise Sprint2BlockedError(
            "BLOCKED: preliminary runner requires formal observations to remain empty"
        )
    if frame.empty:
        raise Sprint2BlockedError(
            "BLOCKED: wind_evidence_staging produced no engineering rows"
        )
    price_mapping = {
        sid for sid in series_mapping.values() if sid is not None
    }
    price_starts = (
        frame[frame.series_id.isin(price_mapping)]
        .groupby("series_id")
        .observation_date.min()
    )
    if len(price_starts) != len(price_mapping):
        raise Sprint2BlockedError(
            "BLOCKED: partial-universe price history is incomplete"
        )
    common_history_start = pd.Timestamp(price_starts.max()).date()
    first = max(
        pd.Timestamp(start or common_history_start).date(),
        common_history_start,
    )
    last = pd.Timestamp(end or frame.observation_date.max()).date()
    try:
        calendar = cn_hk_calendar(provider=calendar_adapter)
        dates = calendar.weekly_decision_dates(first, last)
    except CalendarBlockedError as exc:
        raise Sprint2BlockedError(str(exc)) from exc
    if not dates:
        raise Sprint2BlockedError(
            "BLOCKED: exchange calendar returned no common sessions"
        )

    cfg_hash = config_hash(raw)
    no_tuning = protocol_hash(
        {
            "cost_bps": 10,
            "transaction_costs_bps": [0, 5, 10, 20, 30],
            "turnover_convention": protocol_obj.turnover_convention,
            "return_model": protocol_obj.return_model,
            "charge_initial_trade": protocol_obj.charge_initial_trade,
            "signal_model_version": protocol_obj.signal_model_version,
            "mode": "expanding",
            "universe": protocol_obj.universe,
        }
    )
    data_hash = sha256_frame(frame)
    code_hash = protocol_hash(
        {
            "runner": sha256_file(Path(__file__)),
            "artifact": sha256_file(
                Path(__file__).with_name("artifact.py")
            ),
        }
    )
    raw_hashes = sorted(
        {str(x) for x in frame.source_file_sha256.dropna()}
    )
    decisions, returns, scores = [], [], []
    allocations, turnovers, costs = [], [], []
    unavailable = []

    for benchmark in protocol_obj.benchmarks:
        previous = None
        full_strategy = (
            FullModelStrategy(
                protocol_obj.universe,
                strategic_weights=_strategic_weights(),
                asset_series_map=series_mapping,
                return_specs=return_specs,
                macro_config=_macro_config(),
                asset_signal_map=_asset_signal_map(),
                allocation_config={
                    "constraints": {
                        "max_tactical_tilt": 0.10,
                        "min_weight": 0.0,
                        "max_weight": 0.5,
                    }
                },
            )
            if benchmark == "FULL_MODEL"
            else None
        )
        for index, decision in enumerate(dates):
            info = frame[
                pd.to_datetime(frame.available_at, utc=True).dt.date
                <= decision
            ]
            if benchmark == "MACRO_ONLY":
                weights, available, reason = _macro_only_weights(
                    info, decision
                )
            else:
                weights, available, reason = _weights(
                    benchmark,
                    info,
                    protocol_obj.universe,
                    decision=decision,
                    series_mapping=series_mapping,
                    return_specs=return_specs,
                    full_strategy=full_strategy,
                )
            if not available:
                unavailable.append(
                    f"{benchmark}:{decision.isoformat()}:{reason}"
                )

            next_decision = (
                dates[index + 1]
                if index + 1 < len(dates)
                else None
            )
            if not available:
                turnover = None
            elif next_decision is None:
                turnover = 0.0
            elif previous is None:
                turnover = (
                    portfolio_turnover(
                        weights,
                        {},
                        convention=protocol_obj.turnover_convention,
                    )
                    if protocol_obj.charge_initial_trade
                    else 0.0
                )
            else:
                turnover = portfolio_turnover(
                    weights,
                    previous,
                    convention=protocol_obj.turnover_convention,
                )
            cost = (
                turnover * protocol_obj.base_cost_bps / 10000
                if turnover is not None
                else None
            )
            decisions.append(
                {
                    "decision_date": decision,
                    "benchmark": benchmark,
                    "available": available,
                    "status": "READY" if available else "UNAVAILABLE",
                    "reason": reason,
                }
            )
            scores.append(
                {
                    "decision_date": decision,
                    "benchmark": benchmark,
                    "score_available": available,
                }
            )
            allocations.extend(
                {
                    "decision_date": decision,
                    "benchmark": benchmark,
                    "asset": asset,
                    "weight": (
                        weights.get(asset, 0.0) if available else None
                    ),
                }
                for asset in protocol_obj.universe
            )
            turnovers.append(
                {
                    "decision_date": decision,
                    "benchmark": benchmark,
                    "turnover": turnover,
                    "turnover_convention": (
                        protocol_obj.turnover_convention
                    ),
                }
            )
            for cost_bps in protocol_obj.transaction_cost_bps:
                costs.append(
                    {
                        "decision_date": decision,
                        "benchmark": benchmark,
                        "cost_bps": cost_bps,
                        "turnover_convention": (
                            protocol_obj.turnover_convention
                        ),
                        "cost": (
                            turnover * cost_bps / 10000
                            if turnover is not None
                            else None
                        ),
                    }
                )

            gross_return = (
                _realized_return(
                    frame,
                    weights,
                    decision,
                    next_decision,
                    return_specs=return_specs,
                )
                if available
                else None
            )
            returns.append(
                {
                    "decision_date": decision,
                    "benchmark": benchmark,
                    "gross_return": gross_return,
                    "net_return": (
                        gross_return - cost
                        if gross_return is not None
                        and cost is not None
                        else None
                    ),
                    "available": (
                        available and gross_return is not None
                    ),
                }
            )
            if available:
                previous = weights

    tables = {
        "decisions.parquet": pd.DataFrame(decisions),
        "returns.parquet": pd.DataFrame(returns),
        "scores.parquet": pd.DataFrame(scores),
        "allocations.parquet": pd.DataFrame(allocations),
        "turnover.parquet": pd.DataFrame(turnovers),
        "costs.parquet": pd.DataFrame(costs),
    }

    metric_rows = []
    for benchmark in protocol_obj.benchmarks:
        benchmark_returns = tables["returns.parquet"]
        benchmark_returns = benchmark_returns[
            benchmark_returns.benchmark == benchmark
        ]
        gross = (
            benchmark_returns.set_index("decision_date")
            .gross_return.astype(float)
        )
        allocation = tables["allocations.parquet"]
        allocation = (
            allocation[allocation.benchmark == benchmark]
            .pivot(
                index="decision_date",
                columns="asset",
                values="weight",
            )
        )
        benchmark_costs = tables["costs.parquet"]
        benchmark_costs = benchmark_costs[
            (benchmark_costs.benchmark == benchmark)
            & (
                benchmark_costs.cost_bps
                == protocol_obj.base_cost_bps
            )
        ].set_index("decision_date").cost
        net = gross - benchmark_costs.reindex(
            gross.index
        ).fillna(0.0)
        metrics = performance_metrics(
            net,
            allocation.reindex(gross.index),
            turnover_convention=protocol_obj.turnover_convention,
        )
        metric_rows.append(
            {
                "benchmark": benchmark,
                "CAGR": metrics["CAGR"],
                "Vol": metrics["annualized_vol"],
                "Sharpe": metrics["Sharpe"],
                "MaxDD": metrics["max_drawdown"],
                "Turnover": metrics["turnover"],
                "Cost": float(benchmark_costs.sum()),
                "Worst1M": metrics["Worst1M"],
                "Recovery": metrics["Recovery"],
            }
        )

    status = "PARTIAL" if unavailable else "PRELIMINARY"
    gates = {
        "artifacts": True,
        "engineering_cutoff": True,
        "formal_pit": False,
        "calendar": True,
        "benchmarks": not unavailable,
    }
    required_gates = (
        "artifacts",
        "engineering_cutoff",
        "calendar",
        "benchmarks",
    )
    exit_flag = all(gates[name] for name in required_gates)

    metric_lines = [
        "| Benchmark | CAGR | Vol | Sharpe | MaxDD | Turnover | Cost | Worst1M | Recovery |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in metric_rows:
        values = [
            row["benchmark"],
            *[
                (
                    "NA"
                    if row[key] is None or pd.isna(row[key])
                    else f"{row[key]:.8f}"
                )
                for key in (
                    "CAGR",
                    "Vol",
                    "Sharpe",
                    "MaxDD",
                    "Turnover",
                    "Cost",
                    "Worst1M",
                )
            ],
            (
                "NA"
                if row["Recovery"] is None
                else str(row["Recovery"])
            ),
        ]
        metric_lines.append("| " + " | ".join(values) + " |")

    summary = (
        "# Sprint 2 Preliminary\n\n"
        + f"status: {status}\n"
        + "PRELIMINARY: true\n"
        + "PARTIAL_UNIVERSE: true\n"
        + (
            "PRELIMINARY_WALK_FORWARD_READY: "
            f"{str(exit_flag).lower()}\n"
        )
        + "RESEARCH_VALIDATED: false\n"
        + "FORMAL_PIT: false\n"
        + f"EXIT: {str(exit_flag).lower()}\n"
        + f"observations: {formal_observations}\n"
        + f"calendar: {calendar.metadata.provider}\n"
        + f"benchmarks: {', '.join(protocol_obj.benchmarks)}\n"
        + "base_cost_bps: 10\n"
        + f"charge_initial_trade: {str(protocol_obj.charge_initial_trade).lower()}\n"
        + f"signal_model_version: {protocol_obj.signal_model_version}\n"
        + (
            "turnover_convention: "
            f"{protocol_obj.turnover_convention}\n"
        )
        + (
            "cost_sensitivity_bps: "
            f"{list(protocol_obj.transaction_cost_bps)}\n"
        )
        + f"return_model: {protocol_obj.return_model}\n"
        + f"no_tuning_protocol_hash: {no_tuning}\n"
        + f"config_hash: {cfg_hash}\n"
        + f"code_hash: {code_hash}\n"
        + f"data_hash: {data_hash}\n"
        + f"raw_hashes: {', '.join(raw_hashes) or 'none'}\n\n"
        + f"gates: {gates}\n\n"
        + "## Metrics at 10 bps\n\n"
        + "\n".join(metric_lines)
        + "\n\nNo broker/order path; engineering artifact only.\n"
    )
    result = write_artifacts(output_dir, tables, summary)
    gates["artifacts"] = (
        len(result["artifacts"]) == 7
        and all(Path(path).is_file() for path in result["artifacts"])
    )
    exit_flag = all(gates[name] for name in required_gates)
    result.update(
        {
            "status": status,
            "exit": exit_flag,
            "observations": formal_observations,
            "calendar": calendar.metadata.__dict__,
            "calendar_coverage": (
                calendar.coverage()
                if hasattr(calendar, "coverage")
                else None
            ),
            "no_tuning_protocol_hash": no_tuning,
            "config_hash": cfg_hash,
            "code_hash": code_hash,
            "data_hash": data_hash,
            "raw_hashes": raw_hashes,
            "unavailable_count": len(unavailable),
            "unavailable_sample": unavailable[:20],
            "research_validated": False,
            "gates": gates,
        }
    )
    return result
