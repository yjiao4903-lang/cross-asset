from pathlib import Path

from cross_asset.research.weekly_annex import build_weekly_annex
from cross_asset.research.weekly_review import run_weekly_review


def test_annex_records_claims_without_changing_blocked_status(tmp_path):
    claims = tmp_path / "claims.json"
    claims.write_text(
        Path("examples/event_claims_fixture.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    scenarios = tmp_path / "scenarios.json"
    scenarios.write_text(
        Path("examples/scenario_fixture.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    annex = build_weekly_annex(
        now="2026-09-05T12:00:00+08:00",
        claims_json=claims,
        scenarios_json=scenarios,
    )
    statuses = {row["status"] for row in annex["claims"]["evaluations"]}
    assert statuses <= {"NOT_DUE", "INSUFFICIENT", "OPEN"}
    assert annex["scenarios"]["results"]
    assert annex["scenarios"]["results"][0]["status"] == "ESTIMATED_SCENARIO"
    assert "不改变本周立场" in annex["markdown"]


def test_missing_annex_inputs_are_skipped():
    annex = build_weekly_annex(now="2026-09-05T12:00:00+08:00")
    assert annex["claims"]["status"] == "SKIPPED"
    assert annex["scenarios"]["status"] == "SKIPPED"


def test_personal_weeks_compare_and_keep_us_eq_blocked(tmp_path):
    prior = run_weekly_review(
        as_of="2026-08-29",
        observations_json="examples/personal_week_20260828.json",
        output=tmp_path / "prior.md",
        snapshot_output=tmp_path / "prior.snapshot.json",
        week_end_date="2026-08-28",
        review_cutoff="2026-08-29T12:00:00+08:00",
    )
    current = run_weekly_review(
        as_of="2026-09-05",
        observations_json="examples/personal_week_20260904.json",
        output=tmp_path / "current.md",
        prior_snapshot=tmp_path / "prior.snapshot.json",
        snapshot_output=tmp_path / "current.snapshot.json",
        week_end_date="2026-09-04",
        review_cutoff="2026-09-05T12:00:00+08:00",
        claims_json="examples/event_claims_fixture.json",
        scenarios_json="examples/scenario_fixture.json",
    )
    assert prior["week_end"] == "2026-08-28"
    assert current["week_end"] == "2026-09-04"
    assert prior["status"] == "DATA_BLOCKED"
    assert current["status"] == "DATA_BLOCKED"
    assert "US_EQ" in current["missing_levels"]
    assert current["stance"]["decision"] == "不行动"
    text = Path(current["brief_output"]).read_text(encoding="utf-8")
    assert "观点账本与情景附件" in text
    assert any(
        item["label"].endswith("vs prior week")
        and item["value"] != "未提供上周快照"
        for item in current["prior_week_changes"]
    )
