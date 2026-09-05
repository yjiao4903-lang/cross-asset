"""C0 CFTC positioning parser, PIT contract, and research-only transforms.

This module deliberately stops before the #18 production admission gate.  It
keeps the CFTC contract/report mapping in ``config/cftc_positioning.yml`` and
does not write Cross observations or call Allocation.  A captured CFTC file
must carry an explicit publication time; observation date is never used as a
publication fallback.

The parser accepts the official wide annual layout and a normalized long
layout.  Annual files have changed column names over time, so aliases are
kept in this adapter rather than spread through model code.  The output is a
source-scoped record with explicit report type, contract identity,
publication, availability, and ingestion timestamps.
"""

from __future__ import annotations

import csv
import io
import math
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time
from enum import StrEnum
from pathlib import Path
from statistics import mean, pstdev
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from cross_asset.ingestion.origin import DataOrigin

from .raw_archive import ImmutableRawArchive

PARSER_VERSION = "cftc_positioning_parser_v1"
DEFAULT_STALENESS_DAYS = 14
_EASTERN = ZoneInfo("America/New_York")


class CFTCReportType(StrEnum):
    DISAGGREGATED = "DISAGGREGATED"
    TFF = "TFF"


class CFTCSourceStatus(StrEnum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNAPPROVED = "UNAPPROVED"
    DATA_BLOCKED = "DATA_BLOCKED"


class CFTCPositioningError(ValueError):
    """Explicit parser/PIT failure; callers must stop rather than fill."""


class CFTCUnapprovedSourceError(CFTCPositioningError):
    pass


class CFTCDuplicateReportError(CFTCPositioningError):
    pass


@dataclass(frozen=True)
class CFTCContractSpec:
    series_id: str
    market_key: str
    report_type: CFTCReportType
    contract_market_codes: tuple[str, ...]
    source_series_id: str

    def matches(self, report_type: CFTCReportType, contract_market_code: str) -> bool:
        return self.report_type is report_type and contract_market_code.upper() in {
            code.upper() for code in self.contract_market_codes
        }


def default_cftc_config_path() -> Path:
    """Return the repository-owned CFTC mapping, without reading a cwd path."""

    return Path(__file__).resolve().parents[3] / "config" / "cftc_positioning.yml"


def load_cftc_contracts(path: str | Path | None = None) -> tuple[CFTCContractSpec, ...]:
    """Load and validate the centralized contract/report mapping."""

    config_path = Path(path) if path is not None else default_cftc_config_path()
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CFTCPositioningError(f"cftc_mapping_unavailable:{type(exc).__name__}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("markets"), list):
        raise CFTCPositioningError("cftc_mapping_markets_required")

    specs: list[CFTCContractSpec] = []
    seen_series: set[str] = set()
    seen_codes: set[tuple[CFTCReportType, str]] = set()
    for entry in payload["markets"]:
        if not isinstance(entry, dict):
            raise CFTCPositioningError("cftc_mapping_entry_invalid")
        try:
            series_id = str(entry["series_id"]).strip()
            market_key = str(entry["market_key"]).strip()
            report_type = CFTCReportType(str(entry["report_type"]).upper())
            source_series_id = str(entry["source_series_id"]).strip()
            codes = tuple(str(code).strip().upper() for code in entry["contract_market_codes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CFTCPositioningError("cftc_mapping_entry_incomplete") from exc
        if (
            not series_id
            or not market_key
            or not source_series_id
            or not codes
            or any(not code for code in codes)
        ):
            raise CFTCPositioningError("cftc_mapping_entry_incomplete")
        if series_id in seen_series:
            raise CFTCPositioningError(f"duplicate_cftc_series:{series_id}")
        for code in codes:
            key = (report_type, code)
            if key in seen_codes:
                raise CFTCPositioningError(f"duplicate_cftc_contract_code:{report_type}:{code}")
            seen_codes.add(key)
        seen_series.add(series_id)
        specs.append(
            CFTCContractSpec(
                series_id=series_id,
                market_key=market_key,
                report_type=report_type,
                contract_market_codes=codes,
                source_series_id=source_series_id,
            )
        )
    return tuple(specs)


@dataclass(frozen=True)
class CFTCPositionRecord:
    series_id: str
    market_key: str
    market_name: str
    contract_market_code: str
    report_date: date
    report_type: CFTCReportType
    participant_category: str
    long: float
    short: float
    spreading: float | None
    open_interest: float
    source_file: str
    source_year: int
    publication_at: datetime
    available_at: datetime
    ingested_at: datetime
    provider: str
    source_series_id: str
    origin: DataOrigin
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def net_position(self) -> float:
        return self.long - self.short

    def as_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "market_key": self.market_key,
            "market_name": self.market_name,
            "contract_market_code": self.contract_market_code,
            "report_date": self.report_date.isoformat(),
            "report_type": self.report_type.value,
            "participant_category": self.participant_category,
            "long": self.long,
            "short": self.short,
            "spreading": self.spreading,
            "open_interest": self.open_interest,
            "source_file": self.source_file,
            "source_year": self.source_year,
            "publication_at": self.publication_at.isoformat(),
            "available_at": self.available_at.isoformat(),
            "ingested_at": self.ingested_at.isoformat(),
            "provider": self.provider,
            "source_series_id": self.source_series_id,
            "origin": self.origin.value,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PositioningMetric:
    series_id: str
    market_key: str
    report_date: date
    report_type: CFTCReportType
    participant_category: str
    available_at: datetime
    metric: str
    value: float | None
    unit: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "market_key": self.market_key,
            "report_date": self.report_date.isoformat(),
            "report_type": self.report_type.value,
            "participant_category": self.participant_category,
            "available_at": self.available_at.isoformat(),
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CFTCSourceHealth:
    provider: str
    report_type: CFTCReportType
    source_file: str
    source_year: int
    fetched_at: datetime
    raw_archive_path: str | None
    last_success_at: datetime | None
    latest_observation: date | None
    latest_available_at: datetime | None
    freshness: str
    source_status: CFTCSourceStatus
    parser_status: str
    coverage_status: str
    row_count: int
    warnings: tuple[str, ...] = ()
    failure_reason: str | None = None
    origin: DataOrigin = DataOrigin.UNAVAILABLE

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "report_type": self.report_type.value,
            "source_file": self.source_file,
            "source_year": self.source_year,
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
    "market_name": (
        "MARKETANDEXCHANGENAMES",
        "MARKETNAME",
        "MARKETANDEXCHANGENAME",
    ),
    "contract_market_code": (
        "CFTCCONTRACTMARKETCODE",
        "CONTRACTMARKETCODE",
        "CFTCCONTRACTCODE",
    ),
    "report_date": (
        "ASOFDATEINFORMYYMMDD",
        "ASOFDATE",
        "REPORTDATE",
        "REPORTDATEYYYYMMDD",
    ),
    "open_interest": ("OPENINTERESTALL", "OPENINTEREST", "OPENINTERESTTOTAL"),
    "participant_category": ("PARTICIPANTCATEGORY", "CATEGORY", "PARTICIPANT"),
    "long": ("LONG", "LONGPOSITION", "POSITIONSLONG"),
    "short": ("SHORT", "SHORTPOSITION", "POSITIONSSHORT"),
    "spreading": ("SPREADING", "SPREAD", "POSITIONSSPREAD"),
    "publication_at": ("PUBLICATIONAT", "PUBLICATIONTIME", "RELEASEAT", "RELEASETIME"),
    "available_at": ("AVAILABLEAT", "AVAILABLETIME"),
    "source_file": ("SOURCEFILE", "FILENAME"),
}

_PARTICIPANT_ALIASES: dict[CFTCReportType, dict[str, tuple[str, ...]]] = {
    CFTCReportType.DISAGGREGATED: {
        "PRODUCER_MERCHANT": (
            "PRODMERCPOSITIONS",
            "PRODUCER_MERCHANT",
            "PRODMERC",
            "PRODUCERMERCHANT",
            "PRODUCER",
        ),
        "SWAP_DEALER": ("SWAPPOSITIONS", "SWAP_DEALER", "SWAPDEALER", "SWAP"),
        "MANAGED_MONEY": (
            "MMONEYPOSITIONS",
            "MANAGED_MONEY",
            "MANAGEDMONEY",
            "MANAGED",
        ),
        "OTHER_REPORTABLE": ("OTHERREPTPOSITIONS", "OTHER_REPORTABLE", "OTHERREPORTABLE"),
        "NONREPORTABLE": ("NONREPTPOSITIONS", "NONREPORTABLE", "NONREPORTABLEPOSITIONS"),
    },
    CFTCReportType.TFF: {
        "DEALER_INTERMEDIARY": (
            "DEALERPOSITIONS",
            "DEALER_INTERMEDIARY",
            "DEALERINTERMEDIARY",
            "DEALER",
        ),
        "ASSET_MANAGER": (
            "ASSETMGRPOSITIONS",
            "ASSET_MANAGER",
            "ASSETMANAGER",
            "ASSETMGR",
        ),
        "LEVERAGED_FUNDS": (
            "LEVMONEYPOSITIONS",
            "LEVERAGED_FUNDS",
            "LEVERAGEDFUNDS",
            "LEVMONEY",
            "LEVERAGED",
        ),
        "OTHER_REPORTABLE": ("OTHERREPTPOSITIONS", "OTHER_REPORTABLE", "OTHERREPORTABLE"),
        "NONREPORTABLE": ("NONREPTPOSITIONS", "NONREPORTABLE", "NONREPORTABLEPOSITIONS"),
    },
}

_WIDE_FIELD_SUFFIXES = {
    "long": ("LONGALL", "LONG"),
    "short": ("SHORTALL", "SHORT"),
    "spreading": ("SPREADALL", "SPREAD"),
}


def _token(value: object) -> str:
    return "".join(character for character in str(value).upper() if character.isalnum())


def _utc(value: str | datetime, *, field: str) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CFTCPositioningError(f"{field}_timezone_required")
    return parsed.astimezone(UTC)


def _ingested_at(value: str | datetime | None) -> datetime:
    return _utc(value, field="ingested_at") if value is not None else datetime.now(UTC)


def cftc_publication_at(publication_date: date, *, release_time: time = time(15, 30)) -> datetime:
    """Build the documented 15:30 ET timestamp for a caller-supplied date.

    The date must come from the actual CFTC release schedule.  This helper
    does not guess Friday/holiday shifts.
    """

    return datetime.combine(publication_date, release_time, _EASTERN).astimezone(UTC)


def _parse_date(value: object, *, field: str) -> date:
    raw = str(value or "").strip()
    if not raw:
        raise CFTCPositioningError(f"{field}_required")
    candidates = (raw, raw.replace("/", "-"))
    for candidate in candidates:
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    for separator in ("-", "/"):
        parts = raw.split(separator)
        if len(parts) != 3:
            continue
        try:
            if len(parts[0]) == 4:
                year, month, day = (int(part) for part in parts)
            else:
                month, day = int(parts[0]), int(parts[1])
                year = int(parts[2])
                year = year + 2000 if year < 100 else year
            return date(year, month, day)
        except ValueError:
            continue
    if len(raw) == 8 and raw.isdigit():
        try:
            if int(raw[:4]) >= 1900:
                return date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
            return date(2000 + int(raw[:2]), int(raw[2:4]), int(raw[4:]))
        except ValueError:
            pass
    raise CFTCPositioningError(f"{field}_invalid:{raw}")


def _number(value: object, *, field: str, allow_empty: bool = False) -> float | None:
    raw = ("" if value is None else str(value)).strip().replace(",", "")
    if not raw and allow_empty:
        return None
    if not raw:
        raise CFTCPositioningError(f"{field}_required")
    try:
        parsed = float(raw)
    except (TypeError, ValueError) as exc:
        raise CFTCPositioningError(f"{field}_not_numeric:{raw}") from exc
    if not math.isfinite(parsed):
        raise CFTCPositioningError(f"{field}_not_finite")
    return parsed


def _decode_payload(payload: bytes | str) -> tuple[str, str]:
    if isinstance(payload, str):
        return payload, "snapshot.txt"
    if not isinstance(payload, bytes):
        raise CFTCPositioningError("payload_must_be_text_or_bytes")
    buffer = io.BytesIO(payload)
    if zipfile.is_zipfile(buffer):
        with zipfile.ZipFile(buffer) as archive:
            members = sorted(
                name
                for name in archive.namelist()
                if not name.endswith("/") and name.lower().endswith((".txt", ".csv"))
            )
            if not members:
                raise CFTCPositioningError("zip_has_no_cftc_text_member")
            member = members[0]
            raw = archive.read(member)
    else:
        member = "snapshot.txt"
        raw = payload
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), member
        except UnicodeDecodeError:
            continue
    raise CFTCPositioningError("cftc_payload_encoding_invalid")


def _normalized_row(row: Mapping[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in row.items():
        normalized = _token(key)
        if normalized in result:
            raise CFTCPositioningError(f"duplicate_normalized_header:{normalized}")
        result[normalized] = str(value or "").strip()
    return result


def _find(row: Mapping[str, str], field: str, *, required: bool = True) -> str:
    for alias in _FIELD_ALIASES[field]:
        if alias in row:
            value = row[alias]
            if value or not required:
                return value
            if required:
                raise CFTCPositioningError(f"{field}_required")
    if required:
        raise CFTCPositioningError(f"{field}_column_missing")
    return ""


def _find_wide_field(
    row: Mapping[str, str], report_type: CFTCReportType, participant: str, measure: str
) -> str:
    prefixes = _PARTICIPANT_ALIASES[report_type][participant]
    suffixes = _WIDE_FIELD_SUFFIXES[measure]
    for prefix in prefixes:
        for suffix in suffixes:
            key = prefix + suffix
            if key in row:
                return row[key]
    if measure == "spreading":
        return ""
    raise CFTCPositioningError(f"{report_type}:{participant}:{measure}_column_missing")


def _canonical_participant(report_type: CFTCReportType, value: str) -> str:
    normalized = _token(value)
    for canonical, aliases in _PARTICIPANT_ALIASES[report_type].items():
        if normalized == _token(canonical) or any(normalized.startswith(alias) for alias in aliases):
            return canonical
    raise CFTCPositioningError(f"participant_category_unrecognized:{value}")


def _origin(value: DataOrigin | str) -> DataOrigin:
    try:
        return value if isinstance(value, DataOrigin) else DataOrigin(str(value).upper())
    except ValueError as exc:
        raise CFTCPositioningError(f"origin_invalid:{value}") from exc


def parse_cftc_snapshot(
    payload: bytes | str,
    *,
    report_type: CFTCReportType | str,
    source_year: int,
    provider: str = "cftc",
    publication_at: str | datetime | None = None,
    available_at: str | datetime | None = None,
    source_file: str | None = None,
    origin: DataOrigin | str = DataOrigin.FIXTURE,
    ingested_at: str | datetime | None = None,
    contracts: Iterable[CFTCContractSpec] | None = None,
) -> list[CFTCPositionRecord]:
    """Parse one CFTC annual snapshot without dropping malformed target rows.

    ``publication_at`` is required either as an explicit argument or as a
    per-row column.  If no separate availability timestamp is supplied, the
    explicit publication timestamp is used as the earliest safe availability;
    the observation date is never used as a fallback.
    """

    try:
        report_kind = CFTCReportType(str(report_type).upper())
    except ValueError as exc:
        raise CFTCPositioningError(f"unsupported_report_type:{report_type}") from exc
    if str(provider).lower() != "cftc":
        raise CFTCUnapprovedSourceError(f"unapproved_provider:{provider}")
    if not isinstance(source_year, int) or source_year < 1900:
        raise CFTCPositioningError("source_year_invalid")
    origin_value = _origin(origin)
    default_publication = _utc(publication_at, field="publication_at") if publication_at else None
    default_available = _utc(available_at, field="available_at") if available_at else None
    if (
        default_available is not None
        and default_publication is not None
        and default_available < default_publication
    ):
        raise CFTCPositioningError("available_at_before_publication_at")
    specs = tuple(contracts) if contracts is not None else load_cftc_contracts()
    code_map = {
        code.upper(): spec
        for spec in specs
        if spec.report_type is report_kind
        for code in spec.contract_market_codes
    }
    if not code_map:
        raise CFTCPositioningError(f"no_contract_mapping_for:{report_kind}")

    text, member_name = _decode_payload(payload)
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    if not reader.fieldnames:
        raise CFTCPositioningError("cftc_csv_header_required")
    if any(not str(field).strip() for field in reader.fieldnames):
        raise CFTCPositioningError("cftc_csv_header_invalid")
    normalized_headers = {_token(field) for field in reader.fieldnames}
    is_long_layout = any(
        alias in normalized_headers for alias in _FIELD_ALIASES["participant_category"]
    )
    parsed: list[CFTCPositionRecord] = []
    target_rows = 0
    captured_ingested_at = _ingested_at(ingested_at)

    for line_number, raw_row in enumerate(reader, start=2):
        if None in raw_row:
            raise CFTCPositioningError(f"line_{line_number}_extra_columns")
        row = _normalized_row(raw_row)
        code = _find(row, "contract_market_code").upper()
        spec = code_map.get(code)
        if spec is None:
            continue
        target_rows += 1
        report_date = _parse_date(_find(row, "report_date"), field=f"line_{line_number}:report_date")
        if report_date.weekday() != 1:
            raise CFTCPositioningError(f"line_{line_number}:report_date_must_be_tuesday")
        market_name = _find(row, "market_name", required=False) or spec.market_key
        row_publication_raw = _find(row, "publication_at", required=False)
        row_available_raw = _find(row, "available_at", required=False)
        row_publication = (
            _utc(row_publication_raw, field="publication_at")
            if row_publication_raw
            else default_publication
        )
        if row_publication is None:
            raise CFTCPositioningError(f"line_{line_number}:publication_at_required")
        row_available = (
            _utc(row_available_raw, field="available_at")
            if row_available_raw
            else default_available
        )
        availability_defaulted = False
        if row_available is None:
            row_available = row_publication
            availability_defaulted = True
        if row_available < row_publication:
            raise CFTCPositioningError(f"line_{line_number}:available_at_before_publication_at")
        row_source_file = _find(row, "source_file", required=False) or source_file or member_name

        if is_long_layout:
            participant = _canonical_participant(report_kind, _find(row, "participant_category"))
            rows_to_emit = [
                (
                    participant,
                    _number(_find(row, "long"), field=f"line_{line_number}:long"),
                    _number(_find(row, "short"), field=f"line_{line_number}:short"),
                    _number(
                        _find(row, "spreading", required=False),
                        field=f"line_{line_number}:spreading",
                        allow_empty=True,
                    ),
                    _number(_find(row, "open_interest"), field=f"line_{line_number}:open_interest"),
                )
            ]
        else:
            open_interest = _number(
                _find(row, "open_interest"), field=f"line_{line_number}:open_interest"
            )
            rows_to_emit = []
            for participant in _PARTICIPANT_ALIASES[report_kind]:
                rows_to_emit.append(
                    (
                        participant,
                        _number(
                            _find_wide_field(row, report_kind, participant, "long"),
                            field=f"line_{line_number}:{participant}:long",
                        ),
                        _number(
                            _find_wide_field(row, report_kind, participant, "short"),
                            field=f"line_{line_number}:{participant}:short",
                        ),
                        _number(
                            _find_wide_field(row, report_kind, participant, "spreading"),
                            field=f"line_{line_number}:{participant}:spreading",
                            allow_empty=True,
                        ),
                        open_interest,
                    )
                )
        for participant, long_value, short_value, spreading, open_interest_value in rows_to_emit:
            if long_value is None or short_value is None or open_interest_value is None:
                raise CFTCPositioningError(f"line_{line_number}:numeric_field_missing")
            parsed.append(
                CFTCPositionRecord(
                    series_id=spec.series_id,
                    market_key=spec.market_key,
                    market_name=market_name,
                    contract_market_code=code,
                    report_date=report_date,
                    report_type=report_kind,
                    participant_category=participant,
                    long=long_value,
                    short=short_value,
                    spreading=spreading,
                    open_interest=open_interest_value,
                    source_file=row_source_file,
                    source_year=source_year,
                    publication_at=row_publication,
                    available_at=row_available,
                    ingested_at=captured_ingested_at,
                    provider=provider,
                    source_series_id=spec.source_series_id,
                    origin=origin_value,
                    metadata={
                        "parser_version": PARSER_VERSION,
                        "layout": "long" if is_long_layout else "wide",
                        "availability_defaulted_to_publication": availability_defaulted,
                        "contract_mapping": "config/cftc_positioning.yml",
                    },
                )
            )
    if target_rows == 0:
        raise CFTCPositioningError(f"no_mapped_contract_rows:{report_kind}")
    return parsed


def _cutoff(value: str | datetime) -> datetime:
    return _utc(value, field="decision_time")


def resolve_cftc_revisions(
    records: Iterable[CFTCPositionRecord], *, decision_time: str | datetime | None = None
) -> list[CFTCPositionRecord]:
    """Select one report revision without hiding same-time conflicts.

    A later publication may revise an earlier report.  The latest version
    known by ``decision_time`` is selected.  Two conflicting rows with the
    same availability timestamp are rejected instead of silently choosing
    one.
    """

    source = list(records)
    if decision_time is not None:
        cutoff = _cutoff(decision_time)
        source = [
            record
            for record in source
            if _utc(record.available_at, field="available_at") <= cutoff
        ]
    grouped: dict[tuple[Any, ...], list[CFTCPositionRecord]] = defaultdict(list)
    for record in source:
        grouped[
            (
                record.series_id,
                record.report_type,
                record.contract_market_code,
                record.report_date,
                record.participant_category,
            )
        ].append(record)
    selected: list[CFTCPositionRecord] = []
    for key, candidates in grouped.items():
        candidates.sort(key=lambda item: (item.available_at, item.ingested_at))
        latest = candidates[-1]
        same_time = [item for item in candidates if item.available_at == latest.available_at]
        signature = (latest.long, latest.short, latest.spreading, latest.open_interest)
        if any(
            (item.long, item.short, item.spreading, item.open_interest) != signature
            for item in same_time
        ):
            raise CFTCDuplicateReportError(f"conflicting_same_time_report:{key}")
        metadata = dict(latest.metadata)
        if len(candidates) > 1:
            metadata["revision_candidates"] = len(candidates)
            metadata["revision_selected"] = True
            latest = replace(latest, metadata=metadata)
        selected.append(latest)
    return sorted(
        selected,
        key=lambda item: (
            item.series_id,
            item.report_date,
            item.participant_category,
            item.available_at,
        ),
    )


def asof_cftc_records(
    records: Iterable[CFTCPositionRecord], decision_time: str | datetime
) -> list[CFTCPositionRecord]:
    """Return only records available at the decision boundary."""

    return resolve_cftc_revisions(records, decision_time=decision_time)


def derive_net_position(record: CFTCPositionRecord) -> float:
    return record.long - record.short


def derive_percent_open_interest(record: CFTCPositionRecord) -> float | None:
    if record.open_interest <= 0:
        return None
    return 100.0 * derive_net_position(record) / record.open_interest


def _metric_value(record: CFTCPositionRecord, metric: str) -> float | None:
    if metric == "net_position":
        return derive_net_position(record)
    if metric == "percent_open_interest":
        return derive_percent_open_interest(record)
    raise CFTCPositioningError(f"unsupported_positioning_metric:{metric}")


def _group_records(records: Iterable[CFTCPositionRecord]) -> dict[tuple[Any, ...], list[CFTCPositionRecord]]:
    grouped: dict[tuple[Any, ...], list[CFTCPositionRecord]] = defaultdict(list)
    for record in records:
        grouped[
            (record.series_id, record.market_key, record.report_type, record.participant_category)
        ].append(record)
    for values in grouped.values():
        values.sort(key=lambda item: item.report_date)
    return grouped


def _metric_record(
    record: CFTCPositionRecord, metric: str, value: float | None, unit: str, **metadata: Any
) -> PositioningMetric:
    return PositioningMetric(
        series_id=record.series_id,
        market_key=record.market_key,
        report_date=record.report_date,
        report_type=record.report_type,
        participant_category=record.participant_category,
        available_at=record.available_at,
        metric=metric,
        value=value,
        unit=unit,
        metadata=metadata,
    )


def derive_positioning_metrics(
    records: Iterable[CFTCPositionRecord],
    *,
    decision_time: str | datetime | None = None,
    percentile_window: int = 156,
    zscore_window: int = 156,
) -> list[PositioningMetric]:
    """Produce diagnostic/crowding metrics only; no directional signal."""

    if percentile_window < 1 or zscore_window < 2:
        raise CFTCPositioningError("positioning_window_invalid")
    resolved = resolve_cftc_revisions(records, decision_time=decision_time)
    output: list[PositioningMetric] = []
    for group in _group_records(resolved).values():
        for position, record in enumerate(group):
            net = derive_net_position(record)
            pct_oi = derive_percent_open_interest(record)
            output.append(_metric_record(record, "net_position", net, "contracts"))
            output.append(
                _metric_record(record, "percent_open_interest", pct_oi, "percentage_points")
            )
            history = group[max(0, position - percentile_window + 1) : position + 1]
            percentile_values = [_metric_value(item, "net_position") for item in history]
            percentile_values = [value for value in percentile_values if value is not None]
            percentile = None
            if percentile_values:
                percentile = (
                    100.0 * sum(value <= net for value in percentile_values) / len(percentile_values)
                )
            output.append(
                _metric_record(
                    record,
                    "rolling_percentile_3y",
                    percentile,
                    "percentile",
                    window_observations=len(percentile_values),
                )
            )
            z_history = group[max(0, position - zscore_window + 1) : position + 1]
            z_values = [_metric_value(item, "net_position") for item in z_history]
            z_values = [value for value in z_values if value is not None]
            zscore = None
            if len(z_values) >= 2:
                deviation = pstdev(z_values)
                if deviation > 0:
                    zscore = (net - mean(z_values)) / deviation
            output.append(
                _metric_record(
                    record,
                    "causal_zscore",
                    zscore,
                    "z_score",
                    window_observations=len(z_values),
                )
            )
    return sorted(
        output,
        key=lambda item: (item.series_id, item.report_date, item.participant_category, item.metric),
    )


def evaluate_cftc_source_health(
    records: Iterable[CFTCPositionRecord],
    *,
    decision_time: str | datetime,
    report_type: CFTCReportType | str,
    source_year: int,
    source_file: str,
    provider: str = "cftc",
    expected_series: Iterable[str] | None = None,
    max_staleness_days: int = DEFAULT_STALENESS_DAYS,
    fetched_at: str | datetime | None = None,
    raw_archive_path: str | None = None,
) -> CFTCSourceHealth:
    """Return C0 source-health fields without certifying production use."""

    try:
        report_kind = CFTCReportType(str(report_type).upper())
    except ValueError as exc:
        raise CFTCPositioningError(f"unsupported_report_type:{report_type}") from exc
    cutoff = _cutoff(decision_time)
    fetched = _ingested_at(fetched_at)
    resolved = asof_cftc_records(records, cutoff)
    expected = set(expected_series or ())
    if expected_series is None:
        expected = {
            spec.series_id
            for spec in load_cftc_contracts()
            if spec.report_type is report_kind
        }
    if not resolved:
        return CFTCSourceHealth(
            provider=provider,
            report_type=report_kind,
            source_file=source_file,
            source_year=source_year,
            fetched_at=fetched,
            raw_archive_path=raw_archive_path,
            last_success_at=None,
            latest_observation=None,
            latest_available_at=None,
            freshness="UNKNOWN",
            source_status=CFTCSourceStatus.DATA_BLOCKED,
            parser_status="PASS",
            coverage_status="NO_ADMISSIBLE_ROWS",
            row_count=0,
            warnings=("no_admissible_records",),
            origin=DataOrigin.UNAVAILABLE,
        )
    latest = max(resolved, key=lambda item: item.report_date)
    age_days = (cutoff.date() - latest.report_date).days
    warnings: list[str] = []
    if age_days > max_staleness_days:
        warnings.append(f"stale_latest_observation_age_days:{age_days}")
    present = {item.series_id for item in resolved}
    missing = sorted(expected - present)
    if missing:
        warnings.append(f"missing_expected_series:{','.join(missing)}")
    if age_days > max_staleness_days:
        status = CFTCSourceStatus.STALE
    elif missing:
        status = CFTCSourceStatus.PARTIAL
    else:
        status = CFTCSourceStatus.HEALTHY
    return CFTCSourceHealth(
        provider=provider,
        report_type=report_kind,
        source_file=source_file,
        source_year=source_year,
        fetched_at=fetched,
        raw_archive_path=raw_archive_path,
        last_success_at=fetched,
        latest_observation=latest.report_date,
        latest_available_at=max(item.available_at for item in resolved),
        freshness="STALE" if age_days > max_staleness_days else "FRESH",
        source_status=status,
        parser_status="PASS",
        coverage_status="COMPLETE" if not missing else "PARTIAL",
        row_count=len(resolved),
        warnings=tuple(warnings),
        origin=latest.origin,
    )


def ingest_cftc_snapshot(
    payload: bytes | str,
    *,
    report_type: CFTCReportType | str,
    source_year: int,
    decision_time: str | datetime,
    fetched_at: str | datetime,
    provider: str = "cftc",
    publication_at: str | datetime | None = None,
    available_at: str | datetime | None = None,
    source_file: str | None = None,
    origin: DataOrigin | str = DataOrigin.LIVE,
    raw_archive: ImmutableRawArchive | None = None,
    expected_series: Iterable[str] | None = None,
    max_staleness_days: int = DEFAULT_STALENESS_DAYS,
) -> tuple[list[CFTCPositionRecord], CFTCSourceHealth]:
    """Archive, parse, and evaluate one snapshot; failures remain explicit."""

    try:
        report_kind = CFTCReportType(str(report_type).upper())
    except ValueError as exc:
        raise CFTCPositioningError(f"unsupported_report_type:{report_type}") from exc
    fetched = _utc(fetched_at, field="fetched_at")
    archive_path = None
    if raw_archive is not None:
        extension = (
            "zip"
            if isinstance(payload, bytes) and zipfile.is_zipfile(io.BytesIO(payload))
            else "txt"
        )
        archive_path = raw_archive.write(
            provider,
            f"cftc_{report_kind.value.lower()}",
            payload,
            captured_at=fetched,
            extension=extension,
        )
    try:
        records = parse_cftc_snapshot(
            payload,
            report_type=report_kind,
            source_year=source_year,
            provider=provider,
            publication_at=publication_at,
            available_at=available_at,
            source_file=source_file,
            origin=origin,
            ingested_at=fetched,
        )
        health = evaluate_cftc_source_health(
            records,
            decision_time=decision_time,
            report_type=report_kind,
            source_year=source_year,
            source_file=source_file or records[0].source_file,
            provider=provider,
            expected_series=expected_series,
            max_staleness_days=max_staleness_days,
            fetched_at=fetched,
            raw_archive_path=archive_path,
        )
        return records, health
    except CFTCUnapprovedSourceError as exc:
        return [], CFTCSourceHealth(
            provider=provider,
            report_type=report_kind,
            source_file=source_file or "unknown",
            source_year=source_year,
            fetched_at=fetched,
            raw_archive_path=archive_path,
            last_success_at=None,
            latest_observation=None,
            latest_available_at=None,
            freshness="UNKNOWN",
            source_status=CFTCSourceStatus.UNAPPROVED,
            parser_status="FAIL",
            coverage_status="NOT_PARSED",
            row_count=0,
            failure_reason=str(exc),
            origin=_origin(origin),
        )
    except CFTCPositioningError as exc:
        return [], CFTCSourceHealth(
            provider=provider,
            report_type=report_kind,
            source_file=source_file or "unknown",
            source_year=source_year,
            fetched_at=fetched,
            raw_archive_path=archive_path,
            last_success_at=None,
            latest_observation=None,
            latest_available_at=None,
            freshness="UNKNOWN",
            source_status=CFTCSourceStatus.FAILED,
            parser_status="FAIL",
            coverage_status="NOT_PARSED",
            row_count=0,
            failure_reason=str(exc),
            origin=_origin(origin),
        )


__all__ = [
    "DEFAULT_STALENESS_DAYS",
    "PARSER_VERSION",
    "CFTCContractSpec",
    "CFTCDuplicateReportError",
    "CFTCPositionRecord",
    "CFTCPositioningError",
    "CFTCReportType",
    "CFTCSourceHealth",
    "CFTCSourceStatus",
    "CFTCUnapprovedSourceError",
    "PositioningMetric",
    "asof_cftc_records",
    "cftc_publication_at",
    "default_cftc_config_path",
    "derive_net_position",
    "derive_percent_open_interest",
    "derive_positioning_metrics",
    "evaluate_cftc_source_health",
    "ingest_cftc_snapshot",
    "load_cftc_contracts",
    "parse_cftc_snapshot",
    "resolve_cftc_revisions",
]
