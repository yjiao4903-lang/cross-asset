"""Fail-closed CFTC report/publication chronology guard.

The CFTC report date is the Tuesday reference date.  The actual publication
date remains caller/source-calendar supplied; this guard only proves that the
provided timestamp is temporally possible.  It deliberately does not guess a
Friday release or holiday shift.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")


def guard_parse_cftc_snapshot(parser: Callable) -> Callable:
    """Wrap a CFTC parser with the report-date/publication chronology gate."""

    @wraps(parser)
    def guarded(*args, **kwargs):
        records = parser(*args, **kwargs)
        from .cftc_positioning import CFTCPositioningError

        for record in records:
            publication_date = record.publication_at.astimezone(_EASTERN).date()
            if publication_date <= record.report_date:
                raise CFTCPositioningError(
                    "publication_at_must_be_after_report_date:"
                    f"{record.report_date.isoformat()}:{publication_date.isoformat()}"
                )
        return records

    return guarded


__all__ = ["guard_parse_cftc_snapshot"]
