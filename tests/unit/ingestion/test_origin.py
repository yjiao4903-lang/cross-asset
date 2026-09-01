from cross_asset.ingestion.origin import (
    DataOrigin,
    OriginEvidence,
    summarize_origins,
    validate_origin_evidence,
    validate_run_manifest,
)


def test_mixed_origin_summary_and_legacy_unknown():
    rows=[{"metadata":{"origin":"FIXTURE"}},{"metadata":{"origin":"MANUAL"}},{"metadata":{}}]
    s=summarize_origins(rows); assert s["mixed"] and s["origin"]=="MIXED"

def test_fixture_contamination_and_live_evidence_gate():
    assert not validate_origin_evidence(OriginEvidence(DataOrigin.FIXTURE))[0]
    ok, errors=validate_origin_evidence(OriginEvidence(DataOrigin.LIVE)); assert not ok and "live_raw_file_required" in errors

def test_manual_and_secret_safe_manifest():
    assert validate_origin_evidence(OriginEvidence(DataOrigin.MANUAL,file_hash="sha",template_id="t",available_at="2025-01-01T00:00:00Z"))[0]
    result=validate_run_manifest({"origin":"LIVE","notes":"token=abc"}); assert not result["valid"]; assert "abc" not in str(result)
