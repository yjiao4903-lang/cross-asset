import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from cross_asset.cli import app
from cross_asset.storage import DuckDBStore, latest_observations_asof

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "marco_integration_v1"
DECISION_DATE = date(2026, 9, 2)
MARKET_CUTOFF = date(2026, 8, 31)


def _seed_minimal_real_style_db(path: Path) -> None:
    series = {
        "CN_EQ_LARGE": (100.0, 0.60),
        "HK_EQ": (100.0, 0.45),
        "US_EQ": (100.0, 0.50),
        "CN_BOND_10Y": (2.5, -0.002),
        "GOLD": (1800.0, 1.20),
        "COPPER": (4.0, 0.006),
    }
    start = date(2026, 7, 20)
    rows = []
    for index in range((MARKET_CUTOFF - start).days + 1):
        observation_date = start + timedelta(days=index)
        available_at = datetime.combine(
            observation_date,
            datetime.min.time(),
            tzinfo=UTC,
        ) + timedelta(hours=16)
        for series_id, (base, slope) in series.items():
            rows.append(
                {
                    "series_id": series_id,
                    "observation_date": observation_date,
                    "available_at": available_at,
                    "value": base + slope * index,
                    "source": "minimal-real-style",
                    "source_series_id": series_id,
                    "vintage_date": None,
                    "ingested_at": available_at,
                    "quality": "ok",
                    "raw_file": "candidate-real-style-input",
                }
            )

    # This row is available before the decision time but must be excluded by
    # the Marco market data cutoff.
    future_date = date(2026, 9, 1)
    future_available_at = datetime(2026, 9, 2, 12, tzinfo=UTC)
    for series_id, (base, slope) in series.items():
        rows.append(
            {
                "series_id": series_id,
                "observation_date": future_date,
                "available_at": future_available_at,
                "value": base + slope * 99,
                "source": "minimal-real-style",
                "source_series_id": series_id,
                "vintage_date": None,
                "ingested_at": future_available_at,
                "quality": "ok",
                "raw_file": "candidate-real-style-input",
            }
        )

    store = DuckDBStore(path)
    try:
        store.insert_observations(rows, run_id="first-real-marco-cross-regression")
    finally:
        store.close()


def test_marco_provider_score_allocation_respects_market_cutoff(tmp_path):
    database = tmp_path / "cross_asset.duckdb"
    _seed_minimal_real_style_db(database)

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

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "SUCCESS"
    assert payload["contract_status"] == "PASS"
    assert payload["allocation_status"] == "ACTIVE"
    assert payload["data_cutoff"]["cross_market"] == str(MARKET_CUTOFF)

    store = DuckDBStore(database)
    try:
        selected = latest_observations_asof(
            store.conn,
            datetime(2026, 9, 2, 23, 59, 59, tzinfo=UTC),
            market_data_cutoff=MARKET_CUTOFF,
        ).df()
    finally:
        store.close()
    assert not selected.empty
    assert selected["observation_date"].max().date() == MARKET_CUTOFF
