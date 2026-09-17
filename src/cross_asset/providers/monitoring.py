"""Concrete online monitoring adapters.

Monitoring is an operational observation lane only. It never grants
RESEARCH_ADMISSIBLE or LIVE_VERIFIED usage and never writes the acceptance
registry.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime

from cross_asset.domain.models import DataRequest, Observation
from cross_asset.providers.base import BaseProvider, ProviderCapability, ProviderError
from cross_asset.providers.fred import FREDProvider
from cross_asset.providers.live import probe_yahoo, yahoo_fetch

YAHOO_MONITORING_SERIES = frozenset({"US_EQ", "US_GOV_10Y", "DXY", "HK_EQ"})

# Canonical repository identity -> exact public FRED identity + raw semantics.
# These are raw monitoring inputs only; factor transforms remain producer-owned.
FRED_MONITORING_CONTRACTS = {
    "US_NONFARM_PAYROLLS": {
        "source_series_id": "PAYEMS",
        "frequency": "monthly",
        "unit": "thousands_persons",
    },
    "US_CORE_CPI": {
        "source_series_id": "CPILFESL",
        "frequency": "monthly",
        "unit": "index_1982_1984_100",
    },
    "US_GOV_2Y": {
        "source_series_id": "DGS2",
        "frequency": "daily",
        "unit": "yield_percent",
    },
    "US_REAL_10Y": {
        "source_series_id": "DFII10",
        "frequency": "daily",
        "unit": "yield_percent",
    },
}
FRED_MONITORING_SERIES = frozenset(FRED_MONITORING_CONTRACTS)


class _PublicCsvCapture:
    """Capture bytes emitted by the existing FRED public-CSV evidence method."""

    def __init__(self):
        self.payloads: dict[str, bytes] = {}

    def write(self, _provider, source, payload, *, extension="json"):
        if extension == "csv" and isinstance(payload, bytes):
            self.payloads[str(source)] = payload
        return f"memory://{source}.{extension}"


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


class FREDMonitoringProvider(BaseProvider):
    """Monitoring-only FRED adapter reusing the existing public CSV transport.

    Historical rows are captured as-of *now*. Their observation dates are real,
    but their first-release availability is not asserted; all rows therefore use
    one capture timestamp as ``available_at`` and carry an explicit non-PIT marker.
    """

    name = "fred"
    lane = "MONITORING"

    def probe(self) -> ProviderCapability:
        return ProviderCapability(
            provider=self.name,
            login="not_required",
            bond="public_csv",
            macro="public_csv",
            history="public_monitoring_non_pit",
            notes=(
                "Monitoring-only wrapper around existing FREDProvider public CSV; "
                "capture history is not first-release/PIT evidence."
            ),
            errors=[],
        )

    def fetch(self, request: DataRequest) -> list[Observation]:
        requested = [str(value) for value in request.series_ids]
        unsupported = sorted(set(requested) - FRED_MONITORING_SERIES)
        if unsupported:
            return self._failure(
                ProviderError(
                    "unsupported_monitoring_series",
                    "FRED monitoring series not enabled: " + ",".join(unsupported),
                    provider=self.name,
                )
            )

        source_ids = {
            sid: str(FRED_MONITORING_CONTRACTS[sid]["source_series_id"])
            for sid in requested
        }
        capture = _PublicCsvCapture()
        transport = FREDProvider(
            raw_archive=capture,
            timeout=int(self.config.get("timeout", 10)),
            retries=0,
            min_interval=float(self.config.get("min_interval", 0.0)),
        )
        inner = DataRequest(
            series_ids=requested,
            start=request.start or date(2020, 1, 1),
            end=request.end,
            as_of=request.as_of,
            source_series_ids=source_ids,
        )
        report = transport.fetch_public_csv_sample(inner)
        failures = {
            sid: item
            for sid, item in (report.get("series") or {}).items()
            if str((item or {}).get("status") or "").upper() == "FAILED"
        }
        if failures:
            detail = ",".join(
                f"{sid}:{(item.get('error') or {}).get('code', 'provider_failure')}"
                for sid, item in sorted(failures.items())
            )
            return self._failure(
                ProviderError(
                    "monitoring_fetch_failed",
                    "FRED public CSV failure: " + detail,
                    provider=self.name,
                )
            )

        captured_at = datetime.now(UTC)
        observations: list[Observation] = []
        for sid in requested:
            contract = FRED_MONITORING_CONTRACTS[sid]
            source_series_id = str(contract["source_series_id"])
            payload = capture.payloads.get(f"public_csv_{source_series_id}")
            if payload is None:
                return self._failure(
                    ProviderError(
                        "monitoring_capture_missing",
                        f"FRED public CSV bytes missing for {sid}/{source_series_id}",
                        provider=self.name,
                    )
                )
            try:
                rows = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
                for raw in rows:
                    value_text = str(raw.get(source_series_id) or "").strip()
                    observation_text = str(raw.get("observation_date") or "").strip()
                    if not observation_text or value_text in {"", ".", "NA", "NaN"}:
                        continue
                    observations.append(
                        Observation(
                            series_id=sid,
                            observation_date=date.fromisoformat(observation_text),
                            available_at=captured_at,
                            value=float(value_text),
                            source=self.name,
                            source_series_id=source_series_id,
                            frequency=str(contract["frequency"]),
                            unit=str(contract["unit"]),
                            currency="USD" if sid.startswith("US_GOV_") or sid == "US_REAL_10Y" else None,
                            quality="ok",
                            metadata={
                                "origin": "MONITORING",
                                "usage_lane": "MONITORING_ONLY",
                                "transport": "FRED_PUBLIC_GRAPH_CSV",
                                "available_at_semantics": "monitoring_capture_time_non_pit",
                                "first_release_timestamp_known": False,
                                "history_capture_start": str(inner.start),
                            },
                        )
                    )
            except (UnicodeError, csv.Error, ValueError) as exc:
                return self._failure(
                    ProviderError(
                        "monitoring_schema_error",
                        f"FRED public CSV parse failed for {sid}: {str(exc)[:160]}",
                        provider=self.name,
                    )
                )

        if not observations:
            return self._failure(
                ProviderError(
                    "monitoring_empty",
                    "FRED public CSV returned no usable monitoring observations",
                    provider=self.name,
                )
            )
        self.last_error = None
        return observations


__all__ = [
    "FRED_MONITORING_CONTRACTS",
    "FRED_MONITORING_SERIES",
    "YAHOO_MONITORING_SERIES",
    "FREDMonitoringProvider",
    "YahooMonitoringProvider",
]
