from datetime import UTC, datetime

from cross_asset.domain.models import DataRequest
from cross_asset.providers.manual import ManualProvider


def test_manual_requires_explicit_available_at(tmp_path):
    path = tmp_path / "manual.csv"
    path.write_text("series_id,observation_date,value\nS,2025-01-31,100\n", encoding="utf-8")
    provider = ManualProvider(path=str(path))

    assert provider.fetch(DataRequest(series_ids=["S"])) == []
    assert provider.last_error["code"] == "schema_error"
    assert "available_at" not in provider.last_error["details"]


def test_manual_preserves_explicit_available_at(tmp_path):
    path = tmp_path / "manual.csv"
    path.write_text(
        "series_id,observation_date,available_at,value\n"
        "S,2025-01-31,2025-02-10T09:30:00+08:00,100\n",
        encoding="utf-8",
    )
    observations = ManualProvider(path=str(path)).fetch(DataRequest(series_ids=["S"]))

    assert observations[0].available_at == datetime(2025, 2, 10, 1, 30, tzinfo=UTC)
