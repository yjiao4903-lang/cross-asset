"""Execution-timing disclosure for research artifacts without changing returns."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from cross_asset.operations.execution_timing import (
    RESEARCH_PROXY_PERFORMANCE_SEMANTICS,
    RESEARCH_PROXY_RETURN_TIMING_BASIS,
    portfolio_execution_timing_disclosure,
)


def annotate_research_execution_timing(
    frame: pd.DataFrame,
    return_specs: Mapping[str, Any],
    asset_market_map: Mapping[str, str] | None = None,
    *,
    policy_path: str | Path = "config/execution_timing.yml",
    calendar_config: str | Path | None = None,
) -> pd.DataFrame:
    """Attach auditable timing disclosure while leaving gross/net returns unchanged."""

    if "decision_date" not in frame.columns:
        raise ValueError("decision_date_required_for_execution_timing")
    rows = frame.copy()
    cache: dict[pd.Timestamp, dict[str, Any]] = {}
    disclosures = []
    for raw_decision in rows["decision_date"]:
        decision = pd.Timestamp(raw_decision)
        if decision.tzinfo is None:
            decision = decision.tz_localize("UTC")
        else:
            decision = decision.tz_convert("UTC")
        disclosure = cache.get(decision)
        if disclosure is None:
            disclosure = portfolio_execution_timing_disclosure(
                decision.to_pydatetime(),
                return_specs,
                asset_market_map,
                policy_path=policy_path,
                calendar_config=calendar_config,
            )
            cache[decision] = disclosure
        disclosures.append(disclosure)

    rows["execution_timing_status"] = [item["status"] for item in disclosures]
    rows["execution_timing"] = disclosures
    rows["return_timing_basis"] = RESEARCH_PROXY_RETURN_TIMING_BASIS
    rows["performance_semantics"] = RESEARCH_PROXY_PERFORMANCE_SEMANTICS
    return rows


def research_execution_timing_summary(frame: pd.DataFrame) -> dict[str, Any]:
    """Summarize artifact timing readiness without upgrading performance semantics."""

    if "execution_timing_status" not in frame.columns or "execution_timing" not in frame.columns:
        raise ValueError("execution_timing_columns_required")
    statuses = set(frame["execution_timing_status"].dropna().astype(str))
    blockers: set[str] = set()
    for item in frame["execution_timing"]:
        if isinstance(item, dict):
            blockers.update(str(value) for value in item.get("blockers", []))
    return {
        "status": "RESOLVED" if statuses == {"RESOLVED"} else "BLOCKED",
        "blockers": sorted(blockers),
        "return_timing_basis": RESEARCH_PROXY_RETURN_TIMING_BASIS,
        "performance_semantics": RESEARCH_PROXY_PERFORMANCE_SEMANTICS,
    }


__all__ = ["annotate_research_execution_timing", "research_execution_timing_summary"]
