"""Fail-closed decision/effective/execution timing contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import yaml

from .calendar import MarketCalendar

_MAX_SESSION_WALK_DAYS = 370
_SUPPORTED_EFFECTIVE_RULE = "next_available_session"
_SUPPORTED_PRICE_RULE = "next_available_session_close"
RESEARCH_PROXY_RETURN_TIMING_BASIS = "decision_to_next_decision_research_proxy"
RESEARCH_PROXY_PERFORMANCE_SEMANTICS = "research_proxy_not_investor_realizable"


@dataclass(frozen=True)
class ExecutionTimingPolicy:
    version: str
    effective_from: str
    execution_price_rule: str
    require_verified_calendar: bool
    calendar_config: str

    def validate(self) -> None:
        if self.effective_from != _SUPPORTED_EFFECTIVE_RULE:
            raise ValueError("effective_from_rule_unsupported")
        if self.execution_price_rule != _SUPPORTED_PRICE_RULE:
            raise ValueError("execution_price_rule_unsupported")
        if self.require_verified_calendar is not True:
            raise ValueError("verified_calendar_requirement_must_be_true")
        if not self.calendar_config:
            raise ValueError("calendar_config_required")


@dataclass(frozen=True)
class ExecutionTimingResult:
    status: str  # RESOLVED | BLOCKED
    reason: str
    decision_at: datetime
    market: str
    effective_at: datetime | None = None
    execution_price_at: datetime | None = None
    effective_rule: str | None = None
    execution_price_rule: str | None = None
    calendar_id: str | None = None
    calendar_version: str | None = None

    @property
    def resolved(self) -> bool:
        return self.status == "RESOLVED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_execution_timing_policy(
    path: str | Path = "config/execution_timing.yml",
) -> ExecutionTimingPolicy:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("execution_timing_config_must_be_mapping")
    try:
        policy = ExecutionTimingPolicy(
            version=str(raw["version"]),
            effective_from=str(raw["effective_from"]),
            execution_price_rule=str(raw["execution_price_rule"]),
            require_verified_calendar=bool(raw["require_verified_calendar"]),
            calendar_config=str(raw["calendar_config"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("execution_timing_config_fields_invalid") from exc
    policy.validate()
    return policy


def resolve_market_execution(
    decision_at: datetime,
    market: str,
    *,
    policy: ExecutionTimingPolicy | None = None,
    policy_path: str | Path = "config/execution_timing.yml",
    calendar_config: str | Path | None = None,
) -> ExecutionTimingResult:
    """Resolve the first verified market-session close strictly after decision day.

    No weekend-only heuristic is permitted. Encountering unverified or uncovered
    calendar state blocks resolution rather than skipping across unknown dates.
    """

    def blocked(reason: str, calendar: MarketCalendar | None = None) -> ExecutionTimingResult:
        return ExecutionTimingResult(
            status="BLOCKED",
            reason=reason,
            decision_at=decision_at,
            market=market,
            effective_rule=active_policy.effective_from,
            execution_price_rule=active_policy.execution_price_rule,
            calendar_id=None if calendar is None else calendar.calendar_id,
            calendar_version=None if calendar is None else calendar.version,
        )

    active_policy = policy if policy is not None else load_execution_timing_policy(policy_path)
    active_policy.validate()

    if decision_at.tzinfo is None or decision_at.utcoffset() is None:
        return blocked("decision_time_must_be_timezone_aware")
    if not market:
        return blocked("market_required")

    config_path = calendar_config or active_policy.calendar_config
    try:
        calendar = MarketCalendar(market, config_path)
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError):
        return blocked("calendar_unavailable")
    if active_policy.require_verified_calendar and not calendar.verified:
        return blocked("calendar_unverified", calendar)

    local_decision = decision_at.astimezone(ZoneInfo(calendar.timezone))
    candidate = local_decision.date() + timedelta(days=1)
    for _ in range(_MAX_SESSION_WALK_DAYS):
        status = calendar.session_status(candidate)
        if status == "UNKNOWN":
            return blocked("calendar_coverage_missing", calendar)
        if status == "OPEN":
            execution_at = calendar.session_close_at(candidate)
            if execution_at is None:
                return blocked("session_close_unavailable", calendar)
            if execution_at.astimezone(ZoneInfo("UTC")) <= decision_at.astimezone(
                ZoneInfo("UTC")
            ):
                return blocked("execution_not_after_decision", calendar)
            return ExecutionTimingResult(
                status="RESOLVED",
                reason="next_verified_session_close",
                decision_at=decision_at,
                market=market,
                effective_at=execution_at,
                execution_price_at=execution_at,
                effective_rule=active_policy.effective_from,
                execution_price_rule=active_policy.execution_price_rule,
                calendar_id=calendar.calendar_id,
                calendar_version=calendar.version,
            )
        candidate += timedelta(days=1)
    return blocked("calendar_walk_exhausted", calendar)


def terminal_no_trade_timing_disclosure(decision_at: datetime) -> dict[str, Any]:
    """Represent the existing terminal-no-trade convention without fake timestamps."""

    return {
        "status": "NOT_APPLICABLE",
        "reason": "terminal_no_trade",
        "decision_at": decision_at,
        "by_asset": {},
        "blockers": [],
        "return_timing_basis": RESEARCH_PROXY_RETURN_TIMING_BASIS,
        "performance_semantics": RESEARCH_PROXY_PERFORMANCE_SEMANTICS,
    }


def portfolio_execution_timing_disclosure(
    decision_at: datetime,
    return_specs: Mapping[str, Any],
    asset_market_map: Mapping[str, str] | None = None,
    *,
    policy: ExecutionTimingPolicy | None = None,
    policy_path: str | Path = "config/execution_timing.yml",
    calendar_config: str | Path | None = None,
) -> dict[str, Any]:
    """Build auditable per-asset timing disclosure without inventing market mappings.

    Cash return specs are explicitly not applicable. Every other asset requires
    an explicit asset-to-market mapping and a resolvable VERIFIED calendar.
    Any unresolved non-cash asset blocks the portfolio timing status. The
    disclosure deliberately labels current returns as a research proxy because
    return calculation has not yet been moved to execution-price timestamps.
    """

    mapping = dict(asset_market_map or {})
    by_asset: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    for asset, spec in return_specs.items():
        if getattr(spec, "kind", None) == "cash":
            by_asset[str(asset)] = {
                "status": "NOT_APPLICABLE",
                "reason": "cash_return_no_market_execution",
                "decision_at": decision_at,
                "market": None,
                "effective_at": None,
                "execution_price_at": None,
            }
            continue
        market = mapping.get(str(asset))
        if not market:
            reason = "market_mapping_missing"
            blockers.append(f"{asset}:{reason}")
            by_asset[str(asset)] = {
                "status": "BLOCKED",
                "reason": reason,
                "decision_at": decision_at,
                "market": None,
                "effective_at": None,
                "execution_price_at": None,
            }
            continue
        result = resolve_market_execution(
            decision_at,
            str(market),
            policy=policy,
            policy_path=policy_path,
            calendar_config=calendar_config,
        )
        by_asset[str(asset)] = result.to_dict()
        if not result.resolved:
            blockers.append(f"{asset}:{result.reason}")

    status = "RESOLVED" if not blockers else "BLOCKED"
    return {
        "status": status,
        "reason": (
            "all_non_cash_asset_execution_times_resolved"
            if not blockers
            else "asset_execution_timing_unresolved"
        ),
        "decision_at": decision_at,
        "by_asset": by_asset,
        "blockers": blockers,
        "return_timing_basis": RESEARCH_PROXY_RETURN_TIMING_BASIS,
        "performance_semantics": RESEARCH_PROXY_PERFORMANCE_SEMANTICS,
    }


__all__ = [
    "ExecutionTimingPolicy",
    "ExecutionTimingResult",
    "RESEARCH_PROXY_PERFORMANCE_SEMANTICS",
    "RESEARCH_PROXY_RETURN_TIMING_BASIS",
    "load_execution_timing_policy",
    "portfolio_execution_timing_disclosure",
    "resolve_market_execution",
    "terminal_no_trade_timing_disclosure",
]
