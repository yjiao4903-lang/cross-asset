"""Transparent, development-prior style axis engine."""

from dataclasses import dataclass, field
from typing import Any, ClassVar

import pandas as pd

from cross_asset.features.relative import relative_trend


@dataclass
class StyleAxisResult:
    axis: str
    status: str
    score: float | None = None
    confidence: float = 0.0
    contributions: dict[str, float] = field(default_factory=dict)
    data_cutoff: Any = None
    model_version: str = "style_v0.1"
    semantic_definition: str = ""
    prior: str = "DEVELOPMENT_PRIOR"


class StyleEngine:
    WEIGHTS: ClassVar[dict[str, float]] = {
        "relative_trend": 0.50,
        "macro": 0.30,
        "risk_appetite": 0.20,
    }

    def __init__(
        self, definitions: dict[str, dict[str, Any]] | None = None, model_version="style_v0.1"
    ):
        self.definitions = definitions or {}
        self.model_version = model_version

    def compute_axis(
        self,
        axis: str,
        *,
        lhs: pd.Series | None = None,
        rhs: pd.Series | None = None,
        macro=None,
        risk_appetite=None,
        data_cutoff=None,
    ) -> StyleAxisResult:
        definition = self.definitions.get(axis)
        if not definition or not definition.get("semantic_definition"):
            return StyleAxisResult(axis, "UNAVAILABLE", model_version=self.model_version)
        if lhs is None or rhs is None:
            return StyleAxisResult(
                axis,
                "UNAVAILABLE",
                model_version=self.model_version,
                semantic_definition=definition["semantic_definition"],
            )
        rel = relative_trend(lhs, rhs)
        available = {
            "relative_trend": rel.iloc[-1].dropna().mean() if not rel.empty else None,
            "macro": _last(macro),
            "risk_appetite": _last(risk_appetite),
        }
        present = {k: v for k, v in available.items() if v is not None and pd.notna(v)}
        if not present:
            return StyleAxisResult(
                axis,
                "UNAVAILABLE",
                model_version=self.model_version,
                semantic_definition=definition["semantic_definition"],
            )
        total = sum(self.WEIGHTS[k] for k in present)
        contributions = {k: float(v) * self.WEIGHTS[k] / total for k, v in present.items()}
        raw_score = sum(contributions.values())
        score = max(-2.0, min(2.0, raw_score))
        if raw_score and score != raw_score:
            scale = score / raw_score
            contributions = {k: v * scale for k, v in contributions.items()}
        return StyleAxisResult(
            axis,
            "AVAILABLE",
            score,
            float(len(present) / 3),
            contributions,
            data_cutoff or lhs.index[-1],
            self.model_version,
            definition["semantic_definition"],
        )

    def build(
        self, inputs: dict[str, dict[str, Any]], *, data_cutoff=None
    ) -> dict[str, StyleAxisResult]:
        return {
            axis: self.compute_axis(axis, data_cutoff=data_cutoff, **values)
            for axis, values in inputs.items()
        }


def _last(value):
    if value is None:
        return None
    if isinstance(value, pd.Series):
        return value.dropna().iloc[-1] if not value.dropna().empty else None
    return value
