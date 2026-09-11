"""Official FRED/ALFRED C0 client with deterministic provenance and cache semantics."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from cross_asset.settings import load_fred_api_key

_BASE_URL = "https://api.stlouisfed.org/fred"
_RETRYABLE_HTTP = {429, 500, 502, 503, 504}
_SECRET_KEYS = {"api_key"}


class FredAlfredError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "status_code": self.status_code,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class FredPayload:
    endpoint: str
    params: dict[str, Any]
    payload: dict[str, Any]
    request_fingerprint: str
    raw_sha256: str
    fetched_at: datetime
    ingested_at: datetime
    cache_hit: bool
    status_code: int = 200
    raw_archive_path: str | None = None


class FredResponseCache:
    """Secret-free content cache keyed by deterministic request fingerprint."""

    def __init__(self, root: str | Path = ".cache/fred_alfred"):
        self.root = Path(root)

    def _paths(self, fingerprint: str) -> tuple[Path, Path]:
        prefix = self.root / fingerprint[:2]
        return prefix / f"{fingerprint}.json", prefix / f"{fingerprint}.meta.json"

    def get(
        self,
        fingerprint: str,
        *,
        max_age_seconds: float | None = None,
    ) -> tuple[bytes, dict[str, Any]] | None:
        payload_path, meta_path = self._paths(fingerprint)
        if not payload_path.exists() or not meta_path.exists():
            return None
        if max_age_seconds is not None:
            age = time.time() - payload_path.stat().st_mtime
            if age > max_age_seconds:
                return None
        raw = payload_path.read_bytes()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if hashlib.sha256(raw).hexdigest() != meta.get("raw_sha256"):
            raise FredAlfredError("cache_hash_mismatch", "FRED cache payload hash mismatch")
        if meta.get("request_fingerprint") != fingerprint:
            raise FredAlfredError("cache_fingerprint_mismatch", "FRED cache fingerprint mismatch")
        return raw, meta

    def put(
        self,
        fingerprint: str,
        raw: bytes,
        *,
        metadata: dict[str, Any],
    ) -> None:
        payload_path, meta_path = self._paths(fingerprint)
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        clean_meta = {key: value for key, value in metadata.items() if key not in _SECRET_KEYS}
        clean_meta["request_fingerprint"] = fingerprint
        clean_meta["raw_sha256"] = hashlib.sha256(raw).hexdigest()
        tmp_payload = payload_path.with_suffix(".json.tmp")
        tmp_meta = meta_path.with_suffix(".json.tmp")
        tmp_payload.write_bytes(raw)
        tmp_meta.write_text(
            json.dumps(clean_meta, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(tmp_payload, payload_path)
        os.replace(tmp_meta, meta_path)


def canonical_request_fingerprint(endpoint: str, params: dict[str, Any]) -> str:
    safe = {
        str(key): value
        for key, value in params.items()
        if str(key).lower() not in _SECRET_KEYS
    }
    blob = json.dumps(
        {"endpoint": endpoint.strip("/"), "params": safe},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class FredAlfredClient:
    """Research-staging-only client; it never writes approved observations."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        env_path: str | Path | None = None,
        timeout: float = 10.0,
        retries: int = 3,
        backoff_base: float = 0.25,
        min_interval: float = 0.0,
        cache: FredResponseCache | None = None,
        cache_max_age_seconds: float | None = 86400.0,
        raw_archive: Any | None = None,
        session: Any | None = None,
        sleep: Any = time.sleep,
        monotonic: Any = time.monotonic,
    ):
        self._explicit_api_key = api_key
        self.env_path = env_path
        self.timeout = float(timeout)
        self.retries = int(retries)
        self.backoff_base = float(backoff_base)
        self.min_interval = float(min_interval)
        self.cache = cache
        self.cache_max_age_seconds = cache_max_age_seconds
        self.raw_archive = raw_archive
        self.session = session or requests.Session()
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at = 0.0

    def api_key(self) -> str | None:
        return self._explicit_api_key or load_fred_api_key(self.env_path)

    @staticmethod
    def _safe_message(value: Any, key: str | None) -> str:
        message = str(value)
        if key:
            message = message.replace(key, "<redacted>")
        if "api_key=" in message:
            message = message.split("api_key=", 1)[0] + "api_key=<redacted>"
        return message[:300]

    def _rate_limit(self) -> None:
        remaining = self.min_interval - (self._monotonic() - self._last_request_at)
        if remaining > 0:
            self._sleep(remaining)

    def _retry_delay(self, attempt: int, response: Any | None = None) -> float:
        if response is not None:
            retry_after = getattr(response, "headers", {}).get("Retry-After")
            if retry_after:
                try:
                    return max(float(retry_after), 0.0)
                except (TypeError, ValueError):
                    pass
        return self.backoff_base * (2**attempt)

    def request_json(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        use_cache: bool = True,
        cache_max_age_seconds: float | None = None,
    ) -> FredPayload:
        key = self.api_key()
        if not key:
            raise FredAlfredError(
                "missing_credentials",
                "FRED_API_KEY is not configured; official API smoke is DATA_BLOCKED",
            )
        clean_params = {str(k): v for k, v in params.items() if v is not None}
        clean_params.setdefault("file_type", "json")
        fingerprint = canonical_request_fingerprint(endpoint, clean_params)
        ttl = self.cache_max_age_seconds if cache_max_age_seconds is None else cache_max_age_seconds
        if use_cache and self.cache is not None:
            cached = self.cache.get(fingerprint, max_age_seconds=ttl)
            if cached is not None:
                raw, meta = cached
                try:
                    payload = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise FredAlfredError(
                        "cache_json_invalid", "Cached FRED JSON is invalid"
                    ) from exc
                fetched_at = datetime.fromisoformat(str(meta["fetched_at"]))
                if fetched_at.tzinfo is None:
                    fetched_at = fetched_at.replace(tzinfo=UTC)
                return FredPayload(
                    endpoint=endpoint,
                    params=clean_params,
                    payload=payload,
                    request_fingerprint=fingerprint,
                    raw_sha256=hashlib.sha256(raw).hexdigest(),
                    fetched_at=fetched_at,
                    ingested_at=datetime.now(UTC),
                    cache_hit=True,
                    raw_archive_path=(
                        self.raw_archive.write(
                            "fred_alfred",
                            fingerprint,
                            raw,
                            captured_at=fetched_at,
                            extension="json",
                        )
                        if self.raw_archive is not None
                        else None
                    ),
                )

        request_params = dict(clean_params)
        request_params["api_key"] = key
        last_error: FredAlfredError | None = None
        for attempt in range(self.retries + 1):
            response = None
            try:
                self._rate_limit()
                response = self.session.get(
                    f"{_BASE_URL}/{endpoint.strip('/')}",
                    params=request_params,
                    timeout=self.timeout,
                )
                self._last_request_at = self._monotonic()
                status = int(response.status_code)
                raw = bytes(response.content)
                if status >= 400:
                    try:
                        error_payload = response.json()
                    except (ValueError, json.JSONDecodeError):
                        error_payload = {}
                    provider_message = error_payload.get("error_message") or f"FRED HTTP {status}"
                    retryable = status in _RETRYABLE_HTTP
                    code = "rate_limited" if status == 429 else f"http_{status}"
                    last_error = FredAlfredError(
                        code,
                        self._safe_message(provider_message, key),
                        status_code=status,
                        retryable=retryable,
                    )
                    if not retryable:
                        raise last_error
                    if attempt >= self.retries:
                        raise last_error
                    self._sleep(self._retry_delay(attempt, response))
                    continue
                try:
                    payload = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise FredAlfredError(
                        "malformed_json",
                        "FRED returned malformed JSON",
                        status_code=status,
                    ) from exc
                fetched_at = datetime.now(UTC)
                raw_hash = hashlib.sha256(raw).hexdigest()
                if self.cache is not None:
                    self.cache.put(
                        fingerprint,
                        raw,
                        metadata={
                            "endpoint": endpoint,
                            "params": clean_params,
                            "fetched_at": fetched_at.isoformat(),
                            "status_code": status,
                        },
                    )
                return FredPayload(
                    endpoint=endpoint,
                    params=clean_params,
                    payload=payload,
                    request_fingerprint=fingerprint,
                    raw_sha256=raw_hash,
                    fetched_at=fetched_at,
                    ingested_at=datetime.now(UTC),
                    cache_hit=False,
                    status_code=status,
                    raw_archive_path=(
                        self.raw_archive.write(
                            "fred_alfred",
                            fingerprint,
                            raw,
                            captured_at=fetched_at,
                            extension="json",
                        )
                        if self.raw_archive is not None
                        else None
                    ),
                )
            except FredAlfredError:
                raise
            except requests.Timeout:
                last_error = FredAlfredError(
                    "timeout", "FRED request timed out", retryable=True
                )
            except requests.RequestException as exc:
                last_error = FredAlfredError(
                    "transport_error",
                    self._safe_message(exc, key),
                    retryable=True,
                )
            if attempt >= self.retries:
                raise last_error or FredAlfredError("request_failed", "FRED request failed")
            self._sleep(self._retry_delay(attempt, response))
        raise last_error or FredAlfredError("request_failed", "FRED request failed")

    def fetch_metadata(self, provider_series_id: str, *, use_cache: bool = True) -> FredPayload:
        return self.request_json("series", {"series_id": provider_series_id}, use_cache=use_cache)

    def fetch_vintage_dates(
        self,
        provider_series_id: str,
        *,
        realtime_start: str = "1776-07-04",
        realtime_end: str = "9999-12-31",
        use_cache: bool = True,
    ) -> FredPayload:
        return self.request_json(
            "series/vintagedates",
            {
                "series_id": provider_series_id,
                "realtime_start": realtime_start,
                "realtime_end": realtime_end,
                "limit": 10000,
                "sort_order": "asc",
            },
            use_cache=use_cache,
        )

    def fetch_revised_latest(
        self,
        provider_series_id: str,
        *,
        observation_start: str,
        observation_end: str,
        use_cache: bool = True,
    ) -> FredPayload:
        return self.request_json(
            "series/observations",
            {
                "series_id": provider_series_id,
                "observation_start": observation_start,
                "observation_end": observation_end,
                "output_type": 1,
            },
            use_cache=use_cache,
        )

    def fetch_historical_asof(
        self,
        provider_series_id: str,
        *,
        observation_start: str,
        observation_end: str,
        as_of: str,
        use_cache: bool = True,
    ) -> FredPayload:
        return self.request_json(
            "series/observations",
            {
                "series_id": provider_series_id,
                "observation_start": observation_start,
                "observation_end": observation_end,
                "vintage_dates": as_of,
                "output_type": 1,
            },
            use_cache=use_cache,
            cache_max_age_seconds=None,
        )

    def fetch_initial_release(
        self,
        provider_series_id: str,
        *,
        observation_start: str,
        observation_end: str,
        use_cache: bool = True,
    ) -> FredPayload:
        return self.request_json(
            "series/observations",
            {
                "series_id": provider_series_id,
                "observation_start": observation_start,
                "observation_end": observation_end,
                "realtime_start": "1776-07-04",
                "realtime_end": "9999-12-31",
                "output_type": 4,
            },
            use_cache=use_cache,
            cache_max_age_seconds=None,
        )

    def fetch_all_realtime_periods(
        self,
        provider_series_id: str,
        *,
        observation_start: str,
        observation_end: str,
        realtime_start: str = "1776-07-04",
        realtime_end: str = "9999-12-31",
        use_cache: bool = True,
    ) -> FredPayload:
        return self.request_json(
            "series/observations",
            {
                "series_id": provider_series_id,
                "observation_start": observation_start,
                "observation_end": observation_end,
                "realtime_start": realtime_start,
                "realtime_end": realtime_end,
                "output_type": 1,
            },
            use_cache=use_cache,
            cache_max_age_seconds=None,
        )


__all__ = [
    "FredAlfredClient",
    "FredAlfredError",
    "FredPayload",
    "FredResponseCache",
    "canonical_request_fingerprint",
]
