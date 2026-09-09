"""Missing-component policy diagnostics.

This module compares the current production policy (renormalize available
components) with a reserved-weight alternative. It does not call allocate()
and does not change score_asset() contributions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from cross_asset.engines.asset_score import COMPONENT_WEIGHTS, score_asset

DEFAULT_POLICY_PATH = Path("config/component_coverage.yml")
DEFAULT_ALLOCATION_PATH = Path("config/allocation.yml")

LANE_PERSONAL = "PERSONAL_WEEKLY"
LANE_RESEARCH = "RESEARCH_STATE"


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_component_policy(path: str | Path | None = None) -> dict[str, Any]:
    payload = _load_yaml(Path(path) if path else DEFAULT_POLICY_PATH)
    weights = dict(payload.get("declared_weights") or COMPONENT_WEIGHTS)
    if abs(sum(float(v) for v in weights.values()) - 1.0) > 1e-9:
        raise ValueError("declared component weights must sum to 1")
    return payload


def declared_wiring(
    allocation_path: str | Path | None = None,
) -> dict[str, dict[str, bool]]:
    """Map asset -> component -> wired? from allocation.yml asset_signal_map."""

    payload = _load_yaml(Path(allocation_path) if allocation_path else DEFAULT_ALLOCATION_PATH)
    signal_map = payload.get("asset_signal_map") or {}
    weights = payload.get("component_weights") or COMPONENT_WEIGHTS
    out: dict[str, dict[str, bool]] = {}
    for asset, mapping in signal_map.items():
        row = {name: False for name in weights}
        if isinstance(mapping, dict):
            for component, source in mapping.items():
                if component in row:
                    row[component] = source is not None
        out[str(asset)] = row
    return out


def _available_names(components: Mapping[str, Any], weights: Mapping[str, float]) -> list[str]:
    available = []
    for name in weights:
        value = components.get(name)
        if value is None:
            continue
        if isinstance(value, dict) and value.get("score", value.get("value")) is None:
            continue
        if hasattr(value, "score") and getattr(value, "score") is None:
            continue
        available.append(name)
    return available


def effective_weights(
    components: Mapping[str, Any],
    *,
    weights: Mapping[str, float] | None = None,
    policy: str = "renormalize_available_components",
) -> dict[str, float | None]:
    declared = dict(weights or COMPONENT_WEIGHTS)
    available = _available_names(components, declared)
    if policy == "renormalize_available_components":
        total = sum(float(declared[name]) for name in available)
        if not total:
            return {name: None for name in declared}
        return {
            name: (float(declared[name]) / total if name in available else None)
            for name in declared
        }
    if policy == "reserved_declared_weights":
        return {
            name: (float(declared[name]) if name in available else None) for name in declared
        }
    raise ValueError(f"unknown component policy: {policy}")


def missing_component_budget(
    components: Mapping[str, Any],
    *,
    weights: Mapping[str, float] | None = None,
) -> float:
    declared = dict(weights or COMPONENT_WEIGHTS)
    available = set(_available_names(components, declared))
    return sum(float(declared[name]) for name in declared if name not in available)


def component_coverage(
    components: Mapping[str, Any],
    *,
    weights: Mapping[str, float] | None = None,
) -> float:
    return 1.0 - missing_component_budget(components, weights=weights)


def research_grade(
    coverage: float,
    *,
    missing_budget: float,
    required_missing: tuple[str, ...],
    thresholds: Mapping[str, Any],
) -> str:
    min_research = float(thresholds.get("min_research_coverage", 0.40))
    min_alloc = float(thresholds.get("min_allocation_coverage", 0.70))
    max_missing = float(thresholds.get("max_missing_budget_for_allocation", 0.30))
    if coverage + 1e-12 < min_research:
        return "INSUFFICIENT"
    if required_missing or coverage + 1e-12 < min_alloc or missing_budget > max_missing + 1e-12:
        return "RESEARCH_STATE"
    return "ALLOCATION_CANDIDATE"


@dataclass(frozen=True)
class ComponentSnapshot:
    asset_id: str
    available: tuple[str, ...]
    missing: tuple[str, ...]
    coverage: float
    missing_budget: float
    declared_weights: dict[str, float]
    effective_renormalized: dict[str, float | None]
    effective_reserved: dict[str, float | None]
    research_grade: str
    allocation_eligibility: str
    lane: str
    production_binding_policy: str
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "available": list(self.available),
            "missing": list(self.missing),
            "coverage": self.coverage,
            "missing_budget": self.missing_budget,
            "declared_weights": self.declared_weights,
            "effective_component_weights": {
                "renormalize_available_components": self.effective_renormalized,
                "reserved_declared_weights": self.effective_reserved,
            },
            "research_grade": self.research_grade,
            "allocation_eligibility": self.allocation_eligibility,
            "lane": self.lane,
            "production_binding_policy": self.production_binding_policy,
            "notes": list(self.notes),
        }


def snapshot_asset(
    asset_id: str,
    components: Mapping[str, Any],
    *,
    policy_cfg: Mapping[str, Any] | None = None,
    personal: bool = False,
) -> ComponentSnapshot:
    cfg = dict(policy_cfg or load_component_policy())
    weights = dict(cfg.get("declared_weights") or COMPONENT_WEIGHTS)
    thresholds = dict(cfg.get("thresholds") or {})
    required = tuple(thresholds.get("required_for_allocation") or ("trend",))
    available = tuple(_available_names(components, weights))
    missing = tuple(name for name in weights if name not in available)
    coverage = component_coverage(components, weights=weights)
    budget = missing_component_budget(components, weights=weights)
    required_missing = tuple(name for name in required if name in missing)
    grade = research_grade(
        coverage,
        missing_budget=budget,
        required_missing=required_missing,
        thresholds=thresholds,
    )
    binding = str(cfg.get("production_binding_policy") or "renormalize_available_components")
    notes = [
        "diagnostic_only",
        "does_not_change_score_asset",
        "does_not_change_allocate",
        "not_research_admissible",
    ]
    if personal:
        notes.append("personal_weekly_lane")
    if grade == "ALLOCATION_CANDIDATE":
        notes.append("allocation_candidate_still_requires_g5")
        eligibility = "CANDIDATE_NOT_BOUND"
    elif binding == "renormalize_available_components" and available:
        # Document current production: score_asset still renormalizes.
        eligibility = "PRODUCTION_RENORMALIZES"
        notes.append("current_production_renormalizes_available_weights")
    else:
        eligibility = "NOT_ELIGIBLE"
    return ComponentSnapshot(
        asset_id=asset_id,
        available=available,
        missing=missing,
        coverage=coverage,
        missing_budget=budget,
        declared_weights={k: float(v) for k, v in weights.items()},
        effective_renormalized=effective_weights(
            components, weights=weights, policy="renormalize_available_components"
        ),
        effective_reserved=effective_weights(
            components, weights=weights, policy="reserved_declared_weights"
        ),
        research_grade=grade,
        allocation_eligibility=eligibility,
        lane=LANE_PERSONAL if personal else LANE_RESEARCH,
        production_binding_policy=binding,
        notes=tuple(notes),
    )


def snapshot_from_wiring(
    *,
    allocation_path: str | Path | None = None,
    policy_path: str | Path | None = None,
    personal: bool = False,
) -> dict[str, Any]:
    """Coverage from declared allocation wiring only - no market data required."""

    policy_cfg = load_component_policy(policy_path)
    wiring = declared_wiring(allocation_path)
    assets = []
    for asset, flags in wiring.items():
        components = {name: (1.0 if present else None) for name, present in flags.items()}
        assets.append(snapshot_asset(asset, components, policy_cfg=policy_cfg, personal=personal))
    scored = [item for item in assets if item.available]
    grades = {item.research_grade for item in scored}
    universe_grade = "INSUFFICIENT"
    if scored and grades <= {"ALLOCATION_CANDIDATE"}:
        universe_grade = "ALLOCATION_CANDIDATE"
    elif scored and "INSUFFICIENT" not in grades:
        universe_grade = "RESEARCH_STATE"
    return {
        "status": "DIAGNOSTIC",
        "lane": LANE_PERSONAL if personal else LANE_RESEARCH,
        "research_admissible": False,
        "universe_grade": universe_grade,
        "production_binding_policy": policy_cfg.get("production_binding_policy"),
        "assets": [item.to_dict() for item in assets],
    }


def compare_score_policies(
    asset_id: str,
    components: Mapping[str, Any],
    *,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Show that reserved-weight scoring is not yet bound.

    The reserved policy is represented as score * coverage, i.e. missing
    weight is not donated to surviving components. This is a diagnostic
    contrast only.
    """

    declared = dict(weights or COMPONENT_WEIGHTS)
    current = score_asset(asset_id, components, component_weights=declared)
    coverage = component_coverage(components, weights=declared)
    reserved_score = None if current.score is None else current.score * coverage
    return {
        "asset_id": asset_id,
        "renormalized_score": current.score,
        "reserved_magnitude_score": reserved_score,
        "coverage": coverage,
        "missing_components": list(current.missing_components),
        "bound_to_production": "renormalized_score",
    }
