"""Provider contracts. Adapters never write storage or silently impute values."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from cross_asset.domain.exceptions import ProviderError
from cross_asset.domain.models import DataRequest, Observation, ProviderCapability

# Public provider contracts are aliases of the canonical domain models.  Keep
# imports from this module working for adapters and downstream callers.


class BaseProvider(ABC):
    name = "base"

    def __init__(self, **config: Any):
        self.config = config
        self.last_error: dict[str, Any] | None = None

    @abstractmethod
    def probe(self) -> ProviderCapability: ...
    @abstractmethod
    def fetch(self, request: DataRequest) -> list[Observation]: ...
    def _failure(self, error: ProviderError) -> list[Observation]:
        self.last_error = error.as_dict()
        return []
