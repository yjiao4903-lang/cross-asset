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
    utcnow,
)

NYFED_BASE = "https://markets.newyorkfed.org/api"
NYFED_RP_SEARCH = f"{NYFED_BASE}/rp/results/search.json"
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
    ingested_at: str
    cache_hit: bool
    raw_status: int
    retrieval_mode: str


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

    def _get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        resume: bool = True,
    ) -> CachedResponse:
        return request_with_retry(
            endpoint,
            params=params,
            timeout=self.timeout,
            cache=self.cache,
            transport=self.transport,
            resume=resume,
        )

    def _wrap(
        self,
        endpoint: str,
        kind: str,
        rows: list[dict[str, Any]],
        raw: CachedResponse,
        retrieval_mode: str,
    ) -> NYFedPayload:
        fields = tuple(sorted({key for row in rows for key in row}))
        ingested = utcnow().isoformat()
        return NYFedPayload(
            endpoint=endpoint,
            kind=kind,
            rows=tuple(rows),
            fields=fields,
            schema_hash=schema_hash(fields),
            raw_hash=raw.raw_hash,
            fingerprint=raw.fingerprint,
            fetched_at=raw.fetched_at,
            ingested_at=ingested,
            cache_hit=bool(raw.cache_hit),
            raw_status=raw.status,
            retrieval_mode=retrieval_mode,
        )

    def fetch_repo_results(self, endpoint: str, *, resume: bool = True) -> NYFedPayload:
        raw = self._get(endpoint, resume=resume)
        payload = _decode(raw)
        operations = ((payload.get("repo") or {}).get("operations")) or []
        if not isinstance(operations, list):
            raise NYFedMarketsError("INVALID_PAYLOAD", "repo.operations must be a list")
        rows = [item for item in operations if isinstance(item, dict)]
        return self._wrap(endpoint, "repo_results", rows, raw, "recent_window")

    def fetch_repo_search(
        self,
        *,
        start: str,
        end: str,
        operation_type: str | None = None,
        endpoint: str = NYFED_RP_SEARCH,
        resume: bool = True,
    ) -> NYFedPayload:
        raw = self._get(endpoint, params={"startDate": start, "endDate": end}, resume=resume)
        payload = _decode(raw)
        operations = ((payload.get("repo") or {}).get("operations")) or []
        if not isinstance(operations, list):
            raise NYFedMarketsError("INVALID_PAYLOAD", "repo.operations must be a list")
        rows = [item for item in operations if isinstance(item, dict)]
        if operation_type:
            wanted = operation_type.casefold()
            rows = [
                item
                for item in rows
                if str(item.get("operationType") or "").casefold() == wanted
            ]
        return self._wrap(endpoint, "repo_results", rows, raw, "official_search")

    def fetch_soma_summary(self, endpoint: str, *, resume: bool = True) -> NYFedPayload:
        raw = self._get(endpoint, resume=resume)
        payload = _decode(raw)
        summary = ((payload.get("soma") or {}).get("summary")) or []
        if not isinstance(summary, list):
            raise NYFedMarketsError("INVALID_PAYLOAD", "soma.summary must be a list")
        rows = [item for item in summary if isinstance(item, dict)]
        return self._wrap(endpoint, "soma_summary", rows, raw, "full_series")

    def fetch_primary_dealer(self, endpoint: str, *, resume: bool = True) -> NYFedPayload:
        raw = self._get(endpoint, resume=resume)
        payload = _decode(raw)
        series = ((payload.get("pd") or {}).get("timeseries")) or []
        if not isinstance(series, list):
            raise NYFedMarketsError("INVALID_PAYLOAD", "pd.timeseries must be a list")
        rows = [item for item in series if isinstance(item, dict)]
        return self._wrap(endpoint, "primary_dealer", rows, raw, "full_series")

    def fetch_omo_transaction_history(self) -> None:
        raise NYFedMarketsError(
            "UNRESOLVED",
            f"{OMO_HISTORY_STATUS}:{OMO_HISTORY_REASON}",
        )
