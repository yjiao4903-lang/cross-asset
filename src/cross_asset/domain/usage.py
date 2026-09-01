"""Explicit evidence usage state; states never upgrade implicitly."""
from enum import StrEnum


class UsageStatus(StrEnum):
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    RESEARCH_ADMISSIBLE = "RESEARCH_ADMISSIBLE"
    LIVE_VERIFIED = "LIVE_VERIFIED"


def validate_usage_status(value: str | UsageStatus | None) -> str:
    normalized = str(value.value if isinstance(value, UsageStatus) else value or "EVIDENCE_ONLY").upper()
    if normalized not in {item.value for item in UsageStatus}:
        raise ValueError("usage_status_invalid")
    return normalized
