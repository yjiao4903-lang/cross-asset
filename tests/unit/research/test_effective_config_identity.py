"""B01A regressions for formal research effective-config identity."""

from pathlib import Path

import yaml

from cross_asset.research.model_config import (
    load_research_model_config,
    research_effective_config_paths,
)
from cross_asset.research.storage import persist_research_plan
from cross_asset.storage import ProvenanceStore, config_hash, data_snapshot_id, init_db


def _accounting_copy(tmp_path: Path) -> Path:
    target = tmp_path / "return_accounting.yml"
    target.write_text(
        Path("config/return_accounting.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return target


def _plan() -> dict:
    return {
        "protocol_hash": "protocol-stable",
        "status": "READY_FOR_OOS",
        "holdout_sealed": True,
        "development_start": "2020-01-01T00:00:00+00:00",
        "development_end": "2025-12-31T00:00:00+00:00",
        "holdout_start": "2026-01-01T00:00:00+00:00",
        "holdout_end": "2026-12-31T00:00:00+00:00",
        "holdout_count": 1,
        "fold_count": 0,
        "blockers": [],
        "folds": [],
    }


def _rows() -> list[dict]:
    return [
        {
            "series_id": "TEST_SERIES",
            "source": "TEST",
            "source_series_id": "TEST_SERIES",
            "observation_date": "2026-01-01",
            "value": 1.0,
            "available_at": "2026-01-02T00:00:00+00:00",
            "vintage_date": "2026-01-02",
            "raw_hash": "raw-stable",
        }
    ]


def test_effective_config_identity_includes_consumed_return_accounting(tmp_path):
    accounting_path = _accounting_copy(tmp_path)
    paths = research_effective_config_paths(accounting_path=accounting_path)

    assert str(accounting_path) in paths
    first_hash = config_hash(paths)
    assert config_hash(paths) == first_hash

    first_model = load_research_model_config(accounting_path=accounting_path)
    assert first_model.return_specs["CN_BOND"].accounting["return_type"] == (
        "BOND_YIELD_DURATION_PROXY"
    )

    raw = yaml.safe_load(accounting_path.read_text(encoding="utf-8"))
    raw["assets"]["CN_BOND"]["return_type"] = "UNRESOLVED"
    accounting_path.write_text(
        yaml.safe_dump(raw, sort_keys=False),
        encoding="utf-8",
    )

    second_model = load_research_model_config(accounting_path=accounting_path)
    second_hash = config_hash(paths)

    assert second_model.return_specs["CN_BOND"].accounting["return_type"] == "UNRESOLVED"
    assert second_hash != first_hash


def test_same_rows_and_code_change_snapshot_and_run_only_when_effective_config_changes(
    tmp_path,
):
    accounting_path = _accounting_copy(tmp_path)
    paths = research_effective_config_paths(accounting_path=accounting_path)
    rows = _rows()
    plan = _plan()
    code = "same-code-version"

    first_hash = config_hash(paths)
    assert data_snapshot_id(rows) == data_snapshot_id(rows)

    store = init_db(":memory:")
    provenance = ProvenanceStore(store.conn)
    first_snapshot = provenance.create_snapshot(
        rows,
        data_cutoff="2026-01-02T00:00:00+00:00",
        config_hash_value=first_hash,
    )
    repeated_snapshot = provenance.create_snapshot(
        rows,
        data_cutoff="2026-01-02T00:00:00+00:00",
        config_hash_value=first_hash,
    )
    first_run = persist_research_plan(
        store,
        plan=plan,
        config_hash=first_hash,
        code_version=code,
        data_snapshot_id=first_snapshot,
    )
    repeated_run = persist_research_plan(
        store,
        plan=plan,
        config_hash=first_hash,
        code_version=code,
        data_snapshot_id=repeated_snapshot,
    )

    assert repeated_snapshot == first_snapshot
    assert repeated_run["research_run_id"] == first_run["research_run_id"]
    assert repeated_run["reused"] is True

    raw = yaml.safe_load(accounting_path.read_text(encoding="utf-8"))
    raw["assets"]["CN_BOND"]["return_type"] = "UNRESOLVED"
    accounting_path.write_text(
        yaml.safe_dump(raw, sort_keys=False),
        encoding="utf-8",
    )
    second_hash = config_hash(paths)
    assert second_hash != first_hash

    second_snapshot = provenance.create_snapshot(
        rows,
        data_cutoff="2026-01-02T00:00:00+00:00",
        config_hash_value=second_hash,
    )
    second_run = persist_research_plan(
        store,
        plan=plan,
        config_hash=second_hash,
        code_version=code,
        data_snapshot_id=second_snapshot,
    )

    assert second_snapshot != first_snapshot
    assert second_run["research_run_id"] != first_run["research_run_id"]

    snapshots = store.conn.execute(
        "SELECT snapshot_id,manifest_hash,config_hash FROM data_snapshots ORDER BY snapshot_id"
    ).fetchall()
    assert len(snapshots) == 2
    assert {row[2] for row in snapshots} == {first_hash, second_hash}
    assert len({row[1] for row in snapshots}) == 1
