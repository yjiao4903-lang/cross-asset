"""C0 China margin-financing positioning parser and research transforms.

The first W1 China positioning slice is deliberately financing-first.  This
module keeps one official source identity per snapshot, requires an explicit
publication/availability timestamp, and applies the accepted conservative
T+1 09:00 Asia/Shanghai boundary.  It does not infer a next trading session,
fill missing securities-lending values with zero, or combine exchange
sources.

This is a C0 candidate/shadow foundation.  It does not write observations,
touch the #18 acceptance registry, feed Allocation, or create a Northbound,
CFFEX, free-float-denominator, or directional-alpha signal.
"""

from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time
from enum import StrEnum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from cross_asset.ingestion.origin import DataOrigin

from .raw_archive import ImmutableRawArchive

PARSER_VERSION = "china_leverage_parser_v1"
DEFAULT_STALENESS_DAYS = 7
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_EARLIEST_SAFE_TIME = time(9, 0)
CANONICAL_SERIES_ID = "POS_CN_RZRQ"


class ChinaLeverageSourceStatus(StrEnum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNAPPROVED = "UNAPPROVED"
    DATA_BLOCKED = "DATA_BLOCKED"


class ChinaLeverageError(ValueError):
    """Explicit parser/PIT failure; callers must not silently fill values."""


class ChinaLeverageUnapprovedSourceError(ChinaLeverageError):
    pass


class ChinaLeverageDuplicateError(ChinaLeverageError):
    pass


@dataclass(frozen=True)
class ChinaLeverageSourceSpec:
    provider: str
    source_series_id: str
    source_reference: str
    scope: str


def default_china_leverage_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "china_leverage.yml"


def load_china_leverage_sources(
    path: str | Path | None = None,
) -> tuple[ChinaLeverageSourceSpec, ...]:
    """Load official-source identities from the repository config."""

    config_path = Path(path) if path is not None else default_china_leverage_config_path()
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ChinaLeverageError(
            f"china_leverage_mapping_unavailable:{type(exc).__name__}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("canonical_series_id") != CANONICAL_SERIES_ID:
        raise ChinaLeverageError("china_leverage_canonical_mapping_invalid")
    entries = payload.get("sources")
    if not isinstance(entries, list) or not entries:
        raise ChinaLeverageError("china_leverage_sources_required")
    specs: list[ChinaLeverageSourceSpec] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ChinaLeverageError("china_leverage_source_entry_invalid")
        try:
            provider = str(entry["provider"]).strip().lower()
            source_series_id = str(entry["source_series_id"]).strip()
            source_reference = str(entry["source_reference"]).strip()
            scope = str(entry["scope"]).strip()
        except (KeyError, TypeError) as exc:
            raise ChinaLeverageError("china_leverage_source_entry_incomplete") from exc
        if not provider or not source_series_id or not source_reference or not scope:
            raise ChinaLeverageError("china_leverage_source_entry_incomplete")
        identity = (provider, source_series_id)
        if identity in seen:
            raise ChinaLeverageError(f"duplicate_china_leverage_source:{identity}")
        seen.add(identity)
        specs.append(
            ChinaLeverageSourceSpec(provider, source_series_id, source_reference, scope)
        )
    return tuple(specs)


def source_spec(
    provider: str,
    source_series_id: str | None = None,
    *,
    sources: Iterable[ChinaLeverageSourceSpec] | None = None,
) -> ChinaLeverageSourceSpec:
    """Resolve one configured official source; no provider fallback is used."""

    normalized_provider = str(provider).strip().lower()
    configured = tuple(sources) if sources is not None else load_china_leverage_sources()
    candidates = [item for item in configured if item.provider == normalized_provider]
    if source_series_id is not None:
        candidates = [item for item in candidates if item.source_series_id == source_series_id]
    if len(candidates) != 1:
        raise ChinaLeverageUnapprovedSourceError(
            f"unapproved_source_identity:{normalized_provider}:{source_series_id or '<default>'}"
        )
    return candidates[0]


@dataclass(frozen=True)
class ChinaLeverageRecord:
    series_id: str
    observation_date: date
    financing_balance: float
    securities_lending_balance: float | None
    total_balance: float | None
    publication_at: datetime
    available_at: datetime
    ingested_at: datetime
    provider: str
    source_series_id: str
    source_file: str
    origin: DataOrigin
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "observation_date": self.observation_date.isoformat(),
            "financing_balance": self.financing_balance,
            "securities_lending_balance": self.securities_lending_balance,
            "total_balance": self.total_balance,
            "publication_at": self.publication_at.isoformat(),
            "available_at": self.available_at.isoformat(),
            "ingested_at": self.ingested_at.isoformat(),
            "provider": self.provider,
            "source_series_id": self.source_series_id,
            "source_file": self.source_file,
            "origin": self.origin.value,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ChinaLeverageMetric:
    series_id: str
    observation_date: date
    available_at: datetime
    provider: str
    source_series_id: str
    metric: str
    value: float | None
    unit: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "observation_date": self.observation_date.isoformat(),
            "available_at": self.available_at.isoformat(),
            "provider": self.provider,
            "source_series_id": self.source_series_id,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ChinaLeverageSourceHealth:
    provider: str
    source_series_id: str
    source_file: str
    fetched_at: datetime
    raw_archive_path: str | None
    last_success_at: datetime | None
    latest_observation: date | None
    latest_available_at: datetime | None
    freshness: str
    source_status: ChinaLeverageSourceStatus
    parser_status: str
    coverage_status: str
    row_count: int
    warnings: tuple[str, ...] = ()
    failure_reason: str | None = None
    origin: DataOrigin = DataOrigin.UNAVAILABLE

    def as_dict(self) -> dict[str, Any]:
        return {
            "series_id": CANONICAL_SERIES_ID,
            "provider": self.provider,
            "source_series_id": self.source_series_id,
            "source_file": self.source_file,
            "fetched_at": self.fetched_at.isoformat(),
            "raw_archive_path": self.raw_archive_path,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "latest_observation": self.latest_observation.isoformat()
            if self.latest_observation
            else None,
            "latest_available_at": self.latest_available_at.isoformat()
            if self.latest_available_at
            else None,
            "freshness": self.freshness,
            "source_status": self.source_status.value,
            "parser_status": self.parser_status,
            "coverage_status": self.coverage_status,
            "row_count": self.row_count,
            "warnings": list(self.warnings),
            "failure_reason": self.failure_reason,
            "origin": self.origin.value,
        }


_FIELD_ALIASES = {
    "observation_date": (
        "TRDDT",
        "TRADINGDATE",
        "TRADEDATE",
        "OBSERVATIONDATE",
        "DATE",
    ),
    "publication_date": ("PUBDT", "PUBLICATIONDATE", "PUBLISHDATE"),
    "publication_at": ("PUBLICATIONAT", "PUBLISHAT", "RELEASEAT"),
    "available_at": ("AVAILABLEAT", "AVAILABLETIME"),
    "financing_balance": (
        "FINVAL",
        "FINANCINGBALANCE",
        "MARGINFINANCINGBALANCE",
        "FINANCING",
    ),
    "securities_lending_balance": (
        "SECUVAL",
        "SECURITIESLENDINGBALANCE",
        "SECURITIESLENDING",
        "SHORTBALANCE",
    ),
    "total_balance": ("TTLVAL", "TOTALBALANCE", "MARGINBALANCE", "TOTAL"),
    "source_file": ("SOURCEFILE", "FILENAME"),
}


def _token(value: object) -> str:
    return "".join(character for character in str(value).upper() if character.isalnum())


def _utc(value: str | datetime, *, field: str) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChinaLeverageError(f"{field}_timezone_required")
    return parsed.astimezone(UTC)


def _origin(value: DataOrigin | str) -> DataOrigin:
    try:
        return value if isinstance(value, DataOrigin) else DataOrigin(str(value).upper())
    except ValueError as exc:
        raise ChinaLeverageError(f"origin_invalid:{value}") from exc


def _parse_date(value: object, *, field: str) -> date:
    raw = str(value or "").strip()
    if not raw:
        raise ChinaLeverageError(f"{field}_required")
    normalized = raw.replace("/", "-")
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        pass
    parts = normalized.split("-")
    if len(parts) == 3 and len(parts[0]) != 4:
        try:
            year = int(parts[2])
            year = year + 2000 if year < 100 else year
            return date(year, int(parts[0]), int(parts[1]))
        except ValueError:
            pass
    raise ChinaLeverageError(f"{field}_invalid:{raw}")


def _number(value: object, *, field: str, allow_empty: bool = False) -> float | None:
    raw = ("" if value is None else str(value)).strip().replace(",", "")
    if raw.upper() in {"", "NA", "N/A", "NULL", "-", "--"}:
        if allow_empty:
            return None
        raise ChinaLeverageError(f"{field}_required")
    try:
        parsed = float(raw)
    except (TypeError, ValueError) as exc:
        raise ChinaLeverageError(f"{field}_not_numeric:{raw}") from exc
    if not math.isfinite(parsed):
        raise ChinaLeverageError(f"{field}_not_finite")
    return parsed


def _normalized_row(row: Mapping[str, object]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        token = _token(key)
        if token in normalized:
            raise ChinaLeverageError(f"duplicate_normalized_header:{token}")
        normalized[token] = "" if value is None else str(value).strip()
    return normalized


def _find(row: Mapping[str, str], field: str, *, required: bool = True) -> str:
    for alias in _FIELD_ALIASES[field]:
        if alias in row:
            value = row[alias]
            if value or not required:
                return value
            if required:
                raise ChinaLeverageError(f"{field}_required")
    if required:
        raise ChinaLeverageError(f"{field}_column_missing")
    return ""


def conservative_margin_available_at(
    observation_date: date, *, next_session_date: date
) -> datetime:
    """Return T+1 09:00 Shanghai for an explicitly supplied next session.

    A trading calendar is intentionally not inferred here.  Callers must
    supply the next session date when they want to use this policy.
    """

    if next_session_date <= observation_date:
        raise ChinaLeverageError("next_session_date_must_follow_observation")
    return datetime.combine(next_session_date, _EARLIEST_SAFE_TIME, _SHANGHAI)


def _publication_from_row(
    row: Mapping[str, str],
    *,
    observation_date: date,
    default_publication_at: datetime | None,
    line_number: int,
) -> datetime:
    raw_at = _find(row, "publication_at", required=False)
    if raw_at:
        publication = _utc(raw_at, field=f"line_{line_number}:publication_at")
    else:
        raw_date = _find(row, "publication_date", required=False)
        if raw_date:
            publication_date = _parse_date(
                raw_date, field=f"line_{line_number}:publication_date"
            )
            publication = datetime.combine(publication_date, _EARLIEST_SAFE_TIME, _SHANGHAI).astimezone(
                UTC
            )
        elif default_publication_at is not None:
            publication = default_publication_at
        else:
            raise ChinaLeverageError(f"line_{line_number}:publication_at_required")
    if publication.astimezone(_SHANGHAI).date() <= observation_date:
        raise ChinaLeverageError(f"line_{line_number}:publication_must_follow_observation")
    return publication


def _available_from_row(
    row: Mapping[str, str],
    *,
    default_available_at: datetime | None,
    line_number: int,
) -> datetime:
    raw_at = _find(row, "available_at", required=False)
    if raw_at:
        return _utc(raw_at, field=f"line_{line_number}:available_at")
    if default_available_at is not None:
        return default_available_at
    raise ChinaLeverageError(f"line_{line_number}:available_at_required")


def _validate_t_plus_one(
    observation_date: date, publication_at: datetime, available_at: datetime, *, line_number: int
) -> None:
    available_local = available_at.astimezone(_SHANGHAI)
    if available_local.date() <= observation_date:
        raise ChinaLeverageError(f"line_{line_number}:t_day_data_not_available_at_close")
    if available_local.time() < _EARLIEST_SAFE_TIME:
        raise ChinaLeverageError(f"line_{line_number}:available_at_before_t_plus_1_0900")
    if available_at < publication_at:
        raise ChinaLeverageError(f"line_{line_number}:available_at_before_publication_at")


def parse_china_leverage_snapshot(
    payload: bytes | str,
    *,
    provider: str,
    source_series_id: str | None = None,
    publication_at: str | datetime | None = None,
    available_at: str | datetime | None = None,
    source_file: str | None = None,
    origin: DataOrigin | str = DataOrigin.FIXTURE,
    ingested_at: str | datetime | None = None,
    sources: Iterable[ChinaLeverageSourceSpec] | None = None,
) -> list[ChinaLeverageRecord]:
    """Parse a candidate snapshot with financing balance as the required input."""

    spec = source_spec(provider, source_series_id, sources=sources)
    origin_value = _origin(origin)
    default_publication = _utc(publication_at, field="publication_at") if publication_at else None
    default_available = _utc(available_at, field="available_at") if available_at else None
    captured_ingested_at = _utc(ingested_at, field="ingested_at") if ingested_at else datetime.now(UTC)
    if default_available is not None and default_publication is not None and default_available < default_publication:
        raise ChinaLeverageError("available_at_before_publication_at")
    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ChinaLeverageError("china_leverage_payload_encoding_invalid") from exc
    elif isinstance(payload, str):
        text = payload
    else:
        raise ChinaLeverageError("payload_must_be_text_or_bytes")
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    if not reader.fieldnames:
        raise ChinaLeverageError("china_leverage_csv_header_required")
    if any(not str(field).strip() for field in reader.fieldnames):
        raise ChinaLeverageError("china_leverage_csv_header_invalid")
    records: list[ChinaLeverageRecord] = []
    for line_number, raw_row in enumerate(reader, start=2):
        if None in raw_row:
            raise ChinaLeverageError(f"line_{line_number}:extra_columns")
        row = _normalized_row(raw_row)
        observation_date = _parse_date(
            _find(row, "observation_date"), field=f"line_{line_number}:observation_date"
        )
        publication = _publication_from_row(
            row,
            observation_date=observation_date,
            default_publication_at=default_publication,
            line_number=line_number,
        )
        available = _available_from_row(
            row, default_available_at=default_available, line_number=line_number
        )
        _validate_t_plus_one(observation_date, publication, available, line_number=line_number)
        financing = _number(
            _find(row, "financing_balance"), field=f"line_{line_number}:financing_balance"
        )
        if financing is None:
            raise ChinaLeverageError(f"line_{line_number}:financing_balance_required")
        lending = _number(
            _find(row, "securities_lending_balance", required=False),
            field=f"line_{line_number}:securities_lending_balance",
            allow_empty=True,
        )
        reported_total = _number(
            _find(row, "total_balance", required=False),
            field=f"line_{line_number}:total_balance",
            allow_empty=True,
        )
        computed_total = False
        total = reported_total
        if total is None and lending is not None:
            total = financing + lending
            computed_total = True
        if reported_total is not None and lending is not None:
            tolerance = max(1e-6, abs(reported_total) * 1e-9)
            if abs(reported_total - financing - lending) > tolerance:
                raise ChinaLeverageError(f"line_{line_number}:total_balance_mismatch")
        row_source_file = _find(row, "source_file", required=False) or source_file or "snapshot.csv"
        records.append(
            ChinaLeverageRecord(
                series_id=CANONICAL_SERIES_ID,
                observation_date=observation_date,
                financing_balance=financing,
                securities_lending_balance=lending,
                total_balance=total,
                publication_at=publication,
                available_at=available,
                ingested_at=captured_ingested_at,
                provider=spec.provider,
                source_series_id=spec.source_series_id,
                source_file=row_source_file,
                origin=origin_value,
                metadata={
                    "parser_version": PARSER_VERSION,
                    "availability_policy": "CONSERVATIVE_T_PLUS_1_0900_ASIA_SHANGHAI",
                    "publication_time_policy": "SOURCE_DATE_OR_EXPLICIT_TIMESTAMP",
                    "computed_total_balance": computed_total,
                    "securities_lending_optional": lending is None,
                    "source_scope": spec.scope,
                    "config": "config/china_leverage.yml",
                },
            )
        )
    if not records:
        raise ChinaLeverageError("china_leverage_snapshot_empty")
    return records


def _cutoff(value: str | datetime) -> datetime:
    return _utc(value, field="decision_time")


def _require_single_source(records: Iterable[ChinaLeverageRecord]) -> list[ChinaLeverageRecord]:
    values = list(records)
    identities = {(item.provider, item.source_series_id) for item in values}
    if len(identities) > 1:
        raise ChinaLeverageError("mixed_source_identity_not_combinable")
    return values


def resolve_china_leverage_revisions(
    records: Iterable[ChinaLeverageRecord], *, decision_time: str | datetime | None = None
) -> list[ChinaLeverageRecord]:
    """Select the latest available revision; same-time conflicts fail closed."""

    values = _require_single_source(records)
    if decision_time is not None:
        cutoff = _cutoff(decision_time)
        values = [item for item in values if item.available_at <= cutoff]
    grouped: dict[tuple[Any, ...], list[ChinaLeverageRecord]] = defaultdict(list)
    for item in values:
        grouped[(item.series_id, item.observation_date, item.provider, item.source_series_id)].append(item)
    selected: list[ChinaLeverageRecord] = []
    for key, candidates in grouped.items():
        candidates.sort(key=lambda item: (item.available_at, item.ingested_at))
        latest = candidates[-1]
        same_time = [item for item in candidates if item.available_at == latest.available_at]
        signature = (
            latest.financing_balance,
            latest.securities_lending_balance,
            latest.total_balance,
        )
        if any(
            (
                item.financing_balance,
                item.securities_lending_balance,
                item.total_balance,
            )
            != signature
            for item in same_time
        ):
            raise ChinaLeverageDuplicateError(f"conflicting_same_time_margin_report:{key}")
        if len(candidates) > 1:
            metadata = dict(latest.metadata)
            metadata["revision_candidates"] = len(candidates)
            metadata["revision_selected"] = True
            latest = replace(latest, metadata=metadata)
        selected.append(latest)
    return sorted(selected, key=lambda item: (item.observation_date, item.available_at))


def asof_china_leverage_records(
    records: Iterable[ChinaLeverageRecord], decision_time: str | datetime
) -> list[ChinaLeverageRecord]:
    return resolve_china_leverage_revisions(records, decision_time=decision_time)


def _metric(
    record: ChinaLeverageRecord,
    metric: str,
    value: float | None,
    unit: str,
    **metadata: Any,
) -> ChinaLeverageMetric:
    return ChinaLeverageMetric(
        series_id=record.series_id,
        observation_date=record.observation_date,
        available_at=record.available_at,
        provider=record.provider,
        source_series_id=record.source_series_id,
        metric=metric,
        value=value,
        unit=unit,
        metadata=metadata,
    )


def derive_china_leverage_metrics(
    records: Iterable[ChinaLeverageRecord],
    *,
    decision_time: str | datetime | None = None,
    percentile_window: int = 756,
) -> list[ChinaLeverageMetric]:
    """Derive financing changes and a causal rolling percentile only."""

    if percentile_window < 1:
        raise ChinaLeverageError("percentile_window_invalid")
    resolved = resolve_china_leverage_revisions(records, decision_time=decision_time)
    output: list[ChinaLeverageMetric] = []
    for position, record in enumerate(resolved):
        output.append(_metric(record, "financing_balance", record.financing_balance, "CNY"))
        previous = resolved[position - 1] if position >= 1 else None
        daily_change = (
            record.financing_balance - previous.financing_balance if previous is not None else None
        )
        output.append(
            _metric(
                record,
                "financing_daily_change",
                daily_change,
                "CNY",
                previous_observation=previous.observation_date.isoformat() if previous else None,
            )
        )
        for lookback in (20, 60):
            anchor = resolved[position - lookback] if position >= lookback else None
            change = record.financing_balance - anchor.financing_balance if anchor else None
            output.append(
                _metric(
                    record,
                    f"financing_{lookback}d_change",
                    change,
                    "CNY",
                    anchor_observation=anchor.observation_date.isoformat() if anchor else None,
                    lookback_observations=lookback,
                )
            )
        history = resolved[max(0, position - percentile_window + 1) : position + 1]
        values = [item.financing_balance for item in history]
        percentile = 100.0 * sum(value <= record.financing_balance for value in values) / len(values)
        output.append(
            _metric(
                record,
                "financing_rolling_percentile",
                percentile,
                "percentile",
                window_observations=len(values),
            )
        )
    return sorted(output, key=lambda item: (item.observation_date, item.metric))


def evaluate_china_leverage_source_health(
    records: Iterable[ChinaLeverageRecord],
    *,
    decision_time: str | datetime,
    provider: str,
    source_series_id: str,
    source_file: str,
    fetched_at: str | datetime | None = None,
    raw_archive_path: str | None = None,
    max_staleness_days: int = DEFAULT_STALENESS_DAYS,
) -> ChinaLeverageSourceHealth:
    values = _require_single_source(records)
    if any((item.provider, item.source_series_id) != (provider, source_series_id) for item in values):
        raise ChinaLeverageError("source_identity_mismatch")
    cutoff = _cutoff(decision_time)
    fetched = _utc(fetched_at, field="fetched_at") if fetched_at else datetime.now(UTC)
    resolved = asof_china_leverage_records(values, cutoff)
    if not resolved:
        return ChinaLeverageSourceHealth(
            provider=provider,
            source_series_id=source_series_id,
            source_file=source_file,
            fetched_at=fetched,
            raw_archive_path=raw_archive_path,
            last_success_at=None,
            latest_observation=None,
            latest_available_at=None,
            freshness="UNKNOWN",
            source_status=ChinaLeverageSourceStatus.DATA_BLOCKED,
            parser_status="PASS",
            coverage_status="NO_ADMISSIBLE_ROWS",
            row_count=0,
            warnings=("no_admissible_records",),
            origin=DataOrigin.UNAVAILABLE,
        )
    latest = max(resolved, key=lambda item: item.observation_date)
    age_days = (cutoff.date() - latest.observation_date).days
    warnings: list[str] = []
    if any(item.securities_lending_balance is None for item in resolved):
        warnings.append("securities_lending_optional_unavailable")
    if any(item.total_balance is None for item in resolved):
        warnings.append("total_balance_unavailable_without_source_lending_or_total")
    if age_days > max_staleness_days:
        warnings.append(f"stale_latest_observation_age_days:{age_days}")
    status = ChinaLeverageSourceStatus.STALE if age_days > max_staleness_days else ChinaLeverageSourceStatus.HEALTHY
    return ChinaLeverageSourceHealth(
        provider=provider,
        source_series_id=source_series_id,
        source_file=source_file,
        fetched_at=fetched,
        raw_archive_path=raw_archive_path,
        last_success_at=fetched,
        latest_observation=latest.observation_date,
        latest_available_at=max(item.available_at for item in resolved),
        freshness="STALE" if age_days > max_staleness_days else "FRESH",
        source_status=status,
        parser_status="PASS",
        coverage_status="FINANCING_ONLY",
        row_count=len(resolved),
        warnings=tuple(warnings),
        origin=latest.origin,
    )


def ingest_china_leverage_snapshot(
    payload: bytes | str,
    *,
    provider: str,
    decision_time: str | datetime,
    fetched_at: str | datetime,
    source_series_id: str | None = None,
    publication_at: str | datetime | None = None,
    available_at: str | datetime | None = None,
    source_file: str | None = None,
    origin: DataOrigin | str = DataOrigin.LIVE,
    raw_archive: ImmutableRawArchive | None = None,
    max_staleness_days: int = DEFAULT_STALENESS_DAYS,
) -> tuple[list[ChinaLeverageRecord], ChinaLeverageSourceHealth]:
    """Archive, parse, and evaluate one official-source candidate snapshot."""

    fetched = _utc(fetched_at, field="fetched_at")
    try:
        spec = source_spec(provider, source_series_id)
    except ChinaLeverageUnapprovedSourceError as exc:
        return [], ChinaLeverageSourceHealth(
            provider=str(provider).lower(),
            source_series_id=source_series_id or "unknown",
            source_file=source_file or "unknown",
            fetched_at=fetched,
            raw_archive_path=None,
            last_success_at=None,
            latest_observation=None,
            latest_available_at=None,
            freshness="UNKNOWN",
            source_status=ChinaLeverageSourceStatus.UNAPPROVED,
            parser_status="FAIL",
            coverage_status="NOT_PARSED",
            row_count=0,
            failure_reason=str(exc),
            origin=_origin(origin),
        )
    archive_path = None
    if raw_archive is not None:
        archive_path = raw_archive.write(
            spec.provider,
            CANONICAL_SERIES_ID,
            payload,
            captured_at=fetched,
            extension="csv",
        )
    failure_reason: str
    try:
        records = parse_china_leverage_snapshot(
            payload,
            provider=spec.provider,
            source_series_id=spec.source_series_id,
            publication_at=publication_at,
            available_at=available_at,
            source_file=source_file,
            origin=origin,
            ingested_at=fetched,
        )
        health = evaluate_china_leverage_source_health(
            records,
            decision_time=decision_time,
            provider=spec.provider,
            source_series_id=spec.source_series_id,
            source_file=source_file or records[0].source_file,
            fetched_at=fetched,
            raw_archive_path=archive_path,
            max_staleness_days=max_staleness_days,
        )
        return records, health
    except ChinaLeverageUnapprovedSourceError as exc:
        status = ChinaLeverageSourceStatus.UNAPPROVED
        failure_reason = str(exc)
    except ChinaLeverageError as exc:
        status = ChinaLeverageSourceStatus.FAILED
        failure_reason = str(exc)
    return [], ChinaLeverageSourceHealth(
        provider=spec.provider,
        source_series_id=spec.source_series_id,
        source_file=source_file or "unknown",
        fetched_at=fetched,
        raw_archive_path=archive_path,
        last_success_at=None,
        latest_observation=None,
        latest_available_at=None,
        freshness="UNKNOWN",
        source_status=status,
        parser_status="FAIL",
        coverage_status="NOT_PARSED",
        row_count=0,
        failure_reason=failure_reason,
        origin=_origin(origin),
    )


__all__ = [
    "CANONICAL_SERIES_ID",
    "DEFAULT_STALENESS_DAYS",
    "PARSER_VERSION",
    "ChinaLeverageDuplicateError",
    "ChinaLeverageError",
    "ChinaLeverageMetric",
    "ChinaLeverageRecord",
    "ChinaLeverageSourceHealth",
    "ChinaLeverageSourceSpec",
    "ChinaLeverageSourceStatus",
    "ChinaLeverageUnapprovedSourceError",
    "asof_china_leverage_records",
    "conservative_margin_available_at",
    "default_china_leverage_config_path",
    "derive_china_leverage_metrics",
    "evaluate_china_leverage_source_health",
    "ingest_china_leverage_snapshot",
    "load_china_leverage_sources",
    "parse_china_leverage_snapshot",
    "resolve_china_leverage_revisions",
    "source_spec",
]
