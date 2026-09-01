"""Explainable Macro State v0.1."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from cross_asset.features.macro import transform_series


@dataclass(frozen=True)
class MacroDimension:
    score: float | None
    confidence: float
    coverage: float
    contributions: dict[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class MacroState:
    as_of: datetime
    dimensions: dict[str, MacroDimension]
    score: float | None
    confidence: float
    data_cutoff: datetime
    model_version: str = "macro_v0.1"

    def __getitem__(self, key):
        return self.dimensions[key]


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key)


def _utc(value):
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def build_macro_state(
    observations, decision_time, config=None, *, model_version="macro_v0.1", stale_after_hours=168
):
    cfg = config or {}
    definitions = cfg.get("series", cfg)
    dims = cfg.get("dimensions", {})
    decision_time = _utc(decision_time)
    released = [o for o in observations if _utc(_get(o, "available_at")) <= decision_time]
    by_series = {}
    for o in released:
        by_series.setdefault(_get(o, "series_id"), []).append(o)
    contributions = {}
    freshness = []
    for sid, rows in by_series.items():
        t = (definitions.get(sid, {}) or {}).get("transform", {})
        result = transform_series(rows, t)
        contributions[sid] = result.value
        if rows:
            age = (
                decision_time
                - _get(max(rows, key=lambda x: _get(x, "available_at")), "available_at")
            ).total_seconds() / 3600
            freshness.append(max(0.0, min(1.0, 1 - age / stale_after_hours)))
    out = {}
    for name, ids in dims.items():
        vals = [contributions.get(i) for i in ids if contributions.get(i) is not None]
        coverage = len(vals) / len(ids) if ids else 0.0
        score = max(-2.0, min(2.0, sum(vals) / len(vals))) if vals else None
        agreement = (abs(sum(1 if v >= 0 else -1 for v in vals)) / len(vals)) if vals else 0.0
        fresh = sum(freshness) / len(freshness) if freshness else 0.0
        out[name] = __import__(
            "cross_asset.engines.macro", fromlist=["MacroDimension"]
        ).MacroDimension(
            score, coverage * fresh * agreement, coverage, {i: contributions.get(i) for i in ids}
        )
    available = [d.score for d in out.values() if d.score is not None]
    return MacroState(
        decision_time,
        out,
        sum(available) / len(available) if available else None,
        sum(d.confidence for d in out.values()) / len(out) if out else 0.0,
        max((_get(o, "available_at") for o in released), default=decision_time),
        model_version,
    )


build_macro = build_macro_state
