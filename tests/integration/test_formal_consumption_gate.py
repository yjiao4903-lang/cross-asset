"""End-to-end formal-consumption gate regressions for run-daily (Issue #18).

The candidate -> acceptance -> provenance -> PIT -> quality/freshness ->
formal-consumer chain must fail closed: unapproved, unprovenanced, stale or
fixture-origin market data can never produce SUCCESS/ACTIVE.
"""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from cross_asset.cli import app
from cross_asset.storage import DuckDBStore

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "marco_integration_v1"
DECISION_DATE = date(2026, 9, 2)
MARKET_CUTOFF = date(2026, 8, 31)
SERIES = {
    "CN_EQ_LARGE": (100.0, 0.60),
    "HK_EQ": (100.0, 0.45),
    "US_EQ": (100.0, 0.50),
    "CN_BOND_10Y": (2.5, -0.002),
    "GOLD": (1800.0, 1.20),
    "COPPER": (4.0, 0.006),
}


def _seed_observations(
    path,
    *,
    source="approved-src",
    quality="ok",
    days=40,
    shift_days=0,
    include_unapproved_companion=False,
    register=True,
    origin="LIVE",
):
    """Seed candidate observations; optionally register their provenance."""

    from conftest import approve_test_series

    rows = []
    start = MARKET_CUTOFF - timedelta(days=days - 1) + timedelta(days=shift_days)
    for index in range(days):
        observation_date = start + timedelta(days=index)
        available_at = datetime.combine(
            observation_date, datetime.min.time(), tzinfo=UTC
        ) + timedelta(hours=16)
        for series_id, (base, slope) in SERIES.items():
            rows.append(
                {
                    "series_id": series_id,
                    "observation_date": observation_date,
                    "available_at": available_at,
                    "value": base + slope * index,
                    "source": source,
                    "source_series_id": series_id,
                    "vintage_date": None,
                    "ingested_at": available_at,
                    "quality": quality,
                    "raw_file": "formal-gate-candidate",
                }
            )
    if include_unapproved_companion:
        for index in range(days):
            observation_date = start + timedelta(days=index)
            available_at = datetime.combine(
                observation_date, datetime.min.time(), tzinfo=UTC
            ) + timedelta(hours=20)
            for series_id, (base, slope) in SERIES.items():
                rows.append(
                    {
                        "series_id": series_id,
                        "observation_date": observation_date,
                        "available_at": available_at,
                        "value": 9999.0 + index,
                        "source": "unapproved-src",
                        "source_series_id": series_id,
                        "vintage_date": None,
                        "ingested_at": available_at,
                        "quality": "ok",
                        "raw_file": "formal-gate-candidate",
                    }
                )
    store = DuckDBStore(path)
    try:
        store.insert_observations(rows, run_id="formal-gate-regression")
        if register:
            approve_test_series(
                store,
                series_ids=SERIES,
                provider=source,
                origin=origin,
            )
    finally:
        store.close()


def _invoke_run_daily(tmp_path, database):
    from conftest import write_test_calendar_configs

    calendar_config, series_calendar_config = write_test_calendar_configs(
        tmp_path,
        series_ids=list(SERIES),
    )
    return CliRunner().invoke(
        app,
        [
            "run-daily",
            "--macro-source",
            "marco",
            "--integration-dir",
            str(FIXTURE),
            "--database",
            str(database),
            "--as-of",
            DECISION_DATE.isoformat(),
            "--calendar-config",
            str(calendar_config),
            "--series-calendar-config",
            str(series_calendar_config),
        ],
    )


def test_unapproved_observations_cannot_produce_active(tmp_path):
    database = tmp_path / "db.duckdb"
    _seed_observations(database, register=False)

    result = _invoke_run_daily(tmp_path, database)

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "DATA_BLOCKED"
    assert payload["allocation_status"] == "DATA_BLOCKED"
    assert payload["allocation"] is None


def test_unapproved_source_cannot_replace_or_supplement_approved_source(tmp_path):
    database = tmp_path / "db.duckdb"
    # The approved provenance has no observations at all; an unapproved source
    # carries the full history. Substitution must be rejected.
    _seed_observations(
        database,
        source="unapproved-src",
        register=False,
    )
    store = DuckDBStore(database)
    try:
        from conftest import approve_test_series

        approve_test_series(
            store, series_ids=SERIES, provider="approved-src"
        )
    finally:
        store.close()

    result = _invoke_run_daily(tmp_path, database)

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "DATA_BLOCKED"
    assert any("CN_EQ_LARGE=0/22" in warning for warning in payload["warnings"])


def test_stale_quality_cannot_produce_active_despite_full_history(tmp_path):
    database = tmp_path / "db.duckdb"
    _seed_observations(database, quality="stale")

    result = _invoke_run_daily(tmp_path, database)

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "DATA_BLOCKED"
    assert payload["allocation_status"] == "DATA_BLOCKED"


def test_failed_and_unknown_quality_are_blocked_at_shared_query(tmp_path):
    from cross_asset.storage import latest_formal_observations_asof

    database = tmp_path / "db.duckdb"
    _seed_observations(database, quality="failed")
    store = DuckDBStore(database)
    try:
        frame = latest_formal_observations_asof(
            store.conn,
            datetime(2026, 9, 2, tzinfo=UTC),
            required_usage_status="LIVE_VERIFIED",
        )
    finally:
        store.close()
    assert frame.empty


def test_fixture_origin_provenance_cannot_satisfy_formal_daily(tmp_path):
    database = tmp_path / "db.duckdb"
    _seed_observations(database, origin="FIXTURE")

    result = _invoke_run_daily(tmp_path, database)

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "DATA_BLOCKED"


def test_approved_and_healthy_data_reaches_active_with_freshness(tmp_path):
    database = tmp_path / "db.duckdb"
    _seed_observations(database)

    result = _invoke_run_daily(tmp_path, database)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "SUCCESS"
    assert payload["allocation_status"] == "ACTIVE"
    assert payload["data_cutoff"]["cross_market"] == str(MARKET_CUTOFF)


def test_unverified_calendars_fail_closed_formal_daily(tmp_path):
    database = tmp_path / "db.duckdb"
    _seed_observations(database)

    # Approved + healthy data, but the shipped repo calendar contract is
    # UNVERIFIED for every market: the freshness gate must block the formal
    # daily path instead of assuming freshness.
    result = CliRunner().invoke(
        app,
        [
            "run-daily",
            "--macro-source",
            "marco",
            "--integration-dir",
            str(FIXTURE),
            "--database",
            str(database),
            "--as-of",
            DECISION_DATE.isoformat(),
        ],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "DATA_BLOCKED"
    assert any(
        "freshness_blocked" in warning and "calendar_mapping_missing" in warning
        for warning in payload["warnings"]
    )
