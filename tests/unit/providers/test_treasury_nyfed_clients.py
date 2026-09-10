import json

from cross_asset.ingestion.treasury_nyfed_registry import load_registry
from cross_asset.providers.nyfed_markets import NYFedMarketsClient, NYFedMarketsError
from cross_asset.providers.treasury_fiscaldata import TreasuryFiscalDataClient


def _transport(payloads: dict[str, tuple[int, bytes]]):
    def runner(url: str, timeout: float):
        for key, (status, body) in payloads.items():
            if key in url:
                return status, body, {}
        raise AssertionError(url)

    return runner


def test_fiscaldata_paginates_until_total_count():
    page1 = json.dumps(
        {"data": [{"record_date": "2026-09-02", "close_today_bal": "1"}], "meta": {"count": 1, "total-count": 2}}
    ).encode()
    page2 = json.dumps(
        {"data": [{"record_date": "2026-09-03", "close_today_bal": "2"}], "meta": {"count": 1, "total-count": 2}}
    ).encode()

    def transport(url: str, timeout: float):
        if "page%5Bnumber%5D=2" in url or "page[number]=2" in url:
            return 200, page2, {}
        return 200, page1, {}

    client = TreasuryFiscalDataClient(transport=transport, page_size=1)
    payload = client.fetch_pages("https://api.fiscaldata.treasury.gov/example")
    assert payload.page_count == 2
    assert len(payload.rows) == 2
    assert payload.truncated is False


def test_fiscaldata_marks_truncation_when_pages_stop_early():
    body = json.dumps(
        {"data": [{"record_date": "2026-09-02"}], "meta": {"count": 1, "total-count": 5, "total-pages": 1}}
    ).encode()
    client = TreasuryFiscalDataClient(transport=lambda url, timeout: (200, body, {}), page_size=1)
    payload = client.fetch_pages("https://api.fiscaldata.treasury.gov/example")
    assert payload.truncated is True


def test_nyfed_parses_onrrp_and_pd_payloads():
    onrrp = json.dumps(
        {"repo": {"operations": [{"operationId": "1", "operationDate": "2026-09-02", "totalAmtAccepted": 9}]}}
    ).encode()
    pd_body = json.dumps(
        {"pd": {"timeseries": [{"asofdate": "2026-09-02", "keyid": "PDPOSGST-TOT", "value": "10"}]}}
    ).encode()
    client = NYFedMarketsClient(
        transport=_transport({"reverserepo": (200, onrrp), "PDPOSGST-TOT": (200, pd_body)})
    )
    repo = client.fetch_repo_results("https://markets.newyorkfed.org/api/rp/reverserepo/all/results/last/5.json")
    pd_payload = client.fetch_primary_dealer("https://markets.newyorkfed.org/api/pd/get/PDPOSGST-TOT.json")
    assert repo.rows[0]["operationId"] == "1"
    assert pd_payload.rows[0]["keyid"] == "PDPOSGST-TOT"


def test_omo_history_stays_unresolved():
    registry = load_registry()
    assert registry.get("NYFED_OMO_TRANSACTION_HISTORY").status == "UNRESOLVED"
    client = NYFedMarketsClient()
    try:
        client.fetch_omo_transaction_history()
    except NYFedMarketsError as exc:
        assert exc.code == "UNRESOLVED"
    else:
        raise AssertionError("expected UNRESOLVED")
