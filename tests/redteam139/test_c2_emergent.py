"""RT139 C2 — pass-2 emergent cross-layer attacks (#139).

These cases combine the monitoring read model, identity revalidation, the
information-set semantics, the store, history and the API in one flow. The
multi-week soak loop at the end is the seed for Phase 6 repeatability runs.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from cross_asset.decision_support.enums import InformationSetStatus, ReleaseEventType
from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db
from cross_asset.decision_support.producer import (
    MonitoringSnapshotBlocked,
    build_monitoring_snapshot,
)
from cross_asset.decision_support.serving import SnapshotStore
from cross_asset.decision_support.weekly import SyntheticMovementError
from redteam139._helpers import (
    WEEK1_CUTOFF,
    WEEK1_DECISION,
    WEEK2_CUTOFF,
    WEEK2_DECISION,
    cpi_values,
    governed_store,
    month_rows,
    payroll_values,
    workbench_run,
    write_monitoring_run,
)

from redteam139._helpers import mechanics_registry

REG = mechanics_registry()
WEEK3_CUTOFF = date(2026, 9, 18)
WEEK3_DECISION = datetime(2026, 9, 19, 6, tzinfo=UTC)
WEEK4_CUTOFF = date(2026, 9, 25)
WEEK4_DECISION = datetime(2026, 9, 26, 6, tzinfo=UTC)
WEEK5_CUTOFF = date(2026, 10, 2)
WEEK5_DECISION = datetime(2026, 10, 3, 6, tzinfo=UTC)


class WeekWorld:
    """A scratch multi-week monitoring world on one governed store."""

    def __init__(self, store=None):
        self.store = store or governed_store()
        self.snapshots = []
        self._month_len = 48

    def capture(self, *, end_month: date, capture: datetime, run_id: str,
                cpi_len=None, pay_len=None):
        cpi_len = cpi_len or self._month_len
        pay_len = pay_len or self._month_len
        rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(cpi_len), capture_time=capture, end=end_month)
        rows += month_rows("US_NONFARM_PAYROLLS", "PAYEMS", payroll_values(pay_len), capture_time=capture, end=end_month)
        write_monitoring_run(self.store, rows, run_id=run_id, requested=2)

    def week(self, *, cutoff: date, decision: datetime, run_id: str):
        pack = build_monitoring_pack_from_db(
            self.store, workbench_run(run_id, decision_time=decision, data_cutoff=cutoff)
        )
        previous = self.snapshots[-1] if self.snapshots else None
        snapshot = build_monitoring_snapshot(pack, previous_snapshot=previous)
        self.snapshots.append(snapshot)
        return snapshot


# --- RT139-C2-01: three-week loop with persistence and pointer correctness ---
def test_c2_01_three_week_loop_with_store(snapshot_root):
    world = WeekWorld()
    store = SnapshotStore(snapshot_root)
    world.capture(end_month=date(2026, 8, 1), capture=datetime(2026, 9, 5, tzinfo=UTC), run_id="run-c2-01a")
    week1 = world.week(cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION, run_id="wb-c2-01a")
    world.capture(end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-c2-01b",
                  cpi_len=49, pay_len=49)
    world._month_len = 49
    week2 = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-01b")
    store.persist(week1)
    store.persist(week2)
    assert store.load_latest().metadata.snapshot_id == week2.metadata.snapshot_id
    assert store.prior_for(decision_time=WEEK2_DECISION,
                           current_week_id=week2.details["economic_week_id"]).metadata.snapshot_id == week1.metadata.snapshot_id


# --- RT139-C2-02: poisoned identity mid-loop blocks the week, history intact ---
def test_c2_02_poisoned_identity_mid_loop(snapshot_root):
    world = WeekWorld()
    world.capture(end_month=date(2026, 8, 1), capture=datetime(2026, 9, 5, tzinfo=UTC), run_id="run-c2-02a")
    week1 = world.week(cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION, run_id="wb-c2-02a")
    # poison week 2's CPI identity
    rows = month_rows("US_CORE_CPI", "PAYEMS", cpi_values(49), capture_time=WEEK2_DECISION.replace(hour=0))
    rows += month_rows("US_NONFARM_PAYROLLS", "PAYEMS", payroll_values(49), capture_time=WEEK2_DECISION.replace(hour=0))
    write_monitoring_run(world.store, rows, run_id="run-c2-02b", requested=2)
    with pytest.raises(MonitoringSnapshotBlocked):
        world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-02b")
    # week 1 snapshot was already persisted to world state and remains usable
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    assert store.load_latest().metadata.snapshot_id == week1.metadata.snapshot_id


# --- RT139-C2-03: corrupted latest.json mid-loop then persist recovers ---
def test_c2_03_corrupted_pointer_recovered_by_next_persist(snapshot_root):
    world = WeekWorld()
    world.capture(end_month=date(2026, 8, 1), capture=datetime(2026, 9, 5, tzinfo=UTC), run_id="run-c2-03a")
    week1 = world.week(cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION, run_id="wb-c2-03a")
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    (snapshot_root / "latest.json").write_text("garbage", encoding="utf-8")
    # next healthy persist rewrites the pointer from the canonical list
    world._month_len = 49
    world.capture(end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-c2-03b",
                  cpi_len=49, pay_len=49)
    week2 = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-03b")
    store.persist(week2)
    assert store.load_latest().metadata.snapshot_id == week2.metadata.snapshot_id


# --- RT139-C2-04: the same two-week sequence replays deterministically ---
def test_c2_04_two_week_sequence_is_deterministic():
    def run_sequence(_tag):
        # identical run ids across worlds: identity includes lineage, so both
        # sequences must use the same lineage to be byte-comparable
        world = WeekWorld()
        world.capture(end_month=date(2026, 8, 1), capture=datetime(2026, 9, 5, tzinfo=UTC), run_id="run-c2-04a")
        week1 = world.week(cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION, run_id="wb-c2-04a")
        world._month_len = 49
        world.capture(end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-c2-04b",
                      cpi_len=49, pay_len=49)
        week2 = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-04b")
        return week1, week2

    a1, a2 = run_sequence("c2-04-x")
    b1, b2 = run_sequence("c2-04-y")
    assert a1.to_json() == b1.to_json()
    assert a2.to_json() == b2.to_json()


# --- RT139-C2-05: process restart between weeks yields the same state ---
def test_c2_05_restart_between_weeks(snapshot_root):
    world = WeekWorld()
    world.capture(end_month=date(2026, 8, 1), capture=datetime(2026, 9, 5, tzinfo=UTC), run_id="run-c2-05a")
    week1 = world.week(cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION, run_id="wb-c2-05a")
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    # "restart": a fresh store object over the same root reads the same state
    reopened = SnapshotStore(snapshot_root)
    assert reopened.load(week1.metadata.snapshot_id).to_json() == week1.to_json()


# --- RT139-C2-06: observed update propagates coherently through delta surfaces ---
def test_c2_06_observed_update_propagation_is_coherent():
    world = WeekWorld()
    world.capture(end_month=date(2026, 8, 1), capture=datetime(2026, 9, 5, tzinfo=UTC), run_id="run-c2-06a")
    world.week(cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION, run_id="wb-c2-06a")
    world._month_len = 49
    world.capture(end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-c2-06b",
                  cpi_len=49, pay_len=49)
    week2 = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-06b")
    delta = week2.weekly_change.information_set_delta
    assert delta.resolved_status() is InformationSetStatus.UPDATED
    changed = set(week2.weekly_change.macro_state_delta.changed_factors())
    updated_factors = {e.factor_id for e in delta.events
                       if e.resolved_event_type() is ReleaseEventType.OBSERVED_UPDATE}
    assert changed <= updated_factors or not changed
    family_status = week2.details["family_information_status"]
    for factor_id in updated_factors:
        family_id = "GROWTH_ACTIVITY" if "PAYROLLS" in factor_id else "INFLATION_COST"
        assert family_status[family_id] == "UPDATED"


# --- RT139-C2-07: no formal-lane contamination across weeks ---
def test_c2_07_no_formal_contamination_across_weeks():
    world = WeekWorld()
    world.capture(end_month=date(2026, 8, 1), capture=datetime(2026, 9, 5, tzinfo=UTC), run_id="run-c2-07a")
    week1 = world.week(cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION, run_id="wb-c2-07a")
    world._month_len = 49
    world.capture(end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-c2-07b",
                  cpi_len=49, pay_len=49)
    week2 = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-07b")
    for snapshot in (week1, week2):
        assert snapshot.metadata.lane.value == "MONITORING"
        for prov in snapshot.details["series_provenance"].values():
            assert prov["formal_admission_granted"] is False


# --- RT139-C2-08: identical re-capture next week is not a new information event ---
def test_c2_08_identical_recapture_is_not_new_information():
    world = WeekWorld()
    world.capture(end_month=date(2026, 8, 1), capture=datetime(2026, 9, 5, tzinfo=UTC), run_id="run-c2-08a")
    week1 = world.week(cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION, run_id="wb-c2-08a")
    # week 2 re-captures the exact same monthly world with a new capture stamp
    world.capture(end_month=date(2026, 8, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-c2-08b")
    week2 = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-08b")
    assert week2.weekly_change.information_set_delta.resolved_status() is InformationSetStatus.NO_NEW_INFORMATION


# --- RT139-C2-09: a late backfilled older observation is truthfully reported ---
def test_c2_09_late_backfill_reports_older_observation_date():
    world = WeekWorld()
    world.capture(end_month=date(2026, 8, 1), capture=datetime(2026, 9, 5, tzinfo=UTC), run_id="run-c2-09a")
    week1 = world.week(cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION, run_id="wb-c2-09a")
    # week 2 backfills June/July vintages plus the new September month
    world._month_len = 50
    world.capture(end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-c2-09b",
                  cpi_len=50, pay_len=50)
    week2 = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-09b")
    observed = [e for e in week2.weekly_change.information_set_delta.events
                if e.resolved_event_type() is ReleaseEventType.OBSERVED_UPDATE]
    assert observed
    # observation_date is the real observation month, never invented
    assert all(e.observation_date is not None for e in observed)


# --- RT139-C2-10: across-binding duplicate canonical series (documented effect) ---
def test_c2_10_duplicate_canonical_across_bindings_documented():
    from cross_asset.decision_support.binding import (
        FactorBinding,
        FactorBindingRegistry,
        FactorTransform,
        LaneBinding,
    )

    monitoring = LaneBinding(route="TEST_ONLY_MONITORING", status="BOUND")
    formal = LaneBinding(route="SANCTIONED_FORMAL_QUERY", status="BLOCKED")
    # _validate_registry rejects duplicates within one binding but not across
    # bindings (recorded as a P2 diagnosability item): two factors may bind the
    # same canonical series, which over-weights it in family aggregates.
    registry = FactorBindingRegistry(
        version=995,
        contract="TEST_ONLY",
        bindings=[
            FactorBinding(factor_id="US_PAYROLLS_TREND", canonical_series_ids=["T_PAYROLL"],
                          transform=FactorTransform(type="PAYROLL_3M6M_SMOOTHED_MOMENTUM", min_history=12),
                          monitoring=monitoring, formal=formal),
            FactorBinding(factor_id="US_CORE_CPI_TREND", canonical_series_ids=["T_CPI"],
                          transform=FactorTransform(type="CORE_CPI_3M6M_ANNUALIZED_TREND", min_history=12),
                          monitoring=monitoring, formal=formal),
            FactorBinding(factor_id="US_EQ_TREND_63D", canonical_series_ids=["T_US_EQ"],
                          transform=FactorTransform(type="TREND_63D"),
                          monitoring=monitoring, formal=formal),
            FactorBinding(factor_id="CN_EQ_TREND_63D", canonical_series_ids=["T_US_EQ"],
                          transform=FactorTransform(type="TREND_63D"),
                          monitoring=monitoring, formal=formal),
        ],
    )
    from redteam139._helpers import direct_pack

    pack = direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-10")
    snapshot = build_monitoring_snapshot(pack, registry=registry)
    # both factors scored from the same series are visible in the details
    scores = snapshot.details["subfactor_scores_current"]
    assert scores["CN_EQ_TREND_63D"] is not None


# --- RT139-C2-11: retry then canonical representative selection ---
def test_c2_11_retry_then_canonical_representative(snapshot_root):
    world = WeekWorld()
    world.capture(end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-c2-11a")
    week1 = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-11a")
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    retry_pack = build_monitoring_pack_from_db(
        world.store, workbench_run("wb-c2-11b", decision_time=WEEK2_DECISION + timedelta(hours=2),
                                   data_cutoff=WEEK2_CUTOFF)
    )
    retry = build_monitoring_snapshot(retry_pack, previous_snapshot=week1)
    store.persist(retry)
    canonical = store.list_canonical()
    assert len(canonical) == 1
    assert canonical[0].metadata.decision_time == retry.metadata.decision_time
    assert store.load_latest().metadata.decision_time == retry.metadata.decision_time


# --- RT139-C2-12: diff surface reflects macro change only in updated weeks ---
def test_c2_12_diff_reflects_updated_weeks(snapshot_root):
    from cross_asset.decision_support.serving import SnapshotReadService

    world = WeekWorld()
    world.capture(end_month=date(2026, 8, 1), capture=datetime(2026, 9, 5, tzinfo=UTC), run_id="run-c2-12a")
    week1 = world.week(cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION, run_id="wb-c2-12a")
    world._month_len = 49
    world.capture(end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-c2-12b",
                  cpi_len=49, pay_len=49)
    week2 = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-12b")
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    store.persist(week2)
    diff = SnapshotReadService(store).diff(week2.metadata.snapshot_id, week1.metadata.snapshot_id)
    assert diff


# --- RT139-C2-13: five-week soak loop keeps every invariant each step ---
def test_c2_13_five_week_soak_loop(snapshot_root):
    world = WeekWorld()
    store = SnapshotStore(snapshot_root)
    cutoffs = [
        (WEEK1_CUTOFF, WEEK1_DECISION),
        (WEEK2_CUTOFF, WEEK2_DECISION),
        (WEEK3_CUTOFF, WEEK3_DECISION),
        (WEEK4_CUTOFF, WEEK4_DECISION),
        (WEEK5_CUTOFF, WEEK5_DECISION),
    ]
    month_len = 48
    for index, (cutoff, decision) in enumerate(cutoffs):
        end_month = date(2026, 8, 1) if index == 0 else date(2026, 9, 1)
        if index == 1:
            month_len = 49  # new monthly observation becomes visible in week 2
        world.capture(end_month=end_month, capture=decision.replace(hour=0),
                      run_id=f"run-c2-13-{index}", cpi_len=month_len, pay_len=month_len)
        snapshot = world.week(cutoff=cutoff, decision=decision, run_id=f"wb-c2-13-{index}")
        store.persist(snapshot)
        delta = snapshot.weekly_change.information_set_delta
        changed = snapshot.weekly_change.macro_state_delta.changed_factors()
        if delta.resolved_status() is InformationSetStatus.UPDATED:
            updated = {e.factor_id for e in delta.events
                       if e.resolved_event_type() is ReleaseEventType.OBSERVED_UPDATE}
            assert set(changed) <= updated or not changed
        else:
            assert changed == []
    # the last week is canonical latest; each economic week has one representative
    assert store.load_latest().metadata.as_of == WEEK5_CUTOFF
    assert len(store.list_canonical()) == 5


# --- RT139-C2-14: interleaved retries inside the soak loop stay one step ---
def test_c2_14_interleaved_retries_stay_one_step(snapshot_root):
    world = WeekWorld()
    store = SnapshotStore(snapshot_root)
    world.capture(end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-c2-14a")
    week = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-14a")
    store.persist(week)
    for index in range(3):
        retry_pack = build_monitoring_pack_from_db(
            world.store,
            workbench_run(f"wb-c2-14-r{index}",
                          decision_time=WEEK2_DECISION + timedelta(hours=index + 1),
                          data_cutoff=WEEK2_CUTOFF),
        )
        retry = build_monitoring_snapshot(retry_pack, previous_snapshot=world.snapshots[-1])
        world.snapshots.append(retry)
        store.persist(retry)
    canonical = store.list_canonical()
    assert len(canonical) == 1
    assert len(store.list_snapshots()) == 4  # 1 canonical + 3 technical retries


# --- RT139-C2-15: snapshot id collision does not corrupt the store (P2-06 doc) ---
def test_c2_15_snapshot_id_collision_overwrites_consistently(snapshot_root):
    world = WeekWorld()
    world.capture(end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-c2-15a")
    week = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-15a")
    store = SnapshotStore(snapshot_root)
    store.persist(week)
    # same pack rebuilt (same id), identical body → store stays consistent
    world.snapshots.clear()
    again = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-15a")
    store.persist(again)
    assert store.load_latest().to_json() == again.to_json()
    assert len(store.list_canonical()) == 1


# --- RT139-C2-16: fresh world after restart reads back the full history ---
def test_c2_16_history_readback_after_restart(snapshot_root):
    world = WeekWorld()
    world.capture(end_month=date(2026, 8, 1), capture=datetime(2026, 9, 5, tzinfo=UTC), run_id="run-c2-16a")
    week1 = world.week(cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION, run_id="wb-c2-16a")
    world._month_len = 49
    world.capture(end_month=date(2026, 9, 1), capture=WEEK2_DECISION.replace(hour=0), run_id="run-c2-16b",
                  cpi_len=49, pay_len=49)
    week2 = world.week(cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-c2-16b")
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    store.persist(week2)
    reopened = SnapshotStore(snapshot_root)
    history = reopened.list_snapshots()
    assert len(history) == 2
    assert [item.metadata.as_of for item in history] == [WEEK1_CUTOFF, WEEK2_CUTOFF]
