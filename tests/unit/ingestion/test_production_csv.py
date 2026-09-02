import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cross_asset.cli import app
from cross_asset.ingestion.production_csv import ProductionCSVError, ingest_production_csv
from cross_asset.storage import init_db

HEADER = "series_id,observation_date,value,available_at,source,source_series_id,vintage_date,quality\n"


def _csv(path: Path, rows: list[str]) -> Path:
    path.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def _valid_rows() -> list[str]:
    return [
        "CN_EQ_LARGE,2026-01-01,100,2026-01-02T00:00:00+08:00,wind,000300.SH,,ok",
        "HK_EQ,2026-01-01,200,2026-01-02T00:00:00+08:00,wind,HSI,,ok",
    ]


def test_valid_dry_run_has_no_database_or_archive_side_effects(tmp_path):
    path = _csv(tmp_path / "valid.csv", _valid_rows())
    database = tmp_path / "cross_asset.duckdb"
    raw_dir = tmp_path / "raw"

    result = ingest_production_csv(path, database=database, raw_dir=raw_dir, dry_run=True)

    assert result["status"] == "VALID"
    assert result["dry_run"] is True
    assert result["source"] == "wind"
    assert result["series_ids"] == ["CN_EQ_LARGE", "HK_EQ"]
    assert result["rows"] == 2
    assert not database.exists()
    assert not raw_dir.exists()


def test_missing_required_column_is_rejected_without_side_effects(tmp_path):
    path = tmp_path / "missing-source.csv"
    path.write_text(
        "series_id,observation_date,value,available_at,source_series_id\n"
        "CN_EQ_LARGE,2026-01-01,100,2026-01-02T00:00:00+08:00,000300.SH\n",
        encoding="utf-8",
    )
    database = tmp_path / "cross_asset.duckdb"
    raw_dir = tmp_path / "raw"

    with pytest.raises(ProductionCSVError):
        ingest_production_csv(path, database=database, raw_dir=raw_dir)

    assert not database.exists()
    assert not raw_dir.exists()


def test_successful_import_preserves_source_and_archives_original_csv(tmp_path):
    path = _csv(tmp_path / "valid.csv", _valid_rows())
    database = tmp_path / "cross_asset.duckdb"
    raw_dir = tmp_path / "raw"

    result = ingest_production_csv(path, database=database, raw_dir=raw_dir)

    assert result["status"] == "SUCCESS"
    assert result["rows_written"] == 2
    assert result["rows_existing"] == 0
    assert result["source"] == "wind"
    assert Path(result["raw_file"]).read_bytes() == path.read_bytes()
    store = init_db(database)
    try:
        rows = store.conn.execute(
            "SELECT series_id, source, source_series_id, available_at, raw_file FROM observations ORDER BY series_id"
        ).fetchall()
        assert rows == [
            (
                "CN_EQ_LARGE",
                "wind",
                "000300.SH",
                datetime(2026, 1, 1, 16, tzinfo=UTC).replace(tzinfo=None),
                result["raw_file"],
            ),
            (
                "HK_EQ",
                "wind",
                "HSI",
                datetime(2026, 1, 1, 16, tzinfo=UTC).replace(tzinfo=None),
                result["raw_file"],
            ),
        ]
    finally:
        store.close()


def test_reimport_is_idempotent(tmp_path):
    path = _csv(tmp_path / "valid.csv", _valid_rows())
    database = tmp_path / "cross_asset.duckdb"
    raw_dir = tmp_path / "raw"

    first = ingest_production_csv(path, database=database, raw_dir=raw_dir)
    second = ingest_production_csv(path, database=database, raw_dir=raw_dir)

    assert first["rows_written"] == 2
    assert second["rows_written"] == 0
    assert second["rows_existing"] == 2
    store = init_db(database)
    try:
        assert store.conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 2
    finally:
        store.close()


def test_naive_available_at_is_rejected(tmp_path):
    path = _csv(
        tmp_path / "naive.csv",
        ["CN_EQ_LARGE,2026-01-01,100,2026-01-02T00:00:00,wind,000300.SH,,ok"],
    )
    with pytest.raises(ProductionCSVError, match="validation failed"):
        ingest_production_csv(path, database=tmp_path / "db.duckdb", raw_dir=tmp_path / "raw")


@pytest.mark.parametrize("value", ["", "NaN", "inf", "-inf"])
def test_missing_or_non_finite_value_is_rejected(tmp_path, value):
    path = _csv(
        tmp_path / "invalid-value.csv",
        [f"CN_EQ_LARGE,2026-01-01,{value},2026-01-02T00:00:00+08:00,wind,000300.SH,,ok"],
    )
    with pytest.raises(ProductionCSVError):
        ingest_production_csv(path, database=tmp_path / "db.duckdb", raw_dir=tmp_path / "raw")


def test_unknown_series_is_rejected(tmp_path):
    path = _csv(
        tmp_path / "unknown.csv",
        ["FAKE_SERIES,2026-01-01,100,2026-01-02T00:00:00+08:00,wind,FAKE,,ok"],
    )
    with pytest.raises(ProductionCSVError, match="validation failed"):
        ingest_production_csv(path)


def test_mixed_source_is_rejected(tmp_path):
    path = _csv(
        tmp_path / "mixed.csv",
        [
            "CN_EQ_LARGE,2026-01-01,100,2026-01-02T00:00:00+08:00,wind,000300.SH,,ok",
            "HK_EQ,2026-01-01,200,2026-01-02T00:00:00+08:00,yahoo,^HSI,,ok",
        ],
    )
    with pytest.raises(ProductionCSVError):
        ingest_production_csv(path, database=tmp_path / "db.duckdb", raw_dir=tmp_path / "raw")


def test_malformed_file_causes_zero_observation_writes(tmp_path):
    path = _csv(
        tmp_path / "malformed.csv",
        [
            "CN_EQ_LARGE,2026-01-01,100,2026-01-02T00:00:00+08:00,wind,000300.SH,,ok",
            "HK_EQ,not-a-date,200,2026-01-02T00:00:00+08:00,wind,^HSI,,ok",
        ],
    )
    database = tmp_path / "db.duckdb"
    store = init_db(database)
    store.close()
    with pytest.raises(ProductionCSVError):
        ingest_production_csv(path, database=database, raw_dir=tmp_path / "raw")
    store = init_db(database)
    try:
        assert store.conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 0
        assert store.conn.execute("SELECT count(*) FROM ingestion_runs").fetchone()[0] == 0
    finally:
        store.close()


def test_production_csv_cli_help_and_dry_run(tmp_path):
    path = _csv(tmp_path / "valid.csv", _valid_rows())
    runner = CliRunner()

    help_result = runner.invoke(app, ["ingest-production-csv", "--help"])
    assert help_result.exit_code == 0, help_result.output
    assert "ingest-production-csv" in help_result.output

    dry_run_result = runner.invoke(app, ["ingest-production-csv", str(path), "--dry-run"])
    assert dry_run_result.exit_code == 0, dry_run_result.output
    payload = json.loads(dry_run_result.stdout)
    assert payload["status"] == "VALID"
    assert payload["dry_run"] is True
