"""RT139 B2 — observation/time causality attacks (seeds: #138 B2; re-derived)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db
from cross_asset.decision_support.producer import (
    MonitoringObservation,
    MonitoringObservationPack,
    MonitoringRunLineage,
    MonitoringSeries,
    build_monitoring_snapshot,
)
from cross_asset.decision_support.weekly import ReleaseEvent
from redteam139._helpers import (
    WEEK2_CUTOFF,
    payroll_values,
    WEEK2_DECISION,
    cpi_values,
    governed_store,
    mechanics_registry,
    month_rows,
    workbench_run,
    write_monitoring_run,
)

CAPTURE = datetime(2026, 9, 12, 0, tzinfo=UTC)


def _filled_pack(pack: MonitoringObservationPack) -> MonitoringObservationPack:
    return pack


def _direct_pack_with_cpi_end(cpi_end: date, *, run_id: str = "wb-b2") -> MonitoringObservationPack:
    from redteam139._helpers import direct_pack

    return direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id=run_id, cpi_end=cpi_end)


# --- RT139-B2-01: future available_at is rejected at ingestion ---
def test_b2_01_observation_available_after_decision_time_is_rejected():
    store = governed_store()
    future_capture = WEEK2_DECISION + timedelta(hours=1)
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=future_capture)
    store.start_run("MONITORING:fred", "run-b2-01", requested_series=1)
    store.insert_observations(rows, run_id="run-b2-01")
    store.finish_run("run-b2-01", "success", success_series=1, failed_series=0)
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b2-01"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.observations == []


# --- RT139-B2-02: observation after data_cutoff is a hard boundary ---
def test_b2_02_observation_after_cutoff_never_served_by_read_model():
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE)
    rows = [dict(row, observation_date=date(2026, 9, 20)) if row["observation_date"] == date(2026, 9, 1) else row for row in rows]
    write_monitoring_run(store, rows, run_id="run-b2-02")
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b2-02"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert all(obs.observation_date <= WEEK2_CUTOFF for obs in series.observations)


# --- RT139-B2-03: duplicate observation dates resolve to latest vintage ---
def test_b2_03_duplicate_dates_resolve_to_latest_vintage():
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE)
    revised = dict(rows[0], value=999.0, available_at=CAPTURE + timedelta(hours=1))
    store.start_run("MONITORING:fred", "run-b2-03", requested_series=1)
    store.insert_observations(rows + [revised], run_id="run-b2-03")
    store.finish_run("run-b2-03", "success", success_series=1, failed_series=0)
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b2-03"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    dates = [obs.observation_date for obs in series.observations]
    assert len(dates) == len(set(dates))
    target = [obs for obs in series.observations if obs.observation_date == rows[0]["observation_date"]]
    assert target[0].value == 999.0


# --- RT139-B2-04: direct pack duplicate dates stay unguarded (P2-02 doc) ---
def test_b2_04_direct_pack_duplicate_dates_not_guarded():
    base = _direct_pack_with_cpi_end(date(2026, 9, 1))
    cpi = [item for item in base.series if item.series_id == "T_CPI"][0]
    dup = MonitoringObservation(
        observation_date=cpi.observations[0].observation_date,
        available_at=cpi.observations[0].available_at + timedelta(hours=2),
        value=123.0,
        source_ref="adversarial-test-only:T_CPI",
    )
    poisoned = base.model_copy(deep=True)
    poisoned.series = [
        item if item.series_id != "T_CPI"
        else item.model_copy(deep=True, update={"observations": [item.observations[0], dup, *item.observations[1:]]})
        for item in poisoned.series
    ]
    # Documented P2 (ADV-P2-02): the diagnostic direct-pack contract accepts
    # duplicate observation dates; resolution is a contract decision.
    snapshot = build_monitoring_snapshot(poisoned, registry=mechanics_registry())
    assert snapshot.metadata.as_of == WEEK2_CUTOFF


# --- RT139-B2-05: late arrival within causality is admissible ---
def test_b2_05_late_arriving_row_within_cutoff_is_admitted():
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40),
                      capture_time=WEEK2_DECISION - timedelta(hours=1), end=date(2026, 9, 1))
    write_monitoring_run(store, rows, run_id="run-b2-05")
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b2-05"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert any(obs.observation_date == date(2026, 9, 1) for obs in series.observations)


# --- RT139-B2-06: stale evidence reduces confidence, never dropped/zero-filled ---
def test_b2_06_stale_series_keeps_score_with_reduced_confidence():
    pack = _direct_pack_with_cpi_end(date(2026, 6, 1))
    pack.series = [
        item if item.series_id != "T_CPI"
        else item.model_copy(deep=True, update={"status": "STALE"})
        for item in pack.series
    ]
    snapshot = build_monitoring_snapshot(pack, registry=mechanics_registry())
    status = snapshot.details["factor_statuses"]["US_CORE_CPI_TREND"]
    assert status["stale"] is True
    assert status["confidence"] <= 0.6


# --- RT139-B2-07: missing available_at is rejected (availability mandatory) ---
def test_b2_07_missing_available_at_is_rejected():
    with pytest.raises(Exception):
        MonitoringObservation(
            observation_date=date(2026, 9, 1),
            available_at=None,
            value=1.0,
            source_ref="adversarial-test-only:T_CPI",
        )


# --- RT139-B2-08: capture-time history never grants formal/PIT status ---
def test_b2_08_capture_time_history_never_grants_formal_status():
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE)
    write_monitoring_run(store, rows, run_id="run-b2-08")
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b2-08"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.provenance["formal_admission_granted"] is False
    assert series.provenance["formal_readiness"] != "FORMAL_ADMITTED"


# --- RT139-B2-09: out-of-order rows are served ordered ---
def test_b2_09_out_of_order_direct_pack_is_rejected():
    base = _direct_pack_with_cpi_end(date(2026, 9, 1))
    cpi = [item for item in base.series if item.series_id == "T_CPI"][0]
    observations = list(reversed(cpi.observations[:10])) + cpi.observations[10:]
    reordered = base.model_copy(deep=True)
    reordered.series = [
        item if item.series_id != "T_CPI"
        else item.model_copy(deep=True, update={"observations": observations})
        for item in reordered.series
    ]
    # The direct pack contract orders by observation_date; violations are typed.
    with pytest.raises(ValueError, match="monitoring observations not ordered"):
        build_monitoring_snapshot(reordered, registry=mechanics_registry())


# --- RT139-B2-10: same observation across two runs is deduplicated ---
def test_b2_10_same_observation_two_runs_deduplicated():
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE)
    write_monitoring_run(store, rows, run_id="run-b2-10a")
    write_monitoring_run(store, rows, run_id="run-b2-10b")
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b2-10"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    dates = [obs.observation_date for obs in series.observations]
    assert len(dates) == len(set(dates))


# --- RT139-B2-11: available_at equal to decision_time is admissible (boundary) ---
def test_b2_11_available_at_equal_to_decision_time_boundary():
    store = governed_store()
    boundary = WEEK2_DECISION
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=boundary)
    write_monitoring_run(store, rows, run_id="run-b2-11")
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b2-11"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.observations


# --- RT139-B2-12: observation_date one day past cutoff never enters the pack ---
def test_b2_12_observation_date_past_cutoff_not_served():
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE)
    rows = [dict(row, observation_date=date(2026, 9, 30)) if row["observation_date"] == date(2026, 9, 1) else row for row in rows]
    write_monitoring_run(store, rows, run_id="run-b2-12")
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b2-12"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert all(obs.observation_date <= WEEK2_CUTOFF for obs in series.observations)


# --- RT139-B2-13: as_of/data_cutoff divergence in hand-built packs (P2-03 doc) ---
def test_b2_13_as_of_cutoff_divergence_documented():
    pack = _direct_pack_with_cpi_end(date(2026, 9, 1))
    divergent = pack.model_copy(deep=True)
    divergent.as_of = date(2026, 8, 1)
    snapshot = build_monitoring_snapshot(divergent, registry=mechanics_registry())
    assert snapshot.metadata.as_of == date(2026, 8, 1)
    assert snapshot.details["data_cutoff"] == "2026-09-11"


# --- RT139-B2-14: revision visible in a later week is an OBSERVED_UPDATE (#139) ---
def test_b2_14_revised_value_next_week_is_observed_update():
    from cross_asset.decision_support.enums import ReleaseEventType

    store = governed_store()
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(48), capture_time=datetime(2026, 9, 5, tzinfo=UTC), end=date(2026, 8, 1))
    rows += month_rows("US_NONFARM_PAYROLLS", "PAYEMS", payroll_values(48), capture_time=datetime(2026, 9, 5, tzinfo=UTC), end=date(2026, 8, 1))
    write_monitoring_run(store, rows, run_id="run-b2-14a", requested=2)
    pack1 = build_monitoring_pack_from_db(store, workbench_run("wb-b2-14a", decision_time=datetime(2026, 9, 5, 6, tzinfo=UTC), data_cutoff=date(2026, 9, 4)))
    snap1 = build_monitoring_snapshot(pack1)

    revised = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(49), capture_time=CAPTURE, end=date(2026, 9, 1))
    revised += month_rows("US_NONFARM_PAYROLLS", "PAYEMS", payroll_values(49), capture_time=CAPTURE, end=date(2026, 9, 1))
    write_monitoring_run(store, revised, run_id="run-b2-14b", requested=2)
    pack2 = build_monitoring_pack_from_db(store, workbench_run("wb-b2-14b"))
    snap2 = build_monitoring_snapshot(pack2, previous_snapshot=snap1)
    events = snap2.weekly_change.information_set_delta.events
    observed = [e for e in events if e.resolved_event_type() is ReleaseEventType.OBSERVED_UPDATE]
    assert observed, "a newly visible revised value must become an observed update"
    assert snap2.weekly_change.information_set_delta.resolved_status().value == "UPDATED"
    # observation_date is real; no publication timestamp is invented anywhere.
    for event in observed:
        assert event.observation_date is not None
        assert "no publication timestamp asserted" in event.note


# --- RT139-B2-15: observation identities are persisted for later diffs (#139) ---
def test_b2_15_observation_identities_persisted_in_snapshot():
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE)
    rows += month_rows("US_NONFARM_PAYROLLS", "PAYEMS", payroll_values(40), capture_time=CAPTURE)
    write_monitoring_run(store, rows, run_id="run-b2-15", requested=2)
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b2-15"))
    snapshot = build_monitoring_snapshot(pack)
    identities = snapshot.details["series_provenance"]["US_CORE_CPI"]["observations"]
    assert identities
    first = identities[0]
    assert {"observation_date", "available_at", "value", "source", "source_series_id"} <= set(first)
    assert first["source"] == "fred" and first["source_series_id"] == "CPILFESL"


# --- RT139-B2-16: direct-pack release events are honored by the producer ---
def test_b2_16_direct_pack_release_events_honored():
    pack = _direct_pack_with_cpi_end(date(2026, 9, 1))
    event = ReleaseEvent(
        factor_id="US_CORE_CPI_TREND",
        series_id="T_CPI",
        event_type="NEW_OBSERVATION",
        observation_date=date(2026, 9, 1),
        note="test-supplied",
    )
    supplied = pack.model_copy(deep=True)
    supplied.release_events = [event]
    snapshot = build_monitoring_snapshot(supplied, registry=mechanics_registry())
    assert snapshot.weekly_change.information_set_delta.resolved_status().value == "UPDATED"
