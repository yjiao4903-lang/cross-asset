import hashlib
from datetime import UTC, datetime

from cross_asset.ingestion.research import ingest_research_data
from cross_asset.storage import init_db


def _record(raw_file):
    raw_hash = hashlib.sha256(raw_file.read_bytes()).hexdigest()
    return {
        "series_id": "US_EQ",
        "provider": "manual",
        "source_series_id": "SPX",
        "usage_status": "RESEARCH_ADMISSIBLE",
        "reviewer": "reviewer",
        "approved_at": "2026-09-02T10:00:00+08:00",
        "origin": "MANUAL",
        "pit_grade": "B",
        "raw_hash": raw_hash,
        "raw_file": str(raw_file),
        "source_contract": "manual_csv_v1",
        "observations": [
            {
                "observation_date": "2020-01-02",
                "available_at": "2020-01-02T16:30:00+00:00",
                "value": 100.0,
            }
        ],
    }


def test_admitted_research_data_writes_only_after_registry_pass(tmp_path):
    raw_file = tmp_path / "raw.csv"
    raw_file.write_text("source evidence\n", encoding="utf-8")
    record = _record(raw_file)
    policies = {"US_EQ": {"enabled": True}}

    dry = ingest_research_data([record], policies=policies, dry_run=True)
    assert dry["status"] == "ADMISSIBLE"
    assert dry["candidate_rows"] == 1

    store = init_db(":memory:")
    try:
        blocked = ingest_research_data([record], policies=policies, store=store)
        assert blocked["status"] == "REJECTED"

        now = datetime(2026, 9, 2, 2, 0, 0, tzinfo=UTC)
        store.conn.execute(
            """INSERT INTO data_acceptance_registry
               (series_id,provider,source_series_id,status,tech_gate,legal_gate,pit_gate,
                stability_gate,pit_grade,origin,permission_scope,semantic_equivalence,
                manifest_hash,reviewer,approved_at,evidence_json,updated_at,usage_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                "US_EQ","manual","SPX","PASS","PASS","PASS","PASS","PASS","B","MANUAL",
                "research",True,record["raw_hash"],"reviewer",now,"{}",now,"RESEARCH_ADMISSIBLE",
            ],
        )
        admitted = ingest_research_data([record], policies=policies, store=store)
        assert admitted["status"] == "ADMITTED"
        assert admitted["written"] == 1
        assert store.conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 1

        repeated = ingest_research_data([record], policies=policies, store=store)
        assert repeated["status"] == "ADMITTED"
        assert repeated["written"] == 0
        assert repeated["reused"] is True
    finally:
        store.close()
