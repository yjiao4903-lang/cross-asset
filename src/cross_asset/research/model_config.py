"""Load the frozen full-universe research model configuration."""

from __future__ import annotations

from pathlib import Path

import yaml

from cross_asset.backtest.accounting import load_return_accounting_policy
from cross_asset.backtest.returns import AssetReturnSpec

from .executor import ResearchModelConfig


def _mapping(path):
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"config_must_be_mapping:{path}")
    return value


def load_research_asset_market_map(
    universe_path="config/research_universe.yml",
) -> dict[str, str]:
    """Load only explicit asset -> market mappings; never infer from asset ids."""

    universe = _mapping(universe_path)
    assets_config = universe.get("assets", {})
    if not isinstance(assets_config, dict):
        raise TypeError("research_universe_assets_must_be_mapping")
    return {
        str(asset): str(entry["market"])
        for asset, entry in assets_config.items()
        if isinstance(entry, dict) and entry.get("market")
    }


def load_research_model_config(
    *,
    universe_path="config/research_universe.yml",
    allocation_path="config/allocation.yml",
    macro_path="config/macro.yml",
    accounting_path="config/return_accounting.yml",
) -> ResearchModelConfig:
    universe = _mapping(universe_path)
    allocation = _mapping(allocation_path)
    macro = _mapping(macro_path)
    accounting_policy = load_return_accounting_policy(accounting_path)
    accounting_raw = accounting_policy.to_dict()
    assets_config = universe.get("assets", {})
    strategic = {
        str(asset): float(weight)
        for asset, weight in allocation.get("strategic_weights", {}).items()
    }
    if not strategic or abs(sum(strategic.values()) - 1.0) > 1e-10:
        raise ValueError("strategic_weights_must_sum_to_one")
    if set(strategic) != set(assets_config):
        raise ValueError("research_universe_must_match_strategic_assets")
    if set(strategic) != set(accounting_policy.assets):
        raise ValueError("return_accounting_must_cover_research_universe")

    specs = {}
    for asset in strategic:
        asset_accounting = dict(accounting_raw["assets"][asset])
        asset_accounting.update(
            {
                "policy_version": accounting_policy.version,
                "reporting_currency": accounting_policy.reporting_currency,
                "supported_currencies": list(accounting_policy.supported_currencies),
                "pricing_basis": accounting_policy.pricing_basis,
                "performance_semantics": accounting_policy.performance_semantics,
            }
        )
        specs[asset] = AssetReturnSpec(
            **{
                key: value
                for key, value in dict(assets_config[asset]).items()
                if key != "market"
            },
            accounting=asset_accounting,
        )

    signal_map = {
        asset: dict(value or {})
        for asset, value in allocation.get("asset_signal_map", {}).items()
    }
    if set(signal_map) != set(strategic):
        raise ValueError("asset_signal_map_must_cover_research_universe")
    return ResearchModelConfig(
        assets=tuple(strategic),
        strategic_weights=strategic,
        return_specs=specs,
        asset_signal_map=signal_map,
        component_weights={
            str(name): float(weight)
            for name, weight in allocation.get("component_weights", {}).items()
        },
        allocation_config=allocation,
        macro_config=macro,
    )


__all__ = ["load_research_asset_market_map", "load_research_model_config"]
