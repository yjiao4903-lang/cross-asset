import json
from datetime import UTC, datetime

from cross_asset.ingestion.fred_alfred_pit import (
    MODE_ALL_REALTIME_PERIODS,
    MODE_HISTORICAL_ASOF,
    MODE_INITIAL_RELEASE,
    parse_observations,
)
from cross_asset.ingestion.fred_alfred_registry import load_fred_registry
from cross_asset.ingestion.fred_alfred_staging import (
    FredHistoricalCollector,
    audit_quality,
)
from cross_asset.providers.fred_alfred import FredAlfredClient, FredPayload


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


def test_historical_metadata_revision_is_not_false_current_metadata_drift():
    spec = load_fred_registry().series["US_CPI_HEADLINE"]
    rows = _records(
        spec,
        [_row("2020-01-01", "100", realtime_start="2020-02-15")],
        mode=MODE_HISTORICAL_ASOF,
        request_vintage="2020-03-20",
    )
    report = audit_quality(
        rows,
        spec=spec,
        metadata=_metadata(
            spec,
            title="Historical CPI title",
            units="Historical CPI units",
            realtime_start="2020-03-01",
            realtime_end="2020-04-30",
            last_updated="2020-03-15 12:00:00+00:00",
        ),
        metadata_as_of="2020-03-20",
        now=datetime(2020, 3, 20, 23, 59, tzinfo=UTC),
    )
    assert report.metadata_drift
    assert "metadata_revision_vs_current_registry" in report.warnings
    assert "metadata_drift" not in report.blockers


def test_historical_metadata_last_updated_after_asof_fails_closed():
    spec = load_fred_registry().series["US_CPI_HEADLINE"]
    rows = _records(
        spec,
        [_row("2020-01-01", "100", realtime_start="2020-02-15")],
        mode=MODE_HISTORICAL_ASOF,
        request_vintage="2020-03-20",
    )
    report = audit_quality(
        rows,
        spec=spec,
        metadata=_metadata(
            spec,
            realtime_start="2020-03-01",
            realtime_end="2020-04-30",
            last_updated="2020-03-21 00:00:00+00:00",
        ),
        metadata_as_of="2020-03-20",
        now=datetime(2020, 3, 22, tzinfo=UTC),
    )
    assert "metadata_last_updated_after_as_of" in report.blockers
    assert report.source_health == "BLOCKED"


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
        self.metadata_requests = []

    def fetch_metadata(self, _series_id, *, use_cache=True):
        return FredPayload(
            endpoint="series",
            params={"series_id": self.spec.provider_series_id},
            payload={"seriess": [_metadata(self.spec)]},
            request_fingerprint="meta-current-fp",
            raw_sha256="meta-current-hash",
            fetched_at=datetime(2020, 3, 20, tzinfo=UTC),
            ingested_at=datetime(2020, 3, 20, tzinfo=UTC),
            cache_hit=False,
        )

    def request_json(self, endpoint, params, *, use_cache=True):
        self.metadata_requests.append((endpoint, dict(params)))
        as_of = params["realtime_start"]
        return FredPayload(
            endpoint="series",
            params=dict(params),
            payload={
                "seriess": [
                    _metadata(
                        self.spec,
                        realtime_start="2020-03-01",
                        realtime_end="2020-04-30",
                        last_updated="2020-03-20 12:00:00+00:00",
                    )
                ]
            },
            request_fingerprint="meta-asof-fp",
            raw_sha256="meta-asof-hash",
            fetched_at=datetime.fromisoformat(f"{as_of}T18:00:00+00:00"),
            ingested_at=datetime.fromisoformat(f"{as_of}T18:00:00+00:00"),
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
            params={"vintage_dates": as_of},
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


def test_collector_pins_historical_metadata_and_writes_evidence(tmp_path):
    spec = load_fred_registry().series["US_CPI_HEADLINE"]
    client = FakeClient(spec)
    collector = FredHistoricalCollector(client=client, output_dir=tmp_path)
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
    assert manifest.metadata_raw_sha256 == "meta-asof-hash"
    assert manifest.metadata_request_fingerprint == "meta-asof-fp"
    assert manifest.metadata_realtime_start == "2020-03-01"
    assert manifest.metadata_realtime_end == "2020-04-30"
    assert manifest.metadata_as_of_safe is True
    assert client.metadata_requests == [
        (
            "series",
            {
                "series_id": spec.provider_series_id,
                "realtime_start": "2020-03-20",
                "realtime_end": "2020-03-20",
            },
        )
    ]
    assert (tmp_path / "US_CPI_HEADLINE" / "historical_asof.jsonl").exists()
    assert (tmp_path / "US_CPI_HEADLINE" / "historical_asof_manifest.json").exists()


def test_collector_uses_historical_metadata_values_not_current_registry(tmp_path):
    spec = load_fred_registry().series["US_CPI_HEADLINE"]

    class RevisedMetadataClient(FakeClient):
        def request_json(self, endpoint, params, *, use_cache=True):
            payload = super().request_json(endpoint, params, use_cache=use_cache)
            revised = _metadata(
                self.spec,
                title="Historical CPI title",
                units="Historical CPI units",
                realtime_start="2020-03-01",
                realtime_end="2020-04-30",
                last_updated="2020-03-15 12:00:00+00:00",
            )
            return FredPayload(
                endpoint=payload.endpoint,
                params=payload.params,
                payload={"seriess": [revised]},
                request_fingerprint=payload.request_fingerprint,
                raw_sha256=payload.raw_sha256,
                fetched_at=payload.fetched_at,
                ingested_at=payload.ingested_at,
                cache_hit=payload.cache_hit,
            )

    manifest = FredHistoricalCollector(
        client=RevisedMetadataClient(spec),
        output_dir=tmp_path,
    ).collect_one(
        "US_CPI_HEADLINE",
        start="2020-01-01",
        end="2020-02-01",
        mode=MODE_HISTORICAL_ASOF,
        as_of="2020-03-20",
    )
    assert manifest.title == "Historical CPI title"
    assert manifest.units == "Historical CPI units"
    assert "metadata_revision_vs_current_registry" in manifest.warnings
    assert "metadata_drift" not in manifest.blockers


def test_collector_fails_closed_when_historical_metadata_period_is_unproven(tmp_path):
    spec = load_fred_registry().series["US_CPI_HEADLINE"]

    class UnpinnedMetadataClient(FakeClient):
        def request_json(self, endpoint, params, *, use_cache=True):
            return FredPayload(
                endpoint=endpoint,
                params=dict(params),
                payload={"seriess": [_metadata(self.spec)]},
                request_fingerprint="bad-meta-fp",
                raw_sha256="bad-meta-hash",
                fetched_at=datetime(2020, 3, 20, tzinfo=UTC),
                ingested_at=datetime(2020, 3, 20, tzinfo=UTC),
                cache_hit=False,
            )

    report = FredHistoricalCollector(
        client=UnpinnedMetadataClient(spec),
        output_dir=tmp_path,
    ).collect_batch(
        ["US_CPI_HEADLINE"],
        start="2020-01-01",
        end="2020-02-01",
        mode=MODE_HISTORICAL_ASOF,
        as_of="2020-03-20",
    )
    assert report["failure_count"] == 1
    assert report["source_health"] == "BLOCKED"
    assert report["failures"][0]["error"] == "metadata_vintage_unresolved"


class _Response:
    def __init__(self, payload):
        self.status_code = 200
        self.content = json.dumps(payload).encode()
        self.headers = {}

    def json(self):
        return json.loads(self.content)


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)

    def get(self, _url, **_kwargs):
        return self.responses.pop(0)


def test_official_initial_release_shape_runs_provider_through_collector(tmp_path):
    spec = load_fred_registry().series["US_CPI_HEADLINE"]
    metadata_payload = {"seriess": [_metadata(spec)]}
    initial_release_payload = {
        "output_type": 4,
        "observations": [
            {
                "realtime_start": "2020-02-13",
                "date": "2020-01-01",
                "value": "258.678",
            }
        ],
    }
    client = FredAlfredClient(
        api_key="secret",
        session=_Session([_Response(metadata_payload), _Response(initial_release_payload)]),
        retries=0,
    )
    manifest = FredHistoricalCollector(client=client, output_dir=tmp_path).collect_one(
        "US_CPI_HEADLINE",
        start="2020-01-01",
        end="2020-01-01",
        mode=MODE_INITIAL_RELEASE,
    )
    assert manifest.row_count == 1
    assert manifest.latest_vintage == "2020-02-13"
    record = json.loads(
        (tmp_path / "US_CPI_HEADLINE" / "initial_release.jsonl")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert record["realtime_start"] == "2020-02-13"
    assert record["realtime_end"] is None


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
