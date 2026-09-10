"""Isolated Treasury FiscalData C0 client. Does not share FRED/Wind/CFTC code."""

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

FISCALDATA_BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
DEFAULT_PAGE_SIZE = 1000


class TreasuryFiscalDataError(TreasuryNYFedHTTPError):
    """FiscalData-specific transport or pagination failure."""


@dataclass(frozen=True)
class FiscalDataPage:
    rows: tuple[dict[str, Any], ...]
    meta: dict[str, Any]
    raw: CachedResponse
    page_number: int


@dataclass(frozen=True)
class FiscalDataPayload:
    endpoint: str
    rows: tuple[dict[str, Any], ...]
    fields: tuple[str, ...]
    schema_hash: str
    raw_hash: str
    fingerprint: str
    fetched_at: str
    total_count: int | None
    page_count: int
    truncated: bool
    cache_hit: bool


def _decode(response: CachedResponse) -> dict[str, Any]:
    try:
        payload = json.loads(response.payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise TreasuryFiscalDataError("INVALID_JSON", str(exc)) from exc
    if not isinstance(payload, dict):
        raise TreasuryFiscalDataError("INVALID_PAYLOAD", "FiscalData JSON must be an object")
    return payload


class TreasuryFiscalDataClient:
    def __init__(
        self,
        *,
        cache: ResponseCache | None = None,
        transport=None,
        page_size: int = DEFAULT_PAGE_SIZE,
        timeout: float = 20.0,
    ) -> None:
        self.cache = cache
        self.transport = transport
        self.page_size = page_size
        self.timeout = timeout

    def fetch_pages(
        self,
        endpoint: str,
        *,
        start: str | None = None,
        end: str | None = None,
        date_field: str = "record_date",
        extra_filters: str | None = None,
        resume: bool = True,
    ) -> FiscalDataPayload:
        pages: list[FiscalDataPage] = []
        page_number = 1
        total_count: int | None = None
        cache_hit = True
        while True:
            params: dict[str, Any] = {
                "page[number]": page_number,
                "page[size]": self.page_size,
            }
            filters: list[str] = []
            if start:
                filters.append(f"{date_field}:gte:{start}")
            if end:
                filters.append(f"{date_field}:lte:{end}")
            if extra_filters:
                filters.append(extra_filters)
            if filters:
                params["filter"] = ",".join(filters)
            raw = request_with_retry(
                endpoint,
                params=params,
                timeout=self.timeout,
                cache=self.cache,
                transport=self.transport,
                resume=resume,
            )
            cache_hit = cache_hit and bool(self.cache and self.cache.get(raw.fingerprint))
            payload = _decode(raw)
            rows = payload.get("data") or []
            if not isinstance(rows, list):
                raise TreasuryFiscalDataError("INVALID_PAYLOAD", "data must be a list")
            meta = dict(payload.get("meta") or {})
            if total_count is None and meta.get("total-count") is not None:
                total_count = int(meta["total-count"])
            pages.append(
                FiscalDataPage(
                    rows=tuple(item for item in rows if isinstance(item, dict)),
                    meta=meta,
                    raw=raw,
                    page_number=page_number,
                )
            )
            if not rows:
                break
            if total_count is not None and sum(len(page.rows) for page in pages) >= total_count:
                break
            reported_pages = meta.get("total-pages")
            if reported_pages is not None and page_number >= int(reported_pages):
                break
            if len(rows) < self.page_size:
                break
            page_number += 1
            if page_number > 500:
                raise TreasuryFiscalDataError("PAGINATION_GUARD", "exceeded page guard")

        combined = tuple(row for page in pages for row in page.rows)
        fields = tuple(sorted({key for row in combined for key in row}))
        collected = len(combined)
        truncated = bool(total_count is not None and collected < total_count)
        last = pages[-1].raw if pages else None
        return FiscalDataPayload(
            endpoint=endpoint,
            rows=combined,
            fields=fields,
            schema_hash=schema_hash(fields),
            raw_hash=last.raw_hash if last else "",
            fingerprint=last.fingerprint if last else "",
            fetched_at=last.fetched_at if last else "",
            total_count=total_count,
            page_count=len(pages),
            truncated=truncated,
            cache_hit=cache_hit and bool(pages),
        )
