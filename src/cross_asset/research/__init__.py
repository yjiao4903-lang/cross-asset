"""Formal real-data and out-of-sample research contracts."""

from .evaluation import (
    paired_oos_metrics,
    stitch_oos_path,
    stitch_oos_returns,
    verdict_from_thresholds,
)
from .executor import ResearchModelConfig, execute_walk_forward
from .model_config import load_research_model_config
from .plan import ResearchPlan, build_research_plan, load_decision_dates
from .protocol import ResearchProtocol, load_research_protocol
from .readiness import evaluate_research_readiness

__all__ = [
    "ResearchModelConfig",
    "ResearchPlan",
    "ResearchProtocol",
    "build_research_plan",
    "evaluate_research_readiness",
    "execute_walk_forward",
    "load_decision_dates",
    "load_research_model_config",
    "load_research_protocol",
    "paired_oos_metrics",
    "stitch_oos_path",
    "stitch_oos_returns",
    "verdict_from_thresholds",
]
