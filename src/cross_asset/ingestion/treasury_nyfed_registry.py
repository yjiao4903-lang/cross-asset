"""Load the isolated Treasury / NY Fed C0 registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .treasury_nyfed_c0_contract import DEFAULT_REGISTRY_PATH

ALLOWED_STATUS = {"CANDIDATE", "RESOLVED", "UNRESOLVED", "BLOCKED"}
ALLOWED_PROVIDERS = {"TREASURY_FISCALDATA", "NYFED_MARKETS"}


class TreasuryNYFedRegistryError(ValueError):
    """Raised when the isolated C0 registry cannot be loaded safely."""


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    canonical_series_id: str
    provider: str
    endpoint: str | None
    observation_field: str | None
    value_fields: tuple[str, ...]
    identity_fields: tuple[str, ...]
    confirmed_fields: tuple[str, ...]
    units: str | None
    frequency: str | None
    timezone: str
    available_at_policy: str | None
    available_at_policy_note: str | None
    revision_policy: str | None
    status: str
    official_page: str | None
    official_keyid: str | None
    catalog_endpoint: str | None
    historical_endpoint: str | None
    operation_type_filter: str | None
    notes: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class TreasuryNYFedRegistry:
    workstream: str
    domain_gate: str
    usage: str
    production_admission: bool
    providers: dict[str, dict[str, Any]]
    datasets: tuple[DatasetSpec, ...]
    source_path: str

    def get(self, dataset_id: str) -> DatasetSpec:
        for item in self.datasets:
            if item.dataset_id == dataset_id:
                return item
        raise TreasuryNYFedRegistryError(f"unknown_dataset:{dataset_id}")

    def resolved(self) -> tuple[DatasetSpec, ...]:
        return tuple(item for item in self.datasets if item.status == "RESOLVED")

    def unresolved(self) -> tuple[DatasetSpec, ...]:
        return tuple(item for item in self.datasets if item.status in {"UNRESOLVED", "BLOCKED"})


def _as_tuple(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if not isinstance(value, list):
        raise TreasuryNYFedRegistryError("fields_must_be_list")
    return tuple(str(item) for item in value)


def load_registry(path: str | Path | None = None) -> TreasuryNYFedRegistry:
    registry_path = Path(path or DEFAULT_REGISTRY_PATH)
    if not registry_path.is_file():
        raise TreasuryNYFedRegistryError(f"registry_missing:{registry_path}")
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TreasuryNYFedRegistryError("registry_must_be_mapping")
    if payload.get("domain_gate") != "C0":
        raise TreasuryNYFedRegistryError("domain_gate_must_be_C0")
    if payload.get("usage") != "RESEARCH_STAGING_ONLY":
        raise TreasuryNYFedRegistryError("usage_must_be_RESEARCH_STAGING_ONLY")
    if payload.get("production_admission") is not False:
        raise TreasuryNYFedRegistryError("production_admission_forbidden")
    if payload.get("allocation_signal") is not False:
        raise TreasuryNYFedRegistryError("allocation_signal_forbidden")

    datasets: list[DatasetSpec] = []
    for raw in payload.get("datasets") or []:
        if not isinstance(raw, dict):
            raise TreasuryNYFedRegistryError("dataset_must_be_mapping")
        status = str(raw.get("status") or "")
        provider = str(raw.get("provider") or "")
        if status not in ALLOWED_STATUS:
            raise TreasuryNYFedRegistryError(f"invalid_status:{raw.get('dataset_id')}:{status}")
        if provider not in ALLOWED_PROVIDERS:
            raise TreasuryNYFedRegistryError(f"invalid_provider:{raw.get('dataset_id')}:{provider}")
        datasets.append(
            DatasetSpec(
                dataset_id=str(raw["dataset_id"]),
                canonical_series_id=str(raw.get("canonical_series_id") or raw["dataset_id"]),
                provider=provider,
                endpoint=raw.get("endpoint"),
                observation_field=raw.get("observation_field"),
                value_fields=_as_tuple(raw.get("value_fields")),
                identity_fields=_as_tuple(raw.get("identity_fields")),
                confirmed_fields=_as_tuple(raw.get("confirmed_fields")),
                units=raw.get("units"),
                frequency=raw.get("frequency"),
                timezone=str(raw.get("timezone") or "America/New_York"),
                available_at_policy=raw.get("available_at_policy"),
                available_at_policy_note=raw.get("available_at_policy_note"),
                revision_policy=raw.get("revision_policy"),
                status=status,
                official_page=raw.get("official_page"),
                official_keyid=raw.get("official_keyid"),
                catalog_endpoint=raw.get("catalog_endpoint"),
                historical_endpoint=raw.get("historical_endpoint"),
                operation_type_filter=raw.get("operation_type_filter"),
                notes=raw.get("notes"),
                raw=raw,
            )
        )
    return TreasuryNYFedRegistry(
        workstream=str(payload.get("workstream") or ""),
        domain_gate="C0",
        usage="RESEARCH_STAGING_ONLY",
        production_admission=False,
        providers=dict(payload.get("providers") or {}),
        datasets=tuple(datasets),
        source_path=str(registry_path),
    )
