from cross_asset.pit import PITGrade, classify_pit_grade
from cross_asset.storage import init_db
from cross_asset.storage.acceptance_registry import query_data_acceptance, upsert_data_acceptance


def _record(**overrides):
    value = {
        "series_id": "S", "provider": "p", "source_series_id": "x", "status": "PARTIAL",
        "tech_gate": "PASS", "legal_gate": "PASS", "pit_gate": "PASS", "stability_gate": "UNKNOWN",
        "pit_grade": "C", "origin": "MANUAL", "permission_scope": "research",
        "semantic_equivalence": True, "manifest_hash": "h", "reviewer": "r",
        "approved_at": "2025-01-01T00:00:00+00:00", "evidence_json": "{}", "updated_at": "2025-01-01T00:00:00",
    }
    value.update(overrides)
    return value


def test_pit_grade_rules_and_unknown_does_not_upgrade():
    assert classify_pit_grade({"vintage_rule": "true vintage and revision history"})[0] is PITGrade.A
    assert classify_pit_grade({"available_at_rule": "actual release timestamp"})[0] is PITGrade.B
    assert classify_pit_grade({"available_at_rule": "documented conservative lag"})[0] is PITGrade.C
    assert classify_pit_grade({"available_at_rule": "observation-date-only"})[0] is PITGrade.D
    assert classify_pit_grade({"available_at_rule": "TBD", "vintage_rule": "TBD"})[0] is None


def test_registry_partial_upsert_is_idempotent_and_queryable():
    store = init_db(":memory:")
    upsert_data_acceptance(store, _record())
    upsert_data_acceptance(store, _record(evidence_json='{"revision": 2}'))
    rows = query_data_acceptance(store, "S")
    assert len(rows) == 1 and rows[0]["status"] == "PARTIAL"


def test_registry_pass_requires_approval_and_grade_core_rules():
    store = init_db(":memory:")
    try:
        upsert_data_acceptance(store, _record(status="PASS", reviewer="TBD"))
    except ValueError as exc:
        assert "pass_requires_reviewer_approval" in str(exc)
    else:
        raise AssertionError("unapproved PASS must be rejected")
    try:
        upsert_data_acceptance(store, _record(status="PASS", pit_grade="D", reviewer="r"))
    except ValueError as exc:
        assert "pass_requires_pit_grade_a_or_b" in str(exc)
    else:
        raise AssertionError("D grade must not be registered as usable")


def test_c_and_d_are_allowed_as_partial_evidence_but_fail_never_registers():
    store = init_db(":memory:")
    for grade in ("C", "D"):
        upsert_data_acceptance(store, _record(series_id=f"S{grade}", pit_grade=grade))
    try:
        upsert_data_acceptance(store, _record(status="FAIL"))
    except ValueError as exc:
        assert "fail_cannot_be_registered" in str(exc)
    else:
        raise AssertionError("FAIL must remain in validation artifacts")


def test_pass_requires_all_gates_and_approved_a_or_b():
    store = init_db(":memory:")
    record = _record(status="PASS", pit_grade="A", stability_gate="UNKNOWN")
    try:
        upsert_data_acceptance(store, record)
    except ValueError as exc:
        assert "pass_requires_all_gates" in str(exc)
    else:
        raise AssertionError("PASS with incomplete gates must be rejected")
    record["stability_gate"] = "PASS"
    upsert_data_acceptance(store, record)
    assert query_data_acceptance(store, "S")[0]["status"] == "PASS"
