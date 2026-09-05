"""Regression coverage for the unified formal-consumption gates (Issue #18).

Core principle under test:
    存在数据 ≠ 获准数据; 获准数据 ≠ 新鲜健康数据;
    fixture ≠ production; series_id 相同 ≠ provenance 相同.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from cross_asset.reports.readiness import generate_readiness
from cross_asset.storage import (
    DuckDBStore,
    latest_formal_observations_asof,
)
from cross_asset.storage.acceptance_registry import upsert_data_acceptance

DECISION_TIME = datetime(2026, 9, 2, 23, 59, tzinfo=UTC)
CUTOFF = date(2026, 8, 31)


def _accept(
    store,
    *,
    series_id="A",
    provider="wind",
    source_series_id="A.WIND",
    usage_status="LIVE_VERIFIED",
    origin="LIVE",
    semantic_equivalence=True,
):
    now = datetime(2026, 9, 1, tzinfo=UTC)
    upsert_data_acceptance(
        store,
        {
            "series_id": series_id,
            "provider": provider,
            "source_series_id": source_series_id,
            "status": "PASS",
            "tech_gate": "PASS",
            "legal_gate": "PASS",
            "pit_gate": "PASS",
            "stability_gate": "PASS",
            "pit_grade": "B",
            "origin": origin,
            "permission_scope": "test",
            "semantic_equivalence": semantic_equivalence,
            "manifest_hash": f"manifest-{source_series_id}",
            "reviewer": "reviewer",
            "approved_at": now,
            "evidence_json": "{}",
            "updated_at": now,
            "usage_status": usage_status,
        },
    )


def _observe(
    store,
    *,
    series_id="A",
    source="wind",
    source_series_id="A.WIND",
    value=1.0,
    observation_date=CUTOFF,
    available_at=datetime(2026, 9, 1, 16, tzinfo=UTC),
    quality="ok",
):
    store.insert_observations(
        [
            {
                "series_id": series_id,
                "observation_date": observation_date,
                "available_at": available_at,
                "value": value,
                "source": source,
                "source_series_id": source_series_id,
                "vintage_date": None,
                "ingested_at": available_at,
                "quality": quality,
                "raw_file": "formal-gate-test",
            }
        ],
        run_id=f"formal-gate-{series_id}-{source_series_id}-{value}-{quality}",
    )


def _formal(store, *, usage_status="LIVE_VERIFIED", cutoff=CUTOFF):
    return latest_formal_observations_asof(
        store.conn,
        DECISION_TIME,
        required_usage_status=usage_status,
        market_data_cutoff=cutoff,
    )


def test_observation_without_acceptance_is_never_formal():
    store = DuckDBStore(":memory:")
    try:
        _observe(store, value=5.0)
        frame = _formal(store)
    finally:
        store.close()
    assert frame.empty


def test_approved_source_a_wins_over_unapproved_source_b():
    store = DuckDBStore(":memory:")
    try:
        _accept(store, source_series_id="APPROVED.A")
        _observe(store, source="wind", source_series_id="APPROVED.A", value=1.0)
        _observe(
            store,
            source="wind",
            source_series_id="UNAPPROVED.B",
            available_at=datetime(2026, 9, 1, 18, tzinfo=UTC),
            value=99.0,
        )
        frame = _formal(store)
    finally:
        store.close()
    assert len(frame) == 1
    assert frame.iloc[0]["source_series_id"] == "APPROVED.A"
    assert frame.iloc[0]["value"] == 1.0


def test_wrong_source_series_id_cannot_match_acceptance():
    store = DuckDBStore(":memory:")
    try:
        # Acceptance approved source_series_id "HSI" but the observation
        # claims "OTHER_HSI": same series_id, different provenance.
        _accept(store, series_id="HK_EQ", source_series_id="HSI")
        _observe(
            store,
            series_id="HK_EQ",
            source="wind",
            source_series_id="OTHER_HSI",
            value=7.0,
        )
        frame = _formal(store)
    finally:
        store.close()
    assert frame.empty


@pytest.mark.parametrize("quality", ["stale", "failed", "missing", "fallback", "unknown", ""])
def test_non_ok_or_unknown_quality_is_never_formal(quality):
    store = DuckDBStore(":memory:")
    try:
        _accept(store)
        _observe(store, quality=quality, value=3.0)
        frame = _formal(store)
    finally:
        store.close()
    assert frame.empty


def test_future_available_at_is_not_read():
    store = DuckDBStore(":memory:")
    try:
        _accept(store)
        _observe(
            store,
            available_at=DECISION_TIME + timedelta(hours=1),
            value=4.0,
        )
        frame = _formal(store)
    finally:
        store.close()
    assert frame.empty


def test_observation_beyond_market_cutoff_is_not_read():
    store = DuckDBStore(":memory:")
    try:
        _accept(store)
        _observe(
            store,
            observation_date=date(2026, 9, 1),
            available_at=datetime(2026, 9, 1, 16, tzinfo=UTC),
            value=8.0,
        )
        frame = _formal(store)
    finally:
        store.close()
    assert frame.empty


def test_approved_and_healthy_observation_is_formally_consumable():
    store = DuckDBStore(":memory:")
    try:
        _accept(store)
        _observe(store, value=10.0)
        frame = _formal(store)
    finally:
        store.close()
    assert len(frame) == 1
    assert frame.iloc[0]["value"] == 10.0
    assert frame.iloc[0]["source_series_id"] == "A.WIND"


def test_fixture_origin_registry_row_cannot_satisfy_formal_readiness(tmp_path):
    store = DuckDBStore(":memory:")
    try:
        _accept(store, source_series_id="FIXTURE.A", origin="FIXTURE")
        _observe(store, source="wind", source_series_id="FIXTURE.A", value=2.0)
        frame = _formal(store)
        readiness = generate_readiness(store, tmp_path)
    finally:
        store.close()
    assert frame.empty
    assert readiness["status"] == "DATA_BLOCKED"
    detail = next(
        item for item in readiness["series"] if item["series_id"] == "CN_EQ_LARGE"
    )
    assert "APPROVED_PROVENANCE_OBSERVATIONS_MISSING" in detail["blockers"]
