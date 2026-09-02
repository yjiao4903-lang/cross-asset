"""Deterministic offline full-pipeline snapshot used by the golden gate."""

from datetime import UTC, datetime, timedelta

import pandas as pd

from .replay import FullModelStrategy

DECISION = pd.Timestamp("2025-12-31", tz="UTC")


def fixed_fixture():
    rows = []
    start = datetime(2025, 11, 25, tzinfo=UTC)
    for i in range(37):
        day = start + timedelta(days=i)
        for asset, base, slope in (("A", 100.0, 0.8), ("B", 100.0, 0.1)):
            rows.append(
                {
                    "series_id": asset,
                    "observation_date": day.date(),
                    "available_at": day,
                    "value": base + slope * i,
                }
            )
    rows.append(
        {
            "series_id": "MACRO_GROWTH",
            "observation_date": datetime(2025, 11, 30, tzinfo=UTC).date(),
            "available_at": datetime(2025, 12, 15, 9, tzinfo=UTC),
            "value": 0.5,
        }
    )
    return pd.DataFrame(rows)


def _number(value):
    if value is None or pd.isna(value):
        return None
    return round(float(value), 10)


def snapshot(observations=None):
    strategy = FullModelStrategy(
        ["A", "B"],
        macro_config={
            "series": {"MACRO_GROWTH": {"transform": {"type": "level"}}},
            "dimensions": {"GROWTH": ["MACRO_GROWTH"], "POLICY": ["MISSING_POLICY"]},
        },
    )
    info = observations.copy() if observations is not None else fixed_fixture()
    info["_available"] = pd.to_datetime(info["available_at"], utc=True)
    info = info[info["_available"] <= DECISION].drop(columns="_available")
    weights = strategy(info, DECISION.to_pydatetime())
    record = strategy.last_decision
    market = record["market_state"]
    macro = record["macro_state"]
    style = record["style_state"]
    scores = record["asset_scores"]
    allocation = record["allocation"]
    return {
        "market_state": {
            "model_version": market.model_version,
            "data_cutoff": str(DECISION),
            "status": "AVAILABLE" if market.assets else "UNAVAILABLE",
            "fixture": True,
            "assets": {
                k: {"available": bool(v.get("available")), "trend": {x: _number(y) for x, y in v["trend"].items()}}
                for k, v in sorted(market.assets.items())
            },
            "unavailable": sorted(market.unavailable),
        },
        "macro_state": {
            "model_version": macro.model_version,
            "data_cutoff": str(macro.data_cutoff),
            "status": "AVAILABLE" if macro.score is not None else "UNAVAILABLE",
            "fixture": True,
            "score": _number(macro.score),
            "confidence": _number(macro.confidence),
            "dimensions": {
                k: {"score": _number(v.score), "confidence": _number(v.confidence), "coverage": _number(v.coverage), "contributions": {x: _number(y) for x, y in sorted(v.contributions.items())}}
                for k, v in sorted(macro.dimensions.items())
            },
        },
        "style_state": {
            "model_version": strategy.style_engine.model_version,
            "data_cutoff": str(DECISION),
            "status": "UNAVAILABLE",
            "fixture": True,
            "axes": {k: {"status": v.status, "score": _number(v.score), "confidence": _number(v.confidence), "contributions": v.contributions} for k, v in sorted(style.items())},
        },
        "asset_scores": {
            "model_version": "asset_score_v0.1",
            "data_cutoff": str(DECISION),
            "status": "AVAILABLE",
            "fixture": True,
            "scores": {k: {"score": _number(v.score), "confidence": _number(v.confidence), "contributions": {x: _number(y) for x, y in sorted(v.contributions.items())}} for k, v in sorted(scores.items())},
        },
        "allocation": {
            "model_version": allocation.model_version,
            "data_cutoff": str(DECISION),
            "status": allocation.status,
            "fixture": True,
            "prior": "DEVELOPMENT_PRIOR",
            "weights": {k: _number(v) for k, v in sorted(weights.items())},
            "attribution": {
                asset: {
                    key: _number(value)
                    for key, value in sorted(values.items())
                }
                for asset, values in sorted(allocation.attribution.items())
            },
        },
    }
