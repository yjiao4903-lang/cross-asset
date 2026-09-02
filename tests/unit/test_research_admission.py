import hashlib
import json

from cross_asset.reports.research_admission import build_candidates


def test_research_admission_candidates_are_blocked_without_policy_or_approval(tmp_path):
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    series = {}
    hashes = {}
    for code in ("CPIAUCSL", "PCEPILFE", "UNRATE", "ICSA", "INDPRO"):
        raw_path = raw_root / f"{code}.json"
        payload = {
            "observations": [
                {
                    "date": "2026-01-01",
                    "realtime_start": "2026-01-15",
                    "value": "1.0",
                }
            ]
        }
        raw_path.write_text(json.dumps(payload), encoding="utf-8")
        digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        series[code] = {
            "source_series_id": code,
            "raw_path": str(raw_path),
            "row_count": 1,
        }
        hashes[code] = digest

    batch_path = tmp_path / "batch.json"
    batch_path.write_text(
        json.dumps({"series": series, "raw_sha256": hashes}),
        encoding="utf-8",
    )

    result = build_candidates(batch_path=batch_path)
    assert result["status"] == "BLOCKED"
    assert len(result["series"]) == 5
    assert all(item["status"] == "BLOCKED" for item in result["series"])
    assert all("policy_disabled" in item["blockers"] for item in result["series"])
