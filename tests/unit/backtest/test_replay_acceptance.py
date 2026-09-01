import json
from pathlib import Path

import pandas as pd

from cross_asset.backtest.benchmarks import make_benchmark
from cross_asset.backtest.golden import fixed_fixture, snapshot
from cross_asset.backtest.replay import FullModelStrategy, HistoricalReplay


class _Strategy:
    def __call__(self, _info, _decision):
        return {"A": 0.6, "B": 0.4}

    def next_return(self, info, _allocation, _decision):
        assert info.empty or (pd.to_datetime(info["available_at"]) <= _decision).all()
        return 0.01


def _observations():
    return pd.DataFrame(
        [
            {"available_at": "2025-01-03", "observation_date": "2025-01-03"},
            {"available_at": "2025-01-10", "observation_date": "2025-01-10"},
        ]
    )


def test_replay_config_hash_artifacts_and_metadata(tmp_path):
    first = HistoricalReplay(_observations(), _Strategy(), config={"x": 1}).run(
        "2025-01-03", "2025-01-17"
    )
    second = HistoricalReplay(_observations(), _Strategy(), config={"x": 1}).run(
        "2025-01-03", "2025-01-17"
    )
    changed = HistoricalReplay(_observations(), _Strategy(), config={"x": 2}).run(
        "2025-01-03", "2025-01-17"
    )
    assert first.config_hash == second.config_hash
    assert first.config_hash != changed.config_hash
    out = first.write_artifacts(tmp_path)
    assert {"summary.md", "returns.parquet", "allocations.parquet", "scores.parquet"} <= {
        p.name for p in out.iterdir()
    }
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert first.model_version in summary and first.config_hash in summary
    assert "fixture: True" in summary


def test_benchmarks_have_distinct_explicit_semantics():
    assets = ["A", "B"]
    static = make_benchmark("STATIC", assets)({}, None)
    trend = make_benchmark("TREND_ONLY", assets)({}, None)
    full = make_benchmark("FULL_MODEL", assets)({"weights": {"A": 1.0}}, None)
    assert static.to_dict() == {"A": 0.5, "B": 0.5}
    assert trend.empty
    assert full.to_dict() == {"A": 1.0}


def test_macro_and_risk_benchmarks_isolate_inputs_and_metadata():
    assets = ["A", "B"]
    macro = make_benchmark("MACRO_ONLY", assets)
    risk = make_benchmark("RISK_ONLY", assets)
    macro_a = macro(pd.DataFrame([{"macro_score": 10, "trend": 1}]), None)
    macro_b = macro(pd.DataFrame([{"macro_score": 10, "trend": 999}]), None)
    risk_a = risk(pd.DataFrame([{"risk_score": 10, "macro": 1}]), None)
    risk_b = risk(pd.DataFrame([{"risk_score": 10, "macro": 999}]), None)
    assert macro_a.to_dict() == macro_b.to_dict()
    assert risk_a.to_dict() == risk_b.to_dict()
    assert macro_a.attrs["inputs_used"] != risk_a.attrs["inputs_used"]


def test_macro_risk_missing_data_safe_and_replay_metadata():
    assets = ["A", "B"]
    assert make_benchmark("MACRO_ONLY", assets)({}, None).attrs["unavailable"]
    replay = HistoricalReplay(pd.DataFrame([{"available_at": "2025-01-03", "observation_date": "2025-01-03"}]), make_benchmark("RISK_ONLY", assets)).run("2025-01-03", "2025-01-03")
    assert replay.benchmark_metadata["benchmark"] == "RISK_ONLY"


def test_macro_weights_normalize_and_asset_order_is_not_an_alpha_signal():
    assets = ["B", "A"]
    macro = make_benchmark("MACRO_ONLY", assets, strategic_weights={"B": 0.7, "A": 0.3})
    fallback = macro({"macro_score": 99}, None)
    assert fallback.to_dict() == {"B": 0.7, "A": 0.3}
    mapped = macro({"macro_weights": {"B": 2, "A": 1}}, None)
    assert mapped.to_dict() == {"B": 2 / 3, "A": 1 / 3}


def test_risk_only_uses_inverse_asset_risk_and_all_benchmarks_have_metadata():
    risk = make_benchmark("RISK_ONLY", ["A", "B"], protocol_version="p2", config_hash="c2", parameters={"x": 1})
    result = risk({"volatility": {"A": 1, "B": 2}}, None)
    assert result.to_dict() == {"A": 2 / 3, "B": 1 / 3}
    for name in ("STATIC", "TREND_ONLY", "MACRO_ONLY", "RISK_ONLY", "FULL_MODEL"):
        output = make_benchmark(name, ["A", "B"])({}, None)
        assert {"benchmark", "inputs_used", "parameters", "protocol_version", "config_hash", "unavailable", "reason"} <= set(output.attrs)


def test_five_split_goldens_exist_and_are_json():
    root = Path("tests/golden/full_pipeline")
    names = {"market_state.json", "macro_state.json", "style_state.json", "asset_scores.json", "allocation.json"}
    assert names <= {p.name for p in root.glob("*.json")}
    for name in names:
        json.loads((root / name).read_text(encoding="utf-8"))


def test_full_pipeline_snapshot_matches_golden_exactly():
    root = Path("tests/golden/full_pipeline")
    actual = snapshot()
    expected = {
        name: json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
        for name in actual
    }
    assert actual == expected
    assert snapshot() == actual


def test_future_revision_does_not_change_prior_snapshot():
    rows = fixed_fixture()
    rows.loc[len(rows)] = {
        "series_id": "A",
        "observation_date": "2025-12-30",
        "available_at": "2026-01-15T00:00:00Z",
        "value": 999.0,
    }
    # The fixed snapshot's cutoff excludes the future release by construction.
    assert snapshot(rows) == snapshot(fixed_fixture())


def test_full_model_calls_engine_chain_and_realizes_next_period_return(tmp_path):
    rows = []
    for i in range(25):
        day = pd.Timestamp("2025-01-03") + pd.Timedelta(days=i)
        rows.extend(
            [
                {"series_id": "A", "observation_date": day, "available_at": day, "value": 100 + i},
                {"series_id": "B", "observation_date": day, "available_at": day, "value": 100},
            ]
        )
    strategy = FullModelStrategy(["A", "B"])
    result = HistoricalReplay(pd.DataFrame(rows), strategy).run("2025-01-03", "2025-01-24")
    assert len(result.returns) > 0 and result.returns.sum() > 0
    assert not result.scores.empty and result.decisions
    assert {"market", "macro", "style", "asset", "allocation"} <= set(result.decisions[0]["model_versions"])
    out = result.write_artifacts(tmp_path)
    assert (out / "decisions.json").exists()
