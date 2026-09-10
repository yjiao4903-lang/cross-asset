"""Authoritative formal-research data dependencies.

The formal research path must resolve one identical required-series set for
readiness, snapshot provenance, and walk-forward execution.  Keep accounting
requirements delegated to the existing return-accounting helper so FX/hedge
semantics are not re-parsed here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cross_asset.backtest.accounting import embedded_accounting_required_series_ids

if TYPE_CHECKING:
    from .executor import ResearchModelConfig


def research_required_series_ids(model_config: ResearchModelConfig) -> tuple[str, ...]:
    """Return every series consumed by the effective formal research model."""

    return_series = {
        spec.series_id
        for spec in model_config.return_specs.values()
        if spec.series_id is not None
    }
    accounting_series = embedded_accounting_required_series_ids(model_config.return_specs)
    macro_series = set(model_config.macro_config.get("series", {}))
    return tuple(sorted(return_series | accounting_series | macro_series))


__all__ = ["research_required_series_ids"]
