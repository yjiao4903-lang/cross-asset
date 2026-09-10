"""Isolated NY Fed Markets C0 client. Does not share FRED/Wind/CFTC code."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from cross_asset.ingestion.treasury_nyfed_http import (
    CachedResponse,
    ResponseCache,
    TreasuryNYFedHTTPError,
    request_with_retry,
    schema_hash,
)

NYFED_BASE = "https://markets.newyorkfed.org/api"
OMO_HISTORY_STATUS = "UNRESOLVED"
OMO_HISTORY_REASON = "official_source_is_quarterly_excel_only"


class NYFedMarketsError(TreasuryNYFedHTTPError):
    """NY Fed Markets transport or schema failure."""


@dataclass(frozen=True)
class NYFedPayload:
    endpoint: str
    kind: str
    rows: tuple[dict[str, Any], ...]
    fields: tuple[str, ...]
    schema_hash: str
    raw_hash: str
    fingerprint: str
    fetched_at: str
    cache_hit: bool
    raw_status: int


def _decode(response: CachedResponse) -> dict[str, Any]:
    try:
        payload = json.loads(response.payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise NYFedMarketsError("INVALID_JSON", str(exc)) from exc
    if not isinstance(payload, dict):
        raise NYFedMarketsError("INVALID_PAYLOAD", "NY Fed JSON must be an object")
    return payload


class NYFedMarketsClient:
    def __init__(
        self,
        *,
        cache: ResponseCache | None = None,
        transport=None,
        timeout: float = 20.0,
    ) -> None:
        self.cache = cache
        self.transport = transport
        self.timeout = timeout

    def _get(self, endpoint: str, *, resume: bool = True) -> CachedResponse:
        return request_with_retry(
            endpoint,
            timeout=self.timeout,
            cache=self.cache,
            transport=self.transport,
            resume=resume,
        )

    def _wrap(self, endpoint: str, kind: str, rows: list[dict[str, Any]], raw: CachedResponse) -> NYFedPayload:
        fields = tuple(sorted({key for row in rows for key in row}))
        return NYFedPayload(
            endpoint=endpoint,
            kind=kind,
            rows=tuple(rows),
            fields=fields,
            schema_hash=schema_hash(fields),
            raw_hash=raw.raw_hash,
            fingerprint=raw.fingerprint,
            fetched_at=raw.fetched_at,
            cache_hit=bool(self.cache and self.cache.get(raw.fingerprint)),
            raw_status=raw.status,
        )

    def fetch_repo_results(self, endpoint: str, *, resume: bool = True) -> NYFedPayload:
        raw = self._get(endpoint, resume=resume)
        payload = _decode(raw)
        operations = ((payload.get("repo") or {}).get("operations")) or []
        if not isinstance(operations, list):
            raise NYFedMarketsError("INVALID_PAYLOAD", "repo.operations must be a list")
        rows = [item for item in operations if isinstance(item, dict)]
        return self._wrap(endpoint, "repo_results", rows, raw)

    def fetch_soma_summary(self, endpoint: str, *, resume: bool = True) -> NYFedPayload:
        raw = self._get(endpoint, resume=resume)
        payload = _decode(raw)
        summary = ((payload.get("soma") or {}).get("summary")) or []
        if not isinstance(summary, list):
            raise NYFedMarketsError("INVALID_PAYLOAD", "soma.summary must be a list")
        rows = [item for item in summary if isinstance(item, dict)]
        return self._wrap(endpoint, "soma_summary", rows, raw)

    def fetch_primary_dealer(self, endpoint: str, *, resume: bool = True) -> NYFedPayload:
        raw = self._get(endpoint, resume=resume)
        payload = _decode(raw)
        series = ((payload.get("pd") or {}).get("timeseries")) or []
        if not isinstance(series, list):
            raise NYFedMarketsError("INVALID_PAYLOAD", "pd.timeseries must be a list")
        rows = [item for item in series if isinstance(item, dict)]
        return self._wrap(endpoint, "primary_dealer", rows, raw)

    def fetch_omo_transaction_history(self) -> None:
        raise NYFedMarketsError(
            "UNRESOLVED",
            f"{OMO_HISTORY_STATUS}:{OMO_HISTORY_REASON}",
        )
