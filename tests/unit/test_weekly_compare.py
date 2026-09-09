from pathlib import Path

from cross_asset.research.weekly_compare import build_weekly_compare
from cross_asset.research.weekly_review import run_weekly_review


def test_compare_skips_without_prior():
    result = build_weekly_compare({"week_end": "2026-09-04"}, None, {"macro_boxes": []})
    assert result["status"] == "SKIPPED"
    assert "未提供上周快照" in result["markdown"]


def test_personal_weeks_wire_annex_and_compare(tmp_path):
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
    assert prior["status"] in {"READY", "PARTIAL"}
    assert current["status"] in {"READY", "PARTIAL"}
    assert "US_EQ" not in current["missing_levels"]
    assert current["stance"]["decision"] == "不行动"
    assert current["annex"]["claims_status"] != "SKIPPED"
    assert current["annex"]["scenarios_status"] != "SKIPPED"
    assert current["compare"]["status"] == "READY"
    text = Path(current["brief_output"]).read_text(encoding="utf-8")
    assert "观点账本与情景附件" in text
    assert "两周对照" in text
    assert any(
        item["label"].endswith("vs prior week")
        and item["value"] != "未提供上周快照"
        for item in current["prior_week_changes"]
    )
