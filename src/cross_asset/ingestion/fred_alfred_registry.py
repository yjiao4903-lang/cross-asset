"""Validated C0 registry for official FRED/ALFRED research-staging series."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_ALLOWED_STATUS = {"CANDIDATE", "UNRESOLVED", "BLOCKED"}
_REQUIRED_FIELDS = {
    "provider_series_id",
    "title",
    "units",
    "frequency",
    "seasonal_adjustment",
    "observation_semantics",
    "revision_vintage_policy",
    "release_availability_policy",
    "source_url",
    "status",
}


@dataclass(frozen=True)
class FredSeriesSpec:
    canonical_series_id: str
    provider: str
    provider_series_id: str
    title: str
    units: str
    frequency: str
    seasonal_adjustment: str
    observation_semantics: str
    revision_vintage_policy: str
    release_availability_policy: str
    source_url: str
    status: str
    known_long_gaps: tuple[tuple[str, str], ...] = ()
    metadata_notes: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.provider != "FRED/ALFRED":
            raise ValueError(f"fred_registry_provider_invalid:{self.canonical_series_id}")
        if self.status not in _ALLOWED_STATUS:
            raise ValueError(f"fred_registry_status_invalid:{self.canonical_series_id}")
        if not self.provider_series_id or not self.source_url.startswith(
            "https://fred.stlouisfed.org/"
        ):
            raise ValueError(f"fred_registry_source_identity_invalid:{self.canonical_series_id}")
        if not all(
            (
                self.title,
                self.units,
                self.frequency,
                self.seasonal_adjustment,
                self.observation_semantics,
                self.revision_vintage_policy,
                self.release_availability_policy,
            )
        ):
            raise ValueError(f"fred_registry_metadata_incomplete:{self.canonical_series_id}")


@dataclass(frozen=True)
class FredRegistry:
    version: str
    provider: str
    domain_gate: str
    usage: str
    metadata_audited_at: str
    api_identity: dict[str, str]
    availability_contract: dict[str, str]
    series: dict[str, FredSeriesSpec]

    def validate(self) -> None:
        if self.domain_gate != "C0" or self.usage != "RESEARCH_STAGING_ONLY":
            raise ValueError("fred_registry_must_remain_c0_research_staging_only")
        if self.provider != "FRED/ALFRED":
            raise ValueError("fred_registry_provider_invalid")
        if not self.version or not self.metadata_audited_at:
            raise ValueError("fred_registry_version_required")
        if not self.series:
            raise ValueError("fred_registry_series_required")
        provider_ids: set[str] = set()
        for canonical, spec in self.series.items():
            if canonical != spec.canonical_series_id:
                raise ValueError(f"fred_registry_canonical_key_mismatch:{canonical}")
            spec.validate()
            if spec.provider_series_id in provider_ids:
                raise ValueError(f"fred_registry_duplicate_provider_id:{spec.provider_series_id}")
            provider_ids.add(spec.provider_series_id)

    def candidate_series(self) -> tuple[str, ...]:
        return tuple(key for key, value in self.series.items() if value.status == "CANDIDATE")

    def by_provider_id(self, provider_series_id: str) -> FredSeriesSpec:
        for spec in self.series.values():
            if spec.provider_series_id == provider_series_id:
                return spec
        raise KeyError(provider_series_id)


def _as_mapping(value: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{name}_must_be_mapping")
    return value


def load_fred_registry(path: str | Path = "config/fred_alfred_registry.yml") -> FredRegistry:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    root = _as_mapping(raw, name="fred_registry")
    series_raw = _as_mapping(root.get("series"), name="fred_registry_series")
    specs: dict[str, FredSeriesSpec] = {}
    for canonical, value in series_raw.items():
        entry = _as_mapping(value, name=f"fred_registry_series_{canonical}")
        missing = sorted(_REQUIRED_FIELDS - set(entry))
        if missing:
            raise ValueError(f"fred_registry_missing_fields:{canonical}:{','.join(missing)}")
        specs[str(canonical)] = FredSeriesSpec(
            canonical_series_id=str(canonical),
            provider=str(root.get("provider", "")),
            provider_series_id=str(entry["provider_series_id"]),
            title=str(entry["title"]),
            units=str(entry["units"]),
            frequency=str(entry["frequency"]),
            seasonal_adjustment=str(entry["seasonal_adjustment"]),
            observation_semantics=str(entry["observation_semantics"]),
            revision_vintage_policy=str(entry["revision_vintage_policy"]),
            release_availability_policy=str(entry["release_availability_policy"]),
            source_url=str(entry["source_url"]),
            status=str(entry["status"]),
            known_long_gaps=tuple(
                (str(pair[0]), str(pair[1]))
                for pair in entry.get("known_long_gaps", [])
                if isinstance(pair, list) and len(pair) == 2
            ),
            metadata_notes=tuple(str(note) for note in entry.get("metadata_notes", [])),
        )
    registry = FredRegistry(
        version=str(root.get("version", "")),
        provider=str(root.get("provider", "")),
        domain_gate=str(root.get("domain_gate", "")),
        usage=str(root.get("usage", "")),
        metadata_audited_at=str(root.get("metadata_audited_at", "")),
        api_identity={
            str(key): str(value)
            for key, value in _as_mapping(root.get("api_identity"), name="api_identity").items()
        },
        availability_contract={
            str(key): str(value)
            for key, value in _as_mapping(
                root.get("availability_contract"), name="availability_contract"
            ).items()
        },
        series=specs,
    )
    registry.validate()
    return registry


__all__ = ["FredRegistry", "FredSeriesSpec", "load_fred_registry"]
