"""C0 Treasury/NY Fed collection and standalone CLI entrypoints."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from cross_asset.ingestion.treasury_nyfed_c0_contract import (
    DEFAULT_REGISTRY_PATH,
    require_c0_only,
)
from cross_asset.ingestion.treasury_nyfed_http import ResponseCache
from cross_asset.ingestion.treasury_nyfed_pit import parse_date, visible_asof
from cross_asset.ingestion.treasury_nyfed_quality import (
    attach_available_at,
    audit_quality,
    build_manifest,
    observation_date,
)
from cross_asset.ingestion.treasury_nyfed_registry import DatasetSpec, load_registry
from cross_asset.ingestion.treasury_nyfed_transforms import research_components
from cross_asset.providers.nyfed_markets import NYFedMarketsClient, NYFedMarketsError
from cross_asset.providers.treasury_fiscaldata import TreasuryFiscalDataClient

FIXTURE_DIR = Path("tests/fixtures/treasury_nyfed")
FIXTURE_MAP = {
    "TREASURY_DTS_OPERATING_CASH": "dts_operating_cash.json",
    "TREASURY_DEBT_TO_PENNY": "debt_to_penny.json",
    "TREASURY_AUCTIONS": "auctions.json",
    "TREASURY_DTS_DEPOSITS_WITHDRAWALS": "dts_deposits.json",
    "TREASURY_MSPD_TABLE_1": "mspd_table_1.json",
    "NYFED_ONRRP_RESULTS": "nyfed_onrrp.json",
    "NYFED_REPO_RESULTS": "nyfed_repo.json",
    "NYFED_SOMA_SUMMARY": "nyfed_soma.json",
    "NYFED_PD_TREASURY_POSITIONS": "nyfed_pd.json",
}


def _load_fixture(spec: DatasetSpec) -> tuple[list[dict[str, Any]], str | None, bool]:
    name = FIXTURE_MAP.get(spec.dataset_id)
    if name is None:
        return [], None, False
    payload = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    if spec.provider == "TREASURY_FISCALDATA":
        rows = list(payload.get("data") or [])
    elif spec.dataset_id in {"NYFED_ONRRP_RESULTS", "NYFED_REPO_RESULTS"}:
        rows = list(((payload.get("repo") or {}).get("operations")) or [])
    elif spec.dataset_id == "NYFED_SOMA_SUMMARY":
        rows = list(((payload.get("soma") or {}).get("summary")) or [])
    else:
        rows = list(((payload.get("pd") or {}).get("timeseries")) or [])
    return [row for row in rows if isinstance(row, dict)], None, False


def _collect_live(
    spec: DatasetSpec,
    *,
    start: str | None,
    end: str | None,
    cache: ResponseCache | None,
    treasury: TreasuryFiscalDataClient,
    nyfed: NYFedMarketsClient,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    if spec.status != "RESOLVED" or not spec.endpoint:
        raise NYFedMarketsError("UNRESOLVED", f"{spec.dataset_id}:{spec.status}")
    payload = None
    if spec.provider == "TREASURY_FISCALDATA":
        payload = treasury.fetch_pages(
            spec.endpoint,
            start=start,
            end=end,
            date_field=spec.observation_field or "record_date",
        )
        return list(payload.rows), payload.raw_hash, payload.truncated
    if spec.dataset_id in {"NYFED_ONRRP_RESULTS", "NYFED_REPO_RESULTS"}:
        payload = nyfed.fetch_repo_results(spec.endpoint)
        rows = list(payload.rows)
    elif spec.dataset_id == "NYFED_SOMA_SUMMARY":
        payload = nyfed.fetch_soma_summary(spec.endpoint)
        rows = list(payload.rows)
    elif spec.dataset_id == "NYFED_PD_TREASURY_POSITIONS":
        payload = nyfed.fetch_primary_dealer(spec.endpoint)
        rows = list(payload.rows)
    else:
        nyfed.fetch_omo_transaction_history()
        rows = []
    if start or end:
        start_date = parse_date(start) if start else date.min
        end_date = parse_date(end) if end else date.max
        rows = [row for row in rows if start_date <= observation_date(row, spec) <= end_date]
    return rows, payload.raw_hash if payload else None, False


def collect_dataset(spec: DatasetSpec, **kwargs):
    start = kwargs.get("start")
    end = kwargs.get("end")
    live = bool(kwargs.get("live"))
    cache = kwargs.get("cache")
    fetched_at = kwargs.get("fetched_at")
    if spec.status in {"UNRESOLVED", "BLOCKED"}:
        quality = audit_quality([], spec=spec)
        return [], build_manifest(
            spec=spec, rows=[], quality=quality, requested_start=start, requested_end=end, raw_hash=None, live=live
        )
    if live:
        rows, raw_hash, truncated = _collect_live(
            spec,
            start=start,
            end=end,
            cache=cache,
            treasury=kwargs.get("treasury") or TreasuryFiscalDataClient(cache=cache),
            nyfed=kwargs.get("nyfed") or NYFedMarketsClient(cache=cache),
        )
    else:
        rows, raw_hash, truncated = _load_fixture(spec)
    attached = attach_available_at(rows, spec, fetched_at=fetched_at)
    attached.sort(key=lambda row: (str(row.get("observation_date")), str(row.get("available_at"))))
    quality = audit_quality(attached, spec=spec, truncated=truncated, fetched_at=fetched_at)
    return attached, build_manifest(
        spec=spec,
        rows=attached,
        quality=quality,
        requested_start=start,
        requested_end=end,
        raw_hash=raw_hash,
        live=live,
    )


def collect_all(
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    start: str | None = None,
    end: str | None = None,
    dataset_id: str | None = None,
    cache_dir: str | None = None,
    output: str | None = None,
    live: bool = False,
    fetched_at=None,
) -> dict[str, Any]:
    contract = require_c0_only()
    registry = load_registry(registry_path)
    cache = ResponseCache(cache_dir) if cache_dir else None
    selected = (registry.get(dataset_id),) if dataset_id else registry.datasets
    datasets = []
    for spec in selected:
        rows, manifest = collect_dataset(spec, start=start, end=end, live=live, cache=cache, fetched_at=fetched_at)
        datasets.append({"rows": rows, "manifest": manifest.to_dict()})
    report = {
        "contract": contract,
        "domain_gate": "C0",
        "usage": "RESEARCH_STAGING_ONLY",
        "production_admission": False,
        "live": live,
        "workstream": registry.workstream,
        "datasets": datasets,
    }
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return report


def research_transforms(payload: dict[str, Any], decision_time: str) -> dict[str, Any]:
    rows_by_dataset: dict[str, list[dict[str, Any]]] = {}
    for item in payload.get("datasets") or []:
        rows = list(item.get("rows") or [])
        if not rows:
            continue
        dataset_id = str(rows[0].get("dataset_id") or item.get("manifest", {}).get("dataset_id"))
        rows_by_dataset[dataset_id] = visible_asof(rows, decision_time)
    return {
        "domain_gate": "C0",
        "usage": "RESEARCH_STAGING_ONLY",
        "allocation_signal": False,
        "decision_time": decision_time,
        "components": research_components(rows_by_dataset, decision_time),
    }
