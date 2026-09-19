"""Enums for the Decision Support v2 core (Issue #114).

These are scoped to the decision-support product lane and intentionally do not
touch the legacy domain enums used by the formal admission/backtest surfaces.
"""

from enum import StrEnum


class EvidenceLane(StrEnum):
    """Evidence lane separating monitoring from research and formal OOS work."""

    MONITORING = "MONITORING"
    RESEARCH = "RESEARCH"
    FORMAL_OOS = "FORMAL_OOS"


class HorizonClass(StrEnum):
    """Horizon class every factor/subfactor must declare (Scope B)."""

    CYCLICAL = "CYCLICAL"  # ~3-18 months
    TACTICAL = "TACTICAL"  # daily to ~3 months
    STRUCTURAL_CONTEXT = "STRUCTURAL_CONTEXT"  # display/context only


class InformationSetStatus(StrEnum):
    """Information-set delta status (Scope C.1)."""

    UPDATED = "UPDATED"
    NO_NEW_INFORMATION = "NO_NEW_INFORMATION"
    OVERDUE_STALE = "OVERDUE_STALE"


class ReleaseEventType(StrEnum):
    NEW_OBSERVATION = "NEW_OBSERVATION"
    REVISION = "REVISION"
    OVERDUE = "OVERDUE"
    # MONITORING capture-time lane only (#139 Phase 4). Asserts only that a new
    # observation/value became visible to the monitoring decision set, derived
    # from canonical observation-identity differences against the causal prior
    # snapshot. It never claims a historical first-release/publication timestamp
    # and never enters the FORMAL_OOS lane.
    OBSERVED_UPDATE = "OBSERVED_UPDATE"


class SurpriseMethod(StrEnum):
    """Allowed surprise methods; consensus is forbidden unless truly supplied."""

    TREND_RELATIVE = "TREND_RELATIVE"


class MarketMetricClass(StrEnum):
    """Class of a market condition metric; determines the weekly delta unit."""

    PRICE = "PRICE"  # equity/index levels -> PCT
    FX = "FX"  # FX rates -> PCT
    COMMODITY = "COMMODITY"  # commodity prices -> PCT
    YIELD = "YIELD"  # yields -> BPS
    SPREAD = "SPREAD"  # credit/term spreads -> BPS
    VOLATILITY = "VOLATILITY"  # vol -> POINT or PERCENTILE as configured


class MarketDeltaUnit(StrEnum):
    PCT = "PCT"
    BPS = "BPS"
    POINT = "POINT"
    PERCENTILE = "PERCENTILE"


class MarketConfirmation(StrEnum):
    """Market confirmation state for an asset view (Scope F).

    ``UNKNOWN`` is an explicit data-availability state: the confirmation
    input could not be observed. It must never be conflated with an observed
    ``DIVERGENT`` (flat/neutral vs bias) or ``COUNTER_TREND`` (opposite to
    bias) reading.
    """

    CONFIRMED = "CONFIRMED"
    DIVERGENT = "DIVERGENT"
    COUNTER_TREND = "COUNTER_TREND"
    UNKNOWN = "UNKNOWN"


class AxisDirection(StrEnum):
    RISING = "RISING"
    FLAT = "FLAT"
    FALLING = "FALLING"


class GrowthState(StrEnum):
    EXPANDING = "EXPANDING"
    STABLE = "STABLE"
    CONTRACTING = "CONTRACTING"


class InflationState(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class QuadrantLabel(StrEnum):
    """Interpretable navigation quadrant labels (Scope E)."""

    GOLDILOCKS = "GOLDILOCKS"  # growth rising, inflation falling
    REFLATION = "REFLATION"  # growth rising, inflation rising
    STAGFLATION_RISK = "STAGFLATION_RISK"  # growth falling, inflation rising
    DISINFLATIONARY_SLUMP = "DISINFLATIONARY_SLUMP"  # growth falling, inflation falling


class AssetTarget(StrEnum):
    CN_EQ = "CN_EQ"
    HK_EQ = "HK_EQ"
    US_EQ = "US_EQ"
    CN_BOND = "CN_BOND"
    GOLD = "GOLD"
    COPPER = "COPPER"
    USD_CNY = "USD_CNY"
    CASH = "CASH"


class DataHealthStatus(StrEnum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    MISSING = "MISSING"


class CauseTag(StrEnum):
    NEW_INFORMATION = "NEW_INFORMATION"
    NO_NEW_INFORMATION = "NO_NEW_INFORMATION"
