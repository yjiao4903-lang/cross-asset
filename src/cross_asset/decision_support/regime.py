"""Interpretable regime V0 (Issue #114 Scope E).

Only interpretable logic is implemented: growth state + direction, inflation
state + direction, navigation quadrant label, dwell/hysteresis, transition
flag, confidence/coverage and lens disagreement. No HMM/Markov probabilities
in P0.
"""


from .enums import (
    AxisDirection,
    GrowthState,
    InflationState,
    QuadrantLabel,
)
from .snapshot import LensDisagreement, RegimeState


def _axis_up_down(score: float, threshold: float) -> tuple[bool, bool]:
    return score > threshold, score < -threshold


class RegimeEngine:
    """Deterministic regime engine with deadband hysteresis and dwell.

    ``update`` is called once per weekly step in order. The quadrant may only
    switch after a candidate quadrant has been observed on
    ``min_dwell_weeks`` consecutive weekly steps (dwell hysteresis), and axes
    inside the deadband inherit the prior state instead of flipping (deadband
    hysteresis). Identical input sequences therefore produce identical output
    sequences.
    """

    def __init__(
        self,
        *,
        axis_threshold: float = 0.25,
        min_dwell_weeks: int = 3,
        lens_disagreement_threshold: float = 1.0,
    ) -> None:
        self.axis_threshold = axis_threshold
        self.min_dwell_weeks = min_dwell_weeks
        self.lens_disagreement_threshold = lens_disagreement_threshold
        self._pending_quadrant: QuadrantLabel | None = None
        self._pending_weeks = 0

    def candidate_quadrant(
        self,
        growth_score: float,
        inflation_score: float,
        prior: RegimeState | None = None,
    ) -> QuadrantLabel:
        prior_quadrant = (
            prior.resolved_quadrant() if prior is not None else QuadrantLabel.GOLDILOCKS
        )
        growth_up, growth_down = _axis_up_down(growth_score, self.axis_threshold)
        inflation_up, inflation_down = _axis_up_down(inflation_score, self.axis_threshold)
        if not growth_up and not growth_down:
            growth_up = prior_quadrant in {
                QuadrantLabel.GOLDILOCKS,
                QuadrantLabel.REFLATION,
            }
            growth_down = not growth_up
        if not inflation_up and not inflation_down:
            inflation_up = prior_quadrant in {
                QuadrantLabel.REFLATION,
                QuadrantLabel.STAGFLATION_RISK,
            }
            inflation_down = not inflation_up
        if growth_up and inflation_down:
            return QuadrantLabel.GOLDILOCKS
        if growth_up and inflation_up:
            return QuadrantLabel.REFLATION
        if growth_down and inflation_up:
            return QuadrantLabel.STAGFLATION_RISK
        return QuadrantLabel.DISINFLATIONARY_SLUMP

    def update(
        self,
        *,
        growth_score: float,
        growth_direction: AxisDirection | str,
        inflation_score: float,
        inflation_direction: AxisDirection | str,
        inflation_state: InflationState | str,
        prior: RegimeState | None = None,
        confidence: float = 0.0,
        coverage: float = 0.0,
        lens_disagreement: LensDisagreement | None = None,
    ) -> RegimeState:
        candidate = self.candidate_quadrant(growth_score, inflation_score, prior)

        growth_resolved_state = self._state_with_stickiness(
            score=growth_score,
            high=GrowthState.EXPANDING,
            low=GrowthState.CONTRACTING,
            middle=GrowthState.STABLE,
            prior_state=(
                GrowthState(prior.growth_state) if prior is not None else GrowthState.STABLE
            ),
        )
        inflation_resolved_state = InflationState(inflation_state)

        if prior is None:
            self._pending_quadrant = None
            self._pending_weeks = 0
            quadrant, dwell_weeks, transition = candidate, 1, False
        elif candidate is prior.resolved_quadrant():
            self._pending_quadrant = None
            self._pending_weeks = 0
            quadrant, dwell_weeks, transition = candidate, prior.dwell_weeks + 1, False
        else:
            if self._pending_quadrant is candidate:
                self._pending_weeks += 1
            else:
                self._pending_quadrant = candidate
                self._pending_weeks = 1
            if self._pending_weeks >= self.min_dwell_weeks:
                quadrant, dwell_weeks, transition = candidate, 1, True
                self._pending_quadrant = None
                self._pending_weeks = 0
            else:
                quadrant = prior.resolved_quadrant()
                dwell_weeks = prior.dwell_weeks + 1
                transition = False

        return RegimeState(
            quadrant_label=quadrant,
            growth_state=growth_resolved_state,
            growth_direction=AxisDirection(growth_direction),
            inflation_state=inflation_resolved_state,
            inflation_direction=AxisDirection(inflation_direction),
            dwell_weeks=dwell_weeks,
            transition_flag=transition,
            confidence=max(min(confidence, 1.0), 0.0),
            coverage=max(min(coverage, 1.0), 0.0),
            lens_disagreement=lens_disagreement or LensDisagreement(),
        )

    def _state_with_stickiness(
        self,
        *,
        score: float,
        high: object,
        low: object,
        middle: object,
        prior_state: object,
    ) -> object:
        if score > self.axis_threshold:
            return high
        if score < -self.axis_threshold:
            return low
        return prior_state if prior_state is not None else middle


def evaluate_lens_disagreement(
    lens_scores: dict[str, float],
    *,
    threshold: float | None = None,
    engine: RegimeEngine | None = None,
) -> LensDisagreement:
    """Flag disagreement when growth lenses diverge beyond the threshold."""
    resolved_threshold = (
        threshold if threshold is not None else (engine.lens_disagreement_threshold if engine else 1.0)
    )
    values = list(lens_scores.values())
    if len(values) < 2:
        return LensDisagreement(flag=False, summary="insufficient lenses for disagreement")
    spread = max(values) - min(values)
    if spread > resolved_threshold:
        names = ", ".join(sorted(lens_scores))
        return LensDisagreement(
            flag=True,
            summary=f"growth lens spread {spread:.2f} exceeds {resolved_threshold:.2f} ({names})",
        )
    return LensDisagreement(flag=False, summary="growth lenses aligned")
