"""Climate derivation helpers (Issue #114 Scope A).

Two top-level concepts instead of one misleading number: Macro Climate
(growth/inflation state + direction) and Investment Climate
(liquidity/financial conditions/risk appetite/market confirmation overlay).
Both derive only from horizon-separated aggregates.
"""

from .enums import AxisDirection
from .horizon import HorizonAggregate
from .snapshot import ClimateState


def _direction_from_delta(delta: float | None, *, deadband: float = 0.05) -> AxisDirection:
    if delta is None or abs(delta) <= deadband:
        return AxisDirection.FLAT
    return AxisDirection.RISING if delta > 0 else AxisDirection.FALLING


def derive_macro_climate(
    growth: HorizonAggregate,
    inflation: HorizonAggregate,
    *,
    growth_weekly_delta: float | None = None,
    inflation_weekly_delta: float | None = None,
    summary: str = "",
) -> ClimateState:
    """Macro climate from CYCLICAL growth and inflation aggregates only."""
    scores = [s for s in (growth.score, inflation.score) if s is not None]
    score = round(sum(scores) / len(scores), 4) if scores else None
    confidence = min(growth.confidence, inflation.confidence)
    coverage = min(growth.coverage, inflation.coverage)
    direction = _direction_from_delta(
        None if growth_weekly_delta is None else growth_weekly_delta
    )
    return ClimateState(
        state=f"GROWTH={growth.score if growth.score is not None else 'MISSING'}|"
        f"INFLATION={inflation.score if inflation.score is not None else 'MISSING'}",
        direction=direction,
        score=score,
        confidence=confidence,
        coverage=coverage,
        summary=summary,
    )


def derive_investment_climate(
    financial_conditions: HorizonAggregate,
    risk_appetite: HorizonAggregate,
    market_confirmation: HorizonAggregate,
    *,
    weekly_delta: float | None = None,
    summary: str = "",
) -> ClimateState:
    """Investment climate from TACTICAL aggregates only (same horizon class)."""
    scores = [
        s
        for s in (
            financial_conditions.score,
            risk_appetite.score,
            market_confirmation.score,
        )
        if s is not None
    ]
    score = round(sum(scores) / len(scores), 4) if scores else None
    coverage = min(
        financial_conditions.coverage,
        risk_appetite.coverage,
        market_confirmation.coverage,
    )
    confidence = min(
        financial_conditions.confidence,
        risk_appetite.confidence,
        market_confirmation.confidence,
    )
    if score is None:
        state = "UNDEFINED"
    elif score > 0.25:
        state = "RISK_ON"
    elif score < -0.25:
        state = "RISK_OFF"
    else:
        state = "NEUTRAL"
    return ClimateState(
        state=state,
        direction=_direction_from_delta(weekly_delta),
        score=score,
        confidence=confidence,
        coverage=coverage,
        summary=summary,
    )
