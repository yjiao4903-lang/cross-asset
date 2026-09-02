"""Frozen research-protocol parsing and validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


class ResearchProtocolError(ValueError):
    """Raised when a research protocol is malformed."""


def _missing(value: Any) -> bool:
    return value in (None, "", "TBD")


def _holdout_fraction(value: Any) -> float:
    if isinstance(value, (int, float)):
        fraction = float(value)
    elif isinstance(value, str) and value.startswith("last_") and value.endswith("_percent"):
        fraction = float(value.removeprefix("last_").removesuffix("_percent")) / 100.0
    else:
        raise ResearchProtocolError("final_holdout_format_invalid")
    if not 0 < fraction < 0.5:
        raise ResearchProtocolError("final_holdout_fraction_must_be_between_0_and_0_5")
    return fraction


@dataclass(frozen=True)
class ResearchProtocol:
    version: str
    status: str
    owner: str | None
    reviewer: str | None
    approved_at: str | None
    train_min_years: int
    test_window_months: int
    step_months: int
    default_mode: str
    rolling_years: int | None
    final_holdout_fraction: float
    coverage_threshold: float
    rebalance: str
    transaction_cost_bps: tuple[int, ...]
    turnover_convention: str
    charge_initial_trade: bool
    signal_model_version: str
    benchmarks: tuple[str, ...]
    project_status: str
    zero_imputation: bool
    decision_cutoff: str
    revision_policy: str
    require_protocol_status: str
    holdout_release: bool
    required_registry_status: str
    required_usage_status: str
    require_all_critical_series: bool
    evaluation_thresholds: dict[str, float | int]

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "ResearchProtocol":
        try:
            windows = raw["windows"]
            data_policy = raw["data_policy"]
            execution = raw["execution"]
            thresholds = raw["evaluation_thresholds"]
            coverage = float(raw["coverage_threshold"])
            protocol = cls(
                version=str(raw["version"]),
                status=str(raw["status"]),
                owner=raw.get("owner"),
                reviewer=raw.get("reviewer"),
                approved_at=raw.get("approved_at"),
                train_min_years=int(windows["train_min_years"]),
                test_window_months=int(windows["test_window_months"]),
                step_months=int(windows["step_months"]),
                default_mode=str(windows["default_mode"]),
                rolling_years=(
                    None if windows.get("rolling_years") is None else int(windows["rolling_years"])
                ),
                final_holdout_fraction=_holdout_fraction(windows["final_holdout"]),
                coverage_threshold=coverage,
                rebalance=str(raw["rebalance"]),
                transaction_cost_bps=tuple(int(value) for value in raw["transaction_cost_bps"]),
                turnover_convention=str(raw["turnover_convention"]),
                charge_initial_trade=bool(raw["charge_initial_trade"]),
                signal_model_version=str(raw["signal_model_version"]),
                benchmarks=tuple(str(value) for value in raw["benchmarks"]),
                project_status=str(data_policy["project_status"]),
                zero_imputation=bool(data_policy["zero_imputation"]),
                decision_cutoff=str(data_policy["decision_cutoff"]),
                revision_policy=str(data_policy["revision_policy"]),
                require_protocol_status=str(execution["require_protocol_status"]),
                holdout_release=bool(execution["holdout_release"]),
                required_registry_status=str(execution["required_registry_status"]),
                required_usage_status=str(execution["required_usage_status"]),
                require_all_critical_series=bool(execution["require_all_critical_series"]),
                evaluation_thresholds={
                    "min_oos_observations": int(thresholds["min_oos_observations"]),
                    "min_information_ratio_vs_static": float(
                        thresholds["min_information_ratio_vs_static"]
                    ),
                    "min_annualized_excess_return_vs_static": float(
                        thresholds["min_annualized_excess_return_vs_static"]
                    ),
                    "max_drawdown_penalty_vs_static": float(
                        thresholds["max_drawdown_penalty_vs_static"]
                    ),
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchProtocolError("research_protocol_fields_invalid") from exc
        protocol.validate()
        return protocol

    def validate(self) -> None:
        if self.train_min_years < 1:
            raise ResearchProtocolError("train_min_years_must_be_positive")
        if self.test_window_months < 1 or self.step_months < 1:
            raise ResearchProtocolError("test_and_step_months_must_be_positive")
        if self.default_mode not in {"expanding", "rolling"}:
            raise ResearchProtocolError("default_mode_invalid")
        if self.default_mode == "rolling" and not self.rolling_years:
            raise ResearchProtocolError("rolling_years_required")
        if not 0 < self.coverage_threshold <= 1:
            raise ResearchProtocolError("coverage_threshold_must_be_in_0_1")
        if self.zero_imputation:
            raise ResearchProtocolError("zero_imputation_forbidden")
        if self.decision_cutoff != "available_at <= decision_time":
            raise ResearchProtocolError("decision_cutoff_must_be_pit")
        if self.revision_policy != "latest_released_revision_per_observation_date":
            raise ResearchProtocolError("revision_policy_invalid")
        if self.turnover_convention not in {"two_sided_notional", "one_way"}:
            raise ResearchProtocolError("turnover_convention_invalid")
        if 0 not in self.transaction_cost_bps:
            raise ResearchProtocolError("zero_cost_sensitivity_required")
        if "STATIC" not in self.benchmarks or "FULL_MODEL" not in self.benchmarks:
            raise ResearchProtocolError("static_and_full_model_benchmarks_required")
        if self.require_protocol_status not in {"FROZEN", "APPROVED"}:
            raise ResearchProtocolError("require_protocol_status_invalid")
        if self.required_registry_status != "PASS":
            raise ResearchProtocolError("registry_status_must_be_pass")
        if self.required_usage_status != "RESEARCH_ADMISSIBLE":
            raise ResearchProtocolError("usage_status_must_be_research_admissible")
        if int(self.evaluation_thresholds["min_oos_observations"]) < 1:
            raise ResearchProtocolError("min_oos_observations_must_be_positive")
        if float(self.evaluation_thresholds["max_drawdown_penalty_vs_static"]) < 0:
            raise ResearchProtocolError("max_drawdown_penalty_must_be_non_negative")

    @property
    def approval_complete(self) -> bool:
        return not any(_missing(value) for value in (self.owner, self.reviewer, self.approved_at))

    @property
    def execution_blockers(self) -> tuple[str, ...]:
        blockers = []
        if self.status != self.require_protocol_status:
            blockers.append(
                f"protocol_status_requires_{self.require_protocol_status.lower()}"
            )
        if not self.approval_complete:
            blockers.append("protocol_owner_reviewer_approval_required")
        if self.project_status == "DATA_BLOCKED":
            blockers.append("project_status_data_blocked")
        if self.holdout_release:
            blockers.append("holdout_must_start_sealed")
        return tuple(blockers)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def protocol_hash(self) -> str:
        body = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(body).hexdigest()


def load_research_protocol(path: str | Path = "config/research.yml") -> ResearchProtocol:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ResearchProtocolError("research_protocol_must_be_mapping")
    return ResearchProtocol.from_mapping(raw)


__all__ = ["ResearchProtocol", "ResearchProtocolError", "load_research_protocol"]
