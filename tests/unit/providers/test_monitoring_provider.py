from datetime import UTC, date, datetime

from cross_asset.domain.models import DataRequest, Observation
from cross_asset.providers.monitoring import FREDMonitoringProvider, YahooMonitoringProvider


def test_yahoo_monitoring_provider_preserves_identity_and_marks_lane(monkeypatch):
    def fake_fetch(request, timeout=10):
        assert request.series_ids == ["US_EQ"]
        assert timeout == 3
        return [
            Observation(
                series_id="US_EQ",
                observation_date=date(2026, 9, 16),
                available_at=datetime(2026, 9, 16, 21, tzinfo=UTC),
                value=7000.0,
                source="yahoo",
                source_series_id="^GSPC",
                frequency="daily",
                unit="price",
            )
        ]

    monkeypatch.setattr("cross_asset.providers.monitoring.yahoo_fetch", fake_fetch)
    provider = YahooMonitoringProvider(timeout=3)
    rows = provider.fetch(DataRequest(series_ids=["US_EQ"]))

    assert len(rows) == 1
    row = rows[0]
    assert row.source == "yahoo"
    assert row.source_series_id == "^GSPC"
    assert row.available_at.tzinfo is not None
    assert row.metadata["origin"] == "MONITORING"
    assert row.metadata["usage_lane"] == "MONITORING_ONLY"


def test_yahoo_monitoring_provider_rejects_out_of_scope_series():
    provider = YahooMonitoringProvider()
    rows = provider.fetch(DataRequest(series_ids=["GOLD"]))
    assert rows == []
    assert provider.last_error["code"] == "unsupported_monitoring_series"


def test_yahoo_monitoring_probe_uses_existing_live_probe(monkeypatch):
    monkeypatch.setattr(
        "cross_asset.providers.monitoring.probe_yahoo",
        lambda timeout=8: {
            "provider": "yahoo",
            "reachable": True,
            "error_type": None,
            "safe_error": None,
        },
    )
    capability = YahooMonitoringProvider().probe()
    assert capability.provider == "yahoo"
    assert capability.price == "available"
    assert capability.history == "public_monitoring"
    assert capability.errors == []


def test_fred_monitoring_reuses_public_csv_and_emits_governed_identities(monkeypatch):
    def fake_public_csv(self, request):
        expected = {
            "US_NONFARM_PAYROLLS": "PAYEMS",
            "US_CORE_CPI": "CPILFESL",
            "US_GOV_2Y": "DGS2",
            "US_REAL_10Y": "DFII10",
        }
        assert request.source_series_ids == expected
        assert request.start == date(2020, 1, 1)
        series = {}
        for sid, code in expected.items():
            payload = (
                f"observation_date,{code}\n"
                f"2026-07-01,100.0\n"
                f"2026-08-01,101.0\n"
            ).encode()
            self.raw_archive.write("fred", f"public_csv_{code}", payload, extension="csv")
            series[sid] = {"source_series_id": code, "row_count": 2}
        return {"status": "PARTIAL", "source_mode": "FRED_PUBLIC_GRAPH_CSV", "series": series}

    monkeypatch.setattr(
        "cross_asset.providers.monitoring.FREDProvider.fetch_public_csv_sample",
        fake_public_csv,
    )
    provider = FREDMonitoringProvider()
    rows = provider.fetch(
        DataRequest(
            series_ids=[
                "US_NONFARM_PAYROLLS",
                "US_CORE_CPI",
                "US_GOV_2Y",
                "US_REAL_10Y",
            ]
        )
    )

    assert len(rows) == 8
    by_id = {}
    for row in rows:
        by_id.setdefault(row.series_id, row)
        assert row.source == "fred"
        assert row.metadata["origin"] == "MONITORING"
        assert row.metadata["usage_lane"] == "MONITORING_ONLY"
        assert row.metadata["transport"] == "FRED_PUBLIC_GRAPH_CSV"
        assert row.metadata["available_at_semantics"] == "monitoring_capture_time_non_pit"
        assert row.metadata["first_release_timestamp_known"] is False
        assert row.available_at.tzinfo is not None

    assert by_id["US_NONFARM_PAYROLLS"].source_series_id == "PAYEMS"
    assert by_id["US_NONFARM_PAYROLLS"].frequency == "monthly"
    assert by_id["US_NONFARM_PAYROLLS"].unit == "thousands_persons"
    assert by_id["US_CORE_CPI"].source_series_id == "CPILFESL"
    assert by_id["US_CORE_CPI"].unit == "index_1982_1984_100"
    assert by_id["US_GOV_2Y"].source_series_id == "DGS2"
    assert by_id["US_REAL_10Y"].source_series_id == "DFII10"


def test_fred_monitoring_rejects_semantic_substitutions():
    provider = FREDMonitoringProvider()
    for sid in ("US_INITIAL_CLAIMS", "US_CORE_PCE", "DXY"):
        rows = provider.fetch(DataRequest(series_ids=[sid]))
        assert rows == []
        assert provider.last_error["code"] == "unsupported_monitoring_series"


def test_fred_monitoring_provider_failure_is_explicit_and_has_no_fallback(monkeypatch):
    def failed_public_csv(self, request):
        return {
            "status": "PARTIAL",
            "series": {
                "US_NONFARM_PAYROLLS": {
                    "source_series_id": "PAYEMS",
                    "status": "FAILED",
                    "error": {"code": "http_503", "message": "upstream unavailable"},
                }
            },
        }

    monkeypatch.setattr(
        "cross_asset.providers.monitoring.FREDProvider.fetch_public_csv_sample",
        failed_public_csv,
    )
    provider = FREDMonitoringProvider()
    rows = provider.fetch(DataRequest(series_ids=["US_NONFARM_PAYROLLS"]))

    assert rows == []
    assert provider.last_error["code"] == "monitoring_fetch_failed"
    assert "http_503" in provider.last_error["message"]
