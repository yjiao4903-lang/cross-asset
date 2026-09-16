"""Climate derivation helpers (Issue #114 Scope A + R1 blocker 4).

Two top-level concepts instead of one misleading number: Macro Climate
(growth/inflation state + direction) and Investment Climate
(liquidity/financial conditions/risk appetite/market confirmation overlay).
Both derive only from horizon-separated aggregates.

``derive_climate_components`` additionally emits the render-ready per-lens
components the frozen Overview needs (policy/liquidity, financial conditions,
market confirmation, risk appetite, investment climate) so the frontend never
composes economic meaning itself.
"""

from .enums import AxisDirection, HorizonClass
from .horizon import HorizonAggregate
from .snapshot import ClimateComponent, ClimateState


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


def _three_state(
    score: float | None,
    *,
    positive: str,
    negative: str,
    threshold: float = 0.25,
) -> str:
    if score is None:
        return "UNAVAILABLE"
    if score > threshold:
        return positive
    if score < -threshold:
        return negative
    return "NEUTRAL"


def derive_climate_components(
    current: dict[tuple[str, HorizonClass], HorizonAggregate],
    previous: dict[tuple[str, HorizonClass], HorizonAggregate],
    investment_climate: ClimateState,
) -> list[ClimateComponent]:
    """Build render-ready Overview lens components from typed aggregates.

    Sign conventions follow the subfactor signs in the taxonomy: positive
    policy/financial-conditions scores mean easing, positive market
    confirmation means trend support, positive risk appetite means risk-on.
    """
    def component(
        name: str,
        family: str,
        horizon: HorizonClass,
        *,
        positive: str,
        negative: str,
    ) -> ClimateComponent:
        aggregate = current.get((family, horizon))
        if aggregate is None or aggregate.score is None:
            return ClimateComponent(
                component=name,
                state="UNAVAILABLE",
                direction=AxisDirection.FLAT,
                score=None,
                confidence=aggregate.confidence if aggregate else 0.0,
                coverage=aggregate.coverage if aggregate else 0.0,
            )
        prior = previous.get((family, horizon))
        delta = (
            round(aggregate.score - prior.score, 4)
            if prior is not None and prior.score is not None
            else None
        )
        return ClimateComponent(
            component=name,
            state=_three_state(aggregate.score, positive=positive, negative=negative),
            direction=_direction_from_delta(delta),
            score=aggregate.score,
            confidence=aggregate.confidence,
            coverage=aggregate.coverage,
        )

    return [
        component(
            "POLICY_LIQUIDITY",
            "POLICY_LIQUIDITY",
            HorizonClass.CYCLICAL,
            positive="EASING",
            negative="TIGHTENING",
        ),
        component(
            "FINANCIAL_CONDITIONS",
            "FINANCIAL_CONDITIONS",
            HorizonClass.TACTICAL,
            positive="EASING",
            negative="TIGHTENING",
        ),
        component(
            "MARKET_CONFIRMATION",
            "MARKET_CONFIRMATION",
            HorizonClass.TACTICAL,
            positive="TRENDING_UP",
            negative="TRENDING_DOWN",
        ),
        component(
            "RISK_APPETITE",
            "RISK_APPETITE",
            HorizonClass.TACTICAL,
            positive="RISK_ON",
            negative="RISK_OFF",
        ),
        ClimateComponent(
            component="INVESTMENT_CLIMATE",
            state=investment_climate.state,
            direction=AxisDirection(investment_climate.direction),
            score=investment_climate.score,
            confidence=investment_climate.confidence,
            coverage=investment_climate.coverage,
        ),
    ]
