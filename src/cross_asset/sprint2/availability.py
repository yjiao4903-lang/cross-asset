"""Series-level available_at policies; no implicit global fallback is allowed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AvailabilityPolicy:
    series_id: str
    provider: str
    rule: str
    lag_days: int | None
    temporary: bool
    quality: str
    evidence_status: str

    def validate(self) -> None:
        if not self.series_id or self.provider != "Wind":
            raise ValueError("wind_series_provider_required")
        if self.rule != "conservative_lag":
            raise ValueError("wind_macro_policy_must_be_conservative_lag")
        if self.lag_days != 45:
            raise ValueError("temporary_wind_policy_must_be_plus_45_days")
        if self.temporary is not True or self.quality != "low":
            raise ValueError("temporary_plus_45_requires_explicit_temporary_true_quality_low")
        if self.evidence_status != "UNKNOWN":
            raise ValueError("unknown_release_evidence_must_remain_unknown")


def validate_availability_policies(raw: Any) -> tuple[AvailabilityPolicy, ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("series_level_availability_policies_required")
    if any(not isinstance(item, dict) for item in raw):
        raise ValueError("availability_policy_entry_must_be_mapping")
    if any("default" in item or "global_rule" in item for item in raw):
        raise ValueError("implicit_global_availability_rule_forbidden")
    policies = tuple(
        AvailabilityPolicy(
            series_id=item.get("series_id", ""),
            provider=item.get("provider", ""),
            rule=item.get("rule", ""),
            lag_days=item.get("lag_days"),
            temporary=item.get("temporary", False),
            quality=item.get("quality", ""),
            evidence_status=item.get("evidence_status", ""),
        )
        for item in raw
    )
    for policy in policies:
        policy.validate()
    return policies
