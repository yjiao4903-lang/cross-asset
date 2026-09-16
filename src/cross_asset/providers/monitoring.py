"""Concrete online monitoring adapters.

Monitoring is an operational observation lane only. It never grants
RESEARCH_ADMISSIBLE or LIVE_VERIFIED usage and never writes the acceptance
registry.
"""

from __future__ import annotations

from cross_asset.domain.models import DataRequest
from cross_asset.providers.base import BaseProvider, ProviderCapability, ProviderError
from cross_asset.providers.live import probe_yahoo, yahoo_fetch

YAHOO_MONITORING_SERIES = frozenset({"US_EQ", "US_GOV_10Y", "DXY", "HK_EQ"})


class YahooMonitoringProvider(BaseProvider):
    """Public Yahoo adapter restricted to the Phase-0 monitoring universe."""

    name = "yahoo"
    lane = "MONITORING"

    def probe(self) -> ProviderCapability:
        result = probe_yahoo(timeout=int(self.config.get("timeout", 8)))
        reachable = bool(result.get("reachable"))
        errors = []
        if not reachable:
            errors.append(
                {
                    "error_type": result.get("error_type") or "UNAVAILABLE",
                    "safe_error": result.get("safe_error"),
                }
            )
        return ProviderCapability(
            provider=self.name,
            login="not_required",
            price="available" if reachable else "unavailable",
            index="available" if reachable else "unavailable",
            bond="proxy" if reachable else "unavailable",
            macro="unavailable",
            history="public_monitoring" if reachable else None,
            notes="Monitoring-only public adapter; output is never formal admission evidence.",
            errors=errors,
        )

    def fetch(self, request: DataRequest):
        requested = set(request.series_ids)
        unsupported = sorted(requested - YAHOO_MONITORING_SERIES)
        if unsupported:
            return self._failure(
                ProviderError(
                    "unsupported_monitoring_series",
                    "Yahoo monitoring series not enabled: " + ",".join(unsupported),
                    provider=self.name,
                )
            )
        try:
            rows = yahoo_fetch(request, timeout=int(self.config.get("timeout", 10)))
        except Exception as exc:  # noqa: BLE001 - provider/network failures are operational evidence
            return self._failure(
                ProviderError(
                    "monitoring_fetch_failed",
                    str(exc)[:240],
                    provider=self.name,
                )
            )
        self.last_error = None
        for row in rows:
            row.metadata = {
                **(row.metadata or {}),
                "origin": "MONITORING",
                "usage_lane": "MONITORING_ONLY",
                "available_at_semantics": "provider_adapter_capture_time",
            }
        return rows


__all__ = ["YAHOO_MONITORING_SERIES", "YahooMonitoringProvider"]
