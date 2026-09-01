"""Missing-aware, explainable asset score."""

from dataclasses import dataclass, field

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
    return max(0.0, min(1.0, float(coverage) * float(freshness) * float(agreement) * float(health)))


@dataclass(frozen=True)
class AssetScore:
    asset_id: str
    score: float | None
    confidence: float
    contributions: dict[str, float | None] = field(default_factory=dict)
    data_cutoff: object = None
    model_version: str = "asset_score_v0.1"


def _component_value(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("score", value.get("value"))
    return getattr(value, "score", getattr(value, "value", value))


def score_asset(
    asset_id, components, *, confidence=None, data_cutoff=None, model_version="asset_score_v0.1"
):
    vals = {k: _component_value(components.get(k)) for k in COMPONENT_WEIGHTS}
    available = {k: v for k, v in vals.items() if v is not None}
    if not available:
        return AssetScore(asset_id, None, 0.0, vals, data_cutoff, model_version)
    total_weight = sum(COMPONENT_WEIGHTS[k] for k in available)
    contributions = {
        k: max(-2.0, min(2.0, v)) * COMPONENT_WEIGHTS[k] / total_weight
        for k, v in available.items()
    }
    score = max(-2.0, min(2.0, sum(contributions.values())))
    contributions.update({k: None for k in vals if k not in contributions})
    coverage = len(available) / len(COMPONENT_WEIGHTS)
    base_conf = confidence if confidence is not None else 1.0
    final_conf = max(0.0, min(1.0, coverage * float(base_conf)))
    return AssetScore(asset_id, score, final_conf, contributions, data_cutoff, model_version)


def compute_asset_score(*args, **kwargs):
    return score_asset(*args, **kwargs)
