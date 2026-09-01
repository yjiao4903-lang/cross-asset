from cross_asset.domain.usage import UsageStatus, validate_usage_status
from cross_asset.pit import AvailabilityContract, AvailableAtPolicy
from cross_asset.storage import init_db
from cross_asset.storage.acceptance_registry import upsert_data_acceptance


def _record(**extra):
    row = {"series_id": "S", "provider": "p", "source_series_id": "s", "status": "PARTIAL", "tech_gate": "PASS", "legal_gate": "UNKNOWN", "pit_gate": "PARTIAL", "stability_gate": "PARTIAL", "pit_grade": "D", "origin": "LIVE", "evidence_json": "{}", "updated_at": "2026-01-01"}
    row.update(extra)
    return row


def test_usage_status_is_explicit_and_registry_migrates():
    assert validate_usage_status(UsageStatus.EVIDENCE_ONLY) == "EVIDENCE_ONLY"
    store = init_db(":memory:")
    saved = upsert_data_acceptance(store, _record())
    assert saved["usage_status"] == "EVIDENCE_ONLY"
    store.close()


def test_invalid_usage_status_rejected_without_upgrade():
    store = init_db(":memory:")
    try:
        upsert_data_acceptance(store, _record(usage_status="LIVE_VERIFIED"))
        saved = upsert_data_acceptance(store, _record(usage_status="EVIDENCE_ONLY"))
        assert saved["usage_status"] == "EVIDENCE_ONLY"
    finally:
        store.close()


def test_availability_policy_requires_timezone_evidence_and_lag():
    contract = AvailabilityContract(AvailableAtPolicy.CONSERVATIVE_LAG, "Asia/Shanghai", 24, "manual release evidence", "C")
    contract.validate()
