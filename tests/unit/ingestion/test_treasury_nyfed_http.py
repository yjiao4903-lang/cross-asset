from cross_asset.ingestion.treasury_nyfed_http import (
    ResponseCache,
    TreasuryNYFedHTTPError,
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
    assert second.raw_hash == first.raw_hash
    assert calls["n"] == 2


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
