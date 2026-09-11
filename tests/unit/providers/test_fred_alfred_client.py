import json
from pathlib import Path

import pytest
import requests

from cross_asset.ingestion.raw_archive import ImmutableRawArchive
from cross_asset.providers.fred_alfred import (
    FredAlfredClient,
    FredAlfredError,
    FredResponseCache,
    canonical_request_fingerprint,
)


class Response:
    def __init__(self, payload, status=200, headers=None):
        self.status_code = status
        self.content = json.dumps(payload).encode()
        self.headers = headers or {}
        self._payload = payload

    def json(self):
        return self._payload


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_request_fingerprint_is_ordered_and_secret_independent():
    first = canonical_request_fingerprint(
        "series/observations",
        {"series_id": "CPIAUCSL", "observation_start": "2020-01-01", "api_key": "a"},
    )
    second = canonical_request_fingerprint(
        "series/observations",
        {"api_key": "b", "observation_start": "2020-01-01", "series_id": "CPIAUCSL"},
    )
    assert first == second


def test_client_cache_hash_and_raw_archive_are_secret_free(tmp_path):
    session = Session([Response({"observations": []})])
    client = FredAlfredClient(
        api_key="secret-key",
        session=session,
        cache=FredResponseCache(tmp_path / "cache"),
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
    )
    first = client.fetch_historical_asof(
        "CPIAUCSL",
        observation_start="2020-01-01",
        observation_end="2020-02-01",
        as_of="2020-03-01",
    )
    second = client.fetch_historical_asof(
        "CPIAUCSL",
        observation_start="2020-01-01",
        observation_end="2020-02-01",
        as_of="2020-03-01",
    )
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.raw_sha256 == second.raw_sha256
    assert first.request_fingerprint == second.request_fingerprint
    assert first.raw_archive_path is not None
    # Cache-hit payloads must keep the every-payload-has-immutable-raw-archive
    # invariant (regression for the full-vintage PIT admission path).
    assert second.raw_archive_path is not None
    assert Path(second.raw_archive_path).is_file()
    assert (
        Path(second.raw_archive_path).read_bytes()
        == Path(first.raw_archive_path).read_bytes()
    )
    assert len(session.calls) == 1
    assert not any(
        "secret-key" in path.read_text(encoding="utf-8")
        for path in tmp_path.rglob("*.json")
    )


def test_rate_limit_retry_honors_retry_after_and_succeeds():
    sleeps = []
    session = Session(
        [
            Response({"error_message": "slow down"}, status=429, headers={"Retry-After": "1.5"}),
            Response({"seriess": [{"id": "DGS10"}]}),
        ]
    )
    client = FredAlfredClient(
        api_key="secret",
        session=session,
        retries=2,
        sleep=sleeps.append,
    )
    result = client.fetch_metadata("DGS10", use_cache=False)
    assert result.payload["seriess"][0]["id"] == "DGS10"
    assert len(session.calls) == 2
    assert sleeps == [1.5]


def test_nonretryable_http_fails_once_and_redacts_secret():
    session = Session([Response({"error_message": "bad secret-key"}, status=400)])
    client = FredAlfredClient(api_key="secret-key", session=session, retries=3)
    with pytest.raises(FredAlfredError) as exc_info:
        client.fetch_metadata("BAD", use_cache=False)
    assert exc_info.value.code == "http_400"
    assert "secret-key" not in str(exc_info.value)
    assert len(session.calls) == 1


def test_timeout_retries_then_structured_error():
    session = Session([requests.Timeout(), requests.Timeout()])
    client = FredAlfredClient(
        api_key="secret",
        session=session,
        retries=1,
        backoff_base=0,
        sleep=lambda _value: None,
    )
    with pytest.raises(FredAlfredError, match="timed out") as exc_info:
        client.fetch_metadata("DGS10", use_cache=False)
    assert exc_info.value.code == "timeout"
    assert len(session.calls) == 2


def test_missing_key_is_explicit_data_blocker(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    client = FredAlfredClient(api_key=None, env_path="__missing_fred_test_env__")
    with pytest.raises(FredAlfredError) as exc_info:
        client.fetch_metadata("DGS10", use_cache=False)
    assert exc_info.value.code == "missing_credentials"


def test_request_modes_bind_official_vintage_parameters():
    session = Session(
        [
            Response({"observations": []}),
            Response({"observations": []}),
            Response({"observations": []}),
        ]
    )
    client = FredAlfredClient(api_key="secret", session=session)
    client.fetch_historical_asof(
        "CPIAUCSL",
        observation_start="2020-01-01",
        observation_end="2020-12-01",
        as_of="2021-01-15",
        use_cache=False,
    )
    client.fetch_initial_release(
        "CPIAUCSL",
        observation_start="2020-01-01",
        observation_end="2020-12-01",
        use_cache=False,
    )
    client.fetch_all_realtime_periods(
        "CPIAUCSL",
        observation_start="2020-01-01",
        observation_end="2020-12-01",
        use_cache=False,
    )
    first_params = session.calls[0][1]["params"]
    second_params = session.calls[1][1]["params"]
    third_params = session.calls[2][1]["params"]
    assert first_params["vintage_dates"] == "2021-01-15"
    assert first_params["output_type"] == 1
    assert second_params["output_type"] == 4
    assert third_params["realtime_start"] == "1776-07-04"
    assert third_params["realtime_end"] == "9999-12-31"


def test_fetch_all_realtime_periods_sends_bounded_realtime_window():
    session = Session([Response({"observations": []})])
    client = FredAlfredClient(api_key="secret", session=session)
    client.fetch_all_realtime_periods(
        "DGS10",
        observation_start="2018-01-01",
        observation_end="2020-12-31",
        realtime_start="2017-11-21",
        realtime_end="2019-06-12",
        use_cache=False,
    )
    params = session.calls[0][1]["params"]
    assert params["realtime_start"] == "2017-11-21"
    assert params["realtime_end"] == "2019-06-12"
    assert params["output_type"] == 1
