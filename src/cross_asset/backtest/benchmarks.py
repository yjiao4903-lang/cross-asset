"""Deterministic benchmark contracts; no parameter calibration is implied."""
from __future__ import annotations

import pandas as pd


def _metadata(series, name, inputs, parameters, protocol_version, config_hash, unavailable=False, reason=None):
    series.attrs.update({"benchmark": name, "inputs_used": list(inputs), "parameters": parameters or {}, "protocol_version": protocol_version, "config_hash": config_hash, "unavailable": unavailable, "reason": reason})
    return series


def static_allocation(_info, _decision, weights=None, *, protocol_version="research_v0.1", config_hash=None, parameters=None):
    return _metadata(pd.Series(weights or {}, dtype=float), "STATIC", ("strategic_weights",), parameters, protocol_version, config_hash)


def trend_only(info, _decision, *, protocol_version="research_v0.1", config_hash=None, parameters=None):
    weights = info.get("weights", {}) if isinstance(info, dict) else {}
    return _metadata(pd.Series(weights, dtype=float), "TREND_ONLY", ("trend",), parameters, protocol_version, config_hash, not bool(weights), "mapping_unavailable" if not weights else None)


def full_model(info, _decision, *, protocol_version="research_v0.1", config_hash=None, parameters=None):
    weights = info.get("weights", {}) if isinstance(info, dict) else {}
    return _metadata(pd.Series(weights, dtype=float), "FULL_MODEL", ("full_model",), parameters, protocol_version, config_hash, not bool(weights), "mapping_unavailable" if not weights else None)


def macro_only(info, _decision, assets=None, *, strategic_weights=None, protocol_version="research_v0.1", config_hash=None, parameters=None):
    mapping = info.get("macro_weights") if isinstance(info, dict) else None
    if not isinstance(mapping, dict) or not mapping:
        mapping = strategic_weights or {asset: 1 / len(assets) for asset in (assets or [])}
        return _metadata(pd.Series(mapping, dtype=float), "MACRO_ONLY", ("macro_weights",), parameters, protocol_version, config_hash, True, "mapping_unavailable")
    result = pd.Series({asset: float(mapping.get(asset, 0.0)) for asset in assets or mapping}, dtype=float)
    total = result.sum()
    if total <= 0:
        return _metadata(result, "MACRO_ONLY", ("macro_weights",), parameters, protocol_version, config_hash, True, "mapping_unavailable")
    return _metadata(result / total, "MACRO_ONLY", ("macro_weights",), parameters, protocol_version, config_hash)


def risk_only(info, _decision, assets=None, *, strategic_weights=None, protocol_version="research_v0.1", config_hash=None, parameters=None):
    mapping = info.get("volatility", info.get("risk_scores")) if isinstance(info, dict) else None
    if not isinstance(mapping, dict) or not mapping or any(float(mapping.get(asset, 0)) <= 0 for asset in (assets or mapping)):
        fallback = strategic_weights or {asset: 1 / len(assets) for asset in (assets or [])}
        return _metadata(pd.Series(fallback, dtype=float), "RISK_ONLY", ("volatility", "risk_scores"), parameters, protocol_version, config_hash, True, "mapping_unavailable")
    result = pd.Series({asset: 1.0 / float(mapping[asset]) for asset in assets or mapping}, dtype=float)
    return _metadata(result / result.sum(), "RISK_ONLY", ("volatility", "risk_scores"), parameters, protocol_version, config_hash)


def make_benchmark(name, assets, *, protocol_version="research_v0.1", config_hash=None, parameters=None, strategic_weights=None):
    name = name.upper()
    if name == "STATIC":
        weights = strategic_weights or ({a: 1 / len(assets) for a in assets} if assets else {})
        return lambda info, decision: static_allocation(info, decision, weights, protocol_version=protocol_version, config_hash=config_hash, parameters=parameters)
    if name == "TREND_ONLY":
        return lambda info, decision: trend_only(info, decision, protocol_version=protocol_version, config_hash=config_hash, parameters=parameters)
    if name == "MACRO_ONLY":
        return lambda info, decision: macro_only(info, decision, assets, strategic_weights=strategic_weights, protocol_version=protocol_version, config_hash=config_hash, parameters=parameters)
    if name == "RISK_ONLY":
        return lambda info, decision: risk_only(info, decision, assets, strategic_weights=strategic_weights, protocol_version=protocol_version, config_hash=config_hash, parameters=parameters)
    if name == "FULL_MODEL":
        return lambda info, decision: full_model(info, decision, protocol_version=protocol_version, config_hash=config_hash, parameters=parameters)
    raise ValueError(f"unknown benchmark: {name}")
