"""Missing-aware, explainable cross-asset score aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

COMPONENT_WEIGHTS = {
    "macro": 0.25,
    "trend": 0.30,
    "valuation": 0.15,
    "carry": 0.10,
    "risk": 0.10,
    "structure": 0.10,
}
ASSETS = ("CN_EQ", "HK_EQ", "US_EQ", "CN_BOND", "GOLD", "COMMODITY", "CASH")


def confidence_score(coverage, freshness, agreement, health=1.0):
    """Confidence is a data/signal-quality score, never an earnings probability."""

    return max(
        0.0,
        min(
            1.0,
            float(coverage) * float(freshness) * float(agreement) * float(health),
        ),
    )


@dataclass(frozen=True)
class AssetScore:
    asset_id: str
    score: float | None
    confidence: float
    contributions: dict[str, float | None] = field(default_factory=dict)
    coverage: float = 0.0
    missing_components: tuple[str, ...] = ()
    data_cutoff: object = None
    model_version: str = "asset_score_v0.2"


def _component_value(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("score", value.get("value"))
    return getattr(value, "score", getattr(value, "value", value))


def _component_confidence(value):
    if value is None:
        return 0.0
    if isinstance(value, dict):
        confidence = value.get("confidence", 1.0)
    else:
        confidence = getattr(value, "confidence", 1.0)
    return max(0.0, min(1.0, float(confidence)))


def _validated_weights(component_weights: Mapping[str, float] | None):
    weights = dict(component_weights or COMPONENT_WEIGHTS)
    unknown = set(weights) - set(COMPONENT_WEIGHTS)
    if unknown:
        raise ValueError(f"unknown asset-score components: {sorted(unknown)}")
    if not weights or any(float(value) <= 0 for value in weights.values()):
        raise ValueError("component weights must be positive")
    return weights


def score_asset(
    asset_id,
    components,
    *,
    confidence=None,
    component_weights: Mapping[str, float] | None = None,
    required_components=(),
    data_cutoff=None,
    model_version="asset_score_v0.2",
):
    weights = _validated_weights(component_weights)
    vals = {name: _component_value(components.get(name)) for name in weights}
    missing = tuple(name for name, value in vals.items() if value is None)
    required_missing = [name for name in required_components if vals.get(name) is None]
    available = {name: value for name, value in vals.items() if value is not None}
    total_weight = sum(float(value) for value in weights.values())
    coverage = (
        sum(float(weights[name]) for name in available) / total_weight
        if total_weight
        else 0.0
    )

    if not available or required_missing:
        return AssetScore(
            asset_id=asset_id,
            score=None,
            confidence=0.0,
            contributions={name: None for name in weights},
            coverage=coverage,
            missing_components=missing,
            data_cutoff=data_cutoff,
            model_version=model_version,
        )

    available_weight = sum(float(weights[name]) for name in available)
    contributions = {
        name: max(-2.0, min(2.0, float(value)))
        * float(weights[name])
        / available_weight
        for name, value in available.items()
    }
    raw_score = sum(contributions.values())
    score = max(-2.0, min(2.0, raw_score))
    if raw_score and score != raw_score:
        scale = score / raw_score
        contributions = {name: value * scale for name, value in contributions.items()}
    contributions.update({name: None for name in weights if name not in contributions})

    quality = sum(
        _component_confidence(components.get(name)) * float(weights[name])
        for name in available
    ) / available_weight
    base_confidence = 1.0 if confidence is None else max(0.0, min(1.0, float(confidence)))
    final_confidence = max(0.0, min(1.0, coverage * quality * base_confidence))
    return AssetScore(
        asset_id=asset_id,
        score=score,
        confidence=final_confidence,
        contributions=contributions,
        coverage=coverage,
        missing_components=missing,
        data_cutoff=data_cutoff,
        model_version=model_version,
    )


def compute_asset_score(*args, **kwargs):
    return score_asset(*args, **kwargs)


__all__ = [
    "ASSETS",
    "COMPONENT_WEIGHTS",
    "AssetScore",
    "compute_asset_score",
    "confidence_score",
    "score_asset",
]
