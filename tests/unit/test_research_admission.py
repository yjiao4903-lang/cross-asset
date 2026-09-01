from cross_asset.reports.research_admission import build_candidates


def test_research_admission_candidates_are_blocked_without_policy_or_approval():
    result = build_candidates()
    assert result["status"] == "BLOCKED"
    assert len(result["series"]) == 5
    assert all(item["status"] == "BLOCKED" for item in result["series"])
    assert all("policy_disabled" in item["blockers"] for item in result["series"])
