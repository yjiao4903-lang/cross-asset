from .base import BaseProvider, ProviderCapability, ProviderError


class YahooProvider(BaseProvider):
    name = "yahoo"

    def probe(self):
        return ProviderCapability(
            self.name,
            login="not_required",
            price="available",
            index="available",
            bond="proxy",
            macro="unavailable",
            history="long",
            notes="Network probe disabled; optional yfinance is loaded only on fetch.",
        )

    def fetch(self, request):
        try:
            import yfinance  # noqa: F401
        except ImportError:
            return self._failure(
                ProviderError(
                    "missing_dependency",
                    "Optional yfinance package is not installed",
                    provider=self.name,
                )
            )
        return self._failure(
            ProviderError(
                "network_disabled",
                "Network fetch is disabled in capability phase",
                provider=self.name,
            )
        )
