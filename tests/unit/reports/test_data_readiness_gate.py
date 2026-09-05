import json
from datetime import UTC, date, datetime

from cross_asset.reports.readiness import FIRST_REAL_E2E_PROFILE, generate_readiness
from cross_asset.storage import DuckDBStore
from cross_asset.storage.acceptance_registry import upsert_data_acceptance


def _accept(store: DuckDBStore, series_id: str, source_id: str | None = None) -> str:
    source_id = source_id or f"WIND::{series_id}"
    upsert_data_acceptance(
        store,
        {
            "series_id": series_id,
            "provider": "wind",
            "source_series_id": source_id,
            "status": "PASS",
            "tech_gate": "PASS",
            "legal_gate": "PASS",
            "pit_gate": "PASS",
            "stability_gate": "PASS",
            "pit_grade": "B",
            "origin": "LIVE",
            "permission_scope": "research",
            "semantic_equivalence": True,
            "manifest_hash": f"manifest-{series_id}",
            "reviewer": "reviewer",
            "approved_at": datetime(2026, 9, 1, tzinfo=UTC),
            "evidence_json": "{}",
            "updated_at": datetime(2026, 9, 1, tzinfo=UTC),
            "usage_status": "LIVE_VERIFIED",
        },
    )
    return source_id


def _observe(
    store: DuckDBStore,
    series_id: str,
    source_id: str,
    *,
    source: str = "wind",
) -> None:
    store.insert_observations(
        [
            {
                "series_id": series_id,
                "observation_date": date(2026, 8, 31),
                "available_at": datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
                "value": 1.0,
                "source": source,
                "source_series_id": source_id,
                "vintage_date": None,
                "ingested_at": datetime(2026, 9, 1, 1, 0, tzinfo=UTC),
                "quality": "ok",
                "raw_file": "test.csv",
            }
        ],
        run_id="readiness-test",
    )


def test_empty_db_is_data_blocked(tmp_path):
    store = DuckDBStore(":memory:")
    try:
        result = generate_readiness(store, tmp_path)
    finally:
        store.close()

    assert result["status"] == "DATA_BLOCKED"
    assert result["ready_series_count"] == 0
    assert result["pit_admissible"] is False


def test_unrelated_pass_and_observation_cannot_unlock_data_ready(tmp_path):
    store = DuckDBStore(":memory:")
    try:
        source_id = _accept(store, "DXY", "DXY.WIND")
        _observe(store, "DXY", source_id)
        result = generate_readiness(store, tmp_path)
    finally:
        store.close()

    assert result["accepted_pass"] == 1
    assert result["observations"] == 1
    assert result["status"] == "DATA_BLOCKED"
    assert result["ready_series_count"] == 0


def test_missing_one_required_observation_keeps_data_blocked(tmp_path):
    missing = "COPPER"
    store = DuckDBStore(":memory:")
    try:
        for series_id in FIRST_REAL_E2E_PROFILE:
            source_id = _accept(store, series_id)
            if series_id != missing:
                _observe(store, series_id, source_id)
        result = generate_readiness(store, tmp_path)
    finally:
        store.close()

    detail = next(item for item in result["series"] if item["series_id"] == missing)
    assert result["status"] == "DATA_BLOCKED"
    assert result["ready_series_count"] == len(FIRST_REAL_E2E_PROFILE) - 1
    assert detail["acceptance_pass"] is True
    assert detail["accepted_observation_rows"] == 0
    assert detail["blockers"] == ["ACCEPTED_SOURCE_OBSERVATIONS_MISSING"]


def test_all_six_exact_accepted_wind_sources_unlock_data_ready(tmp_path):
    store = DuckDBStore(":memory:")
    try:
        for series_id in FIRST_REAL_E2E_PROFILE:
            source_id = _accept(store, series_id)
            _observe(store, series_id, source_id)
        result = generate_readiness(store, tmp_path)
    finally:
        store.close()

    assert result["status"] == "DATA_READY"
    assert result["ready_series_count"] == len(FIRST_REAL_E2E_PROFILE)
    assert result["pit_admissible"] is True
    assert result["blockers"] == []
    assert all(item["accepted_observation_rows"] == 1 for item in result["series"])


def test_wrong_observation_provenance_does_not_satisfy_readiness(tmp_path):
    store = DuckDBStore(":memory:")
    try:
        for series_id in FIRST_REAL_E2E_PROFILE:
            source_id = _accept(store, series_id)
            if series_id == "US_EQ":
                _observe(store, series_id, "OTHER.SOURCE")
            else:
                _observe(store, series_id, source_id)
        result = generate_readiness(store, tmp_path)
    finally:
        store.close()

    us_eq = next(item for item in result["series"] if item["series_id"] == "US_EQ")
    assert result["status"] == "DATA_BLOCKED"
    assert us_eq["observation_rows"] == 1
    assert us_eq["accepted_observation_rows"] == 0
    assert "ACCEPTED_SOURCE_OBSERVATIONS_MISSING" in us_eq["blockers"]


def test_history_is_not_auto_promoted_by_minimal_data_readiness(tmp_path):
    store = DuckDBStore(":memory:")
    try:
        for series_id in FIRST_REAL_E2E_PROFILE:
            source_id = _accept(store, series_id)
            _observe(store, series_id, source_id)
        result = generate_readiness(store, tmp_path)
    finally:
        store.close()

    history = json.loads((tmp_path / "HISTORY_READY.json").read_text(encoding="utf-8"))
    assert result["status"] == "DATA_READY"
    assert history["status"] == "HISTORY_BLOCKED"
    assert history["history_completeness_established"] is False
