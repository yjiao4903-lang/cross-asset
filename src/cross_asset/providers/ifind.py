from .base import BaseProvider, ProviderCapability, ProviderError


class IFINProvider(BaseProvider):
    name = "ifind"

    def probe(self):
        try:
            import iFinDPy  # noqa: F401
        except ImportError:
            return ProviderCapability(
                self.name,
                login="missing_dependency",
                notes="iFinDPy is not installed",
                errors=[
                    {
                        "code": "missing_dependency",
                        "message": "Optional iFinDPy package is not installed",
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
                "iFinD fetch requires an explicit live capability probe",
                provider=self.name,
            )
        )


IfindProvider = IFINProvider
