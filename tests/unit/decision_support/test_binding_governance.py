from __future__ import annotations

import pytest
import yaml

from cross_asset.decision_support.binding import load_factor_bindings


def test_bound_binding_rejects_unknown_canonical_series(tmp_path):
    series_path = tmp_path / "series.yml"
    series_path.write_text(
        yaml.safe_dump({"series": [{"series_id": "US_EQ", "frequency": "daily", "unit": "index"}]}),
        encoding="utf-8",
    )
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "contract": "REAL_SNAPSHOT_V1",
                "bindings": [
                    {
                        "factor_id": "US_EQ_TREND_63D",
                        "canonical_series_ids": ["INVENTED_US_EQ"],
                        "transform": {"type": "TREND_63D"},
                        "monitoring": {"route": "CANONICAL_MONITORING_OBSERVATIONS", "status": "BOUND"},
                        "formal": {"route": "SANCTIONED_FORMAL_QUERY", "status": "BLOCKED"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ungoverned canonical series"):
        load_factor_bindings(bindings_path, series_path=series_path)


def test_current_registry_only_binds_governed_exact_semantic_inputs():
    registry = load_factor_bindings()
    bound = {
        binding.factor_id: tuple(binding.canonical_series_ids)
        for binding in registry.bindings
        if binding.monitoring.status == "BOUND"
    }

    assert bound == {
        "US_10Y_REAL_YIELD": ("US_REAL_10Y",),
        "US_EQ_TREND_63D": ("US_EQ",),
        "CN_EQ_TREND_63D": ("CN_EQ_LARGE",),
        "GOLD_TREND_63D": ("GOLD",),
        "COPPER_TREND_63D": ("COPPER",),
    }
    assert "US_PAYROLLS_TREND" not in bound
    assert "US_CORE_CPI_TREND" not in bound
    assert "USD_BROAD_MOMENTUM" not in bound
    assert "US_FIN_COND_TREND" not in bound
