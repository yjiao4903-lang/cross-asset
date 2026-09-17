"""Lane-aware REAL-SNAPSHOT-V1 factor bindings.

This remains a narrow overlay on the accepted ``decision_support_v2`` taxonomy.
A binding may be MONITORING=BOUND only when every raw series identity is a real
repository-governed canonical identity. Provider symbols and correlated proxies
never create canonical authority.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .taxonomy import DecisionSupportConfig, SubfactorSpec, load_taxonomy

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BINDINGS_PATH = _REPO_ROOT / "config" / "decision_support_v2_bindings.yml"
DEFAULT_SERIES_PATH = _REPO_ROOT / "config" / "series.yml"
_ALLOWED_LANE_STATUS = {"BOUND", "UNBOUND", "BLOCKED"}
_ALLOWED_TRANSFORMS = {
    "LEVEL_CAUSAL_ZSCORE",
    "CHANGE_CAUSAL_ZSCORE",
    "YOY_CAUSAL_ZSCORE",
    "SPREAD_CAUSAL_ZSCORE",
    "TREND_63D",
    "PAYROLL_3M6M_SMOOTHED_MOMENTUM",
    "CORE_CPI_3M6M_ANNUALIZED_TREND",
}
_FACTOR_TRANSFORM_CONTRACT = {
    "US_PAYROLLS_TREND": "PAYROLL_3M6M_SMOOTHED_MOMENTUM",
    "US_CORE_CPI_TREND": "CORE_CPI_3M6M_ANNUALIZED_TREND",
    "US_YIELD_CURVE_10Y2Y": "SPREAD_CAUSAL_ZSCORE",
    "US_10Y_REAL_YIELD": "LEVEL_CAUSAL_ZSCORE",
    "US_EQ_TREND_63D": "TREND_63D",
    "CN_EQ_TREND_63D": "TREND_63D",
    "GOLD_TREND_63D": "TREND_63D",
    "COPPER_TREND_63D": "TREND_63D",
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
    canonical_series_ids: list[str] = Field(default_factory=list)
    transform: FactorTransform | None = None
    monitoring: LaneBinding
    formal: LaneBinding
    provenance_note: str = ""

    def render_record(self, spec: SubfactorSpec) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "canonical_series_ids": list(self.canonical_series_ids),
            "horizon": spec.resolved_horizon().value,
            "sign": spec.sign,
            "transform": self.transform.model_dump() if self.transform else None,
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


def _governed_series_ids(path: str | Path) -> set[str]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    result: set[str] = set()
    for item in payload.get("series", []) or []:
        if isinstance(item, dict) and item.get("series_id"):
            result.add(str(item["series_id"]))
    return result


def load_factor_bindings(
    path: str | Path | None = None,
    *,
    taxonomy: DecisionSupportConfig | None = None,
    series_path: str | Path | None = None,
) -> FactorBindingRegistry:
    config_path = Path(path) if path is not None else DEFAULT_BINDINGS_PATH
    canonical_path = Path(series_path) if series_path is not None else DEFAULT_SERIES_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    registry = FactorBindingRegistry(**raw)
    _validate_registry(
        registry,
        taxonomy or load_taxonomy(),
        governed_series_ids=_governed_series_ids(canonical_path),
    )
    return registry


def _validate_registry(
    registry: FactorBindingRegistry,
    taxonomy: DecisionSupportConfig,
    *,
    governed_series_ids: set[str],
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
        for lane_name, lane in (("monitoring", binding.monitoring), ("formal", binding.formal)):
            if lane.status not in _ALLOWED_LANE_STATUS:
                raise ValueError(
                    f"invalid {lane_name} status for {binding.factor_id}: {lane.status}"
                )
        if binding.monitoring.status == "BOUND":
            if not binding.monitoring.route:
                raise ValueError(f"monitoring route missing for {binding.factor_id}")
            if not binding.canonical_series_ids:
                raise ValueError(f"BOUND binding missing canonical series: {binding.factor_id}")
            unknown = sorted(set(binding.canonical_series_ids) - governed_series_ids)
            if unknown:
                raise ValueError(
                    f"BOUND binding references ungoverned canonical series for "
                    f"{binding.factor_id}: {','.join(unknown)}"
                )
            if binding.transform is None:
                raise ValueError(f"BOUND binding missing transform: {binding.factor_id}")
            expected = _FACTOR_TRANSFORM_CONTRACT.get(binding.factor_id)
            if expected is not None and binding.transform.type != expected:
                raise ValueError(
                    f"BOUND transform violates V2 factor definition for {binding.factor_id}: "
                    f"expected {expected}, got {binding.transform.type}"
                )
        if binding.transform is not None and binding.transform.type not in _ALLOWED_TRANSFORMS:
            raise ValueError(
                f"unsupported transform for {binding.factor_id}: {binding.transform.type}"
            )


__all__ = [
    "DEFAULT_BINDINGS_PATH",
    "DEFAULT_SERIES_PATH",
    "FactorBinding",
    "FactorBindingRegistry",
    "FactorTransform",
    "LaneBinding",
    "load_factor_bindings",
]
