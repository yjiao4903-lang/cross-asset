"""B7 — weekly comparability / lane separation / frontend-consumption attacks.

#131/#132 (weekly comparability) and #135 (decision history) are adjacent WIP:
this module pins CURRENT MAIN behaviour and records gaps instead of duplicating
their implementation.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from cross_asset.decision_support.enums import InformationSetStatus, ReleaseEventType
from cross_asset.decision_support.producer import (
    build_monitoring_snapshot,
    score_monitoring_factors,
)
from cross_asset.decision_support.weekly import (
    ReleaseEvent,
    SyntheticMovementError,
    build_information_set_delta,
    build_macro_state_delta,
    build_market_move,
)
from cross_asset.decision_support.enums import MarketMetricClass
from cross_asset.operations.workbench_run import (
    WorkbenchRun,
    is_formal_previous_valid_eligible,
    load_formal_previous_valid,
    persist_run,
)

from _helpers import AS_OF, CAPTURE, DECISION, governed_store, mechanics_registry, month_rows, pack, workbench_run, write_monitoring_run

from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db


# --- B7-01: information-set status classification -------------------------------


def test_adv_b7_01_information_set_status_classification():
    event = ReleaseEvent(factor_id="A", event_type=ReleaseEventType.NEW_OBSERVATION)
    updated = build_information_set_delta([event], expected_releases={}, as_of=AS_OF)
    assert updated.status is InformationSetStatus.UPDATED

    overdue = build_information_set_delta(
        [], expected_releases={"A": AS_OF - timedelta(days=1)}, as_of=AS_OF
    )
    assert overdue.status is InformationSetStatus.OVERDUE_STALE
    assert overdue.stale_factors == ["A"]

    quiet = build_information_set_delta(
        [], expected_releases={"A": AS_OF + timedelta(days=1)}, as_of=AS_OF
    )
    assert quiet.status is InformationSetStatus.NO_NEW_INFORMATION
    assert quiet.stale_factors == []


# --- B7-02: synthetic macro movement is forbidden -------------------------------


def test_adv_b7_02_macro_movement_without_new_information_is_forbidden():
    with pytest.raises(SyntheticMovementError):
        build_macro_state_delta(
            {"A": 0.1},
            {"A": 0.2},
            information_status=InformationSetStatus.NO_NEW_INFORMATION,
            changed_by_release=set(),
        )
    with pytest.raises(SyntheticMovementError):
        build_macro_state_delta(
            {"A": 0.1},
            {"A": 0.2},
            information_status=InformationSetStatus.UPDATED,
            changed_by_release=set(),
        )
    delta = build_macro_state_delta(
        {"A": 0.1},
        {"A": 0.2},
        information_status=InformationSetStatus.UPDATED,
        changed_by_release={"A"},
    )
    assert delta.changed_factors() == ["A"]


# --- B7-03: same-week retry preserves the weekly-change surfaces ---------------


def test_adv_b7_03_same_week_retry_preserves_weekly_change_surfaces():
    registry = mechanics_registry()
    previous = build_monitoring_snapshot(pack(), registry=registry)
    retry = build_monitoring_snapshot(
        pack(decision=DECISION + timedelta(hours=2), run_id="wb-adv-b7-03"),
        previous_snapshot=previous,
        registry=registry,
    )
    assert (
        retry.weekly_change.information_set_delta.status
        == previous.weekly_change.information_set_delta.status
    )
    assert (
        retry.weekly_change.asset_view_delta.model_dump()
        == previous.weekly_change.asset_view_delta.model_dump()
    )


# --- B7-04: real DB path never populates release/market evidence ---------------


def test_adv_b7_04_real_db_adapter_supplies_no_release_or_market_evidence(
    governed_store,
):
    """LEDGER ADV-P1-01: build_monitoring_pack_from_db never populates
    release_events / expected_releases / market_moves / pulse, so every real
    monitoring snapshot reports NO_NEW_INFORMATION with zero market moves."""

    store = governed_store()
    try:
        payroll = [
            145000 + index * 145 + (index % 5) * 18 + (index // 12) * 23
            for index in range(48)
        ]
        cpi: list[float] = [270.0]
        rates = [0.0018, 0.0022, 0.0027, 0.0031, 0.0025, 0.0020]
        for index in range(1, 48):
            cpi.append(cpi[-1] * (1.0 + rates[index % 6]))
        rows = month_rows("US_NONFARM_PAYROLLS", "PAYEMS", payroll)
        rows += month_rows("US_CORE_CPI", "CPILFESL", cpi)
        write_monitoring_run(store, rows, run_id="monitoring-fred-adv-b7-04", requested=2)
        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-b7-04"))
        assert bundle.release_events == []
        assert bundle.expected_releases == {}
        assert bundle.market_moves == []
        assert bundle.pulse == []

        snapshot = build_monitoring_snapshot(bundle)
        assert (
            snapshot.weekly_change.information_set_delta.status
            is InformationSetStatus.NO_NEW_INFORMATION
        )
        assert snapshot.weekly_change.market_condition_delta.moves == []
        assert snapshot.cross_asset_pulse.entries == []
        assert "0 factor release event(s) and 0 market move(s)" in (
            snapshot.executive_brief.what_changed
        )
    finally:
        store.close()


# --- B7-05: market move unit semantics ------------------------------------------


@pytest.mark.parametrize(
    "metric_class,prior,current,expected_unit,expected_change",
    [
        (MarketMetricClass.YIELD, 4.0, 4.1, "BPS", 10.0),
        (MarketMetricClass.SPREAD, 3.0, 3.05, "BPS", 5.0),
        (MarketMetricClass.PRICE, 100.0, 101.0, "PCT", 1.0),
        (MarketMetricClass.FX, 7.0, 7.07, "PCT", 1.0),
        (MarketMetricClass.VOLATILITY, 18.0, 21.0, "POINT", 3.0),
    ],
)
def test_adv_b7_05_market_move_units(
    metric_class, prior, current, expected_unit, expected_change
):
    move = build_market_move("X", metric_class, prior, current)
    assert move.unit.value == expected_unit
    assert move.weekly_change == pytest.approx(expected_change)


def test_adv_b7_06_zero_prior_ratio_move_is_rejected():
    with pytest.raises(ValueError, match="zero prior value"):
        build_market_move("X", MarketMetricClass.PRICE, 0.0, 101.0)


# --- B7-07: late-created backfill must not displace the economic prior ----------


def test_adv_b7_07_late_created_backfill_does_not_displace_economic_prior(tmp_path):
    root = tmp_path / "runs"
    provenance = {
        "formal_gate": True,
        "formal_query": "latest_formal_observations_asof",
        "required_usage_status": "LIVE_VERIFIED",
    }

    def _run(run_id, decision_time, created_at, weights):
        return WorkbenchRun(
            run_id=run_id,
            run_kind="shadow",
            source_mode="LIVE",
            status="SUCCESS",
            model_version="v",
            config_identity="c",
            data_cutoff=decision_time[:10],
            decision_time=decision_time,
            allocation_status="ACTIVE",
            weights=weights,
            created_at=created_at,
            provenance=provenance,
        )

    persist_run(
        _run("wb-adv-newer", "2026-09-09T06:00:00+00:00", "2026-09-09T07:00:00+00:00", {"A": 0.9}),
        root,
    )
    persist_run(
        _run("wb-adv-older", "2026-09-02T06:00:00+00:00", "2026-09-20T00:00:00+00:00", {"A": 0.1}),
        root,
    )
    chosen = load_formal_previous_valid(root, before_decision_time="2026-09-10T00:00:00+00:00")
    assert chosen["run_id"] == "wb-adv-newer"


# --- B7-08: lane separation -----------------------------------------------------


def test_adv_b7_08_monitoring_run_cannot_claim_formal_previous_valid():
    provenance = {
        "formal_gate": True,
        "formal_query": "latest_formal_observations_asof",
        "required_usage_status": "LIVE_VERIFIED",
    }

    def _run(source_mode):
        return WorkbenchRun(
            run_id=f"wb-{source_mode.lower()}",
            run_kind="shadow",
            source_mode=source_mode,
            status="SUCCESS",
            model_version="v",
            config_identity="c",
            data_cutoff="2026-09-11",
            decision_time="2026-09-12T06:00:00+00:00",
            allocation_status="ACTIVE",
            weights={"A": 0.5},
            provenance=provenance,
        )

    assert is_formal_previous_valid_eligible(_run("LIVE")) is True
    assert is_formal_previous_valid_eligible(_run("FIXTURE")) is False
    assert is_formal_previous_valid_eligible(_run("SIMULATED")) is False


def test_adv_b7_09_fixture_run_cannot_claim_a_formal_previous_valid_source():
    run = WorkbenchRun(
        run_id="wb-fixture",
        run_kind="shadow",
        source_mode="FIXTURE",
        status="SUCCESS",
        model_version="v",
        config_identity="c",
        data_cutoff="2026-09-11",
        decision_time="2026-09-12T06:00:00+00:00",
        previous_valid_source="formal",
    )
    with pytest.raises(ValueError, match="cannot_claim_formal_previous_valid"):
        run.validate()


# --- B7-10: product bindings stay the accepted seven ----------------------------


def test_adv_b7_10_product_monitoring_bindings_are_exactly_the_accepted_seven():
    from cross_asset.decision_support.binding import load_factor_bindings

    registry = load_factor_bindings()
    bound = {
        binding.factor_id
        for binding in registry.bindings
        if binding.monitoring.status == "BOUND"
    }
    assert bound == {
        "US_PAYROLLS_TREND",
        "US_CORE_CPI_TREND",
        "US_10Y_REAL_YIELD",
        "US_EQ_TREND_63D",
        "CN_EQ_TREND_63D",
        "GOLD_TREND_63D",
        "COPPER_TREND_63D",
    }
    assert all(binding.formal.status == "BLOCKED" for binding in registry.bindings)


# --- B7-11: frontend normal path is API-first and fails visibly -----------------


def test_adv_b7_11_frontend_normal_path_cannot_fall_back_to_demo_fixtures():
    loader = open("frontend/src/snapshot/loader.js", encoding="utf-8").read()
    app = open("frontend/src/App.jsx", encoding="utf-8").read()
    assert "MODE === 'test' ? 'demo' : 'api'" in loader
    assert "Never substitute a golden/demo fixture for a failed API" in app
    assert "setBundle(null)" in app
    assert "setLoadError(error)" in app


# --- B7-12: weekly comparability hardening is adjacent WIP ----------------------


def test_adv_b7_12_weekly_comparability_gate_is_owned_by_131_132():
    """GAP: #131/#132 harden weekly semantic comparability on
    research/weekly_core.py. This window pins current main and does not
    duplicate or pre-empt that authority."""

    from cross_asset.research import weekly_core

    assert hasattr(weekly_core, "build_fact_table")
    assert not hasattr(weekly_core, "source_semantic_gate")
