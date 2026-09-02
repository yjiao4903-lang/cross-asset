"""Marco Integration Contract v1 models and cross-asset identity rules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_MAJOR_VERSION = 1
REQUIRED_MACRO_DIMENSIONS = ("GROWTH", "LIQUIDITY")
KNOWN_MACRO_DIMENSIONS = ("GROWTH", "INFLATION", "LIQUIDITY", "POLICY", "RISK_APPETITE")

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

ASSET_ID_ALIASES = {
    # Allocation aliases.
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
    "CN_BOND": "CN_BOND",
    "CN_BONDS": "CN_BOND",
    "CHINA_BOND": "CN_BOND",
    "GOLD": "GOLD",
    "XAU": "GOLD",
    "XAUUSD": "GOLD",
    "COMMODITY": "COMMODITY",
    "COMMODITIES": "COMMODITY",
    "CASH": "CASH",
    # View-only canonical market proxies.
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


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def contract_major(value: str) -> int:
    normalized = str(value).strip().lower()
    if normalized.startswith("v"):
        normalized = normalized[1:]
    try:
        return int(normalized.split(".", 1)[0])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid contract_version: {value!r}") from exc


def validate_contract_version(value: str) -> str:
    if contract_major(value) != CONTRACT_MAJOR_VERSION:
        raise ValueError(
            f"unsupported contract_version {value!r}; expected major "
            f"{CONTRACT_MAJOR_VERSION}"
        )
    return str(value)


def normalize_asset_id(asset_id: str) -> str:
    key = str(asset_id).strip().upper().replace("-", "_").replace(" ", "_")
    try:
        return ASSET_ID_ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"unknown Marco asset_id: {asset_id!r}") from exc


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


PayloadStatus = Literal["OK", "DEGRADED", "STALE", "FAILED"]
ValidationStatus = Literal["PASS", "DEGRADED", "FAIL"]


class IntegrationManifest(_StrictModel):
    contract_version: str
    producer: str
    generated_at: datetime
    as_of: datetime
    status: PayloadStatus
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("contract_version")
    @classmethod
    def _contract_v1(cls, value: str) -> str:
        return validate_contract_version(value)

    @field_validator("producer")
    @classmethod
    def _producer_is_marco(cls, value: str) -> str:
        if value.strip().casefold() != "marco":
            raise ValueError("producer must be Marco")
        return value

    @field_validator("status", mode="before")
    @classmethod
    def _status_upper(cls, value: Any) -> Any:
        return str(value).upper()

    @model_validator(mode="after")
    def _time_order(self):
        if _utc(self.generated_at) < _utc(self.as_of):
            raise ValueError("generated_at must be >= as_of")
        if self.expires_at is not None and _utc(self.expires_at) <= _utc(self.as_of):
            raise ValueError("expires_at must be > as_of")
        return self


class MacroDimensionContract(_StrictModel):
    score: float | None
    confidence: float = Field(ge=0.0, le=1.0)
    coverage: float = Field(ge=0.0, le=1.0)
    status: PayloadStatus = "OK"
    data_cutoff: datetime | None = None
    contributions: dict[str, float | None] = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def _status_upper(cls, value: Any) -> Any:
        return str(value).upper()

    @field_validator("score")
    @classmethod
    def _score_bounds(cls, value: float | None) -> float | None:
        if value is not None and not -2.0 <= float(value) <= 2.0:
            raise ValueError("macro dimension score must be in [-2, 2]")
        return value


class MarcoMacroState(_StrictModel):
    contract_version: str
    as_of: datetime
    data_cutoff: datetime
    model_version: str
    status: PayloadStatus
    score: float | None
    confidence: float = Field(ge=0.0, le=1.0)
    dimensions: dict[str, MacroDimensionContract]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("contract_version")
    @classmethod
    def _contract_v1(cls, value: str) -> str:
        return validate_contract_version(value)

    @field_validator("status", mode="before")
    @classmethod
    def _status_upper(cls, value: Any) -> Any:
        return str(value).upper()

    @field_validator("score")
    @classmethod
    def _score_bounds(cls, value: float | None) -> float | None:
        if value is not None and not -2.0 <= float(value) <= 2.0:
            raise ValueError("macro score must be in [-2, 2]")
        return value

    @model_validator(mode="after")
    def _cutoff_is_causal(self):
        if _utc(self.data_cutoff) > _utc(self.as_of):
            raise ValueError("macro data_cutoff must be <= as_of")
        for name, dimension in self.dimensions.items():
            if (
                dimension.data_cutoff is not None
                and _utc(dimension.data_cutoff) > _utc(self.as_of)
            ):
                raise ValueError(f"{name}.data_cutoff must be <= as_of")
        return self


class AssetView(_StrictModel):
    asset_id: str
    score: float | None
    confidence: float = Field(ge=0.0, le=1.0)
    status: PayloadStatus = "OK"
    data_cutoff: datetime | None = None
    horizon: str | None = None
    rationale: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _status_upper(cls, value: Any) -> Any:
        return str(value).upper()

    @field_validator("score")
    @classmethod
    def _score_bounds(cls, value: float | None) -> float | None:
        if value is not None and not -2.0 <= float(value) <= 2.0:
            raise ValueError("asset view score must be in [-2, 2]")
        return value


class AssetViewsContract(_StrictModel):
    contract_version: str
    as_of: datetime
    status: PayloadStatus
    views: list[AssetView]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("contract_version")
    @classmethod
    def _contract_v1(cls, value: str) -> str:
        return validate_contract_version(value)

    @field_validator("status", mode="before")
    @classmethod
    def _status_upper(cls, value: Any) -> Any:
        return str(value).upper()


class IntegrationValidationReport(_StrictModel):
    status: ValidationStatus
    contract_version: str | None = None
    macro_status: PayloadStatus | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    normalized_asset_ids: list[str] = Field(default_factory=list)
    legacy_fallback_used: bool = False

    @property
    def exit_code(self) -> int:
        return {"PASS": 0, "DEGRADED": 2, "FAIL": 1}[self.status]


__all__ = [
    "ALLOCATABLE_ASSETS",
    "ASSET_ID_ALIASES",
    "AssetView",
    "AssetViewsContract",
    "IntegrationManifest",
    "IntegrationValidationReport",
    "KNOWN_MACRO_DIMENSIONS",
    "MacroDimensionContract",
    "MarcoMacroState",
    "REQUIRED_MACRO_DIMENSIONS",
    "VIEWABLE_ASSETS",
    "contract_major",
    "normalize_asset_id",
    "validate_contract_version",
]
