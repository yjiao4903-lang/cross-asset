from datetime import UTC, date, datetime
from types import SimpleNamespace

import duckdb

from cross_asset.storage import DuckDBStore, latest_formal_observations_asof
from cross_asset.storage.acceptance_registry import (
    query_data_acceptance,
    upsert_data_acceptance,
)
from cross_asset.storage.schema import initialize_schema


def _record(usage_status: str, **overrides):
    record = {
        "series_id": "A",
        "provider": "wind",
        "source_series_id": "A.WIND",
        "status": "PASS",
        "tech_gate": "PASS",
        "legal_gate": "PASS",
        "pit_gate": "PASS",
        "stability_gate": "PASS",
        "pit_grade": "B",
        "origin": "LIVE",
        "permission_scope": "formal",
        "semantic_equivalence": True,
        "manifest_hash": f"manifest-{usage_status}",
        "reviewer": "reviewer",
        "approved_at": datetime(2026, 9, 1, tzinfo=UTC),
        "evidence_json": f'{{"usage":"{usage_status}"}}',
        "updated_at": datetime(2026, 9, 1, tzinfo=UTC),
        "usage_status": usage_status,
    }
    record.update(overrides)
    return record


def _primary_key_columns(connection, table: str) -> set[str]:
    return {
        row[1]
        for row in connection.execute(f"PRAGMA table_info('{table}')").fetchall()
        if bool(row[5])
    }


def test_research_and_live_admissions_coexist_without_overwrite():
    store = DuckDBStore(":memory:")
    try:
        upsert_data_acceptance(store, _record("RESEARCH_ADMISSIBLE"))
        upsert_data_acceptance(store, _record("LIVE_VERIFIED"))

        rows = query_data_acceptance(
            store,
            "A",
            "wind",
            "A.WIND",
        )
        assert {row["usage_status"] for row in rows} == {
            "RESEARCH_ADMISSIBLE",
            "LIVE_VERIFIED",
        }

        upsert_data_acceptance(
            store,
            _record(
                "RESEARCH_ADMISSIBLE",
                manifest_hash="research-revision-2",
                evidence_json='{"revision":2}',
            ),
        )
        research = query_data_acceptance(
            store,
            "A",
            "wind",
            "A.WIND",
            usage_status="RESEARCH_ADMISSIBLE",
        )
        live = query_data_acceptance(
            store,
            "A",
            "wind",
            "A.WIND",
            usage_status="LIVE_VERIFIED",
        )
        assert len(research) == 1
        assert len(live) == 1
        assert research[0]["manifest_hash"] == "research-revision-2"
        assert live[0]["manifest_hash"] == "manifest-LIVE_VERIFIED"
    finally:
        store.close()


def test_research_admission_does_not_implicitly_upgrade_to_live():
    store = DuckDBStore(":memory:")
    try:
        upsert_data_acceptance(store, _record("RESEARCH_ADMISSIBLE"))
        available_at = datetime(2026, 9, 1, 12, tzinfo=UTC)
        store.insert_observations(
            [
                {
                    "series_id": "A",
                    "observation_date": date(2026, 9, 1),
                    "available_at": available_at,
                    "value": 1.0,
                    "source": "wind",
                    "source_series_id": "A.WIND",
                    "vintage_date": None,
                    "ingested_at": available_at,
                    "quality": "ok",
                    "raw_file": "usage-identity-test",
                }
            ],
            run_id="usage-identity-test",
        )
        decision_time = datetime(2026, 9, 2, tzinfo=UTC)
        research = latest_formal_observations_asof(
            store.conn,
            decision_time,
            required_usage_status="RESEARCH_ADMISSIBLE",
        )
        live = latest_formal_observations_asof(
            store.conn,
            decision_time,
            required_usage_status="LIVE_VERIFIED",
        )
        assert len(research) == 1
        assert live.empty
    finally:
        store.close()


def test_legacy_three_part_registry_migrates_without_losing_row():
    connection = duckdb.connect(":memory:")
    connection.execute(
        """CREATE TABLE data_acceptance_registry (
            series_id VARCHAR NOT NULL,
            provider VARCHAR NOT NULL,
            source_series_id VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            tech_gate VARCHAR NOT NULL,
            legal_gate VARCHAR NOT NULL,
            pit_gate VARCHAR NOT NULL,
            stability_gate VARCHAR NOT NULL,
            pit_grade VARCHAR,
            origin VARCHAR NOT NULL,
            permission_scope VARCHAR,
            semantic_equivalence BOOLEAN,
            manifest_hash VARCHAR,
            reviewer VARCHAR,
            approved_at TIMESTAMP,
            evidence_json VARCHAR NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP NOT NULL,
            usage_status VARCHAR,
            PRIMARY KEY(series_id, provider, source_series_id)
        )"""
    )
    connection.execute(
        """INSERT INTO data_acceptance_registry VALUES (
            'LEGACY', 'manual', 'LEGACY.SOURCE', 'PARTIAL',
            'PASS', 'PASS', 'PASS', 'UNKNOWN', 'C', 'MANUAL',
            'research', TRUE, 'legacy-hash', 'reviewer',
            TIMESTAMP '2026-01-01 00:00:00', '{}',
            TIMESTAMP '2026-01-01 00:00:00', NULL
        )"""
    )

    initialize_schema(connection)
    store = SimpleNamespace(conn=connection)
    try:
        rows = query_data_acceptance(
            store,
            "LEGACY",
            "manual",
            "LEGACY.SOURCE",
            usage_status="EVIDENCE_ONLY",
        )
        assert len(rows) == 1
        assert rows[0]["manifest_hash"] == "legacy-hash"
        assert rows[0]["usage_status"] == "EVIDENCE_ONLY"
        assert _primary_key_columns(connection, "data_acceptance_registry") == {
            "series_id",
            "provider",
            "source_series_id",
            "usage_status",
        }

        upsert_data_acceptance(
            store,
            _record(
                "RESEARCH_ADMISSIBLE",
                series_id="LEGACY",
                provider="manual",
                source_series_id="LEGACY.SOURCE",
                origin="MANUAL",
            ),
        )
        assert len(
            query_data_acceptance(
                store,
                "LEGACY",
                "manual",
                "LEGACY.SOURCE",
            )
        ) == 2
    finally:
        connection.close()
