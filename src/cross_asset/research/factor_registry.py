"""G0 factor / series specification registry.

Entries here are contracts, not admitted production factors. Loading the
registry never writes scores, never changes allocation, and never upgrades a
lane to RESEARCH_ADMISSIBLE.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS = (
    "economic_hypothesis",
    "canonical_id",
    "role",
    "source_candidate",
    "transforms",
    "target_horizon",
    "falsification",
    "admission_gate",
    "lane",
    "production_allocation",
)

ALLOWED_GATES = frozenset({"G0", "G1", "G2", "G3", "G4_FACTOR", "G5"})
ALLOWED_LANES = frozenset({"PERSONAL_WEEKLY", "RESEARCH_STATE", "RESEARCH_ADMISSIBLE"})
DEFAULT_PATH = Path("config/factor_registry.yml")


@dataclass(frozen=True)
class FactorSpec:
    canonical_id: str
    economic_hypothesis: str
    role: tuple[str, ...]
    lane: str
    admission_gate: str
    production_allocation: bool
    source_candidate: tuple[str, ...]
    transforms: tuple[str, ...]
    target_horizon: tuple[str, ...]
    direction: dict[str, str]
    falsification: tuple[str, ...]
    status: str

    def g0_complete(self) -> bool:
        return bool(
            self.economic_hypothesis.strip()
            and self.canonical_id
            and self.role
            and self.source_candidate
            and self.transforms
            and self.target_horizon
            and self.falsification
        )


@dataclass(frozen=True)
class RegistryAudit:
    status: str
    factor_count: int
    complete: tuple[str, ...]
    incomplete: tuple[str, ...]
    production_blocked: tuple[str, ...]
    research_admissible: tuple[str, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "factor_count": self.factor_count,
            "complete": list(self.complete),
            "incomplete": list(self.incomplete),
            "production_blocked": list(self.production_blocked),
            "research_admissible": list(self.research_admissible),
            "errors": list(self.errors),
        }


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def load_factor_registry(path: str | Path | None = None) -> dict[str, FactorSpec]:
    target = Path(path) if path else DEFAULT_PATH
    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    raw_factors = payload.get("factors") or {}
    if not isinstance(raw_factors, dict) or not raw_factors:
        raise ValueError("factor registry must define a non-empty factors map")

    specs: dict[str, FactorSpec] = {}
    for name, raw in raw_factors.items():
        if not isinstance(raw, dict):
            raise ValueError(f"factor {name} must be a mapping")
        missing = [field for field in REQUIRED_FIELDS if field not in raw]
        if missing:
            raise ValueError(f"factor {name} missing G0 fields: {missing}")
        gate = str(raw["admission_gate"])
        lane = str(raw["lane"])
        if gate not in ALLOWED_GATES:
            raise ValueError(f"factor {name} has unknown admission_gate {gate}")
        if lane not in ALLOWED_LANES:
            raise ValueError(f"factor {name} has unknown lane {lane}")
        canonical = str(raw["canonical_id"])
        if canonical != name:
            raise ValueError(f"factor key {name} != canonical_id {canonical}")
        specs[name] = FactorSpec(
            canonical_id=canonical,
            economic_hypothesis=str(raw["economic_hypothesis"]).strip(),
            role=_as_tuple(raw["role"]),
            lane=lane,
            admission_gate=gate,
            production_allocation=bool(raw["production_allocation"]),
            source_candidate=_as_tuple(raw["source_candidate"]),
            transforms=_as_tuple(raw["transforms"]),
            target_horizon=_as_tuple(raw["target_horizon"]),
            direction={str(k): str(v) for k, v in dict(raw.get("direction") or {}).items()},
            falsification=_as_tuple(raw["falsification"]),
            status=str(raw.get("status") or "SPECIFIED"),
        )
    return specs


def audit_factor_registry(path: str | Path | None = None) -> RegistryAudit:
    specs = load_factor_registry(path)
    complete = tuple(name for name, spec in specs.items() if spec.g0_complete())
    incomplete = tuple(name for name, spec in specs.items() if not spec.g0_complete())
    production_blocked = tuple(
        name for name, spec in specs.items() if not spec.production_allocation
    )
    research_admissible = tuple(
        name
        for name, spec in specs.items()
        if spec.lane == "RESEARCH_ADMISSIBLE" or spec.admission_gate == "G5"
    )
    errors: list[str] = []
    if incomplete:
        errors.append("incomplete_g0_specs")
    if research_admissible:
        errors.append("research_admissible_claimed_without_g5_runtime")
    for name, spec in specs.items():
        if spec.production_allocation:
            errors.append(f"{name}_production_allocation_true_before_g5")
        if spec.lane == "RESEARCH_ADMISSIBLE" and spec.admission_gate != "G5":
            errors.append(f"{name}_lane_admissible_below_g5")
    status = "G0_READY" if not errors else "G0_BLOCKED"
    return RegistryAudit(
        status=status,
        factor_count=len(specs),
        complete=complete,
        incomplete=incomplete,
        production_blocked=production_blocked,
        research_admissible=research_admissible,
        errors=tuple(errors),
    )
