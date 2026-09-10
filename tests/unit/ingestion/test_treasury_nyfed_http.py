from cross_asset.ingestion.treasury_nyfed_http import (
    EvidenceStore,
    RawSnapshotArchive,
    ResponseCache,
    TreasuryNYFedHTTPError,
    aggregate_raw_hash,
    request_fingerprint,
    request_with_retry,
    schema_hash,
)


def test_fingerprint_is_stable_and_order_insensitive():
    left = request_fingerprint("GET", "https://example.test", {"b": 2, "a": 1})
    right = request_fingerprint("GET", "https://example.test", {"a": 1, "b": 2})
    assert left == right
    assert len(left) == 64


def test_retry_then_success(tmp_path):
    calls = {"n": 0}

    def transport(url: str, timeout: float):
        calls["n"] += 1
        if calls["n"] == 1:
            return 503, b"retry", {}
        return 200, b'{"ok": true}', {"content-type": "application/json"}

    cache = ResponseCache(tmp_path)
    first = request_with_retry("https://example.test/data", transport=transport, cache=cache)
    second = request_with_retry("https://example.test/data", transport=transport, cache=cache)
    assert first.status == 200
    assert first.cache_hit is False
    assert second.raw_hash == first.raw_hash
    assert second.cache_hit is True
    assert calls["n"] == 2


def test_network_fetch_is_not_a_cache_hit(tmp_path):
    def transport(url: str, timeout: float):
        return 200, b'{"live": true}', {}

    store = EvidenceStore(tmp_path)
    record = request_with_retry("https://example.test/live", transport=transport, cache=store)
    assert record.cache_hit is False
    assert record.ingested_at
    assert store.archive.list_snapshots(record.fingerprint)


def test_append_only_archive_keeps_multiple_snapshots(tmp_path):
    calls = {"n": 0}

    def transport(url: str, timeout: float):
        calls["n"] += 1
        return 200, f'{{"n": {calls["n"]}}}'.encode(), {}

    archive = RawSnapshotArchive(tmp_path)
    first = request_with_retry(
        "https://example.test/rev",
        transport=transport,
        archive=archive,
        resume=False,
    )
    second = request_with_retry(
        "https://example.test/rev",
        transport=transport,
        archive=archive,
        resume=False,
    )
    snapshots = archive.list_snapshots(first.fingerprint)
    assert len(snapshots) == 2
    assert first.raw_hash != second.raw_hash
    assert first.cache_hit is False
    assert second.cache_hit is False


def test_client_error_is_not_retried():
    def transport(url: str, timeout: float):
        return 400, b"nope", {}

    try:
        request_with_retry("https://example.test/data", transport=transport, retries=3)
    except TreasuryNYFedHTTPError as exc:
        assert exc.code == "HTTP_CLIENT_ERROR"
        assert exc.status == 400
    else:
        raise AssertionError("expected HTTP_CLIENT_ERROR")


def test_schema_hash_changes_with_fields():
    assert schema_hash(["a", "b"]) != schema_hash(["a"])
    assert aggregate_raw_hash(["aa", "bb"]) != aggregate_raw_hash(["aa"])
