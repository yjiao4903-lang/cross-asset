"""Isolated C0 quality checks and coverage manifests for Treasury/NY Fed."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

from cross_asset.ingestion.treasury_nyfed_http import schema_hash
from cross_asset.ingestion.treasury_nyfed_pit import (
    TreasuryNYFedPITError,
    available_at_for_policy,
    parse_date,
    parse_datetime,
)
from cross_asset.ingestion.treasury_nyfed_registry import DatasetSpec


@dataclass(frozen=True)
class QualityReport:
    source_health: str
    row_count: int
    missing_ratio: float
    duplicate_count: int
    non_monotonic_count: int
    future_available_at_count: int
    long_gaps: tuple[tuple[str, str, int], ...]
    schema_drift: tuple[str, ...]
    pagination_truncated: bool
    empty_payload: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CoverageManifest:
    dataset_id: str
    canonical_series_id: str
    provider: str
    status: str
    requested_start: str | None
    requested_end: str | None
    returned_start: str | None
    returned_end: str | None
    row_count: int
    missing_ratio: float
    duplicate_count: int
    schema_hash: str | None
    raw_hash: str | None
    first_observation: str | None
    last_observation: str | None
    latest_available_at: str | None
    source_health: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    live: bool
    official_endpoint: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _numeric(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"null", "none", "na"}:
        return None
    return float(text.replace(",", ""))


def observation_date(row: dict[str, Any], spec: DatasetSpec):
    field = spec.observation_field or "record_date"
    raw = row.get(field)
    if raw is None:
        raise TreasuryNYFedPITError(f"missing_observation_field:{spec.dataset_id}:{field}")
    return parse_date(str(raw))


def attach_available_at(
    rows: Iterable[dict[str, Any]],
    spec: DatasetSpec,
    *,
    fetched_at: datetime | None = None,
) -> list[dict[str, Any]]:
    if spec.status in {"UNRESOLVED", "BLOCKED"}:
        raise TreasuryNYFedPITError(f"dataset_not_collectible:{spec.dataset_id}:{spec.status}")
    if not spec.available_at_policy:
        raise TreasuryNYFedPITError(f"available_at_policy_required:{spec.dataset_id}")
    attached: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        obs = observation_date(row, spec)
        last_updated = row.get("lastUpdated") or row.get("last_updated")
        available = available_at_for_policy(
            observation_date=obs,
            policy=spec.available_at_policy,
            last_updated=str(last_updated) if last_updated else None,
            timezone=spec.timezone,
        )
        row["observation_date"] = obs.isoformat()
        row["available_at"] = available.isoformat()
        row["dataset_id"] = spec.dataset_id
        attached.append(row)
    return attached


def _identity(row: dict[str, Any], spec: DatasetSpec) -> tuple[str, ...]:
    fields = spec.identity_fields or (spec.observation_field or "record_date",)
    return tuple(str(row.get(field) or "") for field in fields)


def audit_quality(
    rows: Iterable[dict[str, Any]],
    *,
    spec: DatasetSpec,
    truncated: bool = False,
    fetched_at: datetime | None = None,
) -> QualityReport:
    records = list(rows)
    blockers: list[str] = []
    warnings: list[str] = []
    if spec.status in {"UNRESOLVED", "BLOCKED"}:
        return QualityReport(
            source_health="BLOCKED",
            row_count=0,
            missing_ratio=1.0,
            duplicate_count=0,
            non_monotonic_count=0,
            future_available_at_count=0,
            long_gaps=(),
            schema_drift=(),
            pagination_truncated=False,
            empty_payload=True,
            blockers=(f"dataset_{spec.status.lower()}",),
            warnings=(),
        )
    if not records:
        return QualityReport(
            source_health="BLOCKED",
            row_count=0,
            missing_ratio=1.0,
            duplicate_count=0,
            non_monotonic_count=0,
            future_available_at_count=0,
            long_gaps=(),
            schema_drift=(),
            pagination_truncated=truncated,
            empty_payload=True,
            blockers=("empty_payload",),
            warnings=(),
        )

    keys = [_identity(row, spec) for row in records]
    duplicate_count = len(keys) - len(set(keys))
    if duplicate_count:
        warnings.append("duplicates")

    dates = [parse_date(str(row.get("observation_date") or observation_date(row, spec))) for row in records]
    non_monotonic = sum(1 for left, right in pairwise(dates) if right < left)
    if non_monotonic:
        warnings.append("non_monotonic_dates")

    fetched = fetched_at or datetime.now(UTC)
    future_count = 0
    for row in records:
        raw_available = row.get("available_at")
        if raw_available is None:
            blockers.append("available_at_required")
            continue
        available = parse_datetime(str(raw_available), timezone=spec.timezone)
        if available > fetched:
            future_count += 1
    if future_count:
        blockers.append("future_available_at")

    missing = 0
    value_fields = spec.value_fields or ()
    for row in records:
        if value_fields and all(_numeric(row.get(field)) is None for field in value_fields):
            missing += 1
        if spec.dataset_id == "TREASURY_DTS_OPERATING_CASH":
            number = _numeric(row.get("close_today_bal"))
            if number is not None and number < 0:
                blockers.append("impossible_negative_value")
    missing_ratio = missing / len(records)
    if missing:
        warnings.append("missing_values")

    unique_dates = sorted(set(dates))
    gap_limit = 10 if spec.frequency == "daily" else 21 if spec.frequency == "weekly" else 75
    long_gaps: list[tuple[str, str, int]] = []
    for left, right in pairwise(unique_dates):
        delta = (right - left).days
        if delta > gap_limit:
            long_gaps.append((left.isoformat(), right.isoformat(), delta))
    if long_gaps:
        warnings.append("long_gaps")

    present = {key for row in records for key in row}
    drift = [f"missing:{field}" for field in spec.confirmed_fields if field not in present]
    if drift:
        blockers.append("schema_drift")
    if truncated:
        blockers.append("pagination_truncated")

    health = "BLOCKED" if blockers else ("DEGRADED" if warnings else "HEALTHY")
    return QualityReport(
        source_health=health,
        row_count=len(records),
        missing_ratio=missing_ratio,
        duplicate_count=duplicate_count,
        non_monotonic_count=non_monotonic,
        future_available_at_count=future_count,
        long_gaps=tuple(long_gaps),
        schema_drift=tuple(drift),
        pagination_truncated=truncated,
        empty_payload=False,
        blockers=tuple(dict.fromkeys(blockers)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def build_manifest(
    *,
    spec: DatasetSpec,
    rows: list[dict[str, Any]],
    quality: QualityReport,
    requested_start: str | None,
    requested_end: str | None,
    raw_hash: str | None,
    live: bool,
) -> CoverageManifest:
    dates = [str(row.get("observation_date")) for row in rows if row.get("observation_date")]
    available = [str(row.get("available_at")) for row in rows if row.get("available_at")]
    fields = sorted({key for row in rows for key in row})
    return CoverageManifest(
        dataset_id=spec.dataset_id,
        canonical_series_id=spec.canonical_series_id,
        provider=spec.provider,
        status=spec.status,
        requested_start=requested_start,
        requested_end=requested_end,
        returned_start=min(dates) if dates else None,
        returned_end=max(dates) if dates else None,
        row_count=quality.row_count,
        missing_ratio=quality.missing_ratio,
        duplicate_count=quality.duplicate_count,
        schema_hash=schema_hash(fields) if fields else None,
        raw_hash=raw_hash,
        first_observation=min(dates) if dates else None,
        last_observation=max(dates) if dates else None,
        latest_available_at=max(available) if available else None,
        source_health=quality.source_health,
        blockers=quality.blockers,
        warnings=quality.warnings,
        live=live,
        official_endpoint=spec.endpoint,
    )
