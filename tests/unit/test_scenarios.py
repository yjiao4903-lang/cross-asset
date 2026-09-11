from cross_asset.research.scenarios import ScenarioSpec, evaluate_scenario


def test_bond_duration_scenario_is_transparent_and_costed():
    result = evaluate_scenario(ScenarioSpec("bond-1", "CN_BOND", "bond_duration", 2.0, 25.0, "bp", duration=8.0, cost_bps=5, as_of="2026-09-09", evidence_refs=("fixture:yield",), assumptions=("parallel shift",)))
    assert result.status == "ESTIMATED_SCENARIO"
    assert result.value < 0 and result.up is None and result.down is None
    assert "duration" in result.formula


def test_foreign_asset_missing_parameters_is_unestimated():
    result = evaluate_scenario(ScenarioSpec("fx-1", "US_EQ", "foreign_asset", None, None, "fraction", currency="USD", as_of="2026-09-09", evidence_refs=("fixture:price",)))
    assert result.status == "UNESTIMATED" and result.up is None


def test_foreign_asset_uses_one_explicit_combined_shock_and_convention():
    result = evaluate_scenario(ScenarioSpec("fx-2", "US_EQ", "foreign_asset", 100.0, None, "fraction", local_price_shock=0.10, fx_shock=0.10, currency="USD", base_currency="CNY", quote_currency="USD", quote_convention="CNY_per_USD", cost_bps=0, as_of="2026-09-09", evidence_refs=("fixture:price", "fixture:fx")))
    assert result.status == "ESTIMATED_SCENARIO" and round(result.value, 6) == 0.21
    bad = ScenarioSpec("fx-3", "US_EQ", "foreign_asset", 100.0, None, "fraction", local_price_shock=-0.10, fx_shock=-0.10, currency="USD", base_currency="CNY", quote_currency="USD", quote_convention="CNY_per_USD", cost_bps=0, as_of="2026-09-09", evidence_refs=("fixture:price", "fixture:fx"))
    assert round(evaluate_scenario(bad).value, 6) == -0.19
    reverse = ScenarioSpec("fx-4", "US_EQ", "foreign_asset", 100.0, None, "fraction", local_price_shock=.1, fx_shock=.1, currency="USD", base_currency="CNY", quote_currency="USD", quote_convention="USD_per_CNY", cost_bps=0, as_of="2026-09-09", evidence_refs=("fixture:price", "fixture:fx"))
    assert evaluate_scenario(reverse).status == "UNESTIMATED"


def test_scenario_requires_cost_and_valid_duration():
    missing_cost = ScenarioSpec("bond-2", "CN_BOND", "bond_duration", 100.0, 25.0, "bp", duration=8.0, as_of="2026-09-09", evidence_refs=("fixture:yield",))
    assert evaluate_scenario(missing_cost).status == "UNESTIMATED"
    negative_duration = ScenarioSpec("bond-3", "CN_BOND", "bond_duration", 100.0, 25.0, "bp", duration=-1.0, cost_bps=0, as_of="2026-09-09", evidence_refs=("fixture:yield",))
    assert evaluate_scenario(negative_duration).status == "UNESTIMATED"
