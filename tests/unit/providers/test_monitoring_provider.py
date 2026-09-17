from datetime import UTC, date, datetime

from cross_asset.domain.models import DataRequest, Observation
from cross_asset.providers.monitoring import YahooMonitoringProvider


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
