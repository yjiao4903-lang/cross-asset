from cross_asset.storage import DuckDBStore
from cross_asset.storage.catalog import (
    expected_source_identities,
    series_catalog_read_model,
    sync_series_catalog,
)


def test_sync_series_catalog_activates_existing_tables_without_admission():
    store = DuckDBStore(":memory:")
    try:
        result = sync_series_catalog(
            store,
            series_ids=["US_EQ", "US_GOV_10Y", "DXY", "HK_EQ"],
            provider="yahoo",
        )
        assert result == {
            "series_catalog_rows": 4,
            "source_mapping_rows": 4,
            "acceptance_registry_writes": 0,
        }
        assert store.conn.execute(
            "SELECT count(*) FROM data_acceptance_registry"
        ).fetchone()[0] == 0

        rows = series_catalog_read_model(
            store.conn,
            series_ids=["US_EQ", "US_GOV_10Y", "DXY", "HK_EQ"],
            provider="yahoo",
        )
        by_id = {row["series_id"]: row for row in rows}
        assert by_id["US_EQ"]["source_series_id"] == "^GSPC"
        assert by_id["HK_EQ"]["source_series_id"] == "^HSI"
        assert by_id["DXY"]["source_series_id"] == "DX-Y.NYB"
        assert by_id["US_GOV_10Y"]["source_series_id"] == "^TNX"
        assert by_id["US_GOV_10Y"]["semantic_equivalence"] is False

        for row in rows:
            assert row["provider"] == "yahoo"
            assert row["frequency"] == "daily"
            assert "unit" in row
            assert "currency" in row
            assert "timezone" in row
            assert row["freshness_expectation"]["stale_after_hours"] is not None
            assert row["usage_eligibility"] == "MONITORING_ONLY"
            assert row["registry_usage_statuses"] == []
    finally:
        store.close()


def test_expected_source_identities_are_exact_and_config_backed():
    store = DuckDBStore(":memory:")
    try:
        sync_series_catalog(store, series_ids=["US_EQ"], provider="yahoo")
        identities = expected_source_identities(store.conn, "yahoo", ["US_EQ"])
        assert identities == {"US_EQ": {"^GSPC"}}
    finally:
        store.close()


def test_fred_monitoring_canonical_identities_and_mappings_are_real_catalog_rows():
    store = DuckDBStore(":memory:")
    series_ids = [
        "US_NONFARM_PAYROLLS",
        "US_CORE_CPI",
        "US_GOV_2Y",
        "US_REAL_10Y",
    ]
    try:
        result = sync_series_catalog(store, series_ids=series_ids, provider="fred")
        assert result == {
            "series_catalog_rows": 4,
            "source_mapping_rows": 4,
            "acceptance_registry_writes": 0,
        }
        assert store.conn.execute(
            "SELECT count(*) FROM data_acceptance_registry"
        ).fetchone()[0] == 0

        identities = expected_source_identities(store.conn, "fred", series_ids)
        assert identities == {
            "US_NONFARM_PAYROLLS": {"PAYEMS"},
            "US_CORE_CPI": {"CPILFESL"},
            "US_GOV_2Y": {"DGS2"},
            "US_REAL_10Y": {"DFII10"},
        }

        rows = series_catalog_read_model(
            store.conn, series_ids=series_ids, provider="fred"
        )
        by_id = {row["series_id"]: row for row in rows}
        assert by_id["US_NONFARM_PAYROLLS"]["frequency"] == "monthly"
        assert by_id["US_NONFARM_PAYROLLS"]["unit"] == "thousands_persons"
        assert by_id["US_CORE_CPI"]["frequency"] == "monthly"
        assert by_id["US_CORE_CPI"]["unit"] == "index_1982_1984_100"
        assert by_id["US_GOV_2Y"]["unit"] == "yield_percent"
        assert by_id["US_REAL_10Y"]["unit"] == "yield_percent"
        for row in rows:
            assert row["semantic_equivalence"] is True
            assert row["usage_eligibility"] == "MONITORING_ONLY"
            assert row["registry_usage_statuses"] == []
    finally:
        store.close()
