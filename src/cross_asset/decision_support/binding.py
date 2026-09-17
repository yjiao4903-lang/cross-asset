"""Lane-aware REAL-SNAPSHOT-V1 factor bindings.

This is a narrow overlay on the accepted ``decision_support_v2`` taxonomy, not
an alternative factor authority. Economic factor identity, horizon and sign
remain owned by :mod:`cross_asset.decision_support.taxonomy`; this module only
binds those factor ids to canonical series and explicitly independent evidence
lanes.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .taxonomy import DecisionSupportConfig, SubfactorSpec, load_taxonomy

DEFAULT_BINDINGS_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "decision_support_v2_bindings.yml"
)
_ALLOWED_LANE_STATUS = {"BOUND", "UNBOUND", "BLOCKED"}
_ALLOWED_TRANSFORMS = {
    "LEVEL_CAUSAL_ZSCORE",
    "CHANGE_CAUSAL_ZSCORE",
    "YOY_CAUSAL_ZSCORE",
    "SPREAD_CAUSAL_ZSCORE",
    "TREND_63D",
}


class LaneBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: str
    status: str
    note: str = ""


class FactorTransform(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    min_history: int = Field(default=20, ge=2)
    lag_periods: int = Field(default=12, ge=1)


class FactorBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_id: str
    canonical_series_ids: list[str] = Field(min_length=1)
    transform: FactorTransform
    monitoring: LaneBinding
    formal: LaneBinding
    provenance_note: str = ""

    def render_record(self, spec: SubfactorSpec) -> dict[str, Any]:
        """Return the API/audit record with taxonomy-owned economics attached."""

        return {
            "factor_id": self.factor_id,
            "canonical_series_ids": list(self.canonical_series_ids),
            "horizon": spec.resolved_horizon().value,
            "sign": spec.sign,
            "transform": self.transform.model_dump(),
            "monitoring": self.monitoring.model_dump(),
            "formal": self.formal.model_dump(),
            "provenance_note": self.provenance_note,
        }


class FactorBindingRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    contract: str
    note: str = ""
    bindings: list[FactorBinding]

    def by_factor(self) -> dict[str, FactorBinding]:
        return {binding.factor_id: binding for binding in self.bindings}

    def records(self, taxonomy: DecisionSupportConfig) -> list[dict[str, Any]]:
        by_factor = self.by_factor()
        records: list[dict[str, Any]] = []
        for spec in taxonomy.subfactors():
            binding = by_factor.get(spec.factor_id)
            if binding is None:
                records.append(
                    {
                        "factor_id": spec.factor_id,
                        "canonical_series_ids": [],
                        "horizon": spec.resolved_horizon().value,
                        "sign": spec.sign,
                        "transform": None,
                        "monitoring": {"route": "", "status": "UNBOUND", "note": ""},
                        "formal": {"route": "", "status": "UNBOUND", "note": ""},
                        "provenance_note": "",
                    }
                )
            else:
                records.append(binding.render_record(spec))
        return records


def load_factor_bindings(
    path: str | Path | None = None,
    *,
    taxonomy: DecisionSupportConfig | None = None,
) -> FactorBindingRegistry:
    config_path = Path(path) if path is not None else DEFAULT_BINDINGS_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    registry = FactorBindingRegistry(**raw)
    _validate_registry(registry, taxonomy or load_taxonomy())
    return registry


def _validate_registry(
    registry: FactorBindingRegistry,
    taxonomy: DecisionSupportConfig,
) -> None:
    specs = {spec.factor_id: spec for spec in taxonomy.subfactors()}
    seen: set[str] = set()
    for binding in registry.bindings:
        if binding.factor_id in seen:
            raise ValueError(f"duplicate factor binding: {binding.factor_id}")
        seen.add(binding.factor_id)
        if binding.factor_id not in specs:
            raise ValueError(f"binding references unknown factor_id: {binding.factor_id}")
        if len(binding.canonical_series_ids) != len(set(binding.canonical_series_ids)):
            raise ValueError(f"duplicate canonical series in binding: {binding.factor_id}")
        if binding.transform.type not in _ALLOWED_TRANSFORMS:
            raise ValueError(
                f"unsupported transform for {binding.factor_id}: {binding.transform.type}"
            )
        for lane_name, lane in (
            ("monitoring", binding.monitoring),
            ("formal", binding.formal),
        ):
            if lane.status not in _ALLOWED_LANE_STATUS:
                raise ValueError(
                    f"invalid {lane_name} status for {binding.factor_id}: {lane.status}"
                )
        if binding.monitoring.status == "BOUND" and not binding.monitoring.route:
            raise ValueError(f"monitoring route missing for {binding.factor_id}")


__all__ = [
    "DEFAULT_BINDINGS_PATH",
    "FactorBinding",
    "FactorBindingRegistry",
    "FactorTransform",
    "LaneBinding",
    "load_factor_bindings",
]
