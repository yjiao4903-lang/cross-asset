from typing import Any


class CrossAssetError(Exception):
    """Base exception for expected application errors."""


class ConfigurationError(CrossAssetError):
    pass


class DataUnavailableError(CrossAssetError):
    pass


class ProviderError(CrossAssetError):
    """Structured provider failure shared by adapters and callers."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider: str = "",
        details: dict[str, Any] | None = None,
    ):
        self.code = code
        self.provider = provider
        self.details = details or {}
        super().__init__(message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "provider": self.provider,
            "message": str(self),
            "details": self.details,
        }
