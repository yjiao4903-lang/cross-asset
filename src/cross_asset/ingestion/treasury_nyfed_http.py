"""Isolated HTTP helpers: fingerprint, retry/backoff, cache, raw hash."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

Transport = Callable[[str, float], tuple[int, bytes, dict[str, str]]]


class TreasuryNYFedHTTPError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        super().__init__(f"{code}:{message}")
        self.code = code
        self.status = status


def canonical_query(params: dict[str, Any] | None) -> str:
    items: list[tuple[str, str]] = []
    for key, value in (params or {}).items():
        if value is None:
            continue
        items.append((str(key), str(value)))
    items.sort()
    return urlencode(items, doseq=True, safe="[]")


def request_fingerprint(method: str, url: str, params: dict[str, Any] | None = None) -> str:
    payload = json.dumps(
        {"method": method.upper(), "url": url, "query": canonical_query(params)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def raw_payload_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def schema_hash(fields: list[str] | tuple[str, ...]) -> str:
    normalized = json.dumps(list(fields), separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def aggregate_raw_hash(hashes: list[str] | tuple[str, ...]) -> str:
    joined = json.dumps(list(hashes), separators=(",", ":"))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC)


def default_transport(url: str, timeout: float) -> tuple[int, bytes, dict[str, str]]:
    request = Request(url, headers={"User-Agent": "cross-asset-c67-treasury-nyfed/0.1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
            return int(response.status), response.read(), headers
    except HTTPError as exc:
        body = exc.read() if exc.fp is not None else b""
        headers = {str(key).lower(): str(value) for key, value in (exc.headers or {}).items()}
        return int(exc.code), body, headers
    except URLError as exc:
        raise TreasuryNYFedHTTPError("SOURCE_FAILURE", str(exc.reason)) from exc
    except TimeoutError as exc:
        raise TreasuryNYFedHTTPError("TIMEOUT", str(exc)) from exc


def _safe_token(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-+_." else "_" for char in value)


@dataclass
class CachedResponse:
    status: int
    payload: bytes
    headers: dict[str, str]
    fetched_at: str
    fingerprint: str
    raw_hash: str
    cache_hit: bool = False
    ingested_at: str = ""


class ResponseCache:
    """Latest-pointer request cache. Not the immutable raw archive."""

    def __init__(self, root: str | Path | None) -> None:
        self.root = Path(root) / "cache" if root else None
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)

    def get(self, fingerprint: str) -> CachedResponse | None:
        if self.root is None:
            return None
        path = self.root / f"{fingerprint}.json"
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return CachedResponse(
            status=int(payload["status"]),
            payload=bytes.fromhex(payload["payload_hex"]),
            headers=dict(payload.get("headers") or {}),
            fetched_at=str(payload["fetched_at"]),
            fingerprint=fingerprint,
            raw_hash=str(payload["raw_hash"]),
            cache_hit=True,
            ingested_at=str(payload.get("ingested_at") or payload["fetched_at"]),
        )

    def put(self, record: CachedResponse) -> None:
        if self.root is None:
            return
        path = self.root / f"{record.fingerprint}.json"
        path.write_text(
            json.dumps(
                {
                    "status": record.status,
                    "payload_hex": record.payload.hex(),
                    "headers": record.headers,
                    "fetched_at": record.fetched_at,
                    "ingested_at": record.ingested_at,
                    "fingerprint": record.fingerprint,
                    "raw_hash": record.raw_hash,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


class RawSnapshotArchive:
    """Append-only raw evidence. Same fingerprint + different payload keeps both files."""

    def __init__(self, root: str | Path | None) -> None:
        self.root = Path(root) / "raw" if root else None
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)

    def snapshot_path(self, record: CachedResponse) -> Path | None:
        if self.root is None:
            return None
        folder = self.root / record.fingerprint
        name = f"{_safe_token(record.fetched_at)}__{record.raw_hash}.json"
        return folder / name

    def put(self, record: CachedResponse) -> Path | None:
        path = self.snapshot_path(record)
        if path is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            return path
        path.write_text(
            json.dumps(
                {
                    "status": record.status,
                    "payload_hex": record.payload.hex(),
                    "headers": record.headers,
                    "fetched_at": record.fetched_at,
                    "ingested_at": record.ingested_at,
                    "fingerprint": record.fingerprint,
                    "raw_hash": record.raw_hash,
                    "revision_policy": "APPEND_ONLY_RAW_SNAPSHOTS",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def list_snapshots(self, fingerprint: str) -> list[Path]:
        if self.root is None:
            return []
        folder = self.root / fingerprint
        if not folder.is_dir():
            return []
        return sorted(folder.glob("*.json"))


class EvidenceStore:
    def __init__(self, root: str | Path | None) -> None:
        self.root = Path(root) if root else None
        self.cache = ResponseCache(self.root)
        self.archive = RawSnapshotArchive(self.root)


def request_with_retry(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 20.0,
    retries: int = 2,
    backoff_seconds: float = 0.25,
    cache: ResponseCache | EvidenceStore | None = None,
    archive: RawSnapshotArchive | None = None,
    transport: Transport | None = None,
    resume: bool = True,
) -> CachedResponse:
    query = canonical_query(params)
    full_url = f"{url}?{query}" if query else url
    fingerprint = request_fingerprint("GET", url, params)
    request_cache = cache.cache if isinstance(cache, EvidenceStore) else cache
    raw_archive = archive
    if raw_archive is None and isinstance(cache, EvidenceStore):
        raw_archive = cache.archive
    if resume and request_cache is not None:
        cached = request_cache.get(fingerprint)
        if cached is not None:
            cached.cache_hit = True
            return cached

    last_error: TreasuryNYFedHTTPError | None = None
    runner = transport or default_transport
    attempts = max(1, retries + 1)
    for attempt in range(attempts):
        try:
            status, payload, headers = runner(full_url, timeout)
        except TreasuryNYFedHTTPError as exc:
            last_error = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(backoff_seconds * (2**attempt))
            continue
        if status >= 500 or status == 429:
            last_error = TreasuryNYFedHTTPError("HTTP_RETRYABLE", f"status={status}", status=status)
            if attempt + 1 >= attempts:
                break
            time.sleep(backoff_seconds * (2**attempt))
            continue
        if status >= 400:
            raise TreasuryNYFedHTTPError("HTTP_CLIENT_ERROR", f"status={status}", status=status)
        fetched = utcnow().isoformat()
        record = CachedResponse(
            status=status,
            payload=payload,
            headers=headers,
            fetched_at=fetched,
            fingerprint=fingerprint,
            raw_hash=raw_payload_hash(payload),
            cache_hit=False,
            ingested_at=fetched,
        )
        if request_cache is not None:
            request_cache.put(record)
        if raw_archive is not None:
            raw_archive.put(record)
        return record
    assert last_error is not None
    raise last_error
