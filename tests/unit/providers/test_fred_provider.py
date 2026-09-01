import json

from cross_asset.ingestion.raw_archive import ImmutableRawArchive
from cross_asset.providers.base import DataRequest
from cross_asset.providers.fred import FREDProvider
from cross_asset.settings import load_fred_api_key


class _Response:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self): return json.dumps(self.payload).encode()


def test_missing_key_probe_is_safe(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    result = FREDProvider(env_path="__missing_test_env__").probe()
    assert result.errors[0]["code"] == "missing_credentials"


def test_env_loader_process_precedence_and_project_path(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FRED_API_KEY=file-key\nOTHER=do-not-read\n", encoding="utf-8")
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert load_fred_api_key(env_file) == "file-key"
    monkeypatch.setenv("FRED_API_KEY", "process-key")
    assert load_fred_api_key(env_file) == "process-key"
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    (tmp_path / "empty.env").write_text("FRED_API_KEY=\n", encoding="utf-8")
    assert load_fred_api_key(tmp_path / "empty.env") is None


def test_fred_fetch_archives_raw_but_refuses_unproven_pit(monkeypatch, tmp_path):
    monkeypatch.setenv("FRED_API_KEY", "secret-test-key")
    calls = []
    def opener(request, timeout):
        calls.append(request.full_url)
        return _Response({"seriess": [{"id": "DGS10"}], "observations": []})
    provider = FREDProvider(opener=opener, raw_archive=ImmutableRawArchive(tmp_path))
    rows = provider.fetch(DataRequest(series_ids=["US_GOV_10Y"]))
    assert rows == [] and provider.last_result["pit_evidence"] == "pit_evidence_insufficient"
    assert len(list(tmp_path.rglob("*.json"))) == 1
    archived = next(tmp_path.rglob("*.json")).read_text(encoding="utf-8")
    assert "api_key" not in archived and calls


def test_fred_rate_limit_retries_and_malformed_is_structured(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "secret-test-key")
    calls = 0
    def opener(_request, **_kwargs):
        nonlocal calls
        calls += 1
        return _Response({"error": "rate"}, status=429)
    result = FREDProvider(opener=opener, retries=2).probe()
    assert calls == 3 and result.errors[0]["code"] == "rate_limited"


def test_requests_transport_uses_default_headers(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "fake-key")
    captured = {}

    class Response:
        status_code = 200
        content = b'{"seriess": []}'

    def get(_url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("cross_asset.providers.fred.requests.get", get)
    FREDProvider()._request("series", {"series_id": "DGS10"})
    assert "headers" not in captured and captured["timeout"] == 8


def test_fred_macro_whitelist_is_configured():
    assert {"US_CPI", "US_CORE_PCE", "US_UNEMPLOYMENT", "US_INITIAL_CLAIMS", "US_INDUSTRIAL_PRODUCTION"} <= set(FREDProvider.SERIES)


def test_fred_priority_whitelist_is_exact_and_separate_from_core():
    assert FREDProvider.PRIORITY_SERIES == ("EFFR", "DGS2", "DGS5", "DGS30", "CPILFESL", "PCEPI", "T10YIE", "T5YIE")
    assert set(FREDProvider.CORE_SERIES) == {"US_GOV_10Y", "US_REAL_10Y"}


def test_alfred_cpi_failure_is_safe_and_single_attempt(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "secret-test-key")
    calls = []

    class Response:
        status_code = 400

        def json(self):
            return {}

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr("cross_asset.providers.fred.requests.Session", Session)
    result = FREDProvider().fetch_alfred_cpi_once()
    assert result["status"] == "FAILED" and result["error"]["code"] == "http_400"
    assert len(calls) == 1 and calls[0][1]["params"]["output_type"] == 4
    assert "secret-test-key" not in repr(result)
