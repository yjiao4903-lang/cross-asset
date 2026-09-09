"""Minimal, point-in-time event and research-claim ledger (DEVELOPMENT_PRIOR)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any

STATUSES = {"OPEN", "NOT_DUE", "SUPPORTED", "CONTRADICTED", "INSUFFICIENT"}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _parse(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).replace("Z", "+00:00")
        if len(text) == 7:  # YYYY-MM observation period
            text += "-01"
        if "T" in text and "+" not in text and "-" not in text.split("T", 1)[-1]:
            return None  # timestamp must carry an explicit offset
        parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_cutoff(value: Any) -> datetime | None:
    parsed = _parse(value)
    if parsed is not None and isinstance(value, str) and len(value) == 10:
        return parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


@dataclass(frozen=True)
class ResearchClaim:
    claim_id: str
    source: str
    source_document: str
    published_at: str | None
    as_of: str
    target: str
    target_unit: str
    baseline: float | None
    operator: str | None
    threshold: float | None
    horizon: str
    evaluation_window_start: str | None
    evaluation_window_end: str | None
    next_release_at: str | None
    evidence_refs: tuple[str, ...] = ()
    support: str | None = None
    counterevidence: str | None = None
    alternative_explanations: tuple[str, ...] = ()
    revision: int = 1
    status: str = "OPEN"

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"unsupported_claim_status:{self.status}")
        if not self.claim_id or not self.source or not self.source_document:
            raise ValueError("claim_identity_required")
        if not self.target or not self.target_unit or not self.as_of or not self.horizon:
            raise ValueError("claim_contract_required")
        if self.operator not in {None, ">=", "<=", ">", "<", "=="}:
            raise ValueError("unsupported_claim_operator")

    def content_hash(self) -> str:
        payload = asdict(self)
        payload.pop("revision", None)
        payload.pop("status", None)
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def revise(self, **changes: Any) -> ResearchClaim:
        return replace(self, **changes, revision=self.revision + 1, status="OPEN")


@dataclass(frozen=True)
class EventObservation:
    target: str
    value: float | None
    unit: str
    as_of: str
    available_at: str | None
    source: str
    revision: str | None = None


@dataclass(frozen=True)
class ClaimEvaluation:
    claim_id: str
    claim_revision: int
    status: str
    evaluated_at: str
    evidence_refs: tuple[str, ...] = ()
    observation_target: str | None = None
    observation_period: str | None = None
    observation_value: float | None = None
    observation_unit: str | None = None
    observation_available_at: str | None = None
    observation_revision: str | None = None

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError("unsupported_claim_status")


def evaluate_claim(claim: ResearchClaim, *, now: Any, observation: EventObservation | None) -> ResearchClaim:
    """Evaluate only evidence available by ``now``; unknown dates stay insufficient."""
    current = _parse(now)
    release = _parse(claim.next_release_at)
    frozen = _parse_cutoff(claim.as_of)
    published = _parse(claim.published_at)
    window_start = _parse(claim.evaluation_window_start)
    window_end = _parse(claim.evaluation_window_end)
    if current is None or not claim.next_release_at or frozen is None:
        return replace(claim, status="INSUFFICIENT")
    # A date-only ``as_of`` is a whole calendar-day cutoff.  Compare calendar
    # dates so a 09:00 publication on the stated day is not rejected.
    if published is None or published > frozen or published >= release:
        return replace(claim, status="INSUFFICIENT")
    # A date-only freeze has no intraday ordering.  Do not claim that a
    # same-day publication was known before that freeze.
    if isinstance(claim.as_of, str) and len(claim.as_of) == 10 and published.date() == frozen.date():
        return replace(claim, status="INSUFFICIENT")
    if release > current:
        return replace(claim, status="NOT_DUE")
    if observation is None or observation.value is None or not observation.available_at:
        return replace(claim, status="INSUFFICIENT")
    available = _parse(observation.available_at)
    if available is None or available > current or observation.unit != claim.target_unit or observation.target != claim.target:
        return replace(claim, status="INSUFFICIENT")
    observed_period = _parse(observation.as_of)
    if observed_period is None or (window_start and observed_period < window_start) or (window_end and observed_period > window_end):
        return replace(claim, status="INSUFFICIENT")
    if claim.operator is None or claim.threshold is None:
        return replace(claim, status="INSUFFICIENT")
    actual = float(observation.value)
    expected = float(claim.threshold)
    matched = {">=": actual >= expected, "<=": actual <= expected, ">": actual > expected, "<": actual < expected, "==": actual == expected}[claim.operator]
    return replace(claim, status="SUPPORTED" if matched else "CONTRADICTED", support=observation.source if matched else claim.support, counterevidence=observation.source if not matched else claim.counterevidence)


def evaluate_claim_record(claim: ResearchClaim, *, now: Any, observation: EventObservation | None) -> ClaimEvaluation:
    result = evaluate_claim(claim, now=now, observation=observation)
    is_outcome = observation is not None and result.status in {"SUPPORTED", "CONTRADICTED"}
    return ClaimEvaluation(claim.claim_id, claim.revision, result.status, _iso(now) or "", (observation.source,) if is_outcome else (),
                            observation.target if is_outcome else None, observation.as_of if is_outcome else None,
                            observation.value if is_outcome else None, observation.unit if is_outcome else None,
                            observation.available_at if is_outcome else None, observation.revision if is_outcome else None)


class ClaimLedger:
    """Append-only claim and evaluation ledger with optional JSONL persistence."""

    def __init__(self, claims: tuple[ResearchClaim, ...] = (), evaluations: tuple[ClaimEvaluation, ...] = ()):
        self._claims = claims
        self._evaluations = evaluations

    def add(self, claim: ResearchClaim) -> ClaimLedger:
        active = [item for item in self._claims if item.claim_id == claim.claim_id and item.revision == claim.revision]
        if active and active[-1].content_hash() != claim.content_hash():
            raise ValueError("claim_revision_conflict")
        if active:
            return self
        return ClaimLedger(self._claims + (claim,), self._evaluations)

    def revise(self, claim_id: str, **changes: Any) -> ClaimLedger:
        current = self.latest(claim_id)
        if current is None:
            raise KeyError("claim_not_found")
        return self.add(current.revise(**changes))

    def latest(self, claim_id: str) -> ResearchClaim | None:
        rows = [item for item in self._claims if item.claim_id == claim_id]
        return max(rows, key=lambda item: item.revision) if rows else None

    def records(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self._claims]

    def evaluate(self, claim_id: str, *, now: Any, observation: EventObservation | None) -> tuple[ClaimLedger, ClaimEvaluation]:
        claim = self.latest(claim_id)
        if claim is None:
            raise KeyError("claim_not_found")
        record = evaluate_claim_record(claim, now=now, observation=observation)
        same_key = [item for item in self._evaluations if (item.claim_id, item.claim_revision, item.evaluated_at) == (record.claim_id, record.claim_revision, record.evaluated_at)]
        if same_key:
            if same_key[-1] != record:
                raise ValueError("evaluation_conflict")
            return self, same_key[-1]
        return ClaimLedger(self._claims, self._evaluations + (record,)), record

    def evaluation_records(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self._evaluations]

    def to_jsonl(self) -> str:
        rows = [{"kind": "claim", **asdict(item)} for item in self._claims]
        rows.extend({"kind": "evaluation", **asdict(item)} for item in self._evaluations)
        return "\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else "")

    @classmethod
    def from_jsonl(cls, text: str) -> ClaimLedger:
        claims: list[ResearchClaim] = []
        evaluations: list[ClaimEvaluation] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            kind = row.pop("kind")
            if kind == "claim":
                row["evidence_refs"] = tuple(row.get("evidence_refs", ()))
                row["alternative_explanations"] = tuple(row.get("alternative_explanations", ()))
                claim = ResearchClaim(**row)
                if any(item.claim_id == claim.claim_id and item.revision == claim.revision and item.content_hash() != claim.content_hash() for item in claims):
                    raise ValueError("claim_revision_conflict")
                if not any(item.claim_id == claim.claim_id and item.revision == claim.revision for item in claims):
                    claims.append(claim)
            elif kind == "evaluation":
                row["evidence_refs"] = tuple(row.get("evidence_refs", ()))
                evaluation = ClaimEvaluation(**row)
                if any((item.claim_id, item.claim_revision, item.evaluated_at) == (evaluation.claim_id, evaluation.claim_revision, evaluation.evaluated_at) and item != evaluation for item in evaluations):
                    raise ValueError("evaluation_conflict")
                if not any(item == evaluation for item in evaluations):
                    evaluations.append(evaluation)
            else:
                raise ValueError("unsupported_ledger_record")
        return cls(tuple(claims), tuple(evaluations))


__all__ = ["STATUSES", "ClaimEvaluation", "ClaimLedger", "EventObservation", "ResearchClaim", "evaluate_claim", "evaluate_claim_record"]
