"""Formal real-data and out-of-sample research contracts."""

from .evaluation import paired_oos_metrics, stitch_oos_returns, verdict_from_thresholds
from .plan import ResearchPlan, build_research_plan, load_decision_dates
from .protocol import ResearchProtocol, load_research_protocol
from .readiness import evaluate_research_readiness

__all__ = [
    "ResearchPlan",
    "ResearchProtocol",
    "build_research_plan",
    "evaluate_research_readiness",
    "load_decision_dates",
    "load_research_protocol",
    "paired_oos_metrics",
    "stitch_oos_returns",
    "verdict_from_thresholds",
]
