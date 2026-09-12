from pathlib import Path

from cross_asset.operations.workbench_run import (
    WorkbenchRun,
    apply_frozen_from_previous_valid,
    blocked_run,
    component_view,
    from_pipeline_payload,
    load_formal_previous_valid,
    load_run,
    persist_from_cli_payload,
    persist_run,
    record_formal_previous_valid,
)


def _live_success(run_id="wb-live-1") -> WorkbenchRun:
    return WorkbenchRun(
        run_id=run_id,
        run_kind="daily",
        source_mode="LIVE",
        status="SUCCESS",
        model_version="workbench_v0.1",
        config_identity="test",
        data_cutoff="2026-09-12T00:00:00+00:00",
        allocation_status="ACTIVE",
        weights={"CN_EQ": 0.4, "CASH": 0.6},
        components={"allocation": {"status": "AVAILABLE", "value": {"CN_EQ": 0.4}}},
        provenance={
            "formal_gate": True,
            "formal_query": "latest_formal_observations_asof",
            "required_usage_status": "LIVE_VERIFIED",
            "macro_source": "marco",
        },
    )


def test_persist_and_load_roundtrip(tmp_path: Path):
    saved = persist_run(_live_success(), tmp_path)
    loaded = load_run(saved.run_id, tmp_path)
    assert loaded.status == "SUCCESS"
    assert loaded.source_mode == "LIVE"
    assert loaded.weights["CN_EQ"] == 0.4
    assert Path(loaded.artifact_path).exists()


def test_fixture_run_cannot_seed_formal_previous_valid(tmp_path: Path):
    fixture = WorkbenchRun(
        run_id="wb-fix-1",
        run_kind="shadow",
        source_mode="FIXTURE",
        status="SUCCESS",
        model_version="workbench_v0.1",
        config_identity="test",
        data_cutoff=None,
        allocation_status="ACTIVE",
        weights={"CN_EQ": 1.0},
    )
    assert record_formal_previous_valid(fixture, tmp_path) is False
    assert load_formal_previous_valid(tmp_path) is None


def test_simulated_run_cannot_seed_formal_previous_valid(tmp_path: Path):
    simulated = WorkbenchRun(
        run_id="wb-sim-1",
        run_kind="shadow",
        source_mode="SIMULATED",
        status="SUCCESS",
        model_version="workbench_v0.1",
        config_identity="test",
        data_cutoff=None,
        allocation_status="ACTIVE",
        weights={"CASH": 1.0},
    )
    assert record_formal_previous_valid(simulated, tmp_path) is False
    persist_run(_live_success("wb-live-ok"), tmp_path)
    record_formal_previous_valid(_live_success("wb-live-ok"), tmp_path)
    assert load_formal_previous_valid(tmp_path)["run_id"] == "wb-live-ok"
    record_formal_previous_valid(simulated, tmp_path)
    assert load_formal_previous_valid(tmp_path)["run_id"] == "wb-live-ok"


def test_active_to_frozen_restores_only_formal_weights(tmp_path: Path):
    live = persist_run(_live_success(), tmp_path)
    assert record_formal_previous_valid(live, tmp_path)
    frozen = WorkbenchRun(
        run_id="wb-frozen",
        run_kind="daily",
        source_mode="LIVE",
        status="SUCCESS",
        model_version="workbench_v0.1",
        config_identity="test",
        data_cutoff="2026-09-13T00:00:00+00:00",
        allocation_status="ACTIVE",
        weights={"CN_EQ": 0.9, "CASH": 0.1},
        blockers=["stale_source"],
    )
    frozen = apply_frozen_from_previous_valid(frozen, tmp_path, reason="stale_source")
    assert frozen.allocation_status == "FROZEN"
    assert frozen.previous_valid_run_id == "wb-live-1"
    assert frozen.previous_valid_source == "formal"
    assert frozen.weights == {"CN_EQ": 0.4, "CASH": 0.6}
    assert frozen.status == "PARTIAL"


def test_frozen_without_previous_valid_is_data_blocked(tmp_path: Path):
    frozen = apply_frozen_from_previous_valid(
        blocked_run(run_kind="daily", source_mode="LIVE", blockers=["empty_db"]),
        tmp_path,
        reason="empty_db",
    )
    assert frozen.status == "DATA_BLOCKED"
    assert "previous_valid_formal_allocation_missing" in frozen.blockers
    assert frozen.weights is None


def test_missing_component_is_data_gap_not_zero():
    run = blocked_run(run_kind="daily", source_mode="LIVE", blockers=["empty_db"])
    view = component_view(run, "allocation")
    assert view["status"] == "UNAVAILABLE"
    assert view["reason"] == "data_gap"
    assert view["value"] is None


def test_persist_from_cli_payload_records_only_formal_marco_success(tmp_path: Path):
    unlabeled_live = persist_from_cli_payload(
        {
            "status": "SUCCESS",
            "allocation_status": "ACTIVE",
            "weights": {"CASH": 1.0},
            "data_cutoff": "2026-09-12",
        },
        run_kind="daily",
        source_mode="LIVE",
        root=tmp_path,
    )
    assert unlabeled_live.status == "SUCCESS"
    assert load_formal_previous_valid(tmp_path) is None
    blocked = persist_from_cli_payload(
        {
            "status": "DATA_BLOCKED",
            "allocation_status": "DATA_BLOCKED",
            "macro_source": "marco",
            "warnings": ["stale"],
        },
        run_kind="daily",
        source_mode="LIVE",
        root=tmp_path,
    )
    assert blocked.status == "DATA_BLOCKED"
    assert "previous_valid_formal_allocation_missing" in blocked.blockers
    assert load_formal_previous_valid(tmp_path) is None
    success = persist_from_cli_payload(
        {
            "status": "SUCCESS",
            "allocation_status": "ACTIVE",
            "weights": {"CASH": 1.0},
            "data_cutoff": "2026-09-12",
            "macro_source": "marco",
        },
        run_kind="daily",
        source_mode="LIVE",
        root=tmp_path,
    )
    assert success.status == "SUCCESS"
    assert success.provenance["formal_gate"] is True
    assert load_formal_previous_valid(tmp_path)["run_id"] == success.run_id
    frozen = persist_from_cli_payload(
        {
            "status": "DATA_BLOCKED",
            "allocation_status": "DATA_BLOCKED",
            "macro_source": "marco",
            "warnings": ["stale_source"],
        },
        run_kind="daily",
        source_mode="LIVE",
        root=tmp_path,
    )
    assert frozen.allocation_status == "FROZEN"
    assert frozen.previous_valid_run_id == success.run_id
    assert frozen.weights == {"CASH": 1.0}


def test_from_pipeline_payload_maps_degraded_and_keeps_source_mode():
    run = from_pipeline_payload(
        {
            "run_id": "sh-1",
            "status": "DEGRADED",
            "allocation_status": "FROZEN",
            "weights": {"CASH": 1.0},
            "warnings": ["stale"],
        },
        run_kind="shadow",
        source_mode="SIMULATED",
    )
    assert run.status == "PARTIAL"
    assert run.source_mode == "SIMULATED"
    assert run.weights == {"CASH": 1.0}
    assert record_formal_previous_valid(run, Path("unused")) is False
