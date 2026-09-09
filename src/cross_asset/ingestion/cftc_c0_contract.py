"""Isolated C0 timing contract for CFTC positioning.

This module does not ingest production observations, touch approved-observations,
or change allocation. It only makes the REQ Tuesday/Friday/holiday rule explicit
so callers cannot treat a guessed nominal Friday 15:30 ET as an actual release.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .cftc_positioning import (
    CFTCPositionRecord,
    CFTCPositioningError,
    asof_cftc_records,
    cftc_publication_at,
)

C0_GATE = "C0"
C0_USAGE = "CANDIDATE_ONLY"
PRODUCTION_ADMISSION = False
NOMINAL_LAG_DAYS = 3


def require_c0_only() -> dict[str, object]:
    return {
        "gate": C0_GATE,
        "usage": C0_USAGE,
        "production_admission": PRODUCTION_ADMISSION,
        "directional_alpha": False,
        "approved_observations": False,
    }


def nominal_friday_after_tuesday(report_date: date) -> date:
    if report_date.weekday() != 1:
        raise CFTCPositioningError(f"report_date_must_be_tuesday:{report_date.isoformat()}")
    return report_date + timedelta(days=NOMINAL_LAG_DAYS)


def nominal_friday_publication_at(report_date: date) -> datetime:
    """Documented ordinary release. Never a substitute for the actual calendar."""

    return cftc_publication_at(nominal_friday_after_tuesday(report_date))


def reject_guessed_friday_before_actual_release(
    *,
    report_date: date,
    claimed_publication_at: datetime,
    actual_publication_at: datetime,
) -> None:
    """Fail closed when a nominal Friday is used before the real holiday shift."""

    if claimed_publication_at.tzinfo is None or claimed_publication_at.utcoffset() is None:
        raise CFTCPositioningError("claimed_publication_timezone_required")
    if actual_publication_at.tzinfo is None or actual_publication_at.utcoffset() is None:
        raise CFTCPositioningError("actual_publication_timezone_required")
    nominal = nominal_friday_publication_at(report_date)
    claimed_utc = claimed_publication_at.astimezone(nominal.tzinfo)
    actual_utc = actual_publication_at.astimezone(nominal.tzinfo)
    if actual_utc > nominal and claimed_utc < actual_utc:
        raise CFTCPositioningError(
            "future_leakage_guessed_friday_before_actual_holiday_release:"
            f"{claimed_utc.isoformat()}:{actual_utc.isoformat()}"
        )
    if claimed_utc < actual_utc:
        raise CFTCPositioningError(
            "publication_before_actual_release:"
            f"{claimed_utc.isoformat()}:{actual_utc.isoformat()}"
        )


def visible_asof(
    records: list[CFTCPositionRecord],
    decision_time: str | datetime,
) -> list[CFTCPositionRecord]:
    return asof_cftc_records(records, decision_time)


__all__ = [
    "C0_GATE",
    "C0_USAGE",
    "PRODUCTION_ADMISSION",
    "nominal_friday_after_tuesday",
    "nominal_friday_publication_at",
    "reject_guessed_friday_before_actual_release",
    "require_c0_only",
    "visible_asof",
]
