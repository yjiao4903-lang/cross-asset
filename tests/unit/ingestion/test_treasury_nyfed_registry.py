from pathlib import Path

import pytest

from cross_asset.ingestion.treasury_nyfed_c0_contract import require_c0_only
from cross_asset.ingestion.treasury_nyfed_registry import (
    TreasuryNYFedRegistryError,
    load_registry,
)


def test_c0_contract_forbids_production_and_allocation():
    contract = require_c0_only()
    assert contract["gate"] == "C0"
    assert contract["usage"] == "RESEARCH_STAGING_ONLY"
    assert contract["production_admission"] is False
    assert contract["allocation_signal"] is False
    assert contract["approved_observations"] is False


def test_registry_covers_issue_67_first_batch():
    registry = load_registry()
    ids = {item.dataset_id for item in registry.datasets}
    assert {
        "TREASURY_DTS_OPERATING_CASH",
        "TREASURY_DTS_DEPOSITS_WITHDRAWALS",
        "TREASURY_DEBT_TO_PENNY",
        "TREASURY_AUCTIONS",
        "TREASURY_MSPD_TABLE_1",
        "NYFED_ONRRP_RESULTS",
        "NYFED_REPO_RESULTS",
        "NYFED_SOMA_SUMMARY",
        "NYFED_PD_TREASURY_POSITIONS",
        "NYFED_OMO_TRANSACTION_HISTORY",
    } <= ids
    assert registry.domain_gate == "C0"
    assert registry.usage == "RESEARCH_STAGING_ONLY"
    assert registry.production_admission is False
    assert registry.get("NYFED_OMO_TRANSACTION_HISTORY").status == "UNRESOLVED"
    assert registry.get("NYFED_PD_TREASURY_POSITIONS").official_keyid == "PDPOSGST-TOT"


def test_registry_rejects_production_admission(tmp_path: Path):
    path = tmp_path / "bad.yml"
    path.write_text(
        "domain_gate: C0\nusage: RESEARCH_STAGING_ONLY\nproduction_admission: true\n"
        "allocation_signal: false\ndatasets: []\n",
        encoding="utf-8",
    )
    with pytest.raises(TreasuryNYFedRegistryError, match="production_admission_forbidden"):
        load_registry(path)
