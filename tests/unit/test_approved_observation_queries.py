from datetime import UTC, date, datetime

from cross_asset.storage import (
    DuckDBStore,
    approved_observations_asof,
    latest_approved_observations_asof,
)
from cross_asset.storage.acceptance_registry import upsert_data_acceptance


def _accept(
    store: DuckDBStore,
    *,
    series_id: str = "A",
    provider: str = "wind",
    source_series_id: str = "A.WIND",
    usage_status: str = "LIVE_VERIFIED",
    semantic_equivalence: bool = True,
) -> None:
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
            "origin": "LIVE",
            "permission_scope": "research",
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
    store: DuckDBStore,
    *,
    source: str,
    source_series_id: str,
    observation_date: date = date(2026, 8, 31),
    available_at: datetime = datetime(2026, 9, 1, 16, tzinfo=UTC),
    value: float = 1.0,
) -> None:
    store.insert_observations(
        [
            {
                "series_id": "A",
                "observation_date": observation_date,
                "available_at": available_at,
                "value": value,
                "source": source,
                "source_series_id": source_series_id,
                "vintage_date": None,
                "ingested_at": available_at,
                "quality": "ok",
                "raw_file": "query-test.csv",
            }
        ],
        run_id=f"query-test-{source_series_id}-{value}",
    )


def test_unapproved_alternative_source_is_never_consumed():
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

        rows = approved_observations_asof(
            store.conn,
            datetime(2026, 9, 2, tzinfo=UTC),
            required_usage_status="LIVE_VERIFIED",
            series_id="A",
        ).fetchall()
        latest = latest_approved_observations_asof(
            store.conn,
            datetime(2026, 9, 2, tzinfo=UTC),
            required_usage_status="LIVE_VERIFIED",
            series_id="A",
        ).fetchall()
    finally:
        store.close()

    assert len(rows) == 1
    assert rows[0][5] == "APPROVED.A"
    assert len(latest) == 1
    assert latest[0][5] == "APPROVED.A"
    assert latest[0][3] == 1.0


def test_usage_status_is_part_of_formal_consumption_identity():
    store = DuckDBStore(":memory:")
    try:
        _accept(
            store,
            source_series_id="RESEARCH.A",
            usage_status="RESEARCH_ADMISSIBLE",
        )
        _observe(store, source="wind", source_series_id="RESEARCH.A")

        live = approved_observations_asof(
            store.conn,
            datetime(2026, 9, 2, tzinfo=UTC),
            required_usage_status="LIVE_VERIFIED",
        ).fetchall()
        research = approved_observations_asof(
            store.conn,
            datetime(2026, 9, 2, tzinfo=UTC),
            required_usage_status="RESEARCH_ADMISSIBLE",
        ).fetchall()
    finally:
        store.close()

    assert live == []
    assert len(research) == 1


def test_provider_matches_case_insensitively_but_source_series_id_is_exact():
    store = DuckDBStore(":memory:")
    try:
        _accept(store, provider="wind", source_series_id="EXACT.A")
        _observe(store, source="WIND", source_series_id="EXACT.A", value=2.0)
        _observe(store, source="wind", source_series_id="exact.a", value=3.0)

        rows = approved_observations_asof(
            store.conn,
            datetime(2026, 9, 2, tzinfo=UTC),
            required_usage_status="LIVE_VERIFIED",
        ).fetchall()
    finally:
        store.close()

    assert len(rows) == 1
    assert rows[0][5] == "EXACT.A"
    assert rows[0][3] == 2.0


def test_market_cutoff_and_decision_time_are_both_enforced():
    store = DuckDBStore(":memory:")
    try:
        _accept(store, source_series_id="APPROVED.A")
        _observe(store, source="wind", source_series_id="APPROVED.A", value=1.0)
        _observe(
            store,
            source="wind",
            source_series_id="APPROVED.A",
            observation_date=date(2026, 9, 1),
            available_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
            value=2.0,
        )
        _observe(
            store,
            source="wind",
            source_series_id="APPROVED.A",
            observation_date=date(2026, 8, 30),
            available_at=datetime(2026, 9, 3, 12, tzinfo=UTC),
            value=3.0,
        )

        rows = approved_observations_asof(
            store.conn,
            datetime(2026, 9, 2, 23, 59, tzinfo=UTC),
            required_usage_status="LIVE_VERIFIED",
            market_data_cutoff=date(2026, 8, 31),
        ).fetchall()
    finally:
        store.close()

    assert len(rows) == 1
    assert rows[0][1] == date(2026, 8, 31)
    assert rows[0][3] == 1.0


def test_semantic_equivalence_is_required_even_for_registry_pass():
    store = DuckDBStore(":memory:")
    try:
        _accept(
            store,
            source_series_id="NON_EQUIVALENT.A",
            semantic_equivalence=False,
        )
        _observe(store, source="wind", source_series_id="NON_EQUIVALENT.A")

        rows = approved_observations_asof(
            store.conn,
            datetime(2026, 9, 2, tzinfo=UTC),
            required_usage_status="LIVE_VERIFIED",
        ).fetchall()
    finally:
        store.close()

    assert rows == []
