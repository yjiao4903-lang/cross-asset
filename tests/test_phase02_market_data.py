from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from cross_asset.ingestion.raw_archive import ImmutableRawArchive
from cross_asset.ingestion.runner import IngestionRunner
from cross_asset.pit.asof import query_asof
from cross_asset.providers import DataRequest, FixtureProvider
from cross_asset.storage import DuckDBStore

CORE = {
    "CN_EQ_LARGE",
    "CN_EQ_SMALL",
    "HK_EQ",
    "US_EQ",
    "CN_BOND_10Y",
    "US_GOV_10Y",
    "US_REAL_10Y",
    "GOLD",
    "COPPER",
    "DXY",
}


def test_market_catalog_and_fixture_end_to_end(tmp_path):
    catalog = yaml.safe_load(Path("config/series.yml").read_text(encoding="utf-8"))["series"]
    mappings = yaml.safe_load(Path("config/sources.yml").read_text(encoding="utf-8"))["mappings"]
    assert CORE <= {x["series_id"] for x in catalog}
    assert CORE <= {x["series_id"] for x in mappings}
    values = {sid: i + 1 for i, sid in enumerate(sorted(CORE))}
    provider = FixtureProvider(values=values)
    store = DuckDBStore()
    result = IngestionRunner(store, ImmutableRawArchive(tmp_path / "raw")).run(
        provider,
        provider.fetch,
        DataRequest(series_ids=sorted(CORE), start=date(2025, 1, 2)),
        run_id="p2",
    )
    assert result["status"] == "success" and result["rows_written"] == 10
    assert (
        store.query("SELECT count(*) FROM observations WHERE raw_file IS NOT NULL").fetchone()[0]
        == 10
    )
    # Same logical observations remain idempotent even under a different run id.
    assert (
        IngestionRunner(store).run(
            provider,
            provider.fetch,
            DataRequest(series_ids=sorted(CORE), start=date(2025, 1, 2)),
            run_id="p2b",
        )["rows_written"]
        == 0
    )
    # The as-of query remains PIT-safe.
    future = datetime.now(UTC).replace(year=2099)
    assert query_asof(store.conn, future, "GOLD").fetchone()[0] == "GOLD"


def test_semantic_equivalence_is_explicit():
    mappings = yaml.safe_load(Path("config/sources.yml").read_text(encoding="utf-8"))["mappings"]
    assert all("semantic_equivalence" in m for m in mappings)
