"""Consumer mirror of Marco Integration Contract v1 plus Cross boundary rules."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"

CANONICAL_ASSET_IDS = (
    "CN_EQ",
    "HK_EQ",
    "US_EQ",
    "CN_GOV_BOND",
    "CN_CREDIT",
    "GOLD",
    "COMMODITY",
    "CASH",
)

ASSET_ALIASES = {
    "CN_EQ": "CN_EQ",
    "CN_EQUITY": "CN_EQ",
    "HK_EQ": "HK_EQ",
    "HK_EQUITY": "HK_EQ",
    "US_EQ": "US_EQ",
    "CN_GOV_BOND": "CN_GOV_BOND",
    "CN_BOND": "CN_GOV_BOND",
    "CN_CREDIT": "CN_CREDIT",
    "GOLD": "GOLD",
    "COMMODITY": "COMMODITY",
    "INDUSTRIAL_COMMODITY": "COMMODITY",
    "CASH": "CASH",
}
FX_VIEW_IDS = ("CNY",)

DATA_FILES = (
    "macro_snapshot.json",
    "structural_snapshot.json",
    "fundamental_asset_view.json",
)
MANIFEST_FILE = "integration_manifest.json"
BUNDLE_FILES = (*DATA_FILES, MANIFEST_FILE)


class ContractModel(BaseModel):
    """Strict mirror of the producer models."""

    model_config = ConfigDict(extra="forbid")


class SnapshotStatus(str, Enum):
    READY = "READY"
    WARMUP = "WARMUP"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    NO_SIGNAL = "NO_SIGNAL"
    UNAVAILABLE = "UNAVAILABLE"


class FactorSnapshot(ContractModel):
    score: Optional[float] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    coverage: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: SnapshotStatus

    @model_validator(mode="after")
    def _coherent_missingness(self):
        if self.status == SnapshotStatus.READY and (
            self.score is None or self.confidence is None or self.coverage is None
        ):
            raise ValueError("READY factor requires score, confidence and coverage")
        if self.status == SnapshotStatus.UNAVAILABLE and any(
            value is not None for value in (self.score, self.confidence, self.coverage)
        ):
            raise ValueError("UNAVAILABLE factor must use null values, never zero-fill")
        if self.status == SnapshotStatus.NO_SIGNAL and self.score is not None:
            raise ValueError("NO_SIGNAL factor score must be null")
        return self


class FactorSet(ContractModel):
    growth: FactorSnapshot
    inflation: FactorSnapshot
    domestic_financial: FactorSnapshot
    global_financial: FactorSnapshot
    fiscal: FactorSnapshot


class RegimeSnapshot(ContractModel):
    state: str
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class MacroSnapshot(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    as_of: date
    data_cutoff: date
    model_version: str
    factors: FactorSet
    regime: RegimeSnapshot


class StructuralMetric(ContractModel):
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: SnapshotStatus

    @model_validator(mode="after")
    def _coherent_missingness(self):
        if self.status == SnapshotStatus.READY and (
            self.score is None or self.confidence is None
        ):
            raise ValueError("READY structural metric requires score and confidence")
        if self.status in (SnapshotStatus.NO_SIGNAL, SnapshotStatus.UNAVAILABLE) and (
            self.score is not None
        ):
            raise ValueError(f"{self.status.value} structural score must be null")
        return self


class FragilityScale(ContractModel):
    lower_fragility: Literal[0.0] = 0.0
    higher_fragility: Literal[1.0] = 1.0


class StructuralSnapshot(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    as_of: date
    property_fragility: StructuralMetric
    structural_risk: StructuralMetric
    fragility_scale: FragilityScale = Field(default_factory=FragilityScale)


class AssetContributions(ContractModel):
    growth: Optional[float] = None
    inflation: Optional[float] = None
    domestic_financial: Optional[float] = None
    global_financial: Optional[float] = None
    structural: None = None


class FundamentalAsset(ContractModel):
    asset_id: Literal[
        "CN_EQ",
        "HK_EQ",
        "US_EQ",
        "CN_GOV_BOND",
        "CN_CREDIT",
        "GOLD",
        "COMMODITY",
        "CASH",
    ]
    fundamental_score: Optional[float] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    coverage: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: SnapshotStatus
    contributions: AssetContributions

    @model_validator(mode="after")
    def _coherent_missingness(self):
        if self.status == SnapshotStatus.READY and (
            self.fundamental_score is None
            or self.confidence is None
            or self.coverage is None
        ):
            raise ValueError("READY asset requires score, confidence and coverage")
        if self.status == SnapshotStatus.UNAVAILABLE and any(
            value is not None
            for value in (self.fundamental_score, self.confidence, self.coverage)
        ):
            raise ValueError("UNAVAILABLE asset must use null values, never zero-fill")
        if self.status == SnapshotStatus.NO_SIGNAL and self.fundamental_score is not None:
            raise ValueError("NO_SIGNAL asset score must be null")
        return self


class FxView(ContractModel):
    asset_id: Literal["CNY"]
    fundamental_score: Optional[float] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    coverage: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: SnapshotStatus
    contributions: AssetContributions

    @model_validator(mode="after")
    def _coherent_missingness(self):
        if self.status == SnapshotStatus.READY and (
            self.fundamental_score is None
            or self.confidence is None
            or self.coverage is None
        ):
            raise ValueError("READY FX view requires score, confidence and coverage")
        if self.status in (SnapshotStatus.UNAVAILABLE, SnapshotStatus.NO_SIGNAL) and (
            self.fundamental_score is not None
        ):
            raise ValueError(f"{self.status.value} FX view score must be null")
        return self


class FundamentalAssetView(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    as_of: date
    data_cutoff: date
    model_version: str
    assets: list[FundamentalAsset]
    fx_views: list[FxView] = Field(default_factory=list)

    @model_validator(mode="after")
    def _canonical_asset_surface(self):
        ids = [asset.asset_id for asset in self.assets]
        if ids != list(CANONICAL_ASSET_IDS):
            raise ValueError(
                "assets must contain the canonical allocatable ids exactly once "
                "and in contract order"
            )
        if len(self.fx_views) > 1:
            raise ValueError("v1 supports at most the CNY FX view")
        return self


class ManifestFile(ContractModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class IntegrationManifest(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    generated_at: datetime
    as_of: date
    data_cutoff: date
    marco_model_version: str
    marco_git_commit: str
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: dict[str, ManifestFile]

    @model_validator(mode="after")
    def _exact_file_set(self):
        if set(self.files) != set(DATA_FILES):
            raise ValueError(f"manifest files must be exactly {DATA_FILES}")
        return self


ALLOCATABLE_ASSETS = (
    "CN_EQ",
    "HK_EQ",
    "US_EQ",
    "CN_BOND",
    "GOLD",
    "COMMODITY",
    "CASH",
)

VIEWABLE_ASSETS = ALLOCATABLE_ASSETS + (
    "CN_CREDIT",
    "CNY",
    "CN_EQ_LARGE",
    "CN_EQ_SMALL",
    "CN_BOND_10Y",
    "US_GOV_10Y",
    "US_REAL_10Y",
    "COPPER",
    "DXY",
    "OIL",
    "USDCNH",
)

MARCO_TO_CROSS_ASSET_ID: dict[str, str | None] = {
    "CN_EQ": "CN_EQ",
    "HK_EQ": "HK_EQ",
    "US_EQ": "US_EQ",
    "CN_GOV_BOND": "CN_BOND",
    "CN_CREDIT": None,
    "GOLD": "GOLD",
    "COMMODITY": "COMMODITY",
    "CASH": "CASH",
}

CROSS_ASSET_ID_ALIASES = {
    "CN_EQ": "CN_EQ",
    "CN_EQUITY": "CN_EQ",
    "CHINA_EQ": "CN_EQ",
    "CHINA_EQUITY": "CN_EQ",
    "HK_EQ": "HK_EQ",
    "HK_EQUITY": "HK_EQ",
    "HONG_KONG_EQ": "HK_EQ",
    "HONGKONG_EQ": "HK_EQ",
    "US_EQ": "US_EQ",
    "US_EQUITY": "US_EQ",
    "SPX": "US_EQ",
    "SP500": "US_EQ",
    "S&P500": "US_EQ",
    "CN_GOV_BOND": "CN_BOND",
    "CN_BOND": "CN_BOND",
    "CN_BONDS": "CN_BOND",
    "CHINA_BOND": "CN_BOND",
    "CN_CREDIT": "CN_CREDIT",
    "GOLD": "GOLD",
    "XAU": "GOLD",
    "XAUUSD": "GOLD",
    "COMMODITY": "COMMODITY",
    "COMMODITIES": "COMMODITY",
    "INDUSTRIAL_COMMODITY": "COMMODITY",
    "CASH": "CASH",
    "CNY": "CNY",
    "CN_EQ_LARGE": "CN_EQ_LARGE",
    "CN_EQ_SMALL": "CN_EQ_SMALL",
    "CN_BOND_10Y": "CN_BOND_10Y",
    "US_GOV_10Y": "US_GOV_10Y",
    "US_REAL_10Y": "US_REAL_10Y",
    "COPPER": "COPPER",
    "DXY": "DXY",
    "OIL": "OIL",
    "WTI": "OIL",
    "CRUDE_OIL": "OIL",
    "USDCNH": "USDCNH",
    "USD_CNH": "USDCNH",
}


def normalize_asset_id(asset_id: str) -> str:
    key = str(asset_id).strip().upper().replace("-", "_").replace(" ", "_")
    try:
        return CROSS_ASSET_ID_ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"unknown integration asset_id: {asset_id!r}") from exc


def marco_to_cross_asset_id(asset_id: str) -> str | None:
    try:
        return MARCO_TO_CROSS_ASSET_ID[str(asset_id)]
    except KeyError as exc:
        raise ValueError(f"unsupported Marco canonical asset_id: {asset_id!r}") from exc


ValidationStatus = Literal["PASS", "FAIL"]
SignalStatus = Literal["READY", "PARTIAL"]


class IntegrationValidationReport(ContractModel):
    status: ValidationStatus
    schema_version: str | None = None
    signal_status: SignalStatus = "READY"
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unavailable_factors: list[str] = Field(default_factory=list)
    unavailable_assets: list[str] = Field(default_factory=list)
    view_only_assets: list[str] = Field(default_factory=list)
    legacy_fallback_used: bool = False

    @property
    def exit_code(self) -> int:
        return 0 if self.status == "PASS" else 1


__all__ = [
    "ALLOCATABLE_ASSETS",
    "ASSET_ALIASES",
    "BUNDLE_FILES",
    "CANONICAL_ASSET_IDS",
    "CROSS_ASSET_ID_ALIASES",
    "DATA_FILES",
    "FX_VIEW_IDS",
    "MANIFEST_FILE",
    "MARCO_TO_CROSS_ASSET_ID",
    "SCHEMA_VERSION",
    "VIEWABLE_ASSETS",
    "AssetContributions",
    "ContractModel",
    "FactorSet",
    "FactorSnapshot",
    "FragilityScale",
    "FundamentalAsset",
    "FundamentalAssetView",
    "FxView",
    "IntegrationManifest",
    "IntegrationValidationReport",
    "MacroSnapshot",
    "ManifestFile",
    "RegimeSnapshot",
    "SnapshotStatus",
    "StructuralMetric",
    "StructuralSnapshot",
    "marco_to_cross_asset_id",
    "normalize_asset_id",
]
