"""V1 factor taxonomy/config surface (Issue #114 Scope D).

Loads ``config/decision_support_v2.yml`` without deleting or touching the
legacy ``config/factors.yml``. The 42 research candidates are a ceiling/backlog;
the V1 config only carries a compact orthogonal representative set that
exercises each of the eight families. Real source binding comes later.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .enums import HorizonClass

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "decision_support_v2.yml"
)

CANONICAL_FAMILIES = (
    "GROWTH_ACTIVITY",
    "INFLATION_COST",
    "POLICY_LIQUIDITY",
    "CHINA_CYCLE",
    "FINANCIAL_CONDITIONS",
    "MARKET_CONFIRMATION",
    "RISK_APPETITE",
    "VALUATION_RISK_PREMIUM",
)


class SubfactorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_id: str
    family: str
    horizon: HorizonClass
    native_frequency: str
    sign: int = 1
    description: str = ""
    source_route: str = ""
    binding_status: str = "UNBOUND"
    mvp: bool = True

    def resolved_horizon(self) -> HorizonClass:
        return HorizonClass(self.horizon)


class FactorFamily(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: str
    name: str
    subfactors: list[SubfactorSpec] = Field(default_factory=list)


class RegimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    axis_threshold: float = 0.25
    min_dwell_weeks: int = 3
    lens_disagreement_threshold: float = 1.0


class MarketDeltaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    volatility_style: str = "POINT"


class AssetRuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset: str
    macro_weights: dict[str, float] = Field(default_factory=dict)
    macro_scale: float = 1.0
    confirmation_source: str = ""
    confirmation_bonus: float = 0.1
    counter_trend_cap: int = 1
    valuation_source: str = ""
    valuation_cap_threshold: float = -1.0
    valuation_cushion_threshold: float = 1.0
    valuation_tag: str = ""
    invalidator: str = ""


class DecisionSupportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    contract: str
    parameter_status: str
    families: list[FactorFamily]
    regime: RegimeConfig = Field(default_factory=RegimeConfig)
    market_delta: MarketDeltaConfig = Field(default_factory=MarketDeltaConfig)
    asset_rules: list[AssetRuleSpec] = Field(default_factory=list)

    def subfactors(self) -> list[SubfactorSpec]:
        return [s for family in self.families for s in family.subfactors]

    def asset_rule(self, asset: str) -> AssetRuleSpec:
        for rule in self.asset_rules:
            if rule.asset == asset:
                return rule
        raise KeyError(f"no asset rule configured for {asset}")

    def subfactor(self, factor_id: str) -> SubfactorSpec:
        for sub in self.subfactors():
            if sub.factor_id == factor_id:
                return sub
        raise KeyError(f"unknown factor_id: {factor_id}")


def load_taxonomy(path: str | Path | None = None) -> DecisionSupportConfig:
    """Load and validate the V2 decision-support config surface."""
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with open(config_path, encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle)
    families = [
        FactorFamily(**family)
        for family in raw.pop("families", [])
    ]
    rules = [AssetRuleSpec(**rule) for rule in raw.pop("asset_rules", [])]
    config = DecisionSupportConfig(
        families=families,
        asset_rules=rules,
        regime=RegimeConfig(**raw.pop("regime", {})),
        market_delta=MarketDeltaConfig(**raw.pop("market_delta", {})),
        **raw,
    )
    _validate(config)
    return config


def _validate(config: DecisionSupportConfig) -> None:
    family_ids = [family.family_id for family in config.families]
    if len(family_ids) != len(CANONICAL_FAMILIES) or set(family_ids) != set(
        CANONICAL_FAMILIES
    ):
        raise ValueError(
            f"families must be exactly the eight canonical families, got {family_ids}"
        )
    seen: set[str] = set()
    for family in config.families:
        for sub in family.subfactors:
            if sub.family != family.family_id:
                raise ValueError(
                    f"subfactor {sub.factor_id} declares family {sub.family} but "
                    f"lives under {family.family_id}"
                )
            if sub.factor_id in seen:
                raise ValueError(f"duplicate factor_id: {sub.factor_id}")
            seen.add(sub.factor_id)
            HorizonClass(sub.horizon)
    assets = [rule.asset for rule in config.asset_rules]
    if len(assets) != len(set(assets)):
        raise ValueError(f"duplicate asset rules: {assets}")
