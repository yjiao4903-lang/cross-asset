import pandas as pd
import yaml

from cross_asset.backtest.returns import AssetReturnSpec
from cross_asset.research.execution_timing import (
    annotate_research_execution_timing,
    research_execution_timing_summary,
)
from cross_asset.research.model_config import (
    load_research_asset_market_map,
    load_research_model_config,
)


def _frame():
    return pd.DataFrame(
        [
            {
                "fold": 1,
                "benchmark": "FULL_MODEL",
                "decision_date": "2026-09-04T12:00:00Z",
                "gross_return": 0.01,
            },
            {
                "fold": 1,
                "benchmark": "FULL_MODEL",
                "decision_date": "2026-09-11T12:00:00Z",
                "gross_return": None,
            },
        ]
    )


def _specs():
    return {
        "A": AssetReturnSpec("A", kind="price"),
        "CASH": AssetReturnSpec(None, kind="cash"),
    }


def _calendar(tmp_path):
    path = tmp_path / "calendars.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "calendars": {
                    "CN": {
                        "calendar_id": "CN_TEST",
                        "capability_status": "VERIFIED",
                        "timezone": "Asia/Shanghai",
                        "source": "fixture",
                        "source_version": "1",
                        "version": "fixture-v1",
                        "regular_close": "15:00",
                        "verified": True,
                        "evidence": ["fixture"],
                        "reviewer": "test",
                        "approved_at": "2026-01-01T00:00:00+08:00",
                        "covered_years": [2026],
                        "holidays": [],
                        "early_closes": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def test_research_annotation_blocks_missing_mapping_and_preserves_returns():
    original = _frame()
    annotated = annotate_research_execution_timing(original, _specs(), {})

    assert annotated.loc[0, "gross_return"] == original.loc[0, "gross_return"]
    assert annotated.loc[0, "execution_timing_status"] == "BLOCKED"
    assert annotated.loc[0, "execution_timing"]["blockers"] == ["A:market_mapping_missing"]
    assert annotated.loc[1, "execution_timing_status"] == "NOT_APPLICABLE"
    assert annotated.loc[1, "execution_timing"]["reason"] == "terminal_no_trade"
    summary = research_execution_timing_summary(annotated)
    assert summary["status"] == "BLOCKED"
    assert summary["performance_semantics"] == "research_proxy_not_investor_realizable"


def test_research_annotation_can_resolve_explicit_market_but_remains_research_proxy(tmp_path):
    annotated = annotate_research_execution_timing(
        _frame(),
        _specs(),
        {"A": "CN"},
        calendar_config=_calendar(tmp_path),
    )

    assert annotated.loc[0, "execution_timing_status"] == "RESOLVED"
    assert annotated.loc[0, "execution_timing"]["by_asset"]["A"]["execution_price_at"] is not None
    assert annotated.loc[1, "execution_timing_status"] == "NOT_APPLICABLE"
    summary = research_execution_timing_summary(annotated)
    assert summary["status"] == "RESOLVED"
    assert summary["return_timing_basis"] == "decision_to_next_decision_research_proxy"
    assert summary["performance_semantics"] == "research_proxy_not_investor_realizable"


def test_stitched_terminal_scope_uses_global_benchmark_endpoint():
    frame = pd.DataFrame(
        [
            {"fold": 1, "benchmark": "FULL_MODEL", "decision_date": "2026-09-04T12:00:00Z"},
            {"fold": 1, "benchmark": "FULL_MODEL", "decision_date": "2026-09-11T12:00:00Z"},
            {"fold": 2, "benchmark": "FULL_MODEL", "decision_date": "2026-09-11T12:00:00Z"},
            {"fold": 2, "benchmark": "FULL_MODEL", "decision_date": "2026-09-18T12:00:00Z"},
        ]
    )
    annotated = annotate_research_execution_timing(
        frame,
        _specs(),
        {},
        terminal_group_columns=("benchmark",),
    )

    assert list(annotated["execution_timing_status"]) == [
        "BLOCKED",
        "BLOCKED",
        "BLOCKED",
        "NOT_APPLICABLE",
    ]
    assert annotated.iloc[-1]["execution_timing"]["reason"] == "terminal_no_trade"


def test_research_universe_market_metadata_is_explicit_and_not_part_of_return_spec(tmp_path):
    universe = tmp_path / "universe.yml"
    allocation = tmp_path / "allocation.yml"
    macro = tmp_path / "macro.yml"
    universe.write_text(
        yaml.safe_dump(
            {
                "assets": {
                    "A": {"series_id": "A", "kind": "price", "market": "CN"},
                    "CASH": {"series_id": None, "kind": "cash"},
                }
            }
        ),
        encoding="utf-8",
    )
    allocation.write_text(
        yaml.safe_dump(
            {
                "strategic_weights": {"A": 0.5, "CASH": 0.5},
                "asset_signal_map": {"A": {}, "CASH": {}},
                "component_weights": {"trend": 1.0},
            }
        ),
        encoding="utf-8",
    )
    macro.write_text(yaml.safe_dump({}), encoding="utf-8")

    market_map = load_research_asset_market_map(universe)
    config = load_research_model_config(
        universe_path=universe,
        allocation_path=allocation,
        macro_path=macro,
    )

    assert market_map == {"A": "CN"}
    assert config.return_specs["A"] == AssetReturnSpec("A", kind="price")
    assert config.return_specs["CASH"] == AssetReturnSpec(None, kind="cash")
