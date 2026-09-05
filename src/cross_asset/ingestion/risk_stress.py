"""C0 Risk Stress source/parser/PIT foundation (research-only).

This module is the low-coupling foundation for the Cross W1 Risk Stress pack
(#38, child of #36).  It deliberately stops at C0:

- canonical/source contracts for ``RISK_VIX_LEVEL``, ``RISK_VIX_TS``,
  ``RISK_HY_OAS`` and ``RISK_BAA10Y``;
- an isolated CSV parser/normalizer with explicit ``available_at``;
- point-in-time enforcement (``available_at <= decision_time``);
- stale/partial/missing/unapproved source-state representation;
- source-health records and raw-archive plumbing reusing
  :class:`cross_asset.ingestion.raw_archive.ImmutableRawArchive`.

It does NOT wire anything into allocation, factors, reports or production
ingestion.  No production stress thresholds are encoded here beyond the
mathematical term-structure ratio contract.  ``RISK_BAA10Y`` is a shadow
proxy and must never be treated as a substitute or historical splice of
``RISK_HY_OAS``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from cross_asset.pit.availability import AvailabilityContract, AvailableAtPolicy

PARSER_VERSION = "risk_stress_parser_v1"

#: Number of calendar days after which a source's latest observation is
#: reported STALE.  This is a C0 research-only representation; production
#: trading-calendar-driven freshness belongs to the #18 gate work.
DEFAULT_STALENESS_DAYS = 7

ORIGINS = ("FIXTURE", "MANUAL", "LIVE")


class RiskStressSeries(StrEnum):
    VIX_LEVEL = "RISK_VIX_LEVEL"
    VIX_TS = "RISK_VIX_TS"
    HY_OAS = "RISK_HY_OAS"
    BAA10Y = "RISK_BAA10Y"


class SourceRole(StrEnum):
    PRIMARY = "PRIMARY"
    SHADOW_PROXY = "SHADOW_PROXY"
    DERIVED = "DERIVED"


class SourceStatus(StrEnum):
    OK = "OK"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    UNAPPROVED = "UNAPPROVED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SourceContract:
    """Canonical identity + approved source shape for one risk-stress input."""

    series: RiskStressSeries
    description: str
    unit: str
    frequency: str
    role: SourceRole
    #: Approved (provider, source_series_id) pairs.  Anything else is
    #: UNAPPROVED and must never enter computation.
    approved_sources: tuple[tuple[str, str], ...]
    availability: AvailabilityContract
    #: Earliest observation date this series is expected to cover; used only
    #: to *warn* about truncated history (e.g. HY OAS free-history cutoffs),
    #: never to splice or impute.
    expected_history_start: date | None = None
    notes: str = field(default="")

    def is_approved(self, provider: str, source_series_id: str) -> bool:
        return (str(provider), str(source_series_id)) in self.approved_sources


VIX_TS_DEFINITION = "RISK_VIX_TS = VIX / VIX3M"

_BAA10Y_NOTES = (
    "RISK_BAA10Y != RISK_HY_OAS. Moody's Baa minus 10Y Treasury is a "
    "long-history shadow proxy: direction confirmation / rolling-percentile "
    "shadow only. No historical splice with HY OAS, no shared absolute bp "
    "thresholds, not a HY OAS fallback equivalent."
)

#: Availability evidence strings are deliberately placeholders pending the
#: RESEARCH-AUX evidence pass on #37.  pit_grade stays None: no acceptance
#: claim is made by this module.
_RISK_STRESS_CONTRACTS: dict[RiskStressSeries, SourceContract] = {
    RiskStressSeries.VIX_LEVEL: SourceContract(
        series=RiskStressSeries.VIX_LEVEL,
        description="Cboe VIX close (volatility index level).",
        unit="index_level",
        frequency="daily",
        role=SourceRole.PRIMARY,
        approved_sources=(("cboe", "VIX"), ("fred", "VIXCLS")),
        availability=AvailabilityContract(
            policy=AvailableAtPolicy.EXACT,
            timezone="America/New_York",
            evidence="pending_research_aux_37",
        ),
    ),
    RiskStressSeries.VIX_TS: SourceContract(
        series=RiskStressSeries.VIX_TS,
        description=f"{VIX_TS_DEFINITION}; <1 contango/normal, ~1 flat, "
        ">1 backwardation/stress. Computed, never sourced directly.",
        unit="ratio",
        frequency="daily",
        role=SourceRole.DERIVED,
        approved_sources=(),  # derived from VIX_LEVEL + VIX3M legs
        availability=AvailabilityContract(
            policy=AvailableAtPolicy.EXACT,
            timezone="America/New_York",
            evidence="pending_research_aux_37",
        ),
        notes="available_at of the ratio is the max of both legs' available_at.",
    ),
    RiskStressSeries.HY_OAS: SourceContract(
        series=RiskStressSeries.HY_OAS,
        description="ICE BofA US High Yield index option-adjusted spread.",
        unit="percentage_points",
        frequency="daily",
        role=SourceRole.PRIMARY,
        approved_sources=(("fred", "BAMLH0A0HYM2"),),
        availability=AvailabilityContract(
            policy=AvailableAtPolicy.RELEASE_DATE_EOD,
            timezone="America/New_York",
            evidence="pending_research_aux_37",
        ),
        expected_history_start=date(1996, 8, 1),
        notes="Free public history may be truncated; keep local raw archive.",
    ),
    RiskStressSeries.BAA10Y: SourceContract(
        series=RiskStressSeries.BAA10Y,
        description="Moody's Baa corporate bond yield less 10-year Treasury "
        "constant maturity (FRED BAA10Y). Long-history shadow proxy.",
        unit="percentage_points",
        frequency="daily",
        role=SourceRole.SHADOW_PROXY,
        approved_sources=(("fred", "BAA10Y"),),
        availability=AvailabilityContract(
            policy=AvailableAtPolicy.RELEASE_DATE_EOD,
            timezone="America/New_York",
            evidence="pending_research_aux_37",
        ),
        notes=_BAA10Y_NOTES,
    ),
}


def source_contract(series: RiskStressSeries | str) -> SourceContract:
    key = RiskStressSeries(series)
    if key is RiskStressSeries.VIX_TS:
        raise ValueError("RISK_VIX_TS is derived; use the VIX_LEVEL/VIX3M leg contracts")
    return _RISK_STRESS_CONTRACTS[key]


VIX3M_LEG_KEY = "RISK_VIX3M"


def vix3m_contract() -> SourceContract:
    """VIX3M is a term-structure leg, not one of the four canonical outputs."""
    return SourceContract(
        series=RiskStressSeries.VIX_LEVEL,
        description="Cboe VIX3M close; term-structure denominator leg for RISK_VIX_TS.",
        unit="index_level",
        frequency="daily",
        role=SourceRole.PRIMARY,
        approved_sources=(("cboe", "VIX3M"),),
        availability=AvailabilityContract(
            policy=AvailableAtPolicy.EXACT,
            timezone="America/New_York",
            evidence="pending_research_aux_37",
        ),
        notes="Leg input for RISK_VIX_TS only; not a canonical stress output.",
    )


def _resolve_contract(series: RiskStressSeries | str) -> SourceContract:
    """Resolve one of the four canonical contracts or the VIX3M leg."""
    if isinstance(series, str) and series == VIX3M_LEG_KEY:
        return vix3m_contract()
    return _RISK_STRESS_CONTRACTS[RiskStressSeries(series)]


class RiskStressError(ValueError):
    """Explicit failure; callers must never silently impute around it."""


class UnapprovedSourceError(RiskStressError):
    pass


class SpliceViolationError(RiskStressError):
    pass


def _utc(stamp: str | datetime) -> datetime:

    value = datetime.fromisoformat(stamp) if isinstance(stamp, str) else stamp
    if value.tzinfo is None:
        raise RiskStressError("available_at_requires_explicit_utc_offset")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class RiskStressRecord:
    series_id: str
    observation_date: date
    available_at: datetime
    value: float | None
    provider: str
    source_series_id: str
    origin: str
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_risk_stress_csv(
    text: str,
    *,
    series: RiskStressSeries | str,
    provider: str,
    origin: str,
    available_at_default: str | datetime | None = None,
) -> list[RiskStressRecord]:
    """Parse a CSV snapshot of one risk-stress source shape.

    Required columns: ``observation_date``, ``value``, ``available_at``
    (explicit publication timestamp, mirroring the ManualProvider contract:
    falling back to the observation date would silently manufacture an
    information set).  ``available_at_default`` exists only for captured
    fixtures whose publication time is contractually uniform; supplying it
    is recorded in each record's metadata.

    Every row is validated; the first malformed row raises
    :class:`RiskStressError` instead of being dropped.
    """
    if origin not in ORIGINS:
        raise RiskStressError(f"origin must be one of {ORIGINS}, got {origin!r}")
    contract = _resolve_contract(series)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise RiskStressError("empty_csv_no_header")
    required = {"observation_date", "value", "available_at"}
    missing = required - set(reader.fieldnames)
    if missing:
        raise RiskStressError(f"missing_required_columns:{sorted(missing)}")
    records: list[RiskStressRecord] = []
    for line, row in enumerate(reader, start=2):
        raw_date = (row.get("observation_date") or "").strip()
        raw_value = (row.get("value") or "").strip()
        raw_avail = (row.get("available_at") or "").strip()
        if not raw_date:
            raise RiskStressError(f"line_{line}_missing_observation_date")
        try:
            observation_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise RiskStressError(f"line_{line}_invalid_observation_date:{raw_date!r}") from exc
        if not raw_value:
            raise RiskStressError(f"line_{line}_missing_value")
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise RiskStressError(f"line_{line}_non_numeric_value:{raw_value!r}") from exc
        if math.isnan(value):
            value = None
        source_series_id = (row.get("source_series_id") or "").strip() or contract.approved_sources[0][1]
        if not raw_avail:
            if available_at_default is None:
                raise RiskStressError(f"line_{line}_missing_available_at")
            avail = _utc(available_at_default)
        else:
            try:
                avail = _utc(raw_avail)
            except (ValueError, RiskStressError) as exc:
                raise RiskStressError(
                    f"line_{line}_invalid_available_at:{raw_avail!r}:{exc}"
                ) from exc
        if not contract.is_approved(provider, source_series_id):
            raise UnapprovedSourceError(
                f"unapproved_source:{provider}:{source_series_id} for {contract.series}"
            )
        records.append(
            RiskStressRecord(
                series_id=str(contract.series),
                observation_date=observation_date,
                available_at=avail,
                value=value,
                provider=provider,
                source_series_id=source_series_id,
                origin=origin,
                metadata={
                    "parser_version": PARSER_VERSION,
                    "origin": origin,
                    "available_at_default_applied": raw_avail == "" and available_at_default is not None,
                },
            )
        )
    return records


def check_series_identity(records, series: RiskStressSeries | str) -> None:
    """Reject any record whose source identity does not belong to ``series``.

    This is the guard that keeps BAA10Y rows from being spliced into the
    HY OAS series (and any other cross-series mixing).
    """
    contract = _RISK_STRESS_CONTRACTS[RiskStressSeries(series)]
    for record in records:
        provider = getattr(record, "provider", None) or record.get("provider")  # type: ignore[union-attr]
        sid = getattr(record, "source_series_id", None) or record.get("source_series_id")  # type: ignore[union-attr]
        if not contract.is_approved(provider, sid):
            raise SpliceViolationError(
                f"record_source_identity_{provider}:{sid}_does_not_belong_to_{contract.series}"
            )


def asof_records(records, decision_time: datetime) -> list[RiskStressRecord]:
    """Hard PIT boundary: drop anything published after ``decision_time``.

    ``available_at > decision_time`` must never enter the computation for
    that decision; this is the C0 analogue of the shared approved-observations
    query being built under #18.
    """

    cutoff = decision_time if decision_time.tzinfo else decision_time.replace(tzinfo=UTC)
    cutoff = cutoff.astimezone(UTC)
    out = []
    for record in records:
        avail = record.available_at
        if avail.tzinfo is None:
            raise RiskStressError("available_at_requires_explicit_utc_offset")
        if avail.astimezone(UTC) <= cutoff:
            out.append(record)
    return out


@dataclass(frozen=True)
class TermStructurePoint:
    observation_date: date
    ratio: float | None
    available_at: datetime | None
    state: str  # OK | MISSING_DENOMINATOR | INVALID_DENOMINATOR | MISSING_NUMERATOR
    warnings: tuple[str, ...] = ()


def classify_term_structure(ratio: float, *, flat_tolerance: float = 0.0) -> str:
    """Ratio-band semantics only. ``flat_tolerance`` is a research knob;
    no production stress threshold is encoded or claimed here."""
    if flat_tolerance < 0:
        raise ValueError("flat_tolerance_must_be_non_negative")
    if ratio < 1 - flat_tolerance:
        return "CONTANGO_NORMAL"
    if ratio > 1 + flat_tolerance:
        return "BACKWARDATION_STRESS"
    return "FLAT"


def compute_vix_term_structure(
    vix: list[RiskStressRecord],
    vix3m: list[RiskStressRecord],
) -> list[TermStructurePoint]:
    """Compute ``RISK_VIX_TS = VIX / VIX3M`` per observation date.

    The ratio's ``available_at`` is the max of both legs' publication times:
    a term-structure reading cannot be known before its slowest leg.  When
    the two legs disagree on ``available_at`` for the same date, a
    ``cutoff_mismatch`` warning is attached (and the later one wins).
    """
    by_date_vix = {r.observation_date: r for r in vix}
    by_date_vix3m = {r.observation_date: r for r in vix3m}
    points: list[TermStructurePoint] = []
    for observation_date in sorted(set(by_date_vix) | set(by_date_vix3m)):
        num = by_date_vix.get(observation_date)
        den = by_date_vix3m.get(observation_date)
        warnings: list[str] = []
        if num is None or den is None:
            state = "MISSING_NUMERATOR" if num is None else "MISSING_DENOMINATOR"
            points.append(TermStructurePoint(observation_date, None, None, state))
            continue
        if num.available_at != den.available_at:
            warnings.append("cutoff_mismatch")
        available_at = max(num.available_at, den.available_at)
        if den.value is None or den.value <= 0:
            points.append(
                TermStructurePoint(observation_date, None, available_at, "INVALID_DENOMINATOR", tuple(warnings))
            )
            continue
        if num.value is None:
            points.append(
                TermStructurePoint(observation_date, None, available_at, "MISSING_NUMERATOR", tuple(warnings))
            )
            continue
        ratio = num.value / den.value
        points.append(TermStructurePoint(observation_date, ratio, available_at, "OK", tuple(warnings)))
    return points


def evaluate_series_state(
    records,
    *,
    decision_time: datetime,
    max_staleness_days: int = DEFAULT_STALENESS_DAYS,
    expected_history_start: date | None = None,
) -> dict[str, Any]:
    """C0 source-state evaluation: OK / STALE / PARTIAL / MISSING plus
    truncated-history warnings.  Research-only representation."""

    cutoff = decision_time if decision_time.tzinfo else decision_time.replace(tzinfo=UTC)
    admissible = asof_records(records, cutoff)
    if not admissible:
        return {
            "status": SourceStatus.MISSING,
            "row_count": 0,
            "warnings": ["no_admissible_observations"],
            "failure_reason": None,
        }
    warnings: list[str] = []
    null_values = sum(1 for r in admissible if r.value is None)
    if null_values:
        warnings.append(f"partial_null_values:{null_values}")
    latest = max(admissible, key=lambda r: r.observation_date)
    age = (cutoff.date() - latest.observation_date).days
    if age > max_staleness_days:
        warnings.append(f"stale_latest_observation_age_days:{age}")
    contract_hint = expected_history_start
    if contract_hint is not None:
        earliest = min(r.observation_date for r in admissible)
        if earliest > contract_hint:
            warnings.append(
                f"history_truncated:coverage_starts_{earliest.isoformat()}"
                f"_expected_{contract_hint.isoformat()}"
            )
    status = SourceStatus.OK
    if any(w.startswith("stale") for w in warnings):
        status = SourceStatus.STALE
    elif null_values:
        status = SourceStatus.PARTIAL
    return {
        "status": status,
        "row_count": len(admissible),
        "latest_observation_date": latest.observation_date,
        "latest_available_at": max(r.available_at for r in admissible),
        "coverage_start": min(r.observation_date for r in admissible),
        "coverage_end": latest.observation_date,
        "warnings": warnings,
        "failure_reason": None,
    }


@dataclass(frozen=True)
class SourceHealth:
    """C0 source-health record (raw snapshot provenance + parser state)."""

    series: str
    provider: str
    source_series_id: str
    raw_sha256: str
    raw_archive_path: str | None
    fetched_at: datetime
    parser_version: str
    row_count: int
    coverage_start: date | None
    coverage_end: date | None
    latest_observation_date: date | None
    latest_available_at: datetime | None
    status: SourceStatus
    warnings: tuple[str, ...] = ()
    failure_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data = {
            "series": self.series,
            "provider": self.provider,
            "source_series_id": self.source_series_id,
            "raw_sha256": self.raw_sha256,
            "raw_archive_path": self.raw_archive_path,
            "fetched_at": self.fetched_at.isoformat(),
            "parser_version": self.parser_version,
            "row_count": self.row_count,
            "coverage_start": self.coverage_start.isoformat() if self.coverage_start else None,
            "coverage_end": self.coverage_end.isoformat() if self.coverage_end else None,
            "latest_observation_date": self.latest_observation_date.isoformat()
            if self.latest_observation_date
            else None,
            "latest_available_at": self.latest_available_at.isoformat() if self.latest_available_at else None,
            "status": str(self.status),
            "warnings": list(self.warnings),
            "failure_reason": self.failure_reason,
        }
        return data


def ingest_source_snapshot(
    text: str,
    *,
    series: RiskStressSeries | str,
    provider: str,
    origin: str,
    fetched_at: datetime,
    decision_time: datetime,
    raw_archive=None,
    max_staleness_days: int = DEFAULT_STALENESS_DAYS,
) -> SourceHealth:
    """Parse + evaluate one raw source snapshot and record its health.

    Raises :class:`UnapprovedSourceError` for unapproved sources and
    :class:`RiskStressError` for malformed input; callers convert those into
    FAILED/stop reasons, never into silent success.
    """
    contract = _resolve_contract(series)
    raw_payload = text.encode("utf-8")
    raw_sha256 = hashlib.sha256(raw_payload).hexdigest()
    archive_path = None
    if raw_archive is not None:
        archive_path = raw_archive.write(provider, str(contract.series), raw_payload, captured_at=fetched_at)
    try:
        records = parse_risk_stress_csv(text, series=series, provider=provider, origin=origin)
    except RiskStressError as exc:
        return SourceHealth(
            series=str(contract.series),
            provider=provider,
            source_series_id=contract.approved_sources[0][1],
            raw_sha256=raw_sha256,
            raw_archive_path=archive_path,
            fetched_at=fetched_at,
            parser_version=PARSER_VERSION,
            row_count=0,
            coverage_start=None,
            coverage_end=None,
            latest_observation_date=None,
            latest_available_at=None,
            status=SourceStatus.FAILED,
            warnings=(),
            failure_reason=str(exc),
        )
    state = evaluate_series_state(
        records,
        decision_time=decision_time,
        max_staleness_days=max_staleness_days,
        expected_history_start=contract.expected_history_start,
    )
    return SourceHealth(
        series=str(contract.series),
        provider=provider,
        source_series_id=records[0].source_series_id,
        raw_sha256=raw_sha256,
        raw_archive_path=archive_path,
        fetched_at=fetched_at,
        parser_version=PARSER_VERSION,
        row_count=state["row_count"],
        coverage_start=state.get("coverage_start"),
        coverage_end=state.get("coverage_end"),
        latest_observation_date=state.get("latest_observation_date"),
        latest_available_at=state.get("latest_available_at"),
        status=state["status"],
        warnings=tuple(state["warnings"]),
        failure_reason=None,
    )
