from pathlib import Path

import yaml

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


def _allocation_config() -> dict:
    return yaml.safe_load(Path("config/allocation.yml").read_text(encoding="utf-8"))


def _strategic_weights() -> dict[str, float]:
    return {
        key: float(value)
        for key, value in _allocation_config()["strategic_weights"].items()
    }


def _live_success(
    run_id="wb-live-1",
    *,
    decision_time="2026-09-12",
    created_at="",
    weights=None,
) -> WorkbenchRun:
    return WorkbenchRun(
        run_id=run_id,
        run_kind="daily",
        source_mode="LIVE",
        status="SUCCESS",
        model_version="workbench_v0.1",
        config_identity="test",
        data_cutoff="2026-09-12T00:00:00+00:00",
        decision_time=decision_time,
        allocation_status="ACTIVE",
        weights=dict(weights or _strategic_weights()),
        components={
            "allocation": {
                "status": "AVAILABLE",
                "value": dict(weights or _strategic_weights()),
            }
        },
        provenance={
            "formal_gate": True,
            "formal_query": "latest_formal_observations_asof",
            "required_usage_status": "LIVE_VERIFIED",
            "macro_source": "marco",
        },
        created_at=created_at,
    )


def test_persist_and_load_roundtrip(tmp_path: Path):
    saved = persist_run(_live_success(), tmp_path)
    loaded = load_run(saved.run_id, tmp_path)
    assert loaded.status == "SUCCESS"
    assert loaded.source_mode == "LIVE"
    assert loaded.decision_time == "2026-09-12"
    assert loaded.weights == _strategic_weights()
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
        decision_time="2026-09-12",
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
        decision_time="2026-09-13",
        allocation_status="ACTIVE",
        weights={"CASH": 1.0},
    )
    assert record_formal_previous_valid(simulated, tmp_path) is False
    assert record_formal_previous_valid(
        _live_success("wb-live-ok", decision_time="2026-09-12"), tmp_path
    )
    assert load_formal_previous_valid(tmp_path)["run_id"] == "wb-live-ok"
    record_formal_previous_valid(simulated, tmp_path)
    assert load_formal_previous_valid(tmp_path)["run_id"] == "wb-live-ok"


def test_previous_valid_uses_decision_time_then_deterministic_retry(tmp_path: Path):
    weights = _strategic_weights()
    assert record_formal_previous_valid(
        _live_success(
            "older-backfill-created-last",
            decision_time="2026-09-10",
            created_at="2026-09-15T12:00:00+00:00",
            weights=weights,
        ),
        tmp_path,
    )
    assert record_formal_previous_valid(
        _live_success(
            "same-decision-early",
            decision_time="2026-09-11",
            created_at="2026-09-12T09:00:00+00:00",
            weights=weights,
        ),
        tmp_path,
    )
    assert record_formal_previous_valid(
        _live_success(
            "same-decision-retry",
            decision_time="2026-09-11",
            created_at="2026-09-12T10:00:00+00:00",
            weights=weights,
        ),
        tmp_path,
    )

    selected = load_formal_previous_valid(
        tmp_path, before_decision_time="2026-09-12"
    )
    assert selected["run_id"] == "same-decision-retry"
    assert selected["decision_time"] == "2026-09-11"


def test_active_to_frozen_reuses_current_allocation_authority(tmp_path: Path):
    previous_weights = _strategic_weights()
    previous_weights["CN_EQ"] += 0.05
    previous_weights["CASH"] -= 0.05
    assert record_formal_previous_valid(
        _live_success(
            "wb-live-1",
            decision_time="2026-09-12",
            weights=previous_weights,
        ),
        tmp_path,
    )
    frozen = WorkbenchRun(
        run_id="wb-frozen",
        run_kind="daily",
        source_mode="LIVE",
        status="SUCCESS",
        model_version="workbench_v0.1",
        config_identity="test",
        data_cutoff="2026-09-13T00:00:00+00:00",
        decision_time="2026-09-13",
        allocation_status="ACTIVE",
        weights={"CN_EQ": 0.9, "CASH": 0.1},
        blockers=["stale_source"],
    )
    frozen = apply_frozen_from_previous_valid(
        frozen, tmp_path, reason="stale_source"
    )
    assert frozen.allocation_status == "FROZEN"
    assert frozen.previous_valid_run_id == "wb-live-1"
    assert frozen.previous_valid_source == "formal"
    assert frozen.weights == previous_weights
    assert frozen.provenance["frozen_projection"]["authority"].endswith(
        "engines.allocation.allocate"
    )
    assert frozen.status == "PARTIAL"


def test_frozen_projects_prior_outside_current_bounds(tmp_path: Path):
    previous_weights = _strategic_weights()
    previous_weights.update(
        {
            "CN_EQ": 0.50,
            "US_EQ": 0.10,
            "CN_BOND": 0.10,
            "CASH": 0.05,
        }
    )
    assert abs(sum(previous_weights.values()) - 1.0) < 1e-12
    assert record_formal_previous_valid(
        _live_success(
            "wb-outside-bounds",
            decision_time="2026-09-12",
            weights=previous_weights,
        ),
        tmp_path,
    )
    frozen = blocked_run(
        run_kind="daily",
        source_mode="LIVE",
        blockers=["stale_source"],
        decision_time="2026-09-13",
    )
    apply_frozen_from_previous_valid(frozen, tmp_path, reason="stale_source")

    cfg = _allocation_config()
    tilt = float(cfg["constraints"]["max_tactical_tilt"])
    cn_upper = min(
        float(cfg["constraints"]["max_weight"]),
        float(cfg["strategic_weights"]["CN_EQ"]) + tilt,
    )
    assert frozen.weights["CN_EQ"] <= cn_upper + 1e-12
    assert abs(sum(frozen.weights.values()) - 1.0) < 1e-9
    assert (
        "previous_valid_allocation_outside_current_constraints_projected"
        in frozen.warnings
    )


def test_frozen_mismatched_previous_universe_falls_back_to_current_universe(
    tmp_path: Path,
):
    assert record_formal_previous_valid(
        _live_success(
            "wb-old-universe",
            decision_time="2026-09-12",
            weights={"CN_EQ": 0.4, "CASH": 0.6},
        ),
        tmp_path,
    )
    frozen = blocked_run(
        run_kind="daily",
        source_mode="LIVE",
        blockers=["stale_source"],
        decision_time="2026-09-13",
    )
    apply_frozen_from_previous_valid(frozen, tmp_path, reason="stale_source")
    assert frozen.weights == _strategic_weights()
    assert (
        "previous_valid_allocation_keys_differ_from_current_universe"
        in frozen.warnings
    )


def test_frozen_without_previous_valid_is_data_blocked(tmp_path: Path):
    frozen = apply_frozen_from_previous_valid(
        blocked_run(
            run_kind="daily",
            source_mode="LIVE",
            blockers=["empty_db"],
            decision_time="2026-09-13",
        ),
        tmp_path,
        reason="empty_db",
    )
    assert frozen.status == "DATA_BLOCKED"
    assert "previous_valid_formal_allocation_missing" in frozen.blockers
    assert frozen.weights is None


def test_frozen_without_decision_time_fails_closed_even_with_prior(tmp_path: Path):
    assert record_formal_previous_valid(_live_success(), tmp_path)
    frozen = apply_frozen_from_previous_valid(
        blocked_run(
            run_kind="daily",
            source_mode="LIVE",
            blockers=["empty_db"],
        ),
        tmp_path,
        reason="empty_db",
    )
    assert frozen.status == "DATA_BLOCKED"
    assert "decision_time_missing_for_previous_valid_selection" in frozen.blockers
    assert frozen.previous_valid_run_id is None
    assert frozen.weights is None


def test_missing_component_is_data_gap_not_zero():
    run = blocked_run(
        run_kind="daily",
        source_mode="LIVE",
        blockers=["empty_db"],
        decision_time="2026-09-13",
    )
    view = component_view(run, "allocation")
    assert view["status"] == "UNAVAILABLE"
    assert view["reason"] == "data_gap"
    assert view["value"] is None


def test_persist_from_cli_payload_records_only_formal_marco_success(tmp_path: Path):
    unlabeled_live = persist_from_cli_payload(
        {
            "status": "SUCCESS",
            "allocation_status": "ACTIVE",
            "weights": _strategic_weights(),
            "data_cutoff": "2026-09-10",
            "as_of": "2026-09-10",
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
            "as_of": "2026-09-11",
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
            "weights": _strategic_weights(),
            "data_cutoff": "2026-09-12",
            "as_of": "2026-09-12",
            "macro_source": "marco",
        },
        run_kind="daily",
        source_mode="LIVE",
        root=tmp_path,
    )
    assert success.status == "SUCCESS"
    assert success.provenance["formal_gate"] is True
    assert success.decision_time == "2026-09-12"
    assert load_formal_previous_valid(tmp_path)["run_id"] == success.run_id
    frozen = persist_from_cli_payload(
        {
            "status": "DATA_BLOCKED",
            "allocation_status": "DATA_BLOCKED",
            "macro_source": "marco",
            "warnings": ["stale_source"],
            "as_of": "2026-09-13",
        },
        run_kind="daily",
        source_mode="LIVE",
        root=tmp_path,
    )
    assert frozen.allocation_status == "FROZEN"
    assert frozen.previous_valid_run_id == success.run_id
    assert frozen.weights == _strategic_weights()


def test_from_pipeline_payload_maps_degraded_and_keeps_source_mode():
    run = from_pipeline_payload(
        {
            "run_id": "sh-1",
            "status": "DEGRADED",
            "allocation_status": "FROZEN",
            "weights": {"CASH": 1.0},
            "warnings": ["stale"],
            "as_of": "2026-09-13",
        },
        run_kind="shadow",
        source_mode="SIMULATED",
    )
    assert run.status == "PARTIAL"
    assert run.source_mode == "SIMULATED"
    assert run.decision_time == "2026-09-13"
    assert run.weights == {"CASH": 1.0}
    assert record_formal_previous_valid(run, Path("unused")) is False
