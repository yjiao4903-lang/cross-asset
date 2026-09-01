from .base import BaseProvider, ProviderCapability, ProviderError


class TushareProvider(BaseProvider):
    name = "tushare"

    def probe(self):
        return ProviderCapability(
            self.name,
            login="configured" if self.config.get("token") else "missing",
            price="available",
            index="available",
            valuation="permission",
            history="permission",
            notes="Token entitlement and endpoint probes require explicit live run.",
            errors=[]
            if self.config.get("token")
            else [{"code": "missing_credentials", "message": "TUSHARE_TOKEN is not configured"}],
        )

    def fetch(self, request):
        try:
            import tushare  # noqa: F401
        except ImportError:
            return self._failure(
                ProviderError(
                    "missing_dependency",
                    "Optional tushare package is not installed",
                    provider=self.name,
                )
            )
        if not self.config.get("token"):
            return self._failure(
                ProviderError(
                    "missing_credentials", "Tushare token is not configured", provider=self.name
                )
            )
        return self._failure(
            ProviderError(
                "network_disabled",
                "Network fetch is disabled in capability phase",
                provider=self.name,
            )
        )
