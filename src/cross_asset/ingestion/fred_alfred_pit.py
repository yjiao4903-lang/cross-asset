"""Date-granular ALFRED vintage model with fail-closed historical as-of semantics."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pandas as pd

MODE_HISTORICAL_ASOF = "HISTORICAL_ASOF"
MODE_ALL_REALTIME_PERIODS = "ALL_REALTIME_PERIODS"
MODE_INITIAL_RELEASE = "INITIAL_RELEASE"
MODE_REVISED_LATEST = "REVISED_LATEST"
_CAUSAL_MODES = {MODE_HISTORICAL_ASOF, MODE_ALL_REALTIME_PERIODS, MODE_INITIAL_RELEASE}


class FredPITError(ValueError):
    pass


@dataclass(frozen=True)
class VintageObservation:
    canonical_series_id: str
    provider_series_id: str
    observation_date: date
    value: float | None
    realtime_start: date
    realtime_end: date | None
    conservative_available_at: datetime
    mode: str
    request_vintage: date | None
    raw_value: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["observation_date"] = self.observation_date.isoformat()
        payload["realtime_start"] = self.realtime_start.isoformat()
        payload["realtime_end"] = (
            self.realtime_end.isoformat() if self.realtime_end is not None else None
        )
        payload["conservative_available_at"] = self.conservative_available_at.isoformat()
        payload["request_vintage"] = (
            self.request_vintage.isoformat() if self.request_vintage is not None else None
        )
        return payload


def _date(value: Any, *, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise FredPITError(f"fred_invalid_{field}:{value}") from exc


def conservative_available_at(vintage_date: date) -> datetime:
    """Date-only fail-closed policy: two UTC days later, never same vintage date."""
    return datetime.combine(vintage_date + timedelta(days=2), time.min, tzinfo=UTC)


def _numeric(raw: Any) -> float | None:
    text = str(raw).strip()
    if text in {"", ".", "nan", "NaN", "None"}:
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise FredPITError(f"fred_non_numeric_value:{text}") from exc
    if not pd.notna(value):
        return None
    return value


def _realtime_end(row: dict[str, Any], *, mode: str) -> date | None:
    raw = row.get("realtime_end")
    if raw in {None, "", ".", "#NA"}:
        if mode == MODE_INITIAL_RELEASE:
            return None
        raise FredPITError(f"fred_invalid_realtime_end:{raw}")
    return _date(raw, field="realtime_end")


def parse_observations(
    *,
    canonical_series_id: str,
    provider_series_id: str,
    payload: dict[str, Any],
    mode: str,
    request_vintage: str | date | None = None,
) -> list[VintageObservation]:
    if mode not in _CAUSAL_MODES | {MODE_REVISED_LATEST}:
        raise FredPITError(f"fred_unknown_mode:{mode}")
    rows = payload.get("observations")
    if not isinstance(rows, list):
        raise FredPITError("fred_observations_payload_invalid")
    requested = _date(request_vintage, field="request_vintage") if request_vintage else None
    result: list[VintageObservation] = []
    for row in rows:
        if not isinstance(row, dict):
            raise FredPITError("fred_observation_row_invalid")
        observation_date = _date(row.get("date"), field="observation_date")
        realtime_start = _date(row.get("realtime_start"), field="realtime_start")
        realtime_end = _realtime_end(row, mode=mode)
        if realtime_end is not None and realtime_end < realtime_start:
            raise FredPITError("fred_realtime_period_reversed")
        if requested is not None and realtime_start > requested:
            raise FredPITError(
                f"future_vintage_leakage:{provider_series_id}:{realtime_start}:{requested}"
            )
        result.append(
            VintageObservation(
                canonical_series_id=canonical_series_id,
                provider_series_id=provider_series_id,
                observation_date=observation_date,
                value=_numeric(row.get("value")),
                realtime_start=realtime_start,
                realtime_end=realtime_end,
                conservative_available_at=conservative_available_at(realtime_start),
                mode=mode,
                request_vintage=requested,
                raw_value=str(row.get("value")),
            )
        )
    return result


def require_causal_vintage(records: Iterable[VintageObservation]) -> list[VintageObservation]:
    rows = list(records)
    if any(row.mode == MODE_REVISED_LATEST for row in rows):
        raise FredPITError("revised_latest_forbidden_for_historical_decision")
    if any(row.mode not in _CAUSAL_MODES for row in rows):
        raise FredPITError("noncausal_vintage_mode")
    return rows


def _version_key(row: VintageObservation) -> tuple[date, date]:
    return row.realtime_start, row.realtime_end or row.realtime_start


def snapshot_asof(
    records: Iterable[VintageObservation],
    decision_time: datetime | str,
) -> list[VintageObservation]:
    rows = require_causal_vintage(records)
    decision = pd.Timestamp(decision_time)
    if decision.tzinfo is None:
        decision = decision.tz_localize("UTC")
    else:
        decision = decision.tz_convert("UTC")
    decision_dt = decision.to_pydatetime()
    if any(
        row.request_vintage is not None
        and conservative_available_at(row.request_vintage) > decision_dt
        for row in rows
    ):
        raise FredPITError("future_vintage_leakage:request_vintage_after_decision")

    eligible = [
        row
        for row in rows
        if row.conservative_available_at <= decision_dt
        and row.realtime_start <= decision_dt.date()
    ]
    chosen: dict[tuple[str, date], VintageObservation] = {}
    for row in eligible:
        key = (row.canonical_series_id, row.observation_date)
        current = chosen.get(key)
        if current is None or _version_key(row) > _version_key(current):
            chosen[key] = row
    return sorted(
        chosen.values(),
        key=lambda row: (row.canonical_series_id, row.observation_date),
    )


def records_to_frame(records: Iterable[VintageObservation]) -> pd.DataFrame:
    return pd.DataFrame([row.to_dict() for row in records])


__all__ = [
    "MODE_ALL_REALTIME_PERIODS",
    "MODE_HISTORICAL_ASOF",
    "MODE_INITIAL_RELEASE",
    "MODE_REVISED_LATEST",
    "FredPITError",
    "VintageObservation",
    "conservative_available_at",
    "parse_observations",
    "records_to_frame",
    "require_causal_vintage",
    "snapshot_asof",
]
