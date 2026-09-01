class CrossAssetError(Exception):
    """Base exception for expected application errors."""


class ConfigurationError(CrossAssetError):
    pass


class DataUnavailableError(CrossAssetError):
    pass


class ProviderError(CrossAssetError):
    pass
