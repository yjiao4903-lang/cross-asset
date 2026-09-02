"""External integration adapters."""

from .contracts import (
    ALLOCATABLE_ASSETS,
    ASSET_ALIASES,
    CANONICAL_ASSET_IDS,
    CROSS_ASSET_ID_ALIASES,
    DATA_FILES,
    SCHEMA_VERSION,
    VIEWABLE_ASSETS,
    FundamentalAsset,
    FundamentalAssetView,
    IntegrationManifest,
    IntegrationValidationReport,
    MacroSnapshot,
    SnapshotStatus,
    StructuralSnapshot,
    marco_to_cross_asset_id,
    normalize_asset_id,
)
from .marco_provider import (
    MarcoBundle,
    MarcoIntegrationError,
    MarcoProvider,
    resolve_macro_source,
)

__all__ = [
    "ALLOCATABLE_ASSETS",
    "ASSET_ALIASES",
    "CANONICAL_ASSET_IDS",
    "CROSS_ASSET_ID_ALIASES",
    "DATA_FILES",
    "SCHEMA_VERSION",
    "VIEWABLE_ASSETS",
    "FundamentalAsset",
    "FundamentalAssetView",
    "IntegrationManifest",
    "IntegrationValidationReport",
    "MacroSnapshot",
    "MarcoBundle",
    "MarcoIntegrationError",
    "MarcoProvider",
    "SnapshotStatus",
    "StructuralSnapshot",
    "marco_to_cross_asset_id",
    "normalize_asset_id",
    "resolve_macro_source",
]
