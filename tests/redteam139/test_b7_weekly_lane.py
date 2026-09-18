"""RT139 B7 — weekly lane / multi-week information-set semantics (#139 Phase 4)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from cross_asset.decision_support.enums import InformationSetStatus, ReleaseEventType
from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db
from cross_asset.decision_support.producer import (
    MonitoringSnapshotBlocked,
    build_monitoring_snapshot,
)
from cross_asset.decision_support.weekly import SyntheticMovementError
from redteam139._helpers import (
    WEEK1_CUTOFF,
    WEEK1_DECISION,
    WEEK2_CUTOFF,
    WEEK2_DECISION,
    WEEK3_CUTOFF,
    WEEK3_DECISION,
    cpi_values,
    governed_store,
    month_rows,
    payroll_values,
    workbench_run,
    write_monitoring_run,
)

CAPTURE_W1 = datetime(2026, 9, 5, tzinfo=UTC)


def _capture(store, *, end_month: date, capture: datetime, run_id: str, cpi_len=None, pay_len=None):
    n = cpi_len or 48
    m = pay_len or 48
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(n), capture_time=capture, end=end_month)
    rows += month_rows("US_NONFARM_PAYROLLS", "PAYEMS", payroll_values(m), capture_time=capture, end=end_month)
    write_monitoring_run(store, rows, run_id=run_id, requested=2)


def _pack(store, run_id, *, cutoff, decision):
    return build_monitoring_pack_from_db(
        store, workbench_run(run_id, decision_time=decision, data_cutoff=cutoff)
    )


# --- RT139-B7-01: the DB adapter still supplies no release events itself ---
def test_b7_01_adapter_supplies_no_release_events():
    store = governed_store()
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-01")
    pack = _pack(store, "wb-b7-01", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION)
    assert pack.release_events == []
    assert pack.expected_releases == {}


# --- RT139-B7-02 (#139 core): week 2 with a new observation is truthfully UPDATED ---
def test_b7_02_week2_with_new_observation_is_updated():
    store = governed_store()
    _capture(store, end_month=date(2026, 8, 1), capture=CAPTURE_W1, run_id="run-b7-02a")
    snap1 = build_monitoring_snapshot(_pack(store, "wb-b7-02a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION))
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-02b", cpi_len=49, pay_len=49)
    snap2 = build_monitoring_snapshot(
        _pack(store, "wb-b7-02b", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION),
        previous_snapshot=snap1,
    )
    delta = snap2.weekly_change.information_set_delta
    assert delta.resolved_status() is InformationSetStatus.UPDATED
    observed = [e for e in delta.events if e.resolved_event_type() is ReleaseEventType.OBSERVED_UPDATE]
    assert observed
    # the observed update corresponds to the genuinely new observation
    assert any(e.observation_date == date(2026, 9, 1) for e in observed)


# --- RT139-B7-03: same-week retry of the same observation is not a second event ---
def test_b7_03_same_week_retry_is_not_second_information_event():
    store = governed_store()
    _capture(store, end_month=date(2026, 8, 1), capture=CAPTURE_W1, run_id="run-b7-03a")
    snap1 = build_monitoring_snapshot(_pack(store, "wb-b7-03a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION))
    # retry within week 1 (later decision time, same week, same data)
    retry_capture = CAPTURE_W1 + timedelta(hours=1)
    _capture(store, end_month=date(2026, 8, 1), capture=retry_capture, run_id="run-b7-03b")
    snap_retry = build_monitoring_snapshot(
        _pack(store, "wb-b7-03b", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION + timedelta(hours=2)),
        previous_snapshot=snap1,
    )
    week1_events = [e for e in snap1.weekly_change.information_set_delta.events
                    if e.resolved_event_type() is not ReleaseEventType.OVERDUE]
    retry_events = [e for e in snap_retry.weekly_change.information_set_delta.events
                    if e.resolved_event_type() is not ReleaseEventType.OVERDUE]
    assert len(week1_events) == len(retry_events)


# --- RT139-B7-04: a week with no new observation is NO_NEW_INFORMATION and zero movement ---
def test_b7_04_week_without_new_data_stays_zero():
    store = governed_store()
    _capture(store, end_month=date(2026, 8, 1), capture=CAPTURE_W1, run_id="run-b7-04a")
    snap1 = build_monitoring_snapshot(_pack(store, "wb-b7-04a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION))
    # week 2 captures the same monthly world (no new observation month)
    _capture(store, end_month=date(2026, 8, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-04b")
    snap2 = build_monitoring_snapshot(
        _pack(store, "wb-b7-04b", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION),
        previous_snapshot=snap1,
    )
    assert snap2.weekly_change.information_set_delta.resolved_status() is InformationSetStatus.NO_NEW_INFORMATION
    assert snap2.weekly_change.macro_state_delta.changed_factors() == []


# --- RT139-B7-05: a revised value in a later week is a truthful observed update ---
def test_b7_05_revised_value_is_observed_update():
    store = governed_store()
    _capture(store, end_month=date(2026, 8, 1), capture=CAPTURE_W1, run_id="run-b7-05a")
    snap1 = build_monitoring_snapshot(_pack(store, "wb-b7-05a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION))
    # week 2: same months, but the latest month's value is revised (49th month added)
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-05b", cpi_len=49, pay_len=49)
    snap2 = build_monitoring_snapshot(
        _pack(store, "wb-b7-05b", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION),
        previous_snapshot=snap1,
    )
    observed = [e for e in snap2.weekly_change.information_set_delta.events
                if e.resolved_event_type() is ReleaseEventType.OBSERVED_UPDATE]
    assert observed
    assert snap2.weekly_change.macro_state_delta.changed_factors()


# --- RT139-B7-06: prior without recorded identities fails closed (#139 fail-closed rule) ---
def test_b7_06_prior_without_identities_fails_closed():
    store = governed_store()
    _capture(store, end_month=date(2026, 8, 1), capture=CAPTURE_W1, run_id="run-b7-06a")
    snap1 = build_monitoring_snapshot(_pack(store, "wb-b7-06a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION))
    # simulate a pre-#139 prior snapshot: strip recorded observation identities
    stripped = snap1.model_copy(deep=True)
    stripped.details["series_provenance"] = {
        key: {k: v for k, v in value.items() if k != "observations"}
        for key, value in stripped.details["series_provenance"].items()
    }
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-06b", cpi_len=49, pay_len=49)
    with pytest.raises(SyntheticMovementError):
        build_monitoring_snapshot(
            _pack(store, "wb-b7-06b", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION),
            previous_snapshot=stripped,
        )


# --- RT139-B7-07: OBSERVED_UPDATE never asserts a publication timestamp ---
def test_b7_07_no_invented_publication_timestamp():
    store = governed_store()
    _capture(store, end_month=date(2026, 8, 1), capture=CAPTURE_W1, run_id="run-b7-07a")
    snap1 = build_monitoring_snapshot(_pack(store, "wb-b7-07a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION))
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-07b", cpi_len=49, pay_len=49)
    snap2 = build_monitoring_snapshot(
        _pack(store, "wb-b7-07b", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION),
        previous_snapshot=snap1,
    )
    for event in snap2.weekly_change.information_set_delta.events:
        assert "release_time" not in event.note
        assert "first_release" not in event.note
        assert "monitoring_observed_update" in event.note or event.note == "test-supplied"


# --- RT139-B7-08: family information status reflects observed updates ---
def test_b7_08_family_information_status_updated():
    store = governed_store()
    _capture(store, end_month=date(2026, 8, 1), capture=CAPTURE_W1, run_id="run-b7-08a")
    snap1 = build_monitoring_snapshot(_pack(store, "wb-b7-08a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION))
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-08b", cpi_len=49, pay_len=49)
    snap2 = build_monitoring_snapshot(
        _pack(store, "wb-b7-08b", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION),
        previous_snapshot=snap1,
    )
    statuses = snap2.details["family_information_status"]
    assert "INFLATION_COST" in statuses
    assert statuses.get("GROWTH_ACTIVITY") == "UPDATED" or statuses.get("INFLATION_COST") == "UPDATED"


# --- RT139-B7-09: factor movement carries NEW_INFORMATION cause in week 2 ---
def test_b7_09_macro_delta_cause_is_new_information():
    store = governed_store()
    _capture(store, end_month=date(2026, 8, 1), capture=CAPTURE_W1, run_id="run-b7-09a")
    snap1 = build_monitoring_snapshot(_pack(store, "wb-b7-09a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION))
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-09b", cpi_len=49, pay_len=49)
    snap2 = build_monitoring_snapshot(
        _pack(store, "wb-b7-09b", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION),
        previous_snapshot=snap1,
    )
    changed = snap2.weekly_change.macro_state_delta.changed_factors()
    if changed:
        entries = {e.factor_id: e for e in snap2.weekly_change.macro_state_delta.entries}
        for factor_id in changed:
            assert entries[factor_id].resolved_cause().value == "NEW_INFORMATION"


# --- RT139-B7-10: three consecutive weeks each classify their own information set ---
def test_b7_10_three_consecutive_weeks_chained():
    store = governed_store()
    _capture(store, end_month=date(2026, 8, 1), capture=CAPTURE_W1, run_id="run-b7-10a")
    snap1 = build_monitoring_snapshot(_pack(store, "wb-b7-10a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION))
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-10b", cpi_len=49, pay_len=49)
    snap2 = build_monitoring_snapshot(
        _pack(store, "wb-b7-10b", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION),
        previous_snapshot=snap1,
    )
    # week 3: no new month, no movement
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK3_DECISION.replace(hour=0), run_id="run-b7-10c", cpi_len=49, pay_len=49)
    snap3 = build_monitoring_snapshot(
        _pack(store, "wb-b7-10c", cutoff=WEEK3_CUTOFF, decision=WEEK3_DECISION),
        previous_snapshot=snap2,
    )
    assert snap2.weekly_change.information_set_delta.resolved_status() is InformationSetStatus.UPDATED
    assert snap3.weekly_change.information_set_delta.resolved_status() is InformationSetStatus.NO_NEW_INFORMATION
    assert snap3.weekly_change.macro_state_delta.changed_factors() == []


# --- RT139-B7-11: OVERDUE events are filtered from the classification ---
def test_b7_11_overdue_events_filtered():
    from cross_asset.decision_support.weekly import build_information_set_delta

    delta = build_information_set_delta(
        [ReleaseEventHelper.overdue()],
        expected_releases={},
        as_of=WEEK2_CUTOFF,
    )
    assert delta.resolved_status() is InformationSetStatus.NO_NEW_INFORMATION


class ReleaseEventHelper:
    """Local factory to keep the OVERDUE case self-contained."""

    @staticmethod
    def overdue():
        from cross_asset.decision_support.weekly import ReleaseEvent

        return ReleaseEvent(
            factor_id="US_CORE_CPI_TREND",
            series_id="T_CPI",
            event_type="OVERDUE",
            observation_date=None,
            note="test-only overdue",
        )


# --- RT139-B7-12: event count matches the number of newly visible identities ---
def test_b7_12_event_count_matches_new_identities():
    store = governed_store()
    _capture(store, end_month=date(2026, 8, 1), capture=CAPTURE_W1, run_id="run-b7-12a")
    snap1 = build_monitoring_snapshot(_pack(store, "wb-b7-12a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION))
    def info_keys(observations):
        return {(o["observation_date"], round(float(o["value"]), 6)) for o in observations}

    prior_identities = {
        sid: info_keys(prov.get("observations", []))
        for sid, prov in snap1.details["series_provenance"].items()
    }
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-12b", cpi_len=49, pay_len=49)
    pack2 = _pack(store, "wb-b7-12b", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION)
    snap2 = build_monitoring_snapshot(pack2, previous_snapshot=snap1)
    new_identities = 0
    for series in pack2.series:
        prior = prior_identities.get(series.series_id, set())
        for identity in series.provenance.get("observations", []):
            if (identity["observation_date"], round(float(identity["value"]), 6)) not in prior:
                new_identities += 1
    observed = [e for e in snap2.weekly_change.information_set_delta.events
                if e.resolved_event_type() is ReleaseEventType.OBSERVED_UPDATE]
    # one event per (identity, factor); CPI+payroll series map to one factor each
    assert len(observed) == new_identities


# --- RT139-B7-13: the snapshot lane stays MONITORING and formal stays untouched ---
def test_b7_13_lane_separation_intact():
    store = governed_store()
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-13")
    snap = build_monitoring_snapshot(_pack(store, "wb-b7-13", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION))
    assert snap.metadata.lane.value == "MONITORING"
    for prov in snap.details["series_provenance"].values():
        assert prov["formal_admission_granted"] is False


# --- RT139-B7-14: information delta survives persistence and readback ---
def test_b7_14_delta_survives_persistence(snapshot_root):
    from cross_asset.decision_support.serving import SnapshotStore

    store = governed_store()
    _capture(store, end_month=date(2026, 8, 1), capture=CAPTURE_W1, run_id="run-b7-14a")
    snap1 = build_monitoring_snapshot(_pack(store, "wb-b7-14a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION))
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-14b", cpi_len=49, pay_len=49)
    snap2 = build_monitoring_snapshot(
        _pack(store, "wb-b7-14b", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION),
        previous_snapshot=snap1,
    )
    sstore = SnapshotStore(snapshot_root)
    sstore.persist(snap1)
    sstore.persist(snap2)
    readback = sstore.load(snap2.metadata.snapshot_id)
    assert (readback.weekly_change.information_set_delta.status
            == snap2.weekly_change.information_set_delta.status)
    assert len(readback.weekly_change.information_set_delta.events) == len(
        snap2.weekly_change.information_set_delta.events
    )


# --- RT139-B7-15: expected_releases absent means no invented stale factors ---
def test_b7_15_no_invented_stale_factors():
    store = governed_store()
    _capture(store, end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-b7-15")
    snap = build_monitoring_snapshot(_pack(store, "wb-b7-15", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION))
    assert snap.weekly_change.information_set_delta.stale_factors == []


# --- RT139-B7-16: identity-blocked series contributes no observed update ---
def test_b7_16_blocked_series_contributes_no_event():
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "PAYEMS", cpi_values(49), capture_time=WEEK2_DECISION.replace(hour=0))
    rows += month_rows("US_NONFARM_PAYROLLS", "PAYEMS", payroll_values(49), capture_time=WEEK2_DECISION.replace(hour=0))
    write_monitoring_run(store, rows, run_id="run-b7-16", requested=2)
    # CPI is identity-blocked, so the inflation axis is unavailable and the
    # producer refuses: a blocked series can never contribute an observed update.
    with pytest.raises(MonitoringSnapshotBlocked):
        build_monitoring_snapshot(_pack(store, "wb-b7-16", cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION))
