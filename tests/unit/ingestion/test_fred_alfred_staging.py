from datetime import UTC, datetime

from cross_asset.ingestion.fred_alfred_pit import (
    MODE_ALL_REALTIME_PERIODS,
    MODE_HISTORICAL_ASOF,
    parse_observations,
)
from cross_asset.ingestion.fred_alfred_registry import load_fred_registry
from cross_asset.ingestion.fred_alfred_staging import (
    FredHistoricalCollector,
    audit_quality,
)
from cross_asset.providers.fred_alfred import FredPayload


def _metadata(spec, **overrides):
    payload = {
        "id": spec.provider_series_id,
        "title": spec.title,
        "frequency": spec.frequency,
        "units": spec.units,
        "seasonal_adjustment": spec.seasonal_adjustment,
        "last_updated": "2020-03-20 12:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def _records(spec, rows, mode=MODE_ALL_REALTIME_PERIODS, request_vintage=None):
    return parse_observations(
        canonical_series_id=spec.canonical_series_id,
        provider_series_id=spec.provider_series_id,
        payload={"observations": rows},
        mode=mode,
        request_vintage=request_vintage,
    )


def _row(date, value, realtime_start="2020-03-01", realtime_end="9999-12-31"):
    return {
        "date": date,
        "value": value,
        "realtime_start": realtime_start,
        "realtime_end": realtime_end,
    }


def test_quality_detects_missing_duplicate_long_gap_and_metadata_drift():
    spec = load_fred_registry().series["US_CPI_HEADLINE"]
    rows = _records(
        spec,
        [
            _row("2020-01-01", "100"),
            _row("2020-01-01", "101"),
            _row("2020-06-01", "."),
        ],
    )
    report = audit_quality(
        rows,
        spec=spec,
        metadata=_metadata(spec, units="Percent"),
        now=datetime(2020, 7, 1, tzinfo=UTC),
    )
    assert report.duplicate_count == 1
    assert report.conflicting_duplicate_count == 1
    assert report.missing_ratio == 1 / 3
    assert report.long_gaps
    assert report.metadata_drift
    assert report.source_health == "BLOCKED"
    assert "metadata_drift" in report.blockers


def test_quality_flags_impossible_future_available_at():
    spec = load_fred_registry().series["US_CPI_HEADLINE"]
    rows = _records(spec, [_row("2020-01-01", "100", realtime_start="2020-05-01")])
    report = audit_quality(
        rows,
        spec=spec,
        metadata=_metadata(spec),
        now=datetime(2020, 4, 1, tzinfo=UTC),
    )
    assert report.future_available_at_count == 1
    assert "impossible_future_available_at" in report.blockers


def test_known_dgs30_structural_gap_is_not_reported_as_transport_gap():
    spec = load_fred_registry().series["US_TSY_30Y"]
    rows = _records(
        spec,
        [
            _row("2002-02-18", "5.0", realtime_start="2002-02-19"),
            _row("2006-02-09", "4.5", realtime_start="2006-02-10"),
        ],
    )
    report = audit_quality(
        rows,
        spec=spec,
        metadata={
            **_metadata(spec),
            "last_updated": "2006-02-10 12:00:00+00:00",
        },
        now=datetime(2006, 2, 12, tzinfo=UTC),
    )
    assert report.long_gaps == ()


class FakeClient:
    def __init__(self, spec):
        self.spec = spec

    def fetch_metadata(self, _series_id, *, use_cache=True):
        return FredPayload(
            endpoint="series",
            params={},
            payload={"seriess": [_metadata(self.spec)]},
            request_fingerprint="meta-fp",
            raw_sha256="meta-hash",
            fetched_at=datetime(2020, 3, 20, tzinfo=UTC),
            ingested_at=datetime(2020, 3, 20, tzinfo=UTC),
            cache_hit=False,
        )

    def fetch_historical_asof(
        self,
        _series_id,
        *,
        observation_start,
        observation_end,
        as_of,
        use_cache=True,
    ):
        return FredPayload(
            endpoint="series/observations",
            params={},
            payload={
                "observations": [
                    _row("2020-01-01", "100", realtime_start="2020-02-15"),
                    _row("2020-02-01", "101", realtime_start="2020-03-15"),
                ]
            },
            request_fingerprint="obs-fp",
            raw_sha256="obs-hash",
            fetched_at=datetime(2020, 3, 20, tzinfo=UTC),
            ingested_at=datetime(2020, 3, 20, tzinfo=UTC),
            cache_hit=False,
            raw_archive_path="/tmp/raw.json",
        )


def test_collector_writes_records_and_full_coverage_manifest(tmp_path):
    spec = load_fred_registry().series["US_CPI_HEADLINE"]
    collector = FredHistoricalCollector(
        client=FakeClient(spec),
        output_dir=tmp_path,
    )
    manifest = collector.collect_one(
        "US_CPI_HEADLINE",
        start="2020-01-01",
        end="2020-02-01",
        mode=MODE_HISTORICAL_ASOF,
        as_of="2020-03-20",
    )
    assert manifest.row_count == 2
    assert manifest.requested_as_of == "2020-03-20"
    assert manifest.returned_start == "2020-01-01"
    assert manifest.latest_vintage == "2020-03-15"
    assert manifest.raw_sha256 == "obs-hash"
    assert manifest.request_fingerprint == "obs-fp"
    assert (tmp_path / "US_CPI_HEADLINE" / "historical_asof.jsonl").exists()
    assert (tmp_path / "US_CPI_HEADLINE" / "historical_asof_manifest.json").exists()


def test_batch_manifest_records_provider_failure_instead_of_silent_success(tmp_path):
    spec = load_fred_registry().series["US_CPI_HEADLINE"]

    class FailingClient(FakeClient):
        def fetch_historical_asof(self, *args, **kwargs):
            from cross_asset.providers.fred_alfred import FredAlfredError

            raise FredAlfredError("rate_limited", "rate limited", retryable=True)

    collector = FredHistoricalCollector(
        client=FailingClient(spec),
        output_dir=tmp_path,
    )
    report = collector.collect_batch(
        ["US_CPI_HEADLINE"],
        start="2020-01-01",
        end="2020-02-01",
        mode=MODE_HISTORICAL_ASOF,
        as_of="2020-03-20",
    )
    assert report["failure_count"] == 1
    assert report["source_health"] == "BLOCKED"
    assert report["failures"][0]["error"] == "rate_limited"
    assert (tmp_path / "coverage_manifest.json").exists()
