"""Regressions for formal per-decision PIT vintage selection."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd

from cross_asset.backtest.returns import AssetReturnSpec
from cross_asset.research import executor
from cross_asset.research.executor import ResearchModelConfig, execute_walk_forward
from cross_asset.storage import init_db, latest_formal_observations_asof
from cross_asset.storage.acceptance_registry import upsert_data_acceptance


def _store_with_vintages(*, second_quality: str = "ok"):
    store = init_db(":memory:")
    approved_at = datetime(2021, 1, 1, tzinfo=UTC)
    upsert_data_acceptance(
        store,
        {
            "series_id": "A",
            "provider": "srcA",
            "source_series_id": "A",
            "status": "PASS",
            "tech_gate": "PASS",
            "legal_gate": "PASS",
            "pit_gate": "PASS",
            "stability_gate": "PASS",
            "pit_grade": "B",
            "origin": "MANUAL",
            "permission_scope": "research",
            "semantic_equivalence": True,
            "manifest_hash": "manifest-a",
            "reviewer": "reviewer",
            "approved_at": approved_at,
            "evidence_json": "{}",
            "updated_at": approved_at,
            "usage_status": "RESEARCH_ADMISSIBLE",
        },
    )
    rows = [
        {
            "series_id": "A",
            "observation_date": date(2021, 12, 31),
            "available_at": datetime(2022, 1, 5, tzinfo=UTC),
            "value": 1.0,
            "source": "srcA",
            "source_series_id": "A",
            "vintage_date": date(2022, 1, 5),
            "ingested_at": datetime(2022, 1, 5, tzinfo=UTC),
            "quality": "ok",
            "raw_file": "v1.json",
        },
        {
            "series_id": "A",
            "observation_date": date(2021, 12, 31),
            "available_at": datetime(2022, 1, 20, tzinfo=UTC),
            "value": 2.0,
            "source": "srcA",
            "source_series_id": "A",
            "vintage_date": date(2022, 1, 20),
            "ingested_at": datetime(2022, 1, 20, tzinfo=UTC),
            "quality": second_quality,
            "raw_file": "v2.json",
        },
    ]
    store.insert_observations(rows, run_id=f"pit-vintages-{second_quality}")
    return store


def test_formal_query_selects_latest_vintage_visible_at_each_decision():
    store = _store_with_vintages()
    try:
        early = latest_formal_observations_asof(
            store.conn,
            datetime(2022, 1, 10, tzinfo=UTC),
            required_usage_status="RESEARCH_ADMISSIBLE",
            series_ids=["A"],
        )
        late = latest_formal_observations_asof(
            store.conn,
            datetime(2022, 2, 1, tzinfo=UTC),
            required_usage_status="RESEARCH_ADMISSIBLE",
            series_ids=["A"],
        )
    finally:
        store.close()

    assert early["value"].tolist() == [1.0]
    assert late["value"].tolist() == [2.0]


def test_formal_query_does_not_fall_back_when_newest_vintage_is_bad_quality():
    store = _store_with_vintages(second_quality="stale")
    try:
        early = latest_formal_observations_asof(
            store.conn,
            datetime(2022, 1, 10, tzinfo=UTC),
            required_usage_status="RESEARCH_ADMISSIBLE",
            series_ids=["A"],
        )
        late = latest_formal_observations_asof(
            store.conn,
            datetime(2022, 2, 1, tzinfo=UTC),
            required_usage_status="RESEARCH_ADMISSIBLE",
            series_ids=["A"],
        )
    finally:
        store.close()

    assert early["value"].tolist() == [1.0]
    assert late.empty


def test_executor_resolves_formal_vintage_at_each_historical_decision(monkeypatch):
    store = _store_with_vintages()
    captured: dict[pd.Timestamp, float | None] = {}

    class CaptureStrategy:
        last_status = "ACTIVE"

        def __call__(self, info, decision):
            values = info.loc[info["series_id"] == "A", "value"]
            captured[pd.Timestamp(decision)] = None if values.empty else float(values.iloc[-1])
            return {"A": 1.0}

    monkeypatch.setattr(executor, "_strategy", lambda _name, _config: CaptureStrategy())

    def fake_asset_returns(_observations, _weights, _decision, next_decision, *, specs):
        del specs
        return None if next_decision is None else {"A": 0.0}

    monkeypatch.setattr(executor, "portfolio_asset_returns", fake_asset_returns)

    decisions = pd.DatetimeIndex(
        [
            pd.Timestamp("2022-01-10T00:00:00Z"),
            pd.Timestamp("2022-02-01T00:00:00Z"),
            pd.Timestamp("2022-03-01T00:00:00Z"),
        ]
    )
    plan = {
        "status": "READY_FOR_OOS",
        "holdout_sealed": True,
        "development_count": 2,
        "folds": [
            {
                "fold": 0,
                "test_indices": [0, 1],
                "window_type": "expanding",
                "train_start": "2021-01-01T00:00:00Z",
                "train_end": "2022-01-09T00:00:00Z",
                "test_start": "2022-01-10T00:00:00Z",
                "test_end": "2022-02-01T00:00:00Z",
            }
        ],
    }
    protocol = SimpleNamespace(
        execution_blockers=(),
        required_usage_status="RESEARCH_ADMISSIBLE",
        benchmarks=("STATIC",),
    )
    model_config = ResearchModelConfig(
        assets=("A",),
        strategic_weights={"A": 1.0},
        return_specs={"A": AssetReturnSpec("A", kind="price")},
        asset_signal_map={"A": {"macro": None}},
        component_weights={"trend": 1.0},
        allocation_config={},
        macro_config={"series": {}, "dimensions": {}},
    )

    try:
        result = execute_walk_forward(
            store.conn,
            decision_dates=decisions,
            plan=plan,
            protocol=protocol,
            model_config=model_config,
        )
    finally:
        store.close()

    assert len(result) == 2
    assert captured[pd.Timestamp("2022-01-10T00:00:00Z")] == 1.0
    assert captured[pd.Timestamp("2022-02-01T00:00:00Z")] == 2.0
