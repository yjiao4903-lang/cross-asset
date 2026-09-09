from cross_asset.ingestion.fred_alfred_registry import load_fred_registry


def test_initial_registry_covers_issue_66_first_batch():
    registry = load_fred_registry()
    expected = {
        "US_EFFR",
        "US_TSY_3M",
        "US_TSY_2Y",
        "US_TSY_10Y",
        "US_TSY_30Y",
        "US_CPI_HEADLINE",
        "US_CPI_CORE",
        "US_PCE_HEADLINE",
        "US_PCE_CORE",
        "US_UNEMPLOYMENT",
        "US_NONFARM_PAYROLLS",
        "US_INITIAL_CLAIMS",
        "US_INDUSTRIAL_PRODUCTION",
        "US_RETAIL_SALES",
        "US_HOUSING_STARTS",
        "US_BUILDING_PERMITS",
        "US_M2",
        "US_FED_TOTAL_ASSETS",
        "US_NFCI",
        "USD_BROAD_INDEX",
    }
    assert expected <= set(registry.series)
    assert registry.domain_gate == "C0"
    assert registry.usage == "RESEARCH_STAGING_ONLY"
    assert all(spec.provider == "FRED/ALFRED" for spec in registry.series.values())
    assert all(spec.status == "CANDIDATE" for spec in registry.series.values())


def test_registry_uses_audited_provider_ids_not_derived_spread_ids():
    registry = load_fred_registry()
    assert registry.series["US_EFFR"].provider_series_id == "DFF"
    assert registry.series["US_TSY_3M"].provider_series_id == "DGS3MO"
    assert registry.series["US_TSY_2Y"].provider_series_id == "DGS2"
    assert registry.series["US_TSY_10Y"].provider_series_id == "DGS10"
    assert registry.series["US_TSY_30Y"].provider_series_id == "DGS30"
    assert registry.series["US_NFCI"].provider_series_id == "NFCI"
    assert registry.series["USD_BROAD_INDEX"].provider_series_id == "DTWEXBGS"
    assert "US_10Y_2Y_SPREAD" not in registry.series
    assert "US_10Y_3M_SPREAD" not in registry.series


def test_registry_freezes_conservative_date_only_availability_policy():
    registry = load_fred_registry()
    assert (
        registry.availability_contract["policy"]
        == "VINTAGE_DATE_PLUS_2D_UTC_CONSERVATIVE"
    )
    assert all(
        spec.release_availability_policy
        == "VINTAGE_DATE_PLUS_2D_UTC_CONSERVATIVE"
        for spec in registry.series.values()
    )
