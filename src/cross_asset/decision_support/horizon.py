"""Horizon model (Issue #114 Scope B).

Every factor/subfactor declares a horizon class. No aggregation function may
silently average CYCLICAL and TACTICAL inputs into one generic macro score.
STRUCTURAL_CONTEXT inputs are display/context only and can never be aggregated
into a macro score at all.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from .enums import HorizonClass

_SCORE_MIN = -2.0
_SCORE_MAX = 2.0


class HorizonMixingError(ValueError):
    """Raised when a function would silently mix incompatible horizon classes."""


class SubfactorScore(BaseModel):
    """A scored subfactor at a point in time.

    score lives in [-2, +2]. A missing subfactor must be represented as
    ``missing=True`` with ``score=None`` — never zero-filled.
    """

    model_config = ConfigDict(extra="forbid")

    factor_id: str
    horizon: HorizonClass
    score: float | None = None
    confidence: float = 1.0
    coverage: float = 1.0
    missing: bool = False
    stale: bool = False
    note: str = ""

    def resolved_horizon(self) -> HorizonClass:
        return HorizonClass(self.horizon)

    def effective_score(self) -> float:
        """Score with missing handled explicitly; never silently zero."""
        if self.missing or self.score is None:
            raise ValueError(f"subfactor {self.factor_id} is missing; no score exists")
        return self.score


def separate_by_horizon(
    scores: Sequence[SubfactorScore],
) -> dict[HorizonClass, list[SubfactorScore]]:
    """Split scored subfactors into horizon-separated groups."""
    groups: dict[HorizonClass, list[SubfactorScore]] = {}
    for entry in scores:
        groups.setdefault(entry.resolved_horizon(), []).append(entry)
    return groups


def aggregate_horizon(
    scores: Sequence[SubfactorScore],
    *,
    horizon: HorizonClass,
    clip: float = 2.0,
) -> tuple[float | None, float]:
    """Aggregate a homogeneous-horizon set of subfactor scores.

    Returns ``(score, coverage)`` where ``score`` is ``None`` when no scored
    input exists (missing is preserved, not zero-filled) and ``coverage`` is
    the fraction of scored inputs relative to all declared inputs.

    Raises:
        HorizonMixingError: if any input horizon differs from ``horizon`` or
            if STRUCTURAL_CONTEXT inputs are submitted for macro aggregation.
    """
    usable: list[SubfactorScore] = []
    for entry in scores:
        entry_horizon = entry.resolved_horizon()
        if entry_horizon is HorizonClass.STRUCTURAL_CONTEXT:
            raise HorizonMixingError(
                "STRUCTURAL_CONTEXT inputs are display/context only and may not "
                f"be aggregated into a macro score (got {entry.factor_id})"
            )
        if entry_horizon is not horizon:
            raise HorizonMixingError(
                f"horizon mixing rejected: expected {horizon.value} but "
                f"{entry.factor_id} is {entry_horizon.value}"
            )
        usable.append(entry)

    scored = [e for e in usable if not e.missing and e.score is not None]
    if not scored:
        return None, 0.0
    mean = sum(e.score for e in scored) / len(scored)  # type: ignore[misc]
    mean = max(min(mean, clip), -clip)
    coverage = len(scored) / len(usable) if usable else 0.0
    return round(mean, 4), round(coverage, 4)


class HorizonAggregate(BaseModel):
    """Result of aggregating one horizon class of a cluster."""

    model_config = ConfigDict(extra="forbid")

    horizon: HorizonClass
    score: float | None = None
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    contributors: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    stale: list[str] = Field(default_factory=list)


def aggregate_context(
    scores: Sequence[SubfactorScore],
) -> HorizonAggregate:
    """Aggregate STRUCTURAL_CONTEXT inputs for display/context only.

    This never feeds a macro score; it exists so valuation overlays can be
    rendered as context. Requires every input to be STRUCTURAL_CONTEXT.
    """
    for entry in scores:
        if entry.resolved_horizon() is not HorizonClass.STRUCTURAL_CONTEXT:
            raise HorizonMixingError(
                "aggregate_context accepts STRUCTURAL_CONTEXT inputs only, got "
                f"{entry.factor_id} ({entry.resolved_horizon().value})"
            )
    scored = [e for e in scores if not e.missing and e.score is not None]
    score = (
        round(sum(e.score for e in scored) / len(scored), 4) if scored else None  # type: ignore[misc]
    )
    coverage = len(scored) / len(scores) if scores else 0.0
    confidence = (
        sum(e.confidence for e in scored) / len(scored) * coverage if scored else 0.0
    )
    return HorizonAggregate(
        horizon=HorizonClass.STRUCTURAL_CONTEXT,
        score=score,
        coverage=round(coverage, 4),
        confidence=round(max(min(confidence, 1.0), 0.0), 4),
        contributors=[e.factor_id for e in scored],
        missing=[e.factor_id for e in scores if e.missing],
        stale=[e.factor_id for e in scores if e.stale],
    )


def aggregate_cluster_horizon(
    scores: Sequence[SubfactorScore],
    *,
    horizon: HorizonClass,
) -> HorizonAggregate:
    """Aggregate one horizon class, preserving missing/stale as blockers."""
    for entry in scores:
        entry_horizon = entry.resolved_horizon()
        if entry_horizon is not horizon:
            raise HorizonMixingError(
                f"horizon mixing rejected: expected {horizon.value} but "
                f"{entry.factor_id} is {entry_horizon.value}"
            )
    score, coverage = aggregate_horizon(scores, horizon=horizon)
    scored = [e for e in scores if not e.missing and e.score is not None]
    confidence = (
        sum(e.confidence for e in scored) / len(scored) * coverage if scored else 0.0
    )
    return HorizonAggregate(
        horizon=horizon,
        score=score,
        coverage=round(coverage, 4),
        confidence=round(max(min(confidence, 1.0), 0.0), 4),
        contributors=[e.factor_id for e in scored],
        missing=[e.factor_id for e in scores if e.missing],
        stale=[e.factor_id for e in scores if e.stale],
    )
