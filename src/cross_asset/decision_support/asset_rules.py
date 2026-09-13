"""Asset rules/gates V0 (Issue #114 Scope F).

Config-driven, economically interpretable rules. Binding principles:
- macro establishes the base stance;
- market confirmation may confirm/attenuate/cap conviction;
- valuation is an asymmetric cap/cushion, not short-term timing;
- no weights are fitted or optimized to realized returns;
- a single unavailable factor never silently becomes zero: missing inputs
  lower confidence and are surfaced as blockers.
"""

import math
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from .enums import DataHealthStatus, MarketConfirmation
from .taxonomy import AssetRuleSpec

STANCE_MIN = -2
STANCE_MAX = 2


class GateBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    reason: str


class AssetGateResult(BaseModel):
    """Intermediate gate result before snapshot assembly."""

    model_config = ConfigDict(extra="forbid")

    asset: str
    macro_bias: int = Field(ge=STANCE_MIN, le=STANCE_MAX)
    stance: int = Field(ge=STANCE_MIN, le=STANCE_MAX)
    market_confirmation: MarketConfirmation
    valuation_tag: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    drivers: list[str] = Field(default_factory=list)
    counter_signals: list[str] = Field(default_factory=list)
    blockers: list[GateBlocker] = Field(default_factory=list)
    data_health: DataHealthStatus = DataHealthStatus.OK


def _clip_stance(value: float) -> int:
    return max(min(round(value), STANCE_MAX), STANCE_MIN)


def _attenuate(stance: int) -> int:
    """One interpretable step toward neutral."""
    if stance > 0:
        return stance - 1
    if stance < 0:
        return stance + 1
    return 0


def compute_macro_bias(
    rule: AssetRuleSpec,
    cyclical_scores: Mapping[str, float | None],
) -> tuple[int, float, list[tuple[str, float]], list[GateBlocker]]:
    """Base stance from signed weights over CYCLICAL cluster scores only.

    Returns ``(bias, confidence_factor, contributions, blockers)``. Missing
    clusters are excluded from the sum (never zero-filled) and reduce the
    confidence factor proportionally.
    """
    contributions: list[tuple[str, float]] = []
    blockers: list[GateBlocker] = []
    total = 0.0
    declared = len(rule.macro_weights)
    if declared == 0:
        return 0, 0.0, contributions, blockers
    available = 0
    for family, weight in rule.macro_weights.items():
        score = cyclical_scores.get(family)
        if score is None:
            blockers.append(
                GateBlocker(
                    source=family,
                    reason="cyclical cluster score unavailable; excluded from stance, not zero-filled",
                )
            )
            continue
        available += 1
        total += weight * score
        contributions.append((family, weight * score))
    confidence_factor = available / declared
    bias = _clip_stance(total / rule.macro_scale)
    return bias, confidence_factor, contributions, blockers


def market_confirmation_state(
    bias: int,
    confirmation_score: float | None,
) -> MarketConfirmation:
    """Compare market momentum with the macro bias."""
    if bias == 0 or confirmation_score is None or confirmation_score == 0.0:
        return MarketConfirmation.DIVERGENT
    if math.copysign(1, confirmation_score) == math.copysign(1, bias):
        return MarketConfirmation.CONFIRMED
    return MarketConfirmation.COUNTER_TREND


def apply_confirmation_gate(
    stance: int,
    confirmation: MarketConfirmation,
    *,
    counter_trend_cap: int,
) -> tuple[int, str | None]:
    """Confirm/attenuate/cap conviction; never flips the macro sign."""
    if confirmation is MarketConfirmation.CONFIRMED:
        return stance, None
    if confirmation is MarketConfirmation.COUNTER_TREND:
        cap = max(min(counter_trend_cap, 2), 0)
        capped = max(min(stance, cap), -cap)
        return capped, "counter-trend conviction cap applied"
    # DIVERGENT: market neither confirms nor rejects; attenuate one step.
    return _attenuate(stance), "market divergence attenuation applied"


def apply_valuation_gate(
    stance: int,
    valuation_score: float | None,
    *,
    cap_threshold: float,
    cushion_threshold: float,
) -> tuple[int, str]:
    """Asymmetric valuation cap/cushion; never short-term timing.

    An expensive valuation can cap a long stance; a cheap valuation can
    cushion (soften) a short stance. No symmetric fast flip in either
    direction.
    """
    tag = "valuation overlay not bound"
    if valuation_score is None:
        return stance, tag
    if stance > 0 and valuation_score <= cap_threshold:
        return min(stance, 1), "valuation cap applied (stretched valuation)"
    if stance < 0 and valuation_score >= cushion_threshold:
        return max(stance, -1), "valuation cushion applied (cheap valuation)"
    return stance, "valuation overlay neutral"


def build_asset_gate(
    rule: AssetRuleSpec,
    *,
    cyclical_scores: Mapping[str, float | None],
    tactical_scores: Mapping[str, float | None],
    structural_scores: Mapping[str, float | None],
) -> AssetGateResult:
    """Run the full macro -> confirmation -> valuation gate for one asset."""
    bias, confidence_factor, contributions, blockers = compute_macro_bias(
        rule, cyclical_scores
    )
    confirmation_score = tactical_scores.get(rule.confirmation_source)
    if confirmation_score is None and rule.confirmation_source:
        blockers.append(
            GateBlocker(
                source=rule.confirmation_source,
                reason="market confirmation input unavailable; gate runs attenuated, not zero-filled",
            )
        )
    confirmation = market_confirmation_state(bias, confirmation_score)
    stance = bias
    confidence = confidence_factor
    gate_note: str | None = None
    if confirmation is MarketConfirmation.CONFIRMED:
        confidence = min(confidence + rule.confirmation_bonus, 1.0)
    else:
        stance, gate_note = apply_confirmation_gate(
            stance,
            confirmation,
            counter_trend_cap=rule.counter_trend_cap,
        )
    if confirmation is MarketConfirmation.DIVERGENT:
        confidence *= 0.9

    valuation_score = (
        structural_scores.get(rule.valuation_source) if rule.valuation_source else None
    )
    if rule.valuation_source and valuation_score is None:
        blockers.append(
            GateBlocker(
                source=rule.valuation_source,
                reason="valuation overlay unavailable; cap/cushion not applied",
            )
        )
    stance, valuation_tag = apply_valuation_gate(
        stance,
        valuation_score,
        cap_threshold=rule.valuation_cap_threshold,
        cushion_threshold=rule.valuation_cushion_threshold,
    )
    stance = _clip_stance(float(stance))

    drivers = [
        f"{family}:{contribution:+.2f}"
        for family, contribution in sorted(
            contributions, key=lambda item: abs(item[1]), reverse=True
        )[:4]
    ]
    if confirmation is MarketConfirmation.CONFIRMED:
        drivers.append(f"market_confirmed:{rule.confirmation_source}")
    counter_signals = [
        f"{family}:{contribution:+.2f}"
        for family, contribution in contributions
        if stance != 0
        and math.copysign(1, contribution) != math.copysign(1, stance)
    ]
    if gate_note:
        counter_signals.append(gate_note)

    if blockers and len(blockers) == len(rule.macro_weights):
        data_health = DataHealthStatus.MISSING
    elif blockers:
        data_health = DataHealthStatus.PARTIAL
    else:
        data_health = DataHealthStatus.OK
    if data_health is DataHealthStatus.MISSING:
        # No macro basis at all: stance must be explicit neutral, not a guess.
        stance = 0
        valuation_tag = "macro basis unavailable; explicit neutral stance"

    return AssetGateResult(
        asset=rule.asset,
        macro_bias=bias,
        stance=stance,
        market_confirmation=confirmation,
        valuation_tag=valuation_tag,
        confidence=round(confidence, 4),
        drivers=drivers,
        counter_signals=counter_signals,
        blockers=blockers,
        data_health=data_health,
    )
