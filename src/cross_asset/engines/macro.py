"""Explainable, point-in-time Macro State v0.2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from cross_asset.features.macro import (
    transform_history,
    transform_series,
    transform_unit_semantics,
)
from cross_asset.features.normalization import latest_causal_zscore


@dataclass(frozen=True)
class MacroDimension:
    score: float | None
    confidence: float
    coverage: float
    contributions: dict[str, float | None] = field(default_factory=dict)
    raw_contributions: dict[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class MacroState:
    as_of: datetime
    dimensions: dict[str, MacroDimension]
    score: float | None
    confidence: float
    data_cutoff: datetime
    model_version: str = "macro_v0.2"

    def __getitem__(self, key):
        return self.dimensions[key]


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key)


def _utc(value):
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _latest_revision_snapshot(rows):
    """Keep the latest released revision for each observation date."""

    selected = {}
    for row in rows:
        key = _get(row, "observation_date")
        available = _utc(_get(row, "available_at"))
        current = selected.get(key)
        if current is None or available > _utc(_get(current, "available_at")):
            selected[key] = row
    return sorted(selected.values(), key=lambda row: _get(row, "observation_date"))


def _validated_definition(series_id, definition):
    """Fail closed when a formal active macro input has unresolved semantics."""

    semantics = transform_unit_semantics(definition)
    if not semantics.resolved:
        raise ValueError(
            "macro_unit_semantics_unresolved: "
            f"series_id={series_id}; reason={semantics.reason}; "
            f"transform={semantics.transform_type}; raw_unit={semantics.raw_unit}; "
            f"derived_unit={semantics.derived_unit}"
        )
    return definition


def _normalized_value(rows, definition):
    transform = (definition or {}).get("transform", {})
    raw = transform_series(rows, transform)
    if not raw.available:
        return raw.value, None

    normalization = (definition or {}).get("normalization", {}) or {}
    method = normalization.get("method", "none")
    if method in {"none", None}:
        return raw.value, raw.value
    if method != "causal_zscore":
        raise ValueError(f"unsupported macro normalization: {method}")

    history = transform_history(rows, transform)
    score = latest_causal_zscore(
        history,
        min_history=int(normalization.get("min_history", 20)),
        window=normalization.get("window"),
        clip=float(normalization.get("clip", 2.0)),
    )
    return raw.value, score


def build_macro_state(
    observations,
    decision_time,
    config=None,
    *,
    model_version="macro_v0.2",
    stale_after_hours=168,
):
    cfg = config or {}
    definitions = cfg.get("series", cfg)
    dims = cfg.get("dimensions", {})
    enforce_unit_semantics = bool(cfg.get("enforce_unit_semantics", False))
    requested_series = {
        str(series_id)
        for ids in dims.values()
        for series_id in ids
    }
    decision_time = _utc(decision_time)
    released = [
        observation
        for observation in observations
        if _utc(_get(observation, "available_at")) <= decision_time
        and _get(observation, "series_id") in requested_series
    ]

    by_series = {}
    for observation in released:
        by_series.setdefault(_get(observation, "series_id"), []).append(observation)
    by_series = {
        series_id: _latest_revision_snapshot(rows)
        for series_id, rows in by_series.items()
    }

    contributions = {}
    raw_contributions = {}
    freshness_by_series = {}
    for series_id, rows in by_series.items():
        definition = definitions.get(series_id, {}) or {}
        if enforce_unit_semantics:
            definition = _validated_definition(series_id, definition)
        raw_value, score = _normalized_value(rows, definition)
        raw_contributions[series_id] = raw_value
        contributions[series_id] = score
        if rows:
            latest_available = max(_utc(_get(row, "available_at")) for row in rows)
            age = (decision_time - latest_available).total_seconds() / 3600
            series_stale_hours = float(definition.get("stale_after_hours", stale_after_hours))
            freshness_by_series[series_id] = max(
                0.0,
                min(1.0, 1 - age / series_stale_hours),
            )

    out = {}
    for name, ids in dims.items():
        present_ids = [
            series_id
            for series_id in ids
            if contributions.get(series_id) is not None
        ]
        vals = [contributions[series_id] for series_id in present_ids]
        coverage = len(vals) / len(ids) if ids else 0.0
        score = max(-2.0, min(2.0, sum(vals) / len(vals))) if vals else None
        agreement = (
            abs(sum(1 if value >= 0 else -1 for value in vals)) / len(vals)
            if vals
            else 0.0
        )
        fresh = (
            sum(freshness_by_series.get(series_id, 0.0) for series_id in present_ids)
            / len(present_ids)
            if present_ids
            else 0.0
        )
        out[name] = MacroDimension(
            score=score,
            confidence=coverage * fresh * agreement,
            coverage=coverage,
            contributions={series_id: contributions.get(series_id) for series_id in ids},
            raw_contributions={
                series_id: raw_contributions.get(series_id) for series_id in ids
            },
        )

    available = [dimension.score for dimension in out.values() if dimension.score is not None]
    return MacroState(
        as_of=decision_time,
        dimensions=out,
        score=sum(available) / len(available) if available else None,
        confidence=sum(dimension.confidence for dimension in out.values()) / len(out)
        if out
        else 0.0,
        data_cutoff=max(
            (_utc(_get(observation, "available_at")) for observation in released),
            default=decision_time,
        ),
        model_version=model_version,
    )


build_macro = build_macro_state

__all__ = ["MacroDimension", "MacroState", "build_macro", "build_macro_state"]
