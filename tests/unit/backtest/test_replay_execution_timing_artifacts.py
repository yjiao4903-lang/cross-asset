import json

import pandas as pd
import yaml

from cross_asset.backtest.replay import HistoricalReplay
from cross_asset.backtest.returns import AssetReturnSpec


class _AuditedStrategy:
    def __init__(self):
        self.return_specs = {
            "A": AssetReturnSpec("A", kind="price"),
            "CASH": AssetReturnSpec(None, kind="cash"),
        }
        self.last_scores = {}
        self.last_decision = None

    def __call__(self, _info, decision):
        self.last_decision = {
            "asset_scores": {},
            "attribution": {},
            "signal_components": {},
            "model_versions": {"fixture": "v1"},
            "data_cutoff": decision,
            "missing_signal_assets": [],
        }
        return {"A": 0.5, "CASH": 0.5}


def _observations():
    return pd.DataFrame(
        [
            {
                "series_id": "A",
                "observation_date": "2026-09-04",
                "available_at": "2026-09-04T12:00:00Z",
                "value": 100.0,
            },
            {
                "series_id": "A",
                "observation_date": "2026-09-11",
                "available_at": "2026-09-11T12:00:00Z",
                "value": 110.0,
            },
        ]
    )


def _calendar(tmp_path):
    path = tmp_path / "calendars.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "calendars": {
                    "CN": {
                        "calendar_id": "CN_TEST",
                        "capability_status": "VERIFIED",
                        "timezone": "Asia/Shanghai",
                        "source": "fixture",
                        "source_version": "1",
                        "version": "fixture-v1",
                        "regular_close": "15:00",
                        "verified": True,
                        "evidence": ["fixture"],
                        "reviewer": "test",
                        "approved_at": "2026-01-01T00:00:00+08:00",
                        "covered_years": [2026],
                        "holidays": [],
                        "early_closes": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _run(tmp_path, market_map):
    return HistoricalReplay(
        _observations(),
        _AuditedStrategy(),
        asset_market_map=market_map,
        calendar_config=_calendar(tmp_path),
    ).run(
        start=pd.Timestamp("2026-09-04T12:00:00Z"),
        end=pd.Timestamp("2026-09-11T12:00:00Z"),
    )


def test_historical_replay_records_resolved_trade_and_terminal_no_trade(tmp_path):
    result = _run(tmp_path, {"A": "CN"})

    assert result.execution_timing[0]["status"] == "RESOLVED"
    assert result.execution_timing[0]["by_asset"]["A"]["market"] == "CN"
    assert result.execution_timing[0]["by_asset"]["A"]["execution_price_at"] is not None
    assert result.execution_timing[-1]["status"] == "NOT_APPLICABLE"
    assert result.execution_timing[-1]["reason"] == "terminal_no_trade"
    assert result.decisions[0]["execution_timing"] == result.execution_timing[0]
    assert result.decisions[0]["return_timing_basis"] == "decision_to_next_decision_research_proxy"
    assert result.decisions[0]["performance_semantics"] == "research_proxy_not_investor_realizable"


def test_replay_missing_market_mapping_is_auditable_and_summary_stays_research_proxy(tmp_path):
    result = _run(tmp_path, {})
    assert result.execution_timing[0]["status"] == "BLOCKED"
    assert result.execution_timing[0]["blockers"] == ["A:market_mapping_missing"]

    output = result.write_artifacts(tmp_path / "artifacts")
    timing = json.loads((output / "execution_timing.json").read_text(encoding="utf-8"))
    summary = (output / "summary.md").read_text(encoding="utf-8")

    assert timing[0]["status"] == "BLOCKED"
    assert "execution_timing_status: BLOCKED" in summary
    assert "return_timing_basis: decision_to_next_decision_research_proxy" in summary
    assert "performance_semantics: research_proxy_not_investor_realizable" in summary
    assert "not investor-realizable investment performance" in summary
