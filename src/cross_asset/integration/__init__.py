"""External integration adapters."""

from .contracts import (
    ALLOCATABLE_ASSETS,
    ASSET_ID_ALIASES,
    VIEWABLE_ASSETS,
    IntegrationValidationReport,
    MarcoMacroState,
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
    "ASSET_ID_ALIASES",
    "VIEWABLE_ASSETS",
    "IntegrationValidationReport",
    "MarcoBundle",
    "MarcoIntegrationError",
    "MarcoMacroState",
    "MarcoProvider",
    "normalize_asset_id",
    "resolve_macro_source",
]
