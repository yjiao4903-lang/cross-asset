from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from cross_asset.providers.base import Observation


@dataclass
class QualityEvent:
    series_id: str
    severity: str
    event_type: str
    message: str
    provider: str | None = None

    def as_dict(self):
        return self.__dict__.copy()


def freshness_status(
    obs: Observation | None, *, now: datetime | None = None, stale_after_hours: float | None = None
) -> str:
    if obs is None:
        return "MISSING"
    if obs.value is None:
        return "FAILED"
    if stale_after_hours is None:
        return "OK"
    now = now or datetime.now(UTC)
    at = obs.available_at if obs.available_at.tzinfo else obs.available_at.replace(tzinfo=UTC)
    return "STALE" if (now - at).total_seconds() > stale_after_hours * 3600 else "OK"


def assess_observations(
    observations: Iterable[Observation],
    *,
    now: datetime | None = None,
    stale_after_hours: dict[str, float] | None = None,
) -> list[QualityEvent]:
    events = []
    now = now or datetime.now(UTC)
    stale_after_hours = stale_after_hours or {}
    for o in observations:
        if o.value is not None and (not math.isfinite(o.value)):
            events.append(
                QualityEvent(o.series_id, "error", "invalid_value", "Value is not finite", o.source)
            )
        if o.available_at > now:
            events.append(
                QualityEvent(
                    o.series_id,
                    "error",
                    "future_available_at",
                    "available_at is in the future",
                    o.source,
                )
            )
        status = freshness_status(o, now=now, stale_after_hours=stale_after_hours.get(o.series_id))
        if status == "STALE":
            events.append(
                QualityEvent(
                    o.series_id,
                    "warning",
                    "stale",
                    "Observation is older than configured threshold",
                    o.source,
                )
            )
    return events
