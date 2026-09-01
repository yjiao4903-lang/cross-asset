"""FRED/ALFRED adapter with explicit PIT evidence and secret-safe errors."""
from __future__ import annotations

import csv
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

import requests

from ..settings import load_fred_api_key
from .base import BaseProvider, DataRequest, Observation, ProviderCapability, ProviderError


class FREDProvider(BaseProvider):
    name = "fred"
    SERIES: ClassVar = {"US_GOV_10Y": "DGS10", "US_REAL_10Y": "DFII10", "US_CPI": "CPIAUCSL", "US_CORE_PCE": "PCEPILFE", "US_UNEMPLOYMENT": "UNRATE", "US_INITIAL_CLAIMS": "ICSA", "US_INDUSTRIAL_PRODUCTION": "INDPRO", "EFFR": "EFFR", "DGS2": "DGS2", "DGS5": "DGS5", "DGS30": "DGS30", "CPILFESL": "CPILFESL", "PCEPI": "PCEPI", "T10YIE": "T10YIE", "T5YIE": "T5YIE"}
    PRIORITY_SERIES: ClassVar = ("EFFR", "DGS2", "DGS5", "DGS30", "CPILFESL", "PCEPI", "T10YIE", "T5YIE")
    CORE_SERIES: ClassVar = ("US_GOV_10Y", "US_REAL_10Y")

    def __init__(self, *, opener: Callable[..., Any] | None = None, raw_archive=None, timeout=8, retries=2, **config):
        super().__init__(**config)
        self.opener = opener
        self.raw_archive, self.timeout, self.retries = raw_archive, timeout, retries
        self.min_interval = float(config.get("min_interval", 0.0))
        self._last_public_request = 0.0
        self._last_alfred_request = 0.0
        self.last_result: dict[str, Any] = {}

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = str(exc).split("?")[0]
        key = os.getenv("FRED_API_KEY")
        return message.replace(key, "<redacted>")[:240] if key else message[:240]

    def _api_key(self):
        return load_fred_api_key(self.config.get("env_path"))

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        key = self._api_key()
        if not key:
            raise ProviderError("missing_credentials", "FRED API key is not configured", provider=self.name)
        query = dict(params, api_key=key, file_type="json")
        url = "https://api.stlouisfed.org/fred/" + endpoint + "?" + urllib.parse.urlencode(query)
        last = None
        for attempt in range(self.retries + 1):
            try:
                if self.opener:
                    with self.opener(urllib.request.Request(url, headers={"User-Agent": "cross-asset-engine/0.1"}), timeout=self.timeout) as response:
                        status = getattr(response, "status", 200)
                        body = response.read()
                else:
                    response = requests.get(
                        "https://api.stlouisfed.org/fred/" + endpoint,
                        params=query,
                        timeout=self.timeout,
                    )
                    status, body = response.status_code, response.content
                if status == 429:
                    raise ProviderError("rate_limited", "FRED request rate limited", provider=self.name)
                if status >= 400:
                    raise ProviderError(f"http_{status}", f"FRED HTTP status {status}", provider=self.name)
                return json.loads(body)
            except ProviderError as exc:
                last = exc
                if exc.code.startswith("http_") and exc.code not in {"http_429"}:
                    break
            except (TimeoutError, urllib.error.URLError, OSError, ValueError) as exc:
                last = exc
            if attempt < self.retries:
                time.sleep(0.05 * (attempt + 1))
        if isinstance(last, ProviderError):
            raise last
        raise ProviderError("request_failed", self._safe_error(last or RuntimeError("unknown failure")), provider=self.name)

    def probe(self) -> ProviderCapability:
        key = self._api_key()
        if not key:
            return ProviderCapability(self.name, login="missing", bond="available", macro="available", history="long", notes="FRED DGS10/DFII10 probe requires FRED_API_KEY; no network call made", errors=[{"code": "missing_credentials", "message": "FRED_API_KEY is not configured"}])
        try:
            metadata = {sid: self._request("series", {"series_id": self.SERIES[sid]}) for sid in self.CORE_SERIES}
            self.last_result = {"status": "SUCCESS", "series_metadata": sorted(metadata), "pit_evidence": "requires realtime/vintage verification"}
            return ProviderCapability(self.name, login="configured", bond="available", macro="available", history="long", notes="FRED metadata endpoint reachable; observation PIT requires explicit vintage evidence", errors=[])
        except ProviderError as exc:
            self.last_result = {"status": "FAILED", "error": {"code": exc.code, "message": self._safe_error(exc)}}
            return ProviderCapability(self.name, login="configured", bond="unknown", macro="unknown", history="unknown", errors=[{"code": exc.code, "message": self._safe_error(exc)}])

    def fetch(self, request: DataRequest) -> list[Observation]:
        if not self._api_key():
            return self._failure(ProviderError("missing_credentials", "FRED API key is not configured", provider=self.name))
        rows: list[Observation] = []
        raw: dict[str, Any] = {}
        attempt_id = str(uuid4())
        started = datetime.now(UTC).replace(tzinfo=None)
        try:
            for sid in request.series_ids:
                code = self.SERIES.get(sid, request.source_series_ids.get(sid, sid))
                series = self._request("series", {"series_id": code})
                observations = self._request("series/observations", {"series_id": code, "observation_start": str(request.start or "2020-01-01"), "observation_end": str(request.end or datetime.now(UTC).date()), "realtime_start": str(request.start or "2020-01-01"), "realtime_end": str(request.end or datetime.now(UTC).date())})
                raw[sid] = {"series": series, "observations": observations}
                # FRED observations expose date/realtime_period, not first release time.
                # Never map observation date to available_at.
            if self.raw_archive:
                self.raw_archive.write(self.name, "fred_dgs10_dfii10", raw)
            self.last_result = {"status": "PARTIAL", "pit_evidence": "pit_evidence_insufficient", "series": sorted(raw)}
            store = self.config.get("store")
            if store:
                store.record_provider_attempt({"attempt_id": attempt_id, "provider": self.name, "series_id": ",".join(sorted(raw)), "started_at": started, "finished_at": datetime.now(UTC).replace(tzinfo=None), "status": "SUCCESS", "latency_ms": (datetime.now(UTC).replace(tzinfo=None) - started).total_seconds() * 1000, "schema_error": None, "error_message": "pit_evidence_insufficient"})
            return rows
        except ProviderError as exc:
            self.last_result = {"status": "FAILED", "error": {"code": exc.code, "message": self._safe_error(exc)}}
            return self._failure(exc)

    def fetch_sample(self, request: DataRequest) -> dict[str, Any]:
        """Fetch auditable sample evidence without normalizing or writing observations."""
        if not self._api_key():
            return {"status": "BLOCKED", "error": {"code": "missing_credentials"}}
        archive = self.raw_archive
        report: dict[str, Any] = {"status": "PARTIAL", "series": {}, "pit_verdict": "BLOCKED"}
        for sid in request.series_ids:
            started = datetime.now(UTC).replace(tzinfo=None)
            code = self.SERIES.get(sid, request.source_series_ids.get(sid, sid))
            try:
                metadata = self._request("series", {"series_id": code})
                observations = self._request("series/observations", {"series_id": code, "observation_start": str(request.start or "2024-01-01"), "observation_end": str(request.end or datetime.now(UTC).date()), "realtime_start": str(request.start or "2024-01-01"), "realtime_end": str(request.end or datetime.now(UTC).date())})
                vintage = self._request("series/vintagedates", {"series_id": code})
                payload = {"metadata": metadata, "observations": observations, "vintage_dates": vintage}
                raw_path = archive.write(self.name, code, payload) if archive else None
                rows = observations.get("observations", [])
                report["series"][sid] = {"source_series_id": code, "metadata": metadata.get("seriess", [{}])[0], "row_count": len(rows), "date_start": rows[0].get("date") if rows else None, "date_end": rows[-1].get("date") if rows else None, "realtime_fields": sorted(rows[0]) if rows else [], "vintage_count": len(vintage.get("vintage_dates", [])), "raw_path": str(raw_path) if raw_path else None, "pit_verdict": "INSUFFICIENT_FIRST_RELEASE_TIMESTAMP"}
                status = "SUCCESS"
                error_message = "pit_evidence_insufficient"
            except ProviderError as exc:
                report["series"][sid] = {"source_series_id": code, "status": "FAILED", "error": {"code": exc.code, "message": self._safe_error(exc)}}
                status, error_message = "FAILED", self._safe_error(exc)
            if self.config.get("store"):
                self.config["store"].record_provider_attempt({"attempt_id": str(uuid4()), "provider": self.name, "series_id": sid, "started_at": started, "finished_at": datetime.now(UTC).replace(tzinfo=None), "status": status, "latency_ms": (datetime.now(UTC).replace(tzinfo=None) - started).total_seconds() * 1000, "schema_error": None, "error_message": error_message})
        return report

    def fetch_public_csv_sample(self, request: DataRequest) -> dict[str, Any]:
        """Use public fredgraph CSV only as raw evidence; never infer PIT availability."""
        report: dict[str, Any] = {"status": "PARTIAL", "source_mode": "FRED_PUBLIC_GRAPH_CSV", "series": {}, "pit_verdict": "BLOCKED"}
        for sid in request.series_ids:
            started = datetime.now(UTC).replace(tzinfo=None)
            code = self.SERIES.get(sid, request.source_series_ids.get(sid, sid))
            try:
                wait = self.min_interval - (time.monotonic() - self._last_public_request)
                if wait > 0:
                    time.sleep(wait)
                response = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": code, "cosd": str(request.start or "2024-01-01"), "coed": str(request.end or datetime.now(UTC).date())}, timeout=self.timeout)
                self._last_public_request = time.monotonic()
                if response.status_code >= 400:
                    raise ProviderError(f"http_{response.status_code}", f"FRED public CSV HTTP status {response.status_code}", provider=self.name)
                body = response.content
                rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
                if not rows or "observation_date" not in rows[0] or code not in rows[0]:
                    raise ProviderError("schema_error", "FRED public CSV missing observation_date/value", provider=self.name)
                raw_path = self.raw_archive.write(self.name, f"public_csv_{code}", body, extension="csv") if self.raw_archive else None
                report["series"][sid] = {"source_series_id": code, "header": sorted(rows[0]), "row_count": len(rows), "date_start": rows[0].get("observation_date"), "date_end": rows[-1].get("observation_date"), "raw_path": str(raw_path) if raw_path else None, "transport": "public_csv", "pit_verdict": "INSUFFICIENT_FIRST_RELEASE_TIMESTAMP"}
                status, error_message = "SUCCESS", "pit_evidence_insufficient"
            except (ProviderError, UnicodeError, csv.Error, requests.RequestException) as exc:
                report["series"][sid] = {"source_series_id": code, "status": "FAILED", "error": {"code": getattr(exc, "code", type(exc).__name__), "message": self._safe_error(exc)}}
                status, error_message = "FAILED", self._safe_error(exc)
            if self.config.get("store"):
                self.config["store"].record_provider_attempt({"attempt_id": str(uuid4()), "provider": self.name, "series_id": sid, "started_at": started, "finished_at": datetime.now(UTC).replace(tzinfo=None), "status": status, "latency_ms": (datetime.now(UTC).replace(tzinfo=None) - started).total_seconds() * 1000, "schema_error": None, "error_message": error_message})
        return report

    def fetch_alfred_cpi_once(self, *, observation_start: str = "2024-01-01", realtime_start: str = "1776-07-04", realtime_end: str = "9999-12-31", series_id: str = "US_CPI", source_series_id: str = "CPIAUCSL") -> dict[str, Any]:
        """Single no-retry ALFRED request; never normalizes observations."""
        attempt_id = str(uuid4())
        key = self._api_key()
        if not key:
            return {"status": "BLOCKED", "error": {"code": "missing_credentials"}}
        started = time.monotonic()
        started_at = datetime.now(UTC).replace(tzinfo=None)
        def record(status: str, message: str | None = None) -> None:
            store = self.config.get("store")
            if store:
                store.record_provider_attempt({"attempt_id": attempt_id, "provider": self.name, "series_id": series_id, "started_at": started_at, "finished_at": datetime.now(UTC).replace(tzinfo=None), "status": status, "latency_ms": (time.monotonic() - started) * 1000, "schema_error": None, "error_message": message})
        params = {"series_id": source_series_id, "output_type": 4, "observation_start": observation_start, "realtime_start": realtime_start, "realtime_end": realtime_end, "file_type": "json", "api_key": key}
        try:
            wait = self.min_interval - (time.monotonic() - self._last_alfred_request)
            if wait > 0:
                time.sleep(wait)
            with requests.Session() as session:
                response = session.get("https://api.stlouisfed.org/fred/series/observations", params=params, timeout=self.timeout)
            self._last_alfred_request = time.monotonic()
            if response.status_code >= 400:
                try:
                    error_payload = response.json()
                except ValueError:
                    error_payload = {}
                error_code = str(error_payload.get("error_code") or f"http_{response.status_code}")
                error_message = self._safe_error(RuntimeError(str(error_payload.get("error_message") or "FRED HTTP error")))
                record("FAILED", error_code)
                return {"status": "FAILED", "error": {"code": error_code, "message": error_message}, "elapsed_ms": round((time.monotonic() - started) * 1000, 2)}
            payload = response.json()
            rows = payload.get("observations", [])
            raw_path = self.raw_archive.write(self.name, f"alfred_{source_series_id}_output_type_4", response.content, extension="json") if self.raw_archive else None
            record("SUCCESS", "pit_evidence_insufficient")
            return {"status": "PARTIAL", "series_id": series_id, "source_series_id": source_series_id, "output_type": 4, "row_count": len(rows), "date_start": rows[0].get("date") if rows else None, "date_end": rows[-1].get("date") if rows else None, "realtime_fields": sorted(rows[0]) if rows else [], "raw_path": str(raw_path) if raw_path else None, "pit_verdict": "INSUFFICIENT_FIRST_RELEASE_TIMESTAMP", "elapsed_ms": round((time.monotonic() - started) * 1000, 2)}
        except (requests.RequestException, ValueError) as exc:
            record("FAILED", self._safe_error(exc))
            return {"status": "FAILED", "error": {"code": type(exc).__name__, "message": self._safe_error(exc)}, "elapsed_ms": round((time.monotonic() - started) * 1000, 2)}


FredProvider = FREDProvider
