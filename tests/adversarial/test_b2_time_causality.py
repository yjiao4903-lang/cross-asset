"""B2 — observation/time/causality attacks (ADVERSARIAL-E2E-VALIDATION-V1)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from adversarial._helpers import (
    AS_OF,
    CAPTURE,
    DECISION,
    mechanics_registry,
    month_rows,
    pack,
    workbench_run,
    write_monitoring_run,
)
from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db
from cross_asset.decision_support.producer import (
    build_monitoring_snapshot,
    score_monitoring_factors,
)


def _mutate_last_observation(bundle, series_id, **updates):
    updated = []
    for item in bundle.series:
        if item.series_id != series_id:
            updated.append(item)
            continue
        observations = list(item.observations)
        observations[-1] = observations[-1].model_copy(update=updates)
        updated.append(item.model_copy(update={"observations": observations}))
    return bundle.model_copy(update={"series": updated})


# --- B2-01: future available_at ------------------------------------------------


def test_adv_b2_01_observation_available_after_decision_time_is_rejected():
    mutated = _mutate_last_observation(
        pack(), "T_PAYROLL", available_at=DECISION + timedelta(hours=1)
    )
    with pytest.raises(ValueError, match="available after decision_time"):
        build_monitoring_snapshot(mutated, registry=mechanics_registry())


# --- B2-02: observation_date after data cutoff ---------------------------------


def test_adv_b2_02_observation_after_data_cutoff_is_rejected():
    mutated = _mutate_last_observation(
        pack(), "T_PAYROLL", observation_date=AS_OF + timedelta(days=3)
    )
    with pytest.raises(ValueError, match="after data_cutoff"):
        build_monitoring_snapshot(mutated, registry=mechanics_registry())


# --- B2-03/04: duplicate observation dates ------------------------------------


def test_adv_b2_03_duplicate_dates_from_db_resolve_to_latest_vintage(governed_store):
    store = governed_store()
    try:
        run_id = "monitoring-fred-adv-b2-03"
        rows = month_rows("US_NONFARM_PAYROLLS", "PAYEMS", [145000 + i * 145 for i in range(48)])
        store.start_run("MONITORING:fred", run_id, requested_series=1)
        store.insert_observations(rows, run_id=run_id)
        # Same observation_date, later available_at (a revision capture).
        revised = [
            {
                **rows[-1],
                "value": float(rows[-1]["value"]) + 25.0,
                "available_at": CAPTURE + timedelta(hours=6),
                "ingested_at": CAPTURE + timedelta(hours=6),
            }
        ]
        store.insert_observations(revised, run_id=run_id)
        store.finish_run(run_id, "success", success_series=1, failed_series=0)

        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-b2-03"))
        payroll = next(
            item for item in bundle.series if item.series_id == "US_NONFARM_PAYROLLS"
        )
        dates = [observation.observation_date for observation in payroll.observations]
        assert len(dates) == len(set(dates)), "read model must not double-count a date"
        assert payroll.observations[-1].value == float(rows[-1]["value"]) + 25.0
    finally:
        store.close()


def test_adv_b2_04_duplicate_dates_in_direct_pack_are_not_guarded():
    """LEDGER ADV-P2-02: the direct pack contract has no duplicate-date guard.

    This is a recorded gap, not an accepted invariant: a hand-built pack with
    two rows for one date is accepted. The DB read model dedupes (B2-03), so
    the runtime path is unaffected; the diagnostic `--input` path is not.
    """

    bundle = pack()
    payroll = next(item for item in bundle.series if item.series_id == "T_PAYROLL")
    duplicated = [
        payroll.observations[-1],
        payroll.observations[-1].model_copy(
            update={"available_at": payroll.observations[-1].available_at + timedelta(hours=1)}
        ),
    ]
    mutated = bundle.model_copy(
        update={
            "series": [
                item.model_copy(update={"observations": [*item.observations, *duplicated]})
                if item.series_id == "T_PAYROLL"
                else item
                for item in bundle.series
            ]
        }
    )
    snapshot = build_monitoring_snapshot(mutated, registry=mechanics_registry())
    assert snapshot.details["factor_statuses"]["US_PAYROLLS_TREND"]["missing"] is False


# --- B2-05: late-arriving but causally valid row -------------------------------


def test_adv_b2_05_late_arriving_row_within_cutoff_is_admitted(governed_store):
    store = governed_store()
    try:
        rows = month_rows("US_NONFARM_PAYROLLS", "PAYEMS", [145000 + i * 145 for i in range(48)])
        write_monitoring_run(store, rows, run_id="monitoring-fred-adv-b2-05")
        late = [
            {
                "series_id": "US_NONFARM_PAYROLLS",
                "observation_date": rows[0]["observation_date"],
                "available_at": CAPTURE - timedelta(days=1),
                "value": float(rows[0]["value"]) - 10.0,
                "source": "fred",
                "source_series_id": "PAYEMS",
                "ingested_at": CAPTURE - timedelta(days=1),
                "quality": "ok",
            }
        ]
        write_monitoring_run(store, late, run_id="monitoring-fred-adv-b2-05b")
        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-b2-05"))
        payroll = next(
            item for item in bundle.series if item.series_id == "US_NONFARM_PAYROLLS"
        )
        assert payroll.observations[0].available_at <= DECISION
        assert all(o.available_at <= DECISION for o in payroll.observations)
    finally:
        store.close()


# --- B2-06: stale row keeps reduced confidence ---------------------------------


def test_adv_b2_06_stale_series_reduces_confidence_without_dropping_evidence():
    bundle = pack(statuses={"T_PAYROLL": "STALE", "T_CPI": "STALE"})
    scores, statuses = score_monitoring_factors(bundle, registry=mechanics_registry())
    assert scores["US_PAYROLLS_TREND"].missing is False
    assert scores["US_PAYROLLS_TREND"].confidence == 0.5
    assert statuses["US_PAYROLLS_TREND"]["stale"] is True


# --- B2-07: missing available_at is rejected -----------------------------------


def test_adv_b2_07_missing_available_at_is_rejected():
    bundle = pack()
    payroll = next(item for item in bundle.series if item.series_id == "T_PAYROLL")
    with pytest.raises(ValueError):
        # The canonical observation contract has no disclosure-only mode: a row
        # without available_at cannot be constructed at all.
        MonitoringObservationFactory.drop_available_at(payroll)


class MonitoringObservationFactory:
    @staticmethod
    def drop_available_at(item):
        payload = item.model_dump()
        payload["observations"] = [
            {key: value for key, value in row.items() if key != "available_at"}
            for row in payload["observations"]
        ]
        return type(item).model_validate(payload)


# --- B2-08: capture-time history must not pose as PIT --------------------------


def test_adv_b2_08_capture_time_history_never_grants_formal_or_pit_status(governed_store):
    store = governed_store()
    try:
        rows = month_rows("US_NONFARM_PAYROLLS", "PAYEMS", [145000 + i * 145 for i in range(48)])
        write_monitoring_run(store, rows, run_id="monitoring-fred-adv-b2-08")
        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-b2-08"))
        payroll = next(
            item for item in bundle.series if item.series_id == "US_NONFARM_PAYROLLS"
        )
        # Every historical row is visible at one capture timestamp: that is
        # non-PIT by construction, and must stay out of the formal lane.
        assert len({o.available_at for o in payroll.observations}) == 1
        assert payroll.provenance["formal_readiness"] in {
            "FORMAL_BLOCKED",
            "FORMAL_OBSERVATION_AVAILABLE",
        }
        assert payroll.provenance["formal_admission_granted"] is False
    finally:
        store.close()


# --- B2-09: out-of-order rows ---------------------------------------------------


def test_adv_b2_09_out_of_order_observations_are_rejected():
    bundle = pack()
    mutated = bundle.model_copy(
        update={
            "series": [
                item.model_copy(update={"observations": list(reversed(item.observations))})
                if item.series_id == "T_PAYROLL"
                else item
                for item in bundle.series
            ]
        }
    )
    with pytest.raises(ValueError, match="not ordered"):
        build_monitoring_snapshot(mutated, registry=mechanics_registry())


# --- B2-10: insufficient transform history -------------------------------------


def test_adv_b2_10_insufficient_history_stays_missing_not_zero():
    bundle = pack()
    payroll = next(item for item in bundle.series if item.series_id == "T_PAYROLL")
    truncated = payroll.model_copy(update={"observations": payroll.observations[-6:]})
    mutated = bundle.model_copy(
        update={
            "series": [
                truncated if item.series_id == "T_PAYROLL" else item for item in bundle.series
            ]
        }
    )
    scores, statuses = score_monitoring_factors(mutated, registry=mechanics_registry())
    assert scores["US_PAYROLLS_TREND"].missing is True
    assert scores["US_PAYROLLS_TREND"].score is None
    assert statuses["US_PAYROLLS_TREND"]["reason"].startswith("transform unavailable")


# --- B2-11: one observation visible under two technical runs --------------------


def test_adv_b2_11_same_observation_under_two_runs_is_counted_once(governed_store):
    store = governed_store()
    try:
        rows = month_rows("US_NONFARM_PAYROLLS", "PAYEMS", [145000 + i * 145 for i in range(48)])
        write_monitoring_run(store, rows, run_id="monitoring-fred-adv-b2-11a")
        write_monitoring_run(store, rows, run_id="monitoring-fred-adv-b2-11b")
        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-b2-11"))
        payroll = next(
            item for item in bundle.series if item.series_id == "US_NONFARM_PAYROLLS"
        )
        dates = [observation.observation_date for observation in payroll.observations]
        assert len(dates) == len(set(dates)) == 48
        # Identical (series, date, available_at, source, source_symbol) rows are
        # idempotent at write time, so exactly one run owns each observation.
        assert payroll.provenance["ingestion_run_ids"] == ["monitoring-fred-adv-b2-11a"]
        assert len(payroll.observations) == 48
    finally:
        store.close()


# --- B2-12: available_at exactly at decision_time -------------------------------


def test_adv_b2_12_available_at_boundary_at_decision_time_is_inclusive():
    bundle = pack()
    mutated = _mutate_last_observation(bundle, "T_PAYROLL")
    payroll = next(item for item in mutated.series if item.series_id == "T_PAYROLL")
    boundary = payroll.observations[-1].model_copy(update={"available_at": DECISION})
    mutated = mutated.model_copy(
        update={
            "series": [
                item.model_copy(update={"observations": [*item.observations[:-1], boundary]})
                if item.series_id == "T_PAYROLL"
                else item
                for item in mutated.series
            ]
        }
    )
    snapshot = build_monitoring_snapshot(mutated, registry=mechanics_registry())
    assert snapshot.metadata.decision_time == DECISION


# --- B2-13: observation_date exactly at data_cutoff -----------------------------


def test_adv_b2_13_observation_date_boundary_at_cutoff_is_inclusive():
    bundle = pack()
    mutated = _mutate_last_observation(bundle, "T_PAYROLL", observation_date=AS_OF)
    snapshot = build_monitoring_snapshot(mutated, registry=mechanics_registry())
    assert snapshot.details["data_cutoff"] == AS_OF.isoformat()


# --- B2-14: as_of / data_cutoff divergence is recorded, not silently accepted ---


def test_adv_b2_14_as_of_cutoff_divergence_is_visible_in_the_snapshot():
    """LEDGER ADV-P2-03: pack.as_of may diverge from lineage.data_cutoff."""

    bundle = pack().model_copy(update={"as_of": AS_OF - timedelta(days=30)})
    snapshot = build_monitoring_snapshot(bundle, registry=mechanics_registry())
    assert snapshot.metadata.as_of == AS_OF - timedelta(days=30)
    assert snapshot.details["data_cutoff"] == AS_OF.isoformat()
    assert snapshot.metadata.as_of.isoformat() != snapshot.details["data_cutoff"]
