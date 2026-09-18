"""Weekly change semantics (Issue #114 Scope C).

Four explicit change surfaces:

1. ``information_set_delta`` — UPDATED / NO_NEW_INFORMATION / OVERDUE_STALE,
   with revisions, new observations and monitoring-only capture-time
   OBSERVED_UPDATE events (#139 Phase 4) preserved as events.
2. ``macro_state_delta`` — cyclical factor change caused by new information;
   a missing release must never produce synthetic movement.
3. ``market_condition_delta`` — genuine high-frequency weekly moves with
   unit semantics: prices/FX/commodities in %, yields/spreads in bps,
   volatility in point/percentile style as configured.
4. ``asset_view_delta`` — stance/confidence changes plus reason tags.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    CauseTag,
    InformationSetStatus,
    MarketDeltaUnit,
    MarketMetricClass,
    ReleaseEventType,
    SurpriseMethod,
)

_FLOAT_DIGITS = 6


def _round(value: float) -> float:
    return round(value, _FLOAT_DIGITS)


class SurpriseMetadata(BaseModel):
    """Optional release surprise metadata.

    The method must be declared. ``TREND_RELATIVE`` compares the release to
    its own recent trend; it is never a market-consensus surprise because the
    source does not supply consensus.
    """

    model_config = ConfigDict(extra="forbid")

    method: SurpriseMethod
    value: float
    baseline: str = ""
    note: str = ""

    def resolved_method(self) -> SurpriseMethod:
        return SurpriseMethod(self.method)


class ReleaseEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_id: str
    series_id: str = ""
    event_type: ReleaseEventType
    observation_date: date | None = None
    note: str = ""
    surprise: SurpriseMetadata | None = None

    def resolved_event_type(self) -> ReleaseEventType:
        return ReleaseEventType(self.event_type)


class InformationSetDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: InformationSetStatus
    events: list[ReleaseEvent] = Field(default_factory=list)
    stale_factors: list[str] = Field(default_factory=list)

    def resolved_status(self) -> InformationSetStatus:
        return InformationSetStatus(self.status)


def build_information_set_delta(
    events: list[ReleaseEvent],
    *,
    expected_releases: dict[str, date],
    as_of: date,
) -> InformationSetDelta:
    """Classify the information-set delta for one weekly surface.

    ``events`` are the release events observed since the previous weekly
    snapshot. ``expected_releases`` maps factor_id to the release date that
    was expected on or before ``as_of`` (empty/absent means no expectation).
    """
    real_events = [e for e in events if e.resolved_event_type() is not ReleaseEventType.OVERDUE]
    stale_factors = sorted(
        factor
        for factor, expected in expected_releases.items()
        if expected <= as_of
        and not any(
            e.factor_id == factor
            and e.resolved_event_type() is not ReleaseEventType.OVERDUE
            for e in events
        )
    )
    if real_events:
        status = InformationSetStatus.UPDATED
    elif stale_factors:
        status = InformationSetStatus.OVERDUE_STALE
    else:
        status = InformationSetStatus.NO_NEW_INFORMATION
    return InformationSetDelta(
        status=status,
        events=events,
        stale_factors=stale_factors,
    )


class FactorStateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_id: str
    previous: float
    current: float
    delta: float
    cause: CauseTag

    def resolved_cause(self) -> CauseTag:
        return CauseTag(self.cause)


class MacroStateDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[FactorStateChange] = Field(default_factory=list)

    def changed_factors(self) -> list[str]:
        return [e.factor_id for e in self.entries if e.delta != 0.0]


class SyntheticMovementError(ValueError):
    """Raised when a macro state moves without new information."""


def build_macro_state_delta(
    previous: dict[str, float],
    current: dict[str, float],
    *,
    information_status: InformationSetStatus,
    changed_by_release: set[str] | None = None,
) -> MacroStateDelta:
    """Compute cyclical macro state change strictly caused by new information.

    Invariants:
    - if the information set did not update, every delta must be exactly zero;
    - a non-zero delta is only allowed for factors with an observed release
      (``changed_by_release``) or a monitoring OBSERVED_UPDATE event (#139:
      a new observation/value became visible to the capture-time decision set);
      anything else is synthetic drift and raises.
    """
    resolved_status = InformationSetStatus(information_status)
    changed_by_release = changed_by_release or set()
    entries: list[FactorStateChange] = []
    for factor_id in sorted(set(previous) | set(current)):
        prev = previous.get(factor_id)
        cur = current.get(factor_id)
        if prev is None or cur is None:
            # Factor present in only one state: treat as no comparable delta.
            continue
        delta = _round(cur - prev)
        if resolved_status is not InformationSetStatus.UPDATED and delta != 0.0:
            raise SyntheticMovementError(
                f"factor {factor_id} moved by {delta} while information set "
                f"status was {resolved_status.value}; synthetic movement is forbidden"
            )
        if delta != 0.0 and factor_id not in changed_by_release:
            raise SyntheticMovementError(
                f"factor {factor_id} moved by {delta} without an observed release"
            )
        cause = (
            CauseTag.NEW_INFORMATION
            if delta != 0.0
            else CauseTag.NO_NEW_INFORMATION
        )
        entries.append(
            FactorStateChange(
                factor_id=factor_id,
                previous=prev,
                current=cur,
                delta=delta,
                cause=cause,
            )
        )
    return MacroStateDelta(entries=entries)


class MarketMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument: str
    metric_class: MarketMetricClass
    unit: MarketDeltaUnit
    weekly_change: float
    prior_value: float
    current_value: float

    def resolved_metric_class(self) -> MarketMetricClass:
        return MarketMetricClass(self.metric_class)

    def resolved_unit(self) -> MarketDeltaUnit:
        return MarketDeltaUnit(self.unit)


_BPS_CLASSES = {MarketMetricClass.YIELD, MarketMetricClass.SPREAD}
_RATIO_CLASSES = {
    MarketMetricClass.PRICE,
    MarketMetricClass.FX,
    MarketMetricClass.COMMODITY,
}


def build_market_move(
    instrument: str,
    metric_class: MarketMetricClass,
    prior_value: float,
    current_value: float,
    *,
    volatility_style: str = "POINT",
) -> MarketMove:
    """Build one genuine weekly market move with enforced unit semantics."""
    resolved = MarketMetricClass(metric_class)
    if resolved in _BPS_CLASSES:
        unit = MarketDeltaUnit.BPS
        change = (current_value - prior_value) * 100.0
    elif resolved is MarketMetricClass.VOLATILITY:
        style = volatility_style.upper()
        if style not in {MarketDeltaUnit.POINT.value, MarketDeltaUnit.PERCENTILE.value}:
            raise ValueError(f"unsupported volatility_style: {volatility_style}")
        unit = MarketDeltaUnit(style)
        change = current_value - prior_value
    elif resolved in _RATIO_CLASSES:
        if prior_value == 0.0:
            raise ValueError(
                f"cannot compute % weekly change for {instrument} with zero prior value"
            )
        unit = MarketDeltaUnit.PCT
        change = (current_value / prior_value - 1.0) * 100.0
    else:  # pragma: no cover - enum exhaustive
        raise ValueError(f"unhandled metric class: {resolved}")
    return MarketMove(
        instrument=instrument,
        metric_class=resolved,
        unit=unit,
        weekly_change=_round(change),
        prior_value=prior_value,
        current_value=current_value,
    )


class MarketConditionDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    moves: list[MarketMove] = Field(default_factory=list)


def build_market_condition_delta(moves: list[MarketMove]) -> MarketConditionDelta:
    """Assemble the market-condition surface from validated unit moves."""
    return MarketConditionDelta(moves=moves)


class AssetStanceChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset: str
    previous_stance: int
    current_stance: int
    delta: int
    reason_tags: list[str] = Field(default_factory=list)
    confidence_delta: float | None = None


class AssetViewDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[AssetStanceChange] = Field(default_factory=list)
