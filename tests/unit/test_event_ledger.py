from cross_asset.research.event_ledger import (
    ClaimLedger,
    EventObservation,
    ResearchClaim,
    evaluate_claim,
)


def claim(**kwargs):
    base = {
        "claim_id": "c1", "source": "house", "source_document": "doc-1",
        "published_at": "2026-09-01T07:00:00+08:00", "as_of": "2026-09-01T08:00:00+08:00",
        "target": "PMI", "target_unit": "index", "baseline": 50, "operator": ">=",
        "threshold": 50, "horizon": "next_release", "evaluation_window_start": "2026-09-01",
        "evaluation_window_end": "2026-10-01", "next_release_at": "2026-09-30T09:00:00+08:00",
        "evidence_refs": ("fixture:doc-1",),
    }
    base.update(kwargs)
    return ResearchClaim(**base)


def obs(value=51, available="2026-10-01T09:00:00+08:00", unit="index"):
    return EventObservation("PMI", value, unit, "2026-09", available, "fixture:actual")


def test_claim_statuses_use_release_and_available_at():
    assert evaluate_claim(claim(), now="2026-09-15T00:00:00+00:00", observation=obs()).status == "NOT_DUE"
    assert evaluate_claim(claim(), now="2026-10-02T00:00:00+00:00", observation=obs()).status == "SUPPORTED"
    assert evaluate_claim(claim(), now="2026-10-02T00:00:00+00:00", observation=obs(49)).status == "CONTRADICTED"
    assert evaluate_claim(claim(), now="2026-10-02T00:00:00+00:00", observation=None).status == "INSUFFICIENT"
    assert evaluate_claim(claim(), now="2026-10-02T00:00:00+00:00", observation=obs(51, unit="percent")).status == "INSUFFICIENT"
    assert evaluate_claim(claim(), now="2026-10-02T00:00:00+00:00", observation=EventObservation("PMI", 51, "index", "2025-09", "2026-10-01T09:00:00+08:00", "fixture:actual")).status == "INSUFFICIENT"


def test_ledger_is_append_only_and_revision_is_explicit():
    ledger = ClaimLedger().add(claim())
    ledger = ledger.revise("c1", threshold=52)
    assert ledger.latest("c1").revision == 2
    assert len(ledger.records()) == 2
    try:
        ledger.add(claim(threshold=53))
    except ValueError as exc:
        assert str(exc) == "claim_revision_conflict"
    else:
        raise AssertionError("conflicting same revision must be rejected")


def test_claim_pit_cutoff_rejects_late_publication_and_old_observation():
    late = claim(published_at="2026-10-01T09:00:00+08:00")
    assert evaluate_claim(late, now="2026-10-02T00:00:00+00:00", observation=obs()).status == "INSUFFICIENT"
    old = EventObservation("PMI", 51, "index", "2026-08", "2026-10-01T09:00:00+08:00", "fixture:old")
    assert evaluate_claim(claim(), now="2026-10-02T00:00:00+00:00", observation=old).status == "INSUFFICIENT"


def test_prediction_after_period_start_is_valid_but_same_day_date_freeze_is_not():
    late_period = claim(claim_id="c2", published_at="2026-09-20T09:00:00+08:00", as_of="2026-09-20T10:00:00+08:00")
    assert evaluate_claim(late_period, now="2026-10-02T00:00:00+00:00", observation=obs()).status == "SUPPORTED"
    ambiguous = claim(claim_id="c3", published_at="2026-09-20T09:00:00+08:00", as_of="2026-09-20")
    assert evaluate_claim(ambiguous, now="2026-10-02T00:00:00+00:00", observation=obs()).status == "INSUFFICIENT"


def test_freeze_after_release_is_not_a_valid_historical_evaluation():
    late_freeze = claim(
        claim_id="c4",
        as_of="2026-10-01T10:00:00+08:00",
        published_at="2026-09-20T09:00:00+08:00",
    )
    assert evaluate_claim(late_freeze, now="2026-10-02T00:00:00+00:00", observation=obs()).status == "INSUFFICIENT"


def test_evaluation_is_separate_persisted_append_only_record():
    ledger, record = ClaimLedger().add(claim()).evaluate("c1", now="2026-10-02T00:00:00+00:00", observation=obs())
    assert record.status == "SUPPORTED" and record.evidence_refs == ("fixture:actual",)
    restored = ClaimLedger.from_jsonl(ledger.to_jsonl())
    assert restored.evaluation_records() == [record.__dict__]
    ledger2, record2 = restored.evaluate("c1", now="2026-10-03T00:00:00+00:00", observation=obs())
    assert len(ledger2.evaluation_records()) == 2 and record2.evaluated_at != record.evaluated_at
    ledger3 = ledger2.add(claim())
    assert len(ledger3.evaluation_records()) == 2


def test_same_evaluation_identity_rejects_different_evidence():
    ledger, _ = ClaimLedger().add(claim()).evaluate("c1", now="2026-10-02T00:00:00+00:00", observation=obs())
    try:
        ledger.evaluate("c1", now="2026-10-02T00:00:00+00:00", observation=obs(49))
    except ValueError as exc:
        assert str(exc) == "evaluation_conflict"
    else:
        raise AssertionError("same evaluation identity must reject changed evidence")
