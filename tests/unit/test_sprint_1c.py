from cross_asset.ingestion.research import ingest_research_data
from cross_asset.storage import init_db


def test_research_admission_rejects_disabled_policy_without_write():
    store = init_db(":memory:")
    result = ingest_research_data([{"series_id": "S", "usage_status": "EVIDENCE_ONLY"}], policies={"S": {"enabled": False}}, store=store)
    assert result["status"] == "REJECTED" and result["written"] == 0
    assert store.conn.execute("select count(*) from observations").fetchone()[0] == 0
    store.close()


def test_research_admission_grade_c_is_non_formal_even_with_warning_contract(tmp_path):
    raw = tmp_path / "raw.csv"
    raw.write_text("x", encoding="utf-8")
    record = {"series_id": "S", "usage_status": "RESEARCH_ADMISSIBLE", "reviewer": "r", "approved_at": "2026-01-01T00:00:00+00:00", "origin": "MANUAL", "pit_grade": "C", "raw_file": str(raw), "raw_hash": "bad", "source_contract": "official", "conservative_lag": True}
    result = ingest_research_data([record], policies={"S": {"enabled": True}})
    assert result["status"] == "REJECTED"
    assert result["written"] == 0
    assert result["errors"]["S"] == ["research_admissible_requires_pit_grade_a_or_b"]
