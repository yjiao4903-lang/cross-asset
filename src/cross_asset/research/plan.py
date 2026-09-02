"""Chronological development/walk-forward/final-holdout planning."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from cross_asset.backtest.walk_forward import build_calendar_window_manifest

from .protocol import ResearchProtocol


@dataclass(frozen=True)
class ResearchPlan:
    protocol_hash: str
    status: str
    development_start: str | None
    development_end: str | None
    development_count: int
    fold_count: int
    folds: tuple[dict[str, Any], ...]
    holdout_sealed: bool
    holdout_start: str | None
    holdout_end: str | None
    holdout_count: int
    holdout_hash: str
    holdout_dates: tuple[str, ...]
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _iso(value) -> str:
    return pd.Timestamp(value).isoformat()


def _hash_dates(dates: pd.DatetimeIndex) -> str:
    payload = json.dumps([_iso(value) for value in dates], separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def load_decision_dates(path: str | Path) -> pd.DatetimeIndex:
    """Load an explicit ordered decision-date set from JSON, CSV, or newline text."""

    path = Path(path)
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        values = payload.get("decision_dates", payload) if isinstance(payload, dict) else payload
    elif path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
        if frame.empty:
            values = []
        elif "decision_time" in frame:
            values = frame["decision_time"].tolist()
        elif "decision_date" in frame:
            values = frame["decision_date"].tolist()
        else:
            values = frame.iloc[:, 0].tolist()
    else:
        values = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    parsed = []
    for value in list(values):
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            raise ValueError("decision_times_must_be_timezone_aware")
        parsed.append(timestamp.tz_convert("UTC"))
    dates = pd.DatetimeIndex(parsed)
    if dates.has_duplicates:
        raise ValueError("decision_dates_must_be_unique")
    if not dates.is_monotonic_increasing:
        raise ValueError("decision_dates_must_be_strictly_increasing")
    return dates


def build_research_plan(
    decision_dates,
    protocol: ResearchProtocol,
    *,
    release_holdout: bool = False,
) -> ResearchPlan:
    dates = pd.DatetimeIndex(pd.to_datetime(list(decision_dates), utc=True))
    if len(dates) == 0:
        return ResearchPlan(
            protocol_hash=protocol.protocol_hash,
            status="BLOCKED",
            development_start=None,
            development_end=None,
            development_count=0,
            fold_count=0,
            folds=(),
            holdout_sealed=not release_holdout,
            holdout_start=None,
            holdout_end=None,
            holdout_count=0,
            holdout_hash=_hash_dates(dates),
            holdout_dates=(),
            blockers=("decision_dates_empty", *protocol.execution_blockers),
        )
    if dates.has_duplicates or not dates.is_monotonic_increasing:
        raise ValueError("decision_dates_must_be_strictly_increasing_and_unique")

    holdout_count = max(1, math.ceil(len(dates) * protocol.final_holdout_fraction))
    if holdout_count >= len(dates):
        raise ValueError("holdout_consumes_entire_sample")
    development = dates[:-holdout_count]
    holdout = dates[-holdout_count:]
    blockers = list(protocol.execution_blockers)

    span_years = (
        (development[-1] - development[0]).total_seconds() / (365.25 * 24 * 3600)
        if len(development) > 1
        else 0.0
    )
    if span_years < protocol.train_min_years:
        blockers.append("development_history_shorter_than_train_min_years")

    folds = build_calendar_window_manifest(
        development,
        train_min_years=protocol.train_min_years,
        test_window_months=protocol.test_window_months,
        step_months=protocol.step_months,
        window_type=protocol.default_mode,
        rolling_years=protocol.rolling_years,
    )
    if not folds:
        blockers.append("walk_forward_folds_empty")

    fold_payload = tuple(
        {
            **fold,
            "train_start": _iso(fold["train_start"]),
            "train_end": _iso(fold["train_end"]),
            "test_start": _iso(fold["test_start"]),
            "test_end": _iso(fold["test_end"]),
            "train_indices": list(fold["train_indices"]),
            "test_indices": list(fold["test_indices"]),
        }
        for fold in folds
    )
    status = "READY_FOR_OOS" if not blockers else "BLOCKED"
    return ResearchPlan(
        protocol_hash=protocol.protocol_hash,
        status=status,
        development_start=_iso(development[0]),
        development_end=_iso(development[-1]),
        development_count=len(development),
        fold_count=len(fold_payload),
        folds=fold_payload,
        holdout_sealed=not release_holdout,
        holdout_start=_iso(holdout[0]),
        holdout_end=_iso(holdout[-1]),
        holdout_count=len(holdout),
        holdout_hash=_hash_dates(holdout),
        holdout_dates=tuple(_iso(value) for value in holdout) if release_holdout else (),
        blockers=tuple(sorted(set(blockers))),
    )


__all__ = ["ResearchPlan", "build_research_plan", "load_decision_dates"]
