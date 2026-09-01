"""Read-only Wind staging adapter for engineering feature validation.

This module never writes formal observations and never grants research or live
admission.  Conservative timestamps are synthetic engineering cutoffs, not
claims about the provider's actual publication time.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from cross_asset.engines.allocation import allocate
from cross_asset.engines.asset_score import score_asset
from cross_asset.engines.macro import build_macro_state
from cross_asset.engines.market import MarketEngine
from cross_asset.engines.style import StyleEngine

PRICE_SERIES = ("CN_EQ_LARGE", "CN_EQ_SMALL", "HK_EQ", "CN_BOND_10Y")
MACRO_SERIES = ("CN_CPI", "CN_PPI", "CN_M1", "CN_M2", "CN_DR007")
SUPPORTED_SERIES = PRICE_SERIES + MACRO_SERIES


def _engineering_available_at(observation_date, frequency: str, country: str | None) -> datetime:
    """Return a deliberately conservative synthetic cutoff for engineering only."""
    zone = ZoneInfo("Asia/Hong_Kong" if country == "Hong Kong" else "Asia/Shanghai")
    lag_days = 1 if str(frequency).lower() in {"daily", "day", "日"} else 45
    local = datetime.combine(observation_date + timedelta(days=lag_days), time.min, zone)
    return local.astimezone(UTC)


def load_wind_engineering_frame(connection, *, decision_time=None) -> pd.DataFrame:
    """Load canonical Wind evidence with a safe engineering-only cutoff."""
    placeholders = ",".join("?" for _ in SUPPORTED_SERIES)
    frame = connection.execute(
        f"""SELECT canonical_candidate AS series_id, source_series_id, source_file_sha256,
                   observation_date, value, frequency, country, quality_status
            FROM wind_evidence_staging
            WHERE canonical_candidate IN ({placeholders})
              AND quality_status != 'SEMANTIC_UNIT_REVIEW_REQUIRED'
            ORDER BY canonical_candidate, observation_date""",
        list(SUPPORTED_SERIES),
    ).df()
    if frame.empty:
        return frame
    frame["available_at"] = [
        _engineering_available_at(row.observation_date, row.frequency, row.country)
        for row in frame.itertuples(index=False)
    ]
    frame["usage_status"] = "ENGINEERING_ONLY"
    frame["pit_admissible"] = False
    frame["decision_eligible"] = False
    cutoff = pd.Timestamp(decision_time or datetime.now(UTC))
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    return frame[pd.to_datetime(frame["available_at"], utc=True) <= cutoff].reset_index(drop=True)


def run_wind_evidence_shadow(connection, *, decision_time=None, output=None) -> dict:
    """Exercise market, SIZE and macro engines without producing allocation."""
    cutoff = pd.Timestamp(decision_time or datetime.now(UTC))
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    frame = load_wind_engineering_frame(connection, decision_time=cutoff)
    prices = {
        sid: rows.set_index("observation_date")["value"].sort_index()
        for sid, rows in frame[frame["series_id"].isin(PRICE_SERIES)].groupby("series_id")
    }
    market = MarketEngine().build(prices, as_of=cutoff)
    style = StyleEngine(
        {"SIZE": {"semantic_definition": "CN small-cap relative to CN large-cap"}}
    ).compute_axis(
        "SIZE",
        lhs=prices.get("CN_EQ_SMALL"),
        rhs=prices.get("CN_EQ_LARGE"),
        data_cutoff=cutoff,
    )
    macro_rows = frame[frame["series_id"].isin(MACRO_SERIES)].to_dict("records")
    macro_config = {
        "series": {
            "CN_CPI": {"transform": {"type": "yoy", "direction": "negative"}},
            "CN_PPI": {"transform": {"type": "yoy", "direction": "negative"}},
            "CN_M1": {"transform": {"type": "yoy", "direction": "positive"}},
            "CN_M2": {"transform": {"type": "yoy", "direction": "positive"}},
            "CN_DR007": {"transform": {"type": "level", "direction": "negative"}},
        },
        "dimensions": {
            "INFLATION": ["CN_CPI", "CN_PPI"],
            "LIQUIDITY": ["CN_DR007", "CN_M1", "CN_M2"],
        },
    }
    macro = build_macro_state(macro_rows, cutoff.to_pydatetime(), macro_config)

    def serial(value):
        if isinstance(value, (date, datetime, pd.Timestamp)):
            return value.isoformat()
        if hasattr(value, "__dict__"):
            return {key: serial(item) for key, item in value.__dict__.items()}
        if isinstance(value, dict):
            return {key: serial(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [serial(item) for item in value]
        return value

    result = {
        "status": "ENGINEERING_READY",
        "usage_status": "ENGINEERING_ONLY",
        "decision_eligible": False,
        "pit_admissible": False,
        "no_trade": True,
        "formal_observations_written": 0,
        "synthetic_available_at_policy": {
            "daily": "observation_date + 1 calendar day at 00:00 local",
            "monthly": "observation_date + 45 calendar days at 00:00 Asia/Shanghai",
            "scope": "engineering cutoff only; not actual release evidence",
        },
        "rows": len(frame),
        "series": sorted(frame["series_id"].unique().tolist()) if not frame.empty else [],
        "market": serial(market),
        "style": {"SIZE": serial(style)},
        "macro": serial(macro),
        "blocked_from": ["formal_backtest", "investment_decision", "live_allocation", "order_generation"],
    }
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def run_wind_local_experiment(
    connection, *, decision_time=None, output=None, store=None, persist=False, project_root="."
) -> dict:
    """Run a local allocation experiment without production or trading claims."""
    shadow = run_wind_evidence_shadow(connection, decision_time=decision_time)
    market_assets = shadow["market"]["assets"]
    macro = shadow["macro"]
    liquidity = macro["dimensions"].get("LIQUIDITY", {}).get("score")
    macro_score = macro.get("score")
    asset_series = {
        "CN_EQ": ("CN_EQ_LARGE", macro_score),
        "HK_EQ": ("HK_EQ", macro_score),
        "CN_BOND": ("CN_BOND_10Y", liquidity),
    }
    scores = {}
    for asset, (series_id, macro_component) in asset_series.items():
        state = market_assets.get(series_id, {})
        ret_1m = state.get("trend", {}).get("ret_1m")
        trend_score = None if ret_1m is None else max(-2.0, min(2.0, float(ret_1m) * 10))
        scores[asset] = score_asset(
            asset,
            {"trend": trend_score, "macro": macro_component},
            confidence=0.75,
            data_cutoff=state.get("data_cutoff"),
        )
    scores["CASH"] = score_asset("CASH", {"risk": 0.0}, confidence=0.5)
    original = {"CN_EQ": 0.25, "HK_EQ": 0.10, "CN_BOND": 0.20, "CASH": 0.10}
    total = sum(original.values())
    strategic = {key: value / total for key, value in original.items()}
    allocation = allocate(
        scores,
        strategic,
        max_tilt=0.10,
        min_weight=0.0,
        max_weight=0.5,
        health=all(item.score is not None for item in scores.values()),
        as_of=shadow["market"]["as_of"],
        data_cutoff=shadow["macro"]["data_cutoff"],
        model_version="local_experiment_allocation_v0.1",
    )

    def serial(value):
        if isinstance(value, (date, datetime, pd.Timestamp)):
            return value.isoformat()
        if hasattr(value, "__dict__"):
            return {key: serial(item) for key, item in value.__dict__.items()}
        if isinstance(value, dict):
            return {key: serial(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [serial(item) for item in value]
        return value

    result = {
        "status": "LOCAL_EXPERIMENT_ACTIVE",
        "usage_status": "LOCAL_EXPERIMENT",
        "scope": ["CN_EQ", "HK_EQ", "CN_BOND", "CASH"],
        "excluded_assets": ["US_EQ", "GOLD", "COMMODITY"],
        "strategic_weights_renormalized": strategic,
        "asset_scores": serial(scores),
        "allocation": serial(allocation),
        "market": shadow["market"],
        "macro": shadow["macro"],
        "style": shadow["style"],
        "local_only": True,
        "no_broker_connection": True,
        "no_order_generation": True,
        "production_ready": False,
        "formal_observations_written": 0,
        "warnings": [
            "legal/reviewer/repeatability gates intentionally bypassed for local experiment",
            "conservative synthetic available_at is not actual release evidence",
            "weights are experimental outputs and not investment advice",
        ],
    }
    if persist:
        if store is None:
            raise ValueError("store is required when persist=True")
        from pathlib import Path

        from cross_asset.storage.experiment import persist_local_experiment
        from cross_asset.storage.provenance import code_version, config_hash

        frame = load_wind_engineering_frame(connection, decision_time=decision_time)
        snapshot_rows = [
            {
                "series_id": row.series_id,
                "source": "wind_manual",
                "source_series_id": row.source_series_id,
                "observation_date": row.observation_date,
                "value": row.value,
                "available_at": row.available_at,
                "raw_hash": row.source_file_sha256,
            }
            for row in frame.itertuples(index=False)
        ]
        root = Path(project_root)
        config_paths = [
            root / "config" / name
            for name in ("series.yml", "macro.yml", "factors.yml", "allocation.yml", "sources.yml")
        ]
        persistence = persist_local_experiment(
            store,
            result=result,
            snapshot_rows=snapshot_rows,
            decision_time=pd.Timestamp(result["market"]["as_of"]).to_pydatetime(),
            config_hash=config_hash([path for path in config_paths if path.exists()]),
            code_version=code_version(root),
        )
        result["persistence"] = persistence
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


__all__ = [
    "load_wind_engineering_frame",
    "run_wind_evidence_shadow",
    "run_wind_local_experiment",
]
