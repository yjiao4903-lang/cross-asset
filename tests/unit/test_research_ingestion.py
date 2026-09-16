import hashlib
from datetime import UTC, datetime

from cross_asset.ingestion.research import ingest_research_data
from cross_asset.storage import init_db, latest_formal_observations_asof


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


def _insert_acceptance(store, record, *, pit_grade=None):
    now = datetime(2026, 9, 2, 2, 0, 0, tzinfo=UTC)
    store.conn.execute(
        """INSERT INTO data_acceptance_registry
           (series_id,provider,source_series_id,status,tech_gate,legal_gate,pit_gate,
            stability_gate,pit_grade,origin,permission_scope,semantic_equivalence,
            manifest_hash,reviewer,approved_at,evidence_json,updated_at,usage_status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            record["series_id"],
            record["provider"],
            record["source_series_id"],
            "PASS",
            "PASS",
            "PASS",
            "PASS",
            "PASS",
            pit_grade or record["pit_grade"],
            "MANUAL",
            "research",
            True,
            record["raw_hash"],
            "reviewer",
            now,
            "{}",
            now,
            "RESEARCH_ADMISSIBLE",
        ],
    )


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

        _insert_acceptance(store, record)
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


def test_formal_pit_grades_a_and_b_are_admitted_and_visible(tmp_path):
    raw_file = tmp_path / "formal.csv"
    raw_file.write_text("source evidence\n", encoding="utf-8")
    policies = {"US_EQ": {"enabled": True}}

    for pit_grade in ("A", "B"):
        record = _record(raw_file)
        record["pit_grade"] = pit_grade
        store = init_db(":memory:")
        try:
            _insert_acceptance(store, record, pit_grade=pit_grade)
            admitted = ingest_research_data([record], policies=policies, store=store)
            assert admitted["status"] == "ADMITTED"
            formal = latest_formal_observations_asof(
                store.conn,
                datetime(2026, 9, 3, tzinfo=UTC),
                required_usage_status="RESEARCH_ADMISSIBLE",
            )
            assert len(formal) == 1
            assert formal.iloc[0]["source_series_id"] == "SPX"
        finally:
            store.close()


def test_grade_c_research_admission_is_explicitly_rejected(tmp_path):
    raw_file = tmp_path / "grade-c.csv"
    raw_file.write_text("source evidence\n", encoding="utf-8")
    record = _record(raw_file)
    record["pit_grade"] = "C"
    record["conservative_lag"] = "P30D"

    result = ingest_research_data(
        [record],
        policies={"US_EQ": {"enabled": True}},
        dry_run=True,
    )

    assert result["status"] == "REJECTED"
    assert result["written"] == 0
    assert result["errors"]["US_EQ"] == [
        "research_admissible_requires_pit_grade_a_or_b"
    ]


def test_grade_c_registry_cannot_produce_admitted_b_record(tmp_path):
    raw_file = tmp_path / "registry-c.csv"
    raw_file.write_text("source evidence\n", encoding="utf-8")
    record = _record(raw_file)
    store = init_db(":memory:")
    try:
        _insert_acceptance(store, record, pit_grade="C")
        result = ingest_research_data(
            [record],
            policies={"US_EQ": {"enabled": True}},
            store=store,
        )
        assert result["status"] == "REJECTED"
        assert result["written"] == 0
        assert result["errors"]["US_EQ"] == [
            "acceptance_registry_formal_pit_grade_a_or_b_required"
        ]
        assert store.conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 0
    finally:
        store.close()


def test_grade_c_registry_stays_invisible_to_sanctioned_formal_query(tmp_path):
    raw_file = tmp_path / "formal-query-c.csv"
    raw_file.write_text("source evidence\n", encoding="utf-8")
    record = _record(raw_file)
    store = init_db(":memory:")
    try:
        _insert_acceptance(store, record, pit_grade="C")
        store.insert_observations(
            [
                {
                    "series_id": "US_EQ",
                    "observation_date": "2020-01-02",
                    "available_at": datetime(2020, 1, 2, 16, 30, tzinfo=UTC),
                    "value": 100.0,
                    "source": "manual",
                    "source_series_id": "SPX",
                    "vintage_date": None,
                    "ingested_at": datetime(2020, 1, 2, 16, 30, tzinfo=UTC),
                    "quality": "ok",
                    "raw_file": str(raw_file),
                }
            ],
            run_id="grade-c-query-regression",
        )
        formal = latest_formal_observations_asof(
            store.conn,
            datetime(2026, 9, 3, tzinfo=UTC),
            required_usage_status="RESEARCH_ADMISSIBLE",
        )
        assert formal.empty
    finally:
        store.close()
