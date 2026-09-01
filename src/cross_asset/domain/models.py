from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import DataQuality, Frequency, ProviderName


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    series_id: str
    observation_date: date
    available_at: datetime
    value: float | None = None
    source: str
    source_series_id: str
    vintage_date: date | None = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    frequency: str | Frequency = "unknown"
    unit: str = "unknown"
    currency: str | None = None
    timezone: str | None = None
    quality: str | DataQuality = DataQuality.OK
    is_final: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    series_ids: list[str] = Field(default_factory=list)
    start: date | None = None
    end: date | None = None
    as_of: datetime | None = None
    source_series_ids: dict[str, str] = Field(default_factory=dict)


class ProviderCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderName | str
    login: str | bool | None = None
    price: str | bool | None = None
    index: str | bool | None = None
    bond: str | bool | None = None
    macro: str | bool | None = None
    valuation: str | bool | None = None
    history: str | None = None
    notes: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Preserve the original adapter-friendly ``ProviderCapability(name, ...)``
    # call shape while keeping this Pydantic model canonical.
    def __init__(self, provider=None, **data):
        if provider is not None:
            data["provider"] = provider
        super().__init__(**data)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
