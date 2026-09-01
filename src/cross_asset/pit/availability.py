"""Explicit available_at policy contract, separate from PIT grades."""
from dataclasses import dataclass
from enum import StrEnum


class AvailableAtPolicy(StrEnum):
    EXACT = "exact"
    RELEASE_DATE_EOD = "release_date_eod"
    NEXT_SESSION = "next_session"
    CONSERVATIVE_LAG = "conservative_lag"


@dataclass(frozen=True)
class AvailabilityContract:
    policy: AvailableAtPolicy
    timezone: str
    lag_hours: float | None = None
    evidence: str | None = None
    pit_grade: str | None = None

    def validate(self) -> None:
        if not self.timezone:
            raise ValueError("availability_timezone_required")
        if self.policy is AvailableAtPolicy.CONSERVATIVE_LAG and (self.lag_hours is None or self.lag_hours < 0):
            raise ValueError("conservative_lag_required")
        if not self.evidence:
            raise ValueError("availability_evidence_required")
