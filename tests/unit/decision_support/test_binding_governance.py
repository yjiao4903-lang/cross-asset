from __future__ import annotations

import pytest
import yaml

from cross_asset.decision_support.binding import load_factor_bindings


def _write_series(path, *series_ids: str):
    path.write_text(
        yaml.safe_dump(
            {
                "series": [
                    {"series_id": series_id, "frequency": "daily", "unit": "test"}
                    for series_id in series_ids
                ]
            }
        ),
        encoding="utf-8",
    )


def _write_sources(path, *series_ids: str, semantic_equivalence: bool = True):
    path.write_text(
        yaml.safe_dump(
            {
                "mappings": [
                    {
                        "series_id": series_id,
                        "provider": "test",
                        "source_series_id": f"SRC_{series_id}",
                        "priority": 1,
                        "enabled": True,
                        "semantic_equivalence": semantic_equivalence,
                    }
                    for series_id in series_ids
                ]
            }
        ),
        encoding="utf-8",
    )


def _write_binding(path, *, factor_id: str, series_id: str, transform: str):
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "contract": "REAL_SNAPSHOT_V1",
                "bindings": [
                    {
                        "factor_id": factor_id,
                        "canonical_series_ids": [series_id],
                        "transform": {"type": transform},
                        "monitoring": {
                            "route": "CANONICAL_MONITORING_OBSERVATIONS",
                            "status": "BOUND",
                        },
                        "formal": {
                            "route": "SANCTIONED_FORMAL_QUERY",
                            "status": "BLOCKED",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_bound_binding_rejects_unknown_canonical_series(tmp_path):
    series_path = tmp_path / "series.yml"
    sources_path = tmp_path / "sources.yml"
    _write_series(series_path, "US_EQ")
    _write_sources(sources_path, "INVENTED_US_EQ")
    bindings_path = tmp_path / "bindings.yml"
    _write_binding(
        bindings_path,
        factor_id="US_EQ_TREND_63D",
        series_id="INVENTED_US_EQ",
        transform="TREND_63D",
    )

    with pytest.raises(ValueError, match="ungoverned canonical series"):
        load_factor_bindings(
            bindings_path,
            series_path=series_path,
            sources_path=sources_path,
        )


def test_bound_binding_rejects_non_equivalent_source_mapping(tmp_path):
    series_path = tmp_path / "series.yml"
    sources_path = tmp_path / "sources.yml"
    _write_series(series_path, "US_EQ")
    _write_sources(sources_path, "US_EQ", semantic_equivalence=False)
    bindings_path = tmp_path / "bindings.yml"
    _write_binding(
        bindings_path,
        factor_id="US_EQ_TREND_63D",
        series_id="US_EQ",
        transform="TREND_63D",
    )

    with pytest.raises(ValueError, match="semantically equivalent source mapping"):
        load_factor_bindings(
            bindings_path,
            series_path=series_path,
            sources_path=sources_path,
        )


def test_bound_binding_rejects_implemented_but_wrong_factor_transform(tmp_path):
    series_path = tmp_path / "series.yml"
    sources_path = tmp_path / "sources.yml"
    _write_series(series_path, "TEST_PAYROLL")
    _write_sources(sources_path, "TEST_PAYROLL")
    bindings_path = tmp_path / "bindings.yml"
    _write_binding(
        bindings_path,
        factor_id="US_PAYROLLS_TREND",
        series_id="TEST_PAYROLL",
        transform="CHANGE_CAUSAL_ZSCORE",
    )

    with pytest.raises(ValueError, match="violates V2 factor definition"):
        load_factor_bindings(
            bindings_path,
            series_path=series_path,
            sources_path=sources_path,
        )


def test_current_registry_only_binds_governed_exact_semantic_inputs():
    registry = load_factor_bindings()
    bound = {
        binding.factor_id: tuple(binding.canonical_series_ids)
        for binding in registry.bindings
        if binding.monitoring.status == "BOUND"
    }

    assert bound == {
        "US_PAYROLLS_TREND": ("US_NONFARM_PAYROLLS",),
        "US_CORE_CPI_TREND": ("US_CORE_CPI",),
        "US_10Y_REAL_YIELD": ("US_REAL_10Y",),
        "US_EQ_TREND_63D": ("US_EQ",),
        "CN_EQ_TREND_63D": ("CN_EQ_LARGE",),
        "GOLD_TREND_63D": ("GOLD",),
        "COPPER_TREND_63D": ("COPPER",),
    }
    assert "US_YIELD_CURVE_10Y2Y" not in bound
    assert "USD_BROAD_MOMENTUM" not in bound
    assert "US_FIN_COND_TREND" not in bound
