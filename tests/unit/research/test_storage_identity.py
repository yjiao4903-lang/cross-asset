"""Regression tests for research-run and fold information-set identity."""

import pytest

from cross_asset.research.storage import persist_fold_result, persist_research_plan
from cross_asset.storage import init_db


def _plan(label: str) -> dict:
    return {
        "protocol_hash": "protocol-1",
        "status": "READY_FOR_OOS",
        "holdout_sealed": True,
        "development_start": "2020-01-01T00:00:00+00:00",
        "development_end": "2025-12-31T00:00:00+00:00",
        "holdout_start": "2026-01-01T00:00:00+00:00",
        "holdout_end": "2026-12-31T00:00:00+00:00",
        "holdout_count": 1,
        "fold_count": 1,
        "blockers": [],
        "folds": [{
            "fold": 0,
            "train_start": "2020-01-01T00:00:00+00:00",
            "train_end": "2024-12-31T00:00:00+00:00",
            "test_start": "2025-01-01T00:00:00+00:00",
            "test_end": "2025-12-31T00:00:00+00:00",
        }],
        "label": label,
    }


def test_snapshot_changes_create_distinct_runs_and_preserve_old_fold():
    store = init_db(":memory:")
    first = persist_research_plan(store, plan=_plan("one"), config_hash="cfg", code_version="code", data_snapshot_id="snap-1")
    second = persist_research_plan(store, plan=_plan("two"), config_hash="cfg", code_version="code", data_snapshot_id="snap-2")
    assert first["research_run_id"] != second["research_run_id"]
    persist_fold_result(store, research_run_id=first["research_run_id"], fold=0, benchmark="STATIC", metrics={"observations": 1}, data_snapshot_id="snap-1", status="COMPLETE")
    persist_fold_result(store, research_run_id=second["research_run_id"], fold=0, benchmark="STATIC", metrics={"observations": 2}, data_snapshot_id="snap-2", status="COMPLETE")
    old = store.conn.execute("SELECT data_snapshot_id,metrics_json FROM research_fold_results WHERE research_run_id=?", [first["research_run_id"]]).fetchone()
    assert old[0] == "snap-1" and '"observations": 1' in old[1]


def test_same_fold_key_rejects_information_set_or_metric_overwrite():
    store = init_db(":memory:")
    run = persist_research_plan(store, plan=_plan("one"), config_hash="cfg", code_version="code", data_snapshot_id="snap-1")["research_run_id"]
    persist_fold_result(store, research_run_id=run, fold=0, benchmark="STATIC", metrics={"observations": 1}, data_snapshot_id="snap-1", status="COMPLETE")
    with pytest.raises(ValueError, match="fold_result_conflict"):
        persist_fold_result(store, research_run_id=run, fold=0, benchmark="STATIC", metrics={"observations": 2}, data_snapshot_id="snap-2", status="COMPLETE")
