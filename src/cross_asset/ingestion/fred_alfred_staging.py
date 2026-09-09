"""C0 FRED/ALFRED historical collection, quality checks, and coverage manifests."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from cross_asset.ingestion.fred_alfred_pit import (
    MODE_ALL_REALTIME_PERIODS,
    MODE_HISTORICAL_ASOF,
    MODE_INITIAL_RELEASE,
    MODE_REVISED_LATEST,
    FredPITError,
    VintageObservation,
    parse_observations,
)
from cross_asset.ingestion.fred_alfred_registry import FredSeriesSpec, load_fred_registry
from cross_asset.providers.fred_alfred import (
    FredAlfredClient,
    FredAlfredError,
    FredPayload,
    FredResponseCache,
)

_MODE_ALIASES = {
    "asof": MODE_HISTORICAL_ASOF,
    "historical-asof": MODE_HISTORICAL_ASOF,
    "latest": MODE_REVISED_LATEST,
    "revised-latest": MODE_REVISED_LATEST,
    "all-vintages": MODE_ALL_REALTIME_PERIODS,
    "all-realtime-periods": MODE_ALL_REALTIME_PERIODS,
    "initial-release": MODE_INITIAL_RELEASE,
}


@dataclass(frozen=True)
class QualityReport:
    source_health: str
    row_count: int
    missing_ratio: float
    duplicate_count: int
    conflicting_duplicate_count: int
    non_monotonic_count: int
    long_gaps: tuple[tuple[str, str, int], ...]
    future_available_at_count: int
    metadata_drift: tuple[str, ...]
    stale_metadata: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CoverageManifest:
    canonical_series_id: str
    provider_series_id: str
    mode: str
    requested_start: str
    requested_end: str
    requested_as_of: str | None
    returned_start: str | None
    returned_end: str | None
    row_count: int
    missing_ratio: float
    duplicate_count: int
    latest_observation: str | None
    latest_vintage: str | None
    units: str
    frequency: str
    raw_sha256: str | None
    request_fingerprint: str | None
    raw_archive_path: str | None
    cache_hit: bool | None
    source_health: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata_last_updated: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _metadata(payload: FredPayload) -> dict[str, Any]:
    rows = payload.payload.get("seriess")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise FredAlfredError("metadata_empty", "FRED series metadata payload is empty")
    return dict(rows[0])


def _gap_limit_days(frequency: str) -> int:
    if frequency.startswith("Daily"):
        return 10
    if frequency.startswith("Weekly"):
        return 21
    if frequency.startswith("Monthly"):
        return 75
    if frequency.startswith("Quarterly"):
        return 130
    return 400


def _known_gap(spec: FredSeriesSpec, left: date, right: date) -> bool:
    gap_start = left + timedelta(days=1)
    gap_end = right - timedelta(days=1)
    for start, end in spec.known_long_gaps:
        known_start, known_end = date.fromisoformat(start), date.fromisoformat(end)
        if gap_start >= known_start and gap_end <= known_end:
            return True
    return False


def audit_quality(
    records: Iterable[VintageObservation],
    *,
    spec: FredSeriesSpec,
    metadata: dict[str, Any],
    now: datetime | None = None,
) -> QualityReport:
    rows = list(records)
    now = now or datetime.now(UTC)
    blockers: list[str] = []
    warnings: list[str] = []
    if not rows:
        return QualityReport(
            source_health="BLOCKED",
            row_count=0,
            missing_ratio=1.0,
            duplicate_count=0,
            conflicting_duplicate_count=0,
            non_monotonic_count=0,
            long_gaps=(),
            future_available_at_count=0,
            metadata_drift=(),
            stale_metadata=False,
            blockers=("empty_payload",),
            warnings=(),
        )

    keys = [(row.observation_date, row.realtime_start) for row in rows]
    duplicate_count = len(keys) - len(set(keys))
    by_key: dict[tuple[date, date], set[float | None]] = {}
    for row in rows:
        by_key.setdefault((row.observation_date, row.realtime_start), set()).add(row.value)
    conflicting = sum(1 for values in by_key.values() if len(values) > 1)
    if conflicting:
        blockers.append("conflicting_duplicate_vintages")
    elif duplicate_count:
        warnings.append("duplicate_vintages")

    non_monotonic = sum(
        1
        for previous, current in zip(rows, rows[1:], strict=False)
        if (current.observation_date, current.realtime_start)
        < (previous.observation_date, previous.realtime_start)
    )
    if non_monotonic:
        warnings.append("non_monotonic_dates")

    missing = sum(row.value is None for row in rows)
    missing_ratio = missing / len(rows)
    if missing:
        warnings.append("missing_values")

    future_count = sum(row.conservative_available_at > now for row in rows)
    if future_count:
        blockers.append("impossible_future_available_at")

    unique_dates = sorted({row.observation_date for row in rows})
    gap_limit = _gap_limit_days(spec.frequency)
    long_gaps: list[tuple[str, str, int]] = []
    for left, right in zip(unique_dates, unique_dates[1:], strict=False):
        delta = (right - left).days
        if delta > gap_limit and not _known_gap(spec, left, right):
            long_gaps.append((left.isoformat(), right.isoformat(), delta))
    if long_gaps:
        warnings.append("long_gaps")

    drift: list[str] = []
    expected = {
        "id": spec.provider_series_id,
        "title": spec.title,
        "frequency": spec.frequency,
        "units": spec.units,
        "seasonal_adjustment": spec.seasonal_adjustment,
    }
    for field, expected_value in expected.items():
        actual = metadata.get(field)
        if actual is None:
            drift.append(f"{field}:missing")
        elif str(actual) != expected_value:
            drift.append(f"{field}:{actual!s}!={expected_value}")
    if drift:
        blockers.append("metadata_drift")

    stale_metadata = False
    last_updated = metadata.get("last_updated")
    if last_updated:
        parsed = pd.to_datetime(last_updated, utc=True, errors="coerce")
        if pd.isna(parsed):
            warnings.append("metadata_last_updated_unparseable")
        elif parsed.to_pydatetime() > now:
            blockers.append("metadata_last_updated_future")
        elif unique_dates and parsed.date() < unique_dates[-1]:
            stale_metadata = True
            warnings.append("stale_metadata")
    else:
        stale_metadata = True
        warnings.append("stale_metadata")

    health = "BLOCKED" if blockers else ("DEGRADED" if warnings else "HEALTHY")
    return QualityReport(
        source_health=health,
        row_count=len(rows),
        missing_ratio=missing_ratio,
        duplicate_count=duplicate_count,
        conflicting_duplicate_count=conflicting,
        non_monotonic_count=non_monotonic,
        long_gaps=tuple(long_gaps),
        future_available_at_count=future_count,
        metadata_drift=tuple(drift),
        stale_metadata=stale_metadata,
        blockers=tuple(dict.fromkeys(blockers)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def build_manifest(
    *,
    spec: FredSeriesSpec,
    mode: str,
    requested_start: str,
    requested_end: str,
    requested_as_of: str | None,
    records: Iterable[VintageObservation],
    quality: QualityReport,
    observation_payload: FredPayload,
    metadata: dict[str, Any],
) -> CoverageManifest:
    rows = list(records)
    observation_dates = [row.observation_date for row in rows]
    vintage_dates = [row.realtime_start for row in rows]
    return CoverageManifest(
        canonical_series_id=spec.canonical_series_id,
        provider_series_id=spec.provider_series_id,
        mode=mode,
        requested_start=requested_start,
        requested_end=requested_end,
        requested_as_of=requested_as_of,
        returned_start=min(observation_dates).isoformat() if observation_dates else None,
        returned_end=max(observation_dates).isoformat() if observation_dates else None,
        row_count=quality.row_count,
        missing_ratio=quality.missing_ratio,
        duplicate_count=quality.duplicate_count,
        latest_observation=max(observation_dates).isoformat() if observation_dates else None,
        latest_vintage=max(vintage_dates).isoformat() if vintage_dates else None,
        units=spec.units,
        frequency=spec.frequency,
        raw_sha256=observation_payload.raw_sha256,
        request_fingerprint=observation_payload.request_fingerprint,
        raw_archive_path=observation_payload.raw_archive_path,
        cache_hit=observation_payload.cache_hit,
        source_health=quality.source_health,
        blockers=quality.blockers,
        warnings=quality.warnings,
        metadata_last_updated=(
            str(metadata.get("last_updated")) if metadata.get("last_updated") else None
        ),
    )


class FredHistoricalCollector:
    """Writes only explicit research-staging artifacts and coverage manifests."""

    def __init__(
        self,
        *,
        client: FredAlfredClient,
        output_dir: str | Path,
        registry_path: str | Path = "config/fred_alfred_registry.yml",
    ):
        self.client = client
        self.output_dir = Path(output_dir)
        self.registry = load_fred_registry(registry_path)

    def _fetch_observations(
        self,
        spec: FredSeriesSpec,
        *,
        start: str,
        end: str,
        mode: str,
        as_of: str | None,
        resume: bool,
    ) -> tuple[FredPayload, date | None]:
        use_cache = bool(resume)
        if mode == MODE_HISTORICAL_ASOF:
            if not as_of:
                raise ValueError("historical_asof_requires_as_of")
            payload = self.client.fetch_historical_asof(
                spec.provider_series_id,
                observation_start=start,
                observation_end=end,
                as_of=as_of,
                use_cache=use_cache,
            )
            return payload, date.fromisoformat(as_of)
        if mode == MODE_REVISED_LATEST:
            return (
                self.client.fetch_revised_latest(
                    spec.provider_series_id,
                    observation_start=start,
                    observation_end=end,
                    use_cache=use_cache,
                ),
                None,
            )
        if mode == MODE_INITIAL_RELEASE:
            return (
                self.client.fetch_initial_release(
                    spec.provider_series_id,
                    observation_start=start,
                    observation_end=end,
                    use_cache=use_cache,
                ),
                None,
            )
        if mode == MODE_ALL_REALTIME_PERIODS:
            return (
                self.client.fetch_all_realtime_periods(
                    spec.provider_series_id,
                    observation_start=start,
                    observation_end=end,
                    use_cache=use_cache,
                ),
                None,
            )
        raise ValueError(f"unsupported_fred_collection_mode:{mode}")

    def collect_one(
        self,
        canonical_series_id: str,
        *,
        start: str,
        end: str,
        mode: str,
        as_of: str | None = None,
        resume: bool = True,
    ) -> CoverageManifest:
        spec = self.registry.series[canonical_series_id]
        if spec.status != "CANDIDATE":
            raise ValueError(f"fred_series_not_collectible:{canonical_series_id}:{spec.status}")
        metadata_payload = self.client.fetch_metadata(spec.provider_series_id, use_cache=resume)
        metadata = _metadata(metadata_payload)
        observation_payload, request_vintage = self._fetch_observations(
            spec,
            start=start,
            end=end,
            mode=mode,
            as_of=as_of,
            resume=resume,
        )
        records = parse_observations(
            canonical_series_id=canonical_series_id,
            provider_series_id=spec.provider_series_id,
            payload=observation_payload.payload,
            mode=mode,
            request_vintage=request_vintage,
        )
        quality = audit_quality(records, spec=spec, metadata=metadata)
        manifest = build_manifest(
            spec=spec,
            mode=mode,
            requested_start=start,
            requested_end=end,
            requested_as_of=as_of,
            records=records,
            quality=quality,
            observation_payload=observation_payload,
            metadata=metadata,
        )
        series_dir = self.output_dir / canonical_series_id
        series_dir.mkdir(parents=True, exist_ok=True)
        records_path = series_dir / f"{mode.lower()}.jsonl"
        records_path.write_text(
            "".join(json.dumps(row.to_dict(), sort_keys=True) + "\n" for row in records),
            encoding="utf-8",
        )
        (series_dir / f"{mode.lower()}_manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return manifest

    def collect_batch(
        self,
        series_ids: Iterable[str] | None,
        *,
        start: str,
        end: str,
        mode: str,
        as_of: str | None = None,
        resume: bool = True,
    ) -> dict[str, Any]:
        selected = list(series_ids or self.registry.candidate_series())
        manifests: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for canonical in selected:
            try:
                manifests.append(
                    self.collect_one(
                        canonical,
                        start=start,
                        end=end,
                        mode=mode,
                        as_of=as_of,
                        resume=resume,
                    ).to_dict()
                )
            except (FredAlfredError, FredPITError, ValueError, KeyError) as exc:
                failures.append(
                    {
                        "canonical_series_id": canonical,
                        "error": getattr(exc, "code", type(exc).__name__),
                        "message": str(exc)[:300],
                    }
                )
        report = {
            "domain_gate": "C0",
            "usage": "RESEARCH_STAGING_ONLY",
            "mode": mode,
            "requested_start": start,
            "requested_end": end,
            "requested_as_of": as_of,
            "series_count": len(selected),
            "success_count": len(manifests),
            "failure_count": len(failures),
            "manifests": manifests,
            "failures": failures,
            "source_health": (
                "BLOCKED"
                if not manifests
                else (
                    "DEGRADED"
                    if failures
                    or any(row["source_health"] != "HEALTHY" for row in manifests)
                    else "HEALTHY"
                )
            ),
        }
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "coverage_manifest.json").write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FRED/ALFRED C0 research-staging collector")
    parser.add_argument("--series", action="append", default=[])
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--mode",
        choices=sorted(_MODE_ALIASES),
        default="historical-asof",
    )
    parser.add_argument("--as-of")
    parser.add_argument("--output-dir", default="artifacts/research_staging/fred_alfred")
    parser.add_argument("--cache-dir", default=".cache/fred_alfred")
    parser.add_argument("--no-resume", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    mode = _MODE_ALIASES[args.mode]
    if mode == MODE_HISTORICAL_ASOF and not args.as_of:
        raise SystemExit("--as-of is required for historical-asof mode")
    client = FredAlfredClient(cache=FredResponseCache(args.cache_dir))
    collector = FredHistoricalCollector(client=client, output_dir=args.output_dir)
    report = collector.collect_batch(
        args.series or None,
        start=args.start,
        end=args.end,
        mode=mode,
        as_of=args.as_of,
        resume=not args.no_resume,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["failure_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CoverageManifest",
    "FredHistoricalCollector",
    "QualityReport",
    "audit_quality",
    "build_manifest",
    "main",
]
