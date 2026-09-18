"""Pass-2 emergent cross-layer attacks (ADVERSARIAL-E2E-VALIDATION-V1).

These cases target interactions discovered during Pass 1: the monitoring
read-model, the producer's information-set guard, the store pointer and the
freshness downgrade policy interacting with each other.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, date, datetime, timedelta
from http.client import HTTPConnection

import pytest

from cross_asset.decision_support.enums import DataHealthStatus
from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db
from cross_asset.decision_support.producer import (
    MonitoringSnapshotBlocked,
    build_monitoring_snapshot,
    score_monitoring_factors,
)
from cross_asset.decision_support.serving import SnapshotReadService, SnapshotStore, make_server
from cross_asset.decision_support.weekly import SyntheticMovementError

from _helpers import (
    AS_OF,
    CAPTURE,
    DECISION,
    governed_store,
    mechanics_registry,
    month_rows,
    pack,
    workbench_run,
    write_monitoring_run,
)


def _real_pack(store, *, end_month: date, capture: datetime, decision: datetime, cutoff: date, run_id):
    """Insert a monitoring capture and build the pack exactly as production does."""

    from _helpers import month_rows as rows_for

    months = 49 if end_month.month == 9 else 48
    payroll = [
        145000 + index * 145 + (index % 5) * 18 + (index // 12) * 23
        for index in range(months)
    ]
    cpi: list[float] = [270.0]
    rates = [0.0018, 0.0022, 0.0027, 0.0031, 0.0025, 0.0020]
    for index in range(1, months):
        cpi.append(cpi[-1] * (1.0 + rates[index % 6]))
    rows = rows_for(
        "US_NONFARM_PAYROLLS", "PAYEMS", payroll, capture_time=capture, end=end_month
    )
    rows += rows_for("US_CORE_CPI", "CPILFESL", cpi, capture_time=capture, end=end_month)
    write_monitoring_run(store, rows, run_id=run_id, requested=2)
    return build_monitoring_pack_from_db(
        store,
        workbench_run(run_id, decision_time=decision, data_cutoff=cutoff),
    )


# --- E2-01: the real second week cannot be produced -----------------------------


def test_adv_e2_01_real_second_week_with_new_data_raises_synthetic_movement(
    governed_store,
):
    """LEDGER ADV-P1-01: cross-layer break in the normal monitoring loop.

    The adapter supplies no release events (B7-04), so the information set is
    always NO_NEW_INFORMATION. When a genuinely new monthly observation moves a
    cyclical factor, build_macro_state_delta correctly refuses synthetic
    movement and the whole week-2 snapshot fails.
    """

    store = governed_store()
    try:
        first_pack = _real_pack(
            store,
            end_month=date(2026, 8, 1),
            capture=datetime(2026, 9, 5, 0, tzinfo=UTC),
            decision=datetime(2026, 9, 5, 6, tzinfo=UTC),
            cutoff=date(2026, 9, 4),
            run_id="monitoring-fred-e2-01a",
        )
        first = build_monitoring_snapshot(first_pack)
        assert first.details["subfactor_scores_current"]["US_PAYROLLS_TREND"] is not None

        second_pack = _real_pack(
            store,
            end_month=date(2026, 9, 1),
            capture=CAPTURE,
            decision=DECISION,
            cutoff=AS_OF,
            run_id="monitoring-fred-e2-01b",
        )
        assert any(item.observations for item in second_pack.series)

        with pytest.raises(SyntheticMovementError):
            build_monitoring_snapshot(second_pack, previous_snapshot=first)
    finally:
        store.close()


def test_adv_e2_02_real_second_week_without_new_data_is_still_producible(
    governed_store,
):
    """The same week-2 call succeeds when no cyclical observation changes, which
    confirms the failure above is data-driven and not a lineage/argument error."""

    store = governed_store()
    try:
        first_pack = _real_pack(
            store,
            end_month=date(2026, 8, 1),
            capture=datetime(2026, 9, 5, 0, tzinfo=UTC),
            decision=datetime(2026, 9, 5, 6, tzinfo=UTC),
            cutoff=date(2026, 9, 4),
            run_id="monitoring-fred-e2-02a",
        )
        first = build_monitoring_snapshot(first_pack)
        # Same observations, later decision/cutoff: no new cyclical information.
        second_pack = _real_pack(
            store,
            end_month=date(2026, 8, 1),
            capture=datetime(2026, 9, 5, 0, tzinfo=UTC),
            decision=datetime(2026, 9, 5, 6, tzinfo=UTC) + timedelta(days=7),
            cutoff=date(2026, 9, 11),
            run_id="monitoring-fred-e2-02b",
        )
        snapshot = build_monitoring_snapshot(second_pack, previous_snapshot=first)
        assert snapshot.metadata.run_id == "monitoring-fred-e2-02b"
        assert snapshot.regime is not None
    finally:
        store.close()


# --- E2-03: same-week retry copies the delta while recomputing the views --------


def test_adv_e2_03_same_week_retry_can_desynchronise_delta_and_views():
    """LEDGER ADV-P2-08: on a same-week retry the asset_view_delta is copied from
    the prior snapshot, but the asset views are recomputed, so a within-week data
    change can move a stance without any delta entry describing it."""

    registry = mechanics_registry()

    def _equity_trend(direction_up: bool, *, decision: datetime):
        import pandas as pd

        from _helpers import series as build_series

        bundle = pack(decision=decision)
        daily = pd.bdate_range(end=AS_OF, periods=90)
        if direction_up:
            values = [5000 + index * 10 for index in range(90)]
        else:
            values = [6000 - index * 20 for index in range(90)]
        return bundle.model_copy(
            update={
                "series": [
                    build_series("T_US_EQ", daily, values)
                    if item.series_id == "T_US_EQ"
                    else item
                    for item in bundle.series
                ]
            }
        )

    previous = build_monitoring_snapshot(
        _equity_trend(True, decision=DECISION), registry=registry
    )
    retry = build_monitoring_snapshot(
        _equity_trend(False, decision=DECISION + timedelta(hours=6)),
        previous_snapshot=previous,
        registry=registry,
    )

    previous_views = {view.asset.value: view for view in previous.asset_views}
    retry_views = {view.asset.value: view for view in retry.asset_views}
    moved = {
        asset: (previous_views[asset].market_confirmation.value, view.market_confirmation.value)
        for asset, view in retry_views.items()
        if view.market_confirmation != previous_views[asset].market_confirmation
        or view.confidence != previous_views[asset].confidence
    }
    # The within-week capture genuinely changed the observed market confirmation,
    # yet the copied delta surface still reports nothing about it.
    assert moved, "the adversarial input must actually change an asset surface"
    assert retry.weekly_change.asset_view_delta.model_dump() == (
        previous.weekly_change.asset_view_delta.model_dump()
    )
    assert retry.weekly_change.asset_view_delta.entries == []


# --- E2-04: legacy regime rows are not multiplied into extra weeks --------------


def test_adv_e2_04_legacy_unkeyed_regime_rows_are_not_replayed_as_many_weeks():
    """Pre-F04 rows lacked economic-step identity; only the last one is migrated,
    so a restart cannot inflate dwell weeks."""

    registry = mechanics_registry()
    previous = build_monitoring_snapshot(pack(), registry=registry)
    legacy = dict(previous.details)
    legacy["regime_input_history"] = [
        {"growth_score": 0.5, "inflation_score": -0.5, "confidence": 1.0, "coverage": 1.0},
        {"growth_score": 0.4, "inflation_score": -0.4, "confidence": 1.0, "coverage": 1.0},
        {"growth_score": 0.3, "inflation_score": -0.3, "confidence": 1.0, "coverage": 1.0},
    ]
    legacy.pop("economic_week_id", None)
    migrated = previous.model_copy(update={"details": legacy})

    current = pack(
        as_of=AS_OF + timedelta(days=7),
        decision=DECISION + timedelta(days=7),
        run_id="wb-adv-e2-04",
    )
    snapshot = build_monitoring_snapshot(
        current, previous_snapshot=migrated, registry=registry
    )
    history = snapshot.details["regime_input_history"]
    assert len(history) == 2, "one migrated legacy week plus the current week"
    assert [item["economic_week_id"] for item in history] == [
        "2026-09-07",
        "2026-09-14",
    ]


# --- E2-05: zero-variance input can never yield a neutral regime ----------------


def test_adv_e2_05_degenerate_flat_input_blocks_instead_of_reading_neutral():
    import pandas as pd

    from _helpers import series as build_series

    monthly = pd.date_range(end=date(2026, 9, 1), periods=40, freq="MS")
    flat = pack().model_copy(
        update={
            "series": [
                build_series(
                    item.series_id,
                    monthly,
                    [130000.0] * 40,
                )
                if item.series_id == "T_PAYROLL"
                else item
                for item in pack().series
            ]
        }
    )
    with pytest.raises(MonitoringSnapshotBlocked, match="regime axes unavailable"):
        build_monitoring_snapshot(flat, registry=mechanics_registry())


# --- E2-06: a freshness downgrade must not silently grow coverage ---------------


def test_adv_e2_06_missing_calendar_downgrade_does_not_fabricate_coverage(
    governed_store,
):
    store = governed_store(("US_CORE_CPI",))
    try:
        write_monitoring_run(
            store,
            month_rows("US_CORE_CPI", "CPILFESL", [200 + i for i in range(48)]),
            run_id="monitoring-fred-e2-06",
        )
        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-e2-06"))
        cpi = next(item for item in bundle.series if item.series_id == "US_CORE_CPI")
        assert cpi.status == "STALE"
        assert cpi.provenance["freshness_verified"] is False
        assert cpi.provenance["freshness_limitation"] == "calendar_mapping_missing"
        scores, _ = score_monitoring_factors(bundle)
        # Stale evidence keeps reduced confidence; it is never promoted to full.
        assert scores["US_CORE_CPI_TREND"].confidence == 0.5
    finally:
        store.close()


# --- E2-07: a BLOCKED series must appear, not disappear -------------------------


def test_adv_e2_07_identity_blocked_series_remains_visible_as_blocked(
    governed_store,
):
    store = governed_store()
    try:
        rows = month_rows("US_CORE_CPI", "PAYEMS", [200 + i for i in range(48)])
        rows += month_rows(
            "US_NONFARM_PAYROLLS", "PAYEMS", [145000 + i * 145 + (i % 5) * 18 for i in range(48)]
        )
        write_monitoring_run(store, rows, run_id="monitoring-fred-e2-07", requested=2)
        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-e2-07"))
        by_series = {item.series_id: item for item in bundle.series}
        assert by_series["US_CORE_CPI"].status == "BLOCKED"
        assert by_series["US_CORE_CPI"].provenance["identity_blockers"]
        # It stays enumerated in the lineage, and a blocked factor is reported,
        # never silently dropped from the health surface.
        assert "US_CORE_CPI" in {
            item.series_id for item in bundle.series
        }
        scores, statuses = score_monitoring_factors(bundle)
        assert statuses["US_CORE_CPI_TREND"]["missing"] is True
    finally:
        store.close()


# --- E2-08: the API must not inherit the identity-fix as an authority change ----


def test_adv_e2_08_identity_fix_does_not_grant_formal_authority(governed_store):
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
        write_monitoring_run(store, rows, run_id="monitoring-fred-e2-08", requested=2)
        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-e2-08"))
        cpi = next(item for item in bundle.series if item.series_id == "US_CORE_CPI")
        assert cpi.provenance["identity_verified"] is True
        assert cpi.provenance["formal_admission_granted"] is False
        snapshot = build_monitoring_snapshot(bundle)
        assert snapshot.metadata.lane.value == "MONITORING"
        assert snapshot.details["series_provenance"]["US_CORE_CPI"][
            "formal_admission_granted"
        ] is False
        record = next(
            item
            for item in snapshot.details["factor_bindings"]
            if item["factor_id"] == "US_CORE_CPI_TREND"
        )
        assert record["formal"]["status"] == "BLOCKED"
    finally:
        store.close()


# --- E2-09: store pointer + CLI previous selection ------------------------------


def test_adv_e2_09_cli_previous_selection_rejects_a_look_ahead_latest_pointer(
    snapshot_root,
):
    """The CLI never looks ahead: a latest pointer whose decision_time is not
    strictly earlier than the current run is ignored (unlike raw store.persist,
    see ADV-P1-02)."""

    from cross_asset.decision_support.snapshot_cli import _previous_snapshot_for

    store = SnapshotStore(snapshot_root)
    future = build_monitoring_snapshot(
        pack(
            as_of=AS_OF + timedelta(days=14),
            decision=DECISION + timedelta(days=14),
            run_id="wb-adv-e2-09",
        ),
        registry=mechanics_registry(),
    )
    store.persist(future)
    assert _previous_snapshot_for(store, DECISION) is None
    assert _previous_snapshot_for(store, DECISION + timedelta(days=21)) is not None


# --- E2-10: end-to-end read chain after the identity fix ------------------------


def test_adv_e2_10_full_chain_from_governed_db_to_http_after_identity_fix(
    governed_store, tmp_path
):
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
        write_monitoring_run(store, rows, run_id="monitoring-fred-e2-10", requested=2)

        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-e2-10"))
        assert all(
            item.provenance["identity_verified"] is True for item in bundle.series
        )
        snapshot = build_monitoring_snapshot(bundle)
        assert snapshot.data_health_summary.overall is DataHealthStatus.PARTIAL

        root = tmp_path / "api"
        SnapshotStore(root).persist(snapshot)
        server = make_server(SnapshotReadService(SnapshotStore(root)).store.__class__(root), port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            connection.request("GET", "/api/snapshot/latest")
            response = connection.getresponse()
            payload = json.loads(response.read())
            assert response.status == 200
            assert payload["metadata"]["snapshot_id"] == snapshot.metadata.snapshot_id
            assert payload["details"]["series_provenance"]["US_CORE_CPI"][
                "identity_verified"
            ] is True
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    finally:
        store.close()
