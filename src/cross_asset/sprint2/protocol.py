"""Strict, no-tuning Sprint 2 protocol contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ProtocolValidationError(ValueError):
    """Configuration violates a frozen protocol boundary."""


REQUIRED_BENCHMARKS = ("STATIC", "TREND_ONLY", "MACRO_ONLY", "RISK_ONLY", "FULL_MODEL")
REQUIRED_OUTPUTS = (
    "decisions.parquet",
    "returns.parquet",
    "scores.parquet",
    "allocations.parquet",
    "turnover.parquet",
    "costs.parquet",
    "summary.md",
)
REQUIRED_UNIVERSE = ("CN_EQ", "HK_EQ", "CN_BOND", "CASH")
REQUIRED_TURNOVER_CONVENTION = "two_sided_notional"
REQUIRED_RETURN_MODEL = {
    "CN_EQ": {"series_id": "CN_EQ_LARGE", "kind": "price"},
    "HK_EQ": {"series_id": "HK_EQ", "kind": "price"},
    "CN_BOND": {
        "series_id": "CN_BOND_10Y",
        "kind": "yield_duration_proxy",
        "duration_years": 8.0,
        "yield_scale": 100.0,
    },
    "CASH": {"series_id": None, "kind": "cash", "annual_rate": 0.0},
}


@dataclass(frozen=True)
class Sprint2Protocol:
    universe: tuple[str, ...]
    modes: tuple[str, ...]
    default_mode: str
    transaction_cost_bps: tuple[int, ...]
    base_cost_bps: int
    benchmarks: tuple[str, ...]
    outputs: tuple[str, ...]
    preliminary: bool
    partial_universe: bool
    research_validated: bool
    turnover_convention: str
    return_model: dict[str, dict[str, Any]]

    def validate(self) -> None:
        if self.universe != REQUIRED_UNIVERSE:
            raise ProtocolValidationError("universe_must_match_frozen_local_experiment")
        if set(self.modes) != {"expanding", "rolling"}:
            raise ProtocolValidationError("modes_must_be_expanding_and_rolling")
        if self.default_mode != "expanding":
            raise ProtocolValidationError("default_mode_must_be_expanding")
        if self.transaction_cost_bps != (0, 5, 10, 20, 30):
            raise ProtocolValidationError("transaction_costs_are_frozen")
        if self.base_cost_bps != 10:
            raise ProtocolValidationError("base_cost_must_be_ten_bps")
        if self.benchmarks != REQUIRED_BENCHMARKS:
            raise ProtocolValidationError("benchmarks_are_frozen")
        if self.outputs != REQUIRED_OUTPUTS:
            raise ProtocolValidationError("outputs_are_frozen")
        if (self.preliminary, self.partial_universe, self.research_validated) != (
            True,
            True,
            False,
        ):
            raise ProtocolValidationError("release_status_must_remain_preliminary_partial_false")
        if self.turnover_convention != REQUIRED_TURNOVER_CONVENTION:
            raise ProtocolValidationError("turnover_convention_is_frozen")
        if self.return_model != REQUIRED_RETURN_MODEL:
            raise ProtocolValidationError("return_model_is_frozen")

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "Sprint2Protocol":
        try:
            p = cls(
                tuple(raw["universe"]),
                tuple(raw["modes"]),
                raw["default_mode"],
                tuple(raw["transaction_cost_bps"]),
                int(raw["base_cost_bps"]),
                tuple(raw["benchmarks"]),
                tuple(raw["outputs"]),
                bool(raw["preliminary"]),
                bool(raw["partial_universe"]),
                bool(raw["research_validated"]),
                str(raw["turnover_convention"]),
                {str(k): dict(v) for k, v in raw["return_model"].items()},
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolValidationError("protocol_fields_invalid") from exc
        p.validate()
        return p
