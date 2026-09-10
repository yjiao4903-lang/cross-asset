"""Transparent fixture scenarios; assumptions are not forecasts (DEVELOPMENT_PRIOR)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    asset: str
    kind: str
    baseline: float | None
    shock: float | None = None
    unit: str | None = None
    duration: float | None = None
    local_price_shock: float | None = None
    fx_shock: float | None = None
    currency: str | None = None
    base_currency: str | None = None
    quote_currency: str | None = None
    quote_convention: str | None = None
    cost_bps: float | None = None
    as_of: str | None = None
    evidence_refs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    status: str
    up: float | None
    down: float | None
    value: float | None
    formula: str
    assumptions: tuple[str, ...]
    cost_bps: float | None
    evidence_refs: tuple[str, ...]


def evaluate_scenario(spec: ScenarioSpec) -> ScenarioResult:
    if not spec.scenario_id or not spec.asset or not spec.as_of or not spec.evidence_refs or spec.baseline is None or spec.cost_bps is None or not math.isfinite(float(spec.baseline)) or not math.isfinite(float(spec.cost_bps)):
        return ScenarioResult(spec.scenario_id, "UNESTIMATED", None, None, None, "", spec.assumptions, spec.cost_bps, spec.evidence_refs)
    cost = float(spec.cost_bps) / 10000.0
    if cost < 0:
        return ScenarioResult(spec.scenario_id, "UNESTIMATED", None, None, None, "invalid_cost", spec.assumptions, spec.cost_bps, spec.evidence_refs)
    if spec.kind == "bond_duration":
        if spec.duration is None or spec.shock is None or spec.unit != "bp" or spec.duration < 0 or not math.isfinite(float(spec.duration)) or not math.isfinite(float(spec.shock)):
            return ScenarioResult(spec.scenario_id, "UNESTIMATED", None, None, None, "-duration * yield_shock_bp / 10000 - cost", spec.assumptions, spec.cost_bps, spec.evidence_refs)
        value = -float(spec.duration) * float(spec.shock) / 10000.0 - cost
        up = down = None
        formula = "value=-duration*shock_bp/10000-cost"
    elif spec.kind == "foreign_asset":
        expected_convention = f"{spec.base_currency}_per_{spec.quote_currency}" if spec.base_currency and spec.quote_currency else None
        if spec.local_price_shock is None or spec.fx_shock is None or spec.unit != "fraction" or not spec.base_currency or not spec.quote_currency or spec.base_currency == spec.quote_currency or spec.quote_convention != expected_convention or not all(math.isfinite(float(v)) and float(v) > -1 for v in (spec.local_price_shock, spec.fx_shock)):
            return ScenarioResult(spec.scenario_id, "UNESTIMATED", None, None, None, "(1+local_price_shock)*(1+fx_shock)-1-cost", spec.assumptions, spec.cost_bps, spec.evidence_refs)
        value = (1.0 + float(spec.local_price_shock)) * (1.0 + float(spec.fx_shock)) - 1.0 - cost
        up = down = None
        formula = "value=(1+local_price_shock)*(1+fx_shock)-1-cost"
    else:
        return ScenarioResult(spec.scenario_id, "UNESTIMATED", None, None, None, "unsupported_kind", spec.assumptions, spec.cost_bps, spec.evidence_refs)
    return ScenarioResult(spec.scenario_id, "ESTIMATED_SCENARIO", up, down, value, formula, spec.assumptions, spec.cost_bps, spec.evidence_refs)


__all__ = ["ScenarioResult", "ScenarioSpec", "evaluate_scenario"]
