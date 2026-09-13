"""DashboardSnapshotV0 domain contract (Issue #114 Scope A).

Render-oriented, compact top level. Full lineage belongs under ``details``.
Deterministic serialization: no timestamps are generated inside the model and
``to_json``/``from_json`` round-trip stably.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    AssetTarget,
    AxisDirection,
    DataHealthStatus,
    EvidenceLane,
    GrowthState,
    HorizonClass,
    InflationState,
    MarketConfirmation,
    QuadrantLabel,
)
from .weekly import AssetViewDelta, InformationSetDelta, MacroStateDelta, MarketConditionDelta

SNAPSHOT_VERSION = "DashboardSnapshotV0"


class SnapshotMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_version: str = SNAPSHOT_VERSION
    snapshot_id: str
    as_of: date
    decision_time: datetime
    lane: EvidenceLane | str
    run_id: str
    model_version: str

    def resolved_lane(self) -> EvidenceLane:
        return EvidenceLane(self.lane)


class ClimateState(BaseModel):
    """One top-level climate lens (macro or investment)."""

    model_config = ConfigDict(extra="forbid")

    state: str
    direction: AxisDirection | str = AxisDirection.FLAT
    score: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str = ""


class Contributor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_id: str
    contribution: float


class ClusterView(BaseModel):
    """One horizon-separated cluster view (Scope B: never mixed horizons)."""

    model_config = ConfigDict(extra="forbid")

    cluster_id: str  # e.g. "GROWTH_ACTIVITY@CYCLICAL"
    family: str
    horizon: HorizonClass | str
    score: float | None = None
    weekly_delta: float | None = None
    direction: AxisDirection | str = AxisDirection.FLAT
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    top_positive: list[Contributor] = Field(default_factory=list)
    top_negative: list[Contributor] = Field(default_factory=list)
    missing_factors: list[str] = Field(default_factory=list)
    stale_factors: list[str] = Field(default_factory=list)
    freshness_status: DataHealthStatus | str = DataHealthStatus.OK

    def resolved_horizon(self) -> HorizonClass:
        return HorizonClass(self.horizon)

    def resolved_freshness(self) -> DataHealthStatus:
        return DataHealthStatus(self.freshness_status)


class LensDisagreement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag: bool = False
    summary: str = ""


class RegimeState(BaseModel):
    """Interpretable regime V0 — no HMM/Markov probabilities (Scope E)."""

    model_config = ConfigDict(extra="forbid")

    quadrant_label: QuadrantLabel | str
    growth_state: GrowthState | str
    growth_direction: AxisDirection | str
    inflation_state: InflationState | str
    inflation_direction: AxisDirection | str
    dwell_weeks: int = Field(default=0, ge=0)
    transition_flag: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    lens_disagreement: LensDisagreement = Field(default_factory=LensDisagreement)

    def resolved_quadrant(self) -> QuadrantLabel:
        return QuadrantLabel(self.quadrant_label)


class AssetViewV0(BaseModel):
    """Config/rule-driven asset view (Scope F). All stances are [-2..2]."""

    model_config = ConfigDict(extra="forbid")

    asset: AssetTarget | str
    macro_bias: int = Field(ge=-2, le=2)
    market_confirmation: MarketConfirmation | str
    valuation_tag: str = ""
    stance: int = Field(ge=-2, le=2)
    prior_stance: int = Field(ge=-2, le=2)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    drivers: list[str] = Field(default_factory=list)
    counter_signals: list[str] = Field(default_factory=list)
    invalidator: str = ""
    data_health: DataHealthStatus | str = DataHealthStatus.OK

    def resolved_asset(self) -> AssetTarget:
        return AssetTarget(self.asset)

    def resolved_confirmation(self) -> MarketConfirmation:
        return MarketConfirmation(self.market_confirmation)

    def resolved_data_health(self) -> DataHealthStatus:
        return DataHealthStatus(self.data_health)


class PulseEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset: AssetTarget | str
    ret_1w: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    momentum_label: str = ""


class CrossAssetPulse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[PulseEntry] = Field(default_factory=list)
    summary: str = ""


class ExecutiveBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    what_changed: str = ""
    why_it_matters: str = ""
    what_to_watch: list[str] = Field(default_factory=list)


class DataHealthSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: DataHealthStatus | str = DataHealthStatus.OK
    stale_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)

    def resolved_overall(self) -> DataHealthStatus:
        return DataHealthStatus(self.overall)


class WeeklyChange(BaseModel):
    """The four explicit weekly change surfaces (Scope C)."""

    model_config = ConfigDict(extra="forbid")

    information_set_delta: InformationSetDelta
    macro_state_delta: MacroStateDelta
    market_condition_delta: MarketConditionDelta
    asset_view_delta: AssetViewDelta


class DashboardSnapshotV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: SnapshotMetadata
    macro_climate: ClimateState
    investment_climate: ClimateState
    clusters: list[ClusterView]
    weekly_change: WeeklyChange
    regime: RegimeState
    asset_views: list[AssetViewV0]
    cross_asset_pulse: CrossAssetPulse
    executive_brief: ExecutiveBrief
    data_health_summary: DataHealthSummary
    details: dict[str, Any] = Field(default_factory=dict)

    def to_json(self, *, indent: int = 2) -> str:
        """Deterministic JSON serialization (sorted keys, JSON-safe types)."""
        return self.model_dump_json(indent=indent, by_alias=False)

    @classmethod
    def from_json(cls, raw: str) -> "DashboardSnapshotV0":
        return cls.model_validate_json(raw)
