from datetime import date

import pytest

from cross_asset.operations.exchange_calendar import CalendarMetadata
from cross_asset.sprint2.runner import Sprint2BlockedError, run_preliminary
from cross_asset.storage import init_db


class _Calendar:
    metadata = CalendarMetadata("fake", "test", "1", ("XSHG", "XHKG"))

    def weekly_decision_dates(self, start, end):
        return [date(2026, 1, 2), date(2026, 1, 9)]


def test_missing_calendar_is_hard_blocked(monkeypatch, tmp_path):
    import pandas as pd

    monkeypatch.setattr(
        "cross_asset.sprint2.runner.load_wind_engineering_frame",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "observation_date": [date(2026, 1, 2)],
                "available_at": [pd.Timestamp("2026-01-03", tz="UTC")],
                "series_id": ["CN_EQ_LARGE"],
                "value": [1.0],
                "source_file_sha256": ["x"],
            }
        ),
    )

    def fail(*args, **kwargs):
        raise Sprint2BlockedError("BLOCKED: calendar unavailable")

    monkeypatch.setattr("cross_asset.sprint2.runner.cn_hk_calendar", fail)
    store = init_db(tmp_path / "blocked.duckdb")
    try:
        with pytest.raises(Sprint2BlockedError, match="BLOCKED"):
            run_preliminary(store.conn, output_dir=tmp_path / "blocked-artifacts")
    finally:
        store.close()


def test_runner_requires_explicit_calendar_adapter():
    assert _Calendar.metadata.provider == "fake"


def test_injected_calendar_writes_seven_partial_artifacts(monkeypatch, tmp_path):
    import pandas as pd

    frame = pd.DataFrame(
        {
            "observation_date": [date(2025, 12, 31), date(2026, 1, 2)] * 3,
            "available_at": [
                pd.Timestamp("2026-01-01", tz="UTC"),
                pd.Timestamp("2026-01-03", tz="UTC"),
            ]
            * 3,
            "series_id": ["CN_EQ_LARGE"] * 2 + ["HK_EQ"] * 2 + ["CN_BOND_10Y"] * 2,
            "value": [100.0, 101.0, 200.0, 202.0, 3.0, 2.9],
            "source_file_sha256": ["raw-a"] * 6,
        }
    )
    monkeypatch.setattr(
        "cross_asset.sprint2.runner.load_wind_engineering_frame", lambda *args, **kwargs: frame
    )
    store = init_db(tmp_path / "sprint2.duckdb")
    try:
        result = run_preliminary(
            store.conn,
            output_dir=tmp_path / "artifacts",
            calendar_adapter=_Calendar(),
        )
        assert result["status"] == "PARTIAL"
        assert result["exit"] is False
        assert result["gates"]["engineering_cutoff"] is True
        assert result["gates"]["formal_pit"] is False
        assert result["observations"] == 0
        assert len(result["artifacts"]) == 7
        assert all(
            (tmp_path / "artifacts" / name).is_file()
            for name in (
                "decisions.parquet",
                "returns.parquet",
                "scores.parquet",
                "allocations.parquet",
                "turnover.parquet",
                "costs.parquet",
                "summary.md",
            )
        )
        import duckdb

        check = duckdb.connect()
        try:
            cost_grid = check.execute(
                "SELECT DISTINCT cost_bps FROM read_parquet(?) ORDER BY 1",
                [str(tmp_path / "artifacts" / "costs.parquet")],
            ).fetchall()
        finally:
            check.close()
        assert cost_grid == [(0,), (5,), (10,), (20,), (30,)]
        summary = (tmp_path / "artifacts" / "summary.md").read_text(encoding="utf-8")
        assert "Worst1M" in summary
        assert "cost_sensitivity_bps: [0, 5, 10, 20, 30]" in summary
    finally:
        store.close()
