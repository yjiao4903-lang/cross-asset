from .base import BaseProvider, ProviderCapability, ProviderError


class WindProvider(BaseProvider):
    name = "wind"

    def probe(self):
        try:
            import WindPy  # noqa: F401
        except ImportError:
            return ProviderCapability(
                self.name,
                login="missing_dependency",
                notes="WindPy is not installed",
                errors=[
                    {
                        "code": "missing_dependency",
                        "message": "Optional WindPy package is not installed",
                    }
                ],
            )
        return ProviderCapability(
            self.name,
            login="unknown",
            notes="SDK present; login and entitlement probe requires explicit live run.",
        )

    def fetch(self, request):
        return self._failure(
            ProviderError(
                "not_probed",
                "Wind fetch requires an explicit live capability probe",
                provider=self.name,
            )
        )
