"""Preliminary, no-tuning Sprint 2 historical orchestrator."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from cross_asset.backtest.benchmarks import make_benchmark
from cross_asset.ingestion.evidence_shadow import load_wind_engineering_frame
from cross_asset.operations.exchange_calendar import CalendarBlockedError, cn_hk_calendar
from cross_asset.sprint2.artifact import protocol_hash, sha256_file, sha256_frame, write_artifacts
from cross_asset.sprint2.config import config_hash, load_sprint2_config, validate_sprint2_config


class Sprint2BlockedError(RuntimeError):
    status = "BLOCKED"


def _weights(
    benchmark: str, frame: pd.DataFrame, assets: tuple[str, ...]
) -> tuple[dict[str, float], bool, str | None]:
    strategic = {asset: 1.0 / len(assets) for asset in assets}
    trend = {asset: 0.0 for asset in assets}
    mapping = {"CN_EQ": "CN_EQ_LARGE", "HK_EQ": "HK_EQ", "CN_BOND": "CN_BOND_10Y"}
    for asset, series in mapping.items():
        rows = frame[frame.series_id == series].sort_values("observation_date")
        if len(rows) >= 2:
            trend[asset] = float(rows.iloc[-1].value / rows.iloc[-2].value - 1.0)
    info = {
        "weights": strategic if benchmark == "STATIC" else {},
        "macro_weights": strategic,
        "volatility": {a: abs(trend[a]) for a in assets},
    }
    if benchmark == "TREND_ONLY":
        positive = {a: max(trend[a], 0.0) for a in assets}
        if sum(positive.values()) > 0:
            info["weights"] = {a: positive[a] / sum(positive.values()) for a in assets}
    series = make_benchmark(benchmark, assets, strategic_weights=strategic)(info, None)
    unavailable = bool(series.attrs.get("unavailable", False))
    return (
        {str(k): float(v) for k, v in series.items()},
        not unavailable,
        series.attrs.get("reason"),
    )


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
    frame = load_wind_engineering_frame(
        connection, decision_time=pd.Timestamp("2100-01-01", tz="UTC")
    )
    formal_observations = int(connection.execute("SELECT count(*) FROM observations").fetchone()[0])
    if formal_observations != 0:
        raise Sprint2BlockedError(
            "BLOCKED: preliminary runner requires formal observations to remain empty"
        )
    if frame.empty:
        raise Sprint2BlockedError("BLOCKED: wind_evidence_staging produced no engineering rows")
    first = pd.Timestamp(start or frame.observation_date.min()).date()
    last = pd.Timestamp(end or frame.observation_date.max()).date()
    try:
        calendar = cn_hk_calendar(provider=calendar_adapter)
        dates = calendar.weekly_decision_dates(first, last)
    except CalendarBlockedError as exc:
        raise Sprint2BlockedError(str(exc)) from exc
    if not dates:
        raise Sprint2BlockedError("BLOCKED: exchange calendar returned no common sessions")
    cfg_hash = config_hash(raw)
    no_tuning = protocol_hash(
        {
            "cost_bps": 10,
            "transaction_costs_bps": [0, 5, 10, 20, 30],
            "mode": "expanding",
            "universe": protocol_obj.universe,
        }
    )
    data_hash = sha256_frame(frame)
    code_hash = protocol_hash(
        {
            "runner": sha256_file(Path(__file__)),
            "artifact": sha256_file(Path(__file__).with_name("artifact.py")),
        }
    )
    raw_hashes = sorted({str(x) for x in frame.source_file_sha256.dropna()})
    decisions, returns, scores, allocations, turnovers, costs = [], [], [], [], [], []
    unavailable = []
    for benchmark in protocol_obj.benchmarks:
        previous = {}
        for decision in dates:
            info = frame[pd.to_datetime(frame.available_at, utc=True).dt.date <= decision]
            weights, available, reason = _weights(benchmark, info, protocol_obj.universe)
            if not available:
                unavailable.append(f"{benchmark}:{decision.isoformat()}:{reason}")
            turnover = (
                sum(abs(weights.get(a, 0.0) - previous.get(a, 0.0)) for a in protocol_obj.universe)
                if available
                else None
            )
            cost = turnover * protocol_obj.base_cost_bps / 10000 if turnover is not None else None
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
                {"decision_date": decision, "benchmark": benchmark, "score_available": available}
            )
            allocations.extend(
                {
                    "decision_date": decision,
                    "benchmark": benchmark,
                    "asset": asset,
                    "weight": weights.get(asset, 0.0) if available else None,
                }
                for asset in protocol_obj.universe
            )
            turnovers.append(
                {"decision_date": decision, "benchmark": benchmark, "turnover": turnover}
            )
            costs.append(
                {
                    "decision_date": decision,
                    "benchmark": benchmark,
                    "cost_bps": protocol_obj.base_cost_bps,
                    "cost": cost,
                }
            )
            returns.append(
                {
                    "decision_date": decision,
                    "benchmark": benchmark,
                    "return": None if not available else 0.0,
                    "available": available,
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
    status = "PARTIAL" if unavailable else "PRELIMINARY"
    gates = {"artifacts": True, "pit": False, "calendar": True, "benchmarks": not unavailable}
    exit_flag = False
    summary = (
        "# Sprint 2 Preliminary\n\n"
        + f"status: {status}\nPRELIMINARY: true\nPARTIAL_UNIVERSE: true\nRESEARCH_VALIDATED: false\nEXIT: false\nobservations: {formal_observations}\ncalendar: {calendar.metadata.provider}\nbenchmarks: {', '.join(protocol_obj.benchmarks)}\nbase_cost_bps: 10\nno_tuning_protocol_hash: `{no_tuning}`\nconfig_hash: `{cfg_hash}`\ncode_hash: `{code_hash}`\ndata_hash: `{data_hash}`\nraw_hashes: {', '.join(raw_hashes) or 'none'}\n\ngates: {gates}\nNo broker/order path; engineering artifact only.\n"
    )
    result = write_artifacts(output_dir, tables, summary)
    gates["artifacts"] = len(result["artifacts"]) == 7 and all(
        Path(path).is_file() for path in result["artifacts"]
    )
    exit_flag = all(gates.values())
    result.update(
        {
            "status": status,
            "exit": exit_flag,
            "observations": formal_observations,
            "calendar": calendar.metadata.__dict__,
            "no_tuning_protocol_hash": no_tuning,
            "config_hash": cfg_hash,
            "code_hash": code_hash,
            "data_hash": data_hash,
            "raw_hashes": raw_hashes,
            "unavailable": unavailable,
            "research_validated": False,
            "gates": gates,
        }
    )
    return result
