from datetime import UTC, date, datetime, timedelta

from cross_asset.domain.models import Observation
from cross_asset.ingestion.quality import freshness_status
from cross_asset.ingestion.raw_archive import ImmutableRawArchive
from cross_asset.ingestion.runner import IngestionRunner
from cross_asset.pit.asof import query_asof
from cross_asset.providers.base import BaseProvider, ProviderError
from cross_asset.storage import DuckDBStore


def _obs(available_at, value=1.0):
    return Observation(
        series_id="TEST",
        observation_date=date(2025, 1, 1),
        available_at=available_at,
        value=value,
        source="fake",
        source_series_id="TEST",
    )


def test_pit_no_lookahead():
    store = DuckDBStore()
    store.insert_observations(
        [_obs(datetime(2025, 2, 10, tzinfo=UTC)).model_dump(mode="json")], "r1"
    )
    assert query_asof(store.conn, datetime(2025, 2, 9, tzinfo=UTC), "TEST").fetchall() == []
    assert len(query_asof(store.conn, datetime(2025, 2, 10, tzinfo=UTC), "TEST").fetchall()) == 1


def test_failed_provider_is_recorded():
    class Failed(BaseProvider):
        name = "failed"

        def probe(self):
            raise NotImplementedError

        def fetch(self, request):
            return self._failure(ProviderError("offline", "disabled", provider=self.name))

    provider = Failed()
    result = IngestionRunner(DuckDBStore()).run(provider, provider.fetch, run_id="failed-run")
    assert result["status"] == "failed"


def test_stale_data_status():
    old = datetime(2025, 1, 1, tzinfo=UTC)
    assert (
        freshness_status(_obs(old), now=old + timedelta(hours=25), stale_after_hours=24) == "STALE"
    )


def test_duplicate_ingestion_is_idempotent():
    store = DuckDBStore()
    row = _obs(datetime(2025, 2, 10, tzinfo=UTC)).model_dump(mode="json")
    assert store.insert_observations([row], "r1") == 1
    assert store.insert_observations([row], "r2") == 0
    assert store.query("SELECT count(*) FROM observations").fetchone()[0] == 1


def test_raw_archive_exists_and_is_linked(tmp_path):
    store = DuckDBStore()
    provider = type("Provider", (), {"name": "fake", "last_error": None})()
    archive = ImmutableRawArchive(tmp_path)
    result = IngestionRunner(store, archive).run(
        provider, lambda: [_obs(datetime(2025, 2, 10, tzinfo=UTC))], run_id="r1"
    )
    assert result["rows_written"] == 1
    raw_file = store.query("SELECT raw_file FROM observations").fetchone()[0]
    assert raw_file and __import__("pathlib").Path(raw_file).exists()
