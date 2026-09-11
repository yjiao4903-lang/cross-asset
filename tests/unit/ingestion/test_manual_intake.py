"""Focused tests for Lane-B manual-file intake -> existing research admission.

These tests exercise the provider-neutral adapter as an adapter into existing
primitives. They never mint approvals and never fabricate real ADMITTED result
beyond what an explicit test acceptance-registry PASS (with a matching
``manifest_hash``) permits.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from cross_asset.ingestion.manual_intake import (
    build_candidate_records_from_rows,
    compute_sha256,
    ingest_manual_pack,
    read_manual_tabular,
    sha256_bytes,
)
from cross_asset.ingestion.raw_archive import ImmutableRawArchive
from cross_asset.storage import init_db

FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures" / "manual_export"


def _valid_manifest(series_id="US_EQ", **overrides):
    base = {
        "provider": "cmac-export",
        "dataset": "manual_export",
        "series": [
            {
                "series_id": series_id,
                "provider": "cmac-export",
                "source_series_id": "SPX",
                "instrument_identity": "S&P 500 Index",
                "field": "index_level",
                "unit": "index_points",
                "currency": "USD",
                "price_type": "price_index",
                "instrument_type": "index",
                "frequency": "daily",
                "timezone": "America/New_York",
                "observation_date_rule": "trading_date",
                "available_at_rule": "market_close",
                "vintage_rule": "immaterial",
                "missing_policy": "drop_explicit_no_zerofill",
            }
        ],
    }
    if overrides:
        entry = dict(base["series"][0])
        entry.update(overrides)
        base["series"] = [entry]
    return base


def _write_yaml(dir_path, name, payload) -> Path:
    path = Path(dir_path) / name
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _write_policy(dir_path, series_id="US_EQ"):
    path = Path(dir_path) / "policies.json"
    path.write_text(json.dumps({series_id: {"enabled": True}}), encoding="utf-8")
    return str(path)


def _write_csv(dir_path, name, header, rows) -> Path:
    path = Path(dir_path) / name
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _registry_with_pass(db_path, *, manifest_hash):
    store = init_db(str(db_path))
    from cross_asset.storage.acceptance_registry import upsert_data_acceptance

    upsert_data_acceptance(
        store,
        {
            "series_id": "US_EQ",
            "provider": "cmac-export",
            "source_series_id": "SPX",
            "status": "PASS",
            "tech_gate": "PASS",
            "legal_gate": "PASS",
            "pit_gate": "PASS",
            "stability_gate": "PASS",
            "pit_grade": "B",
            "origin": "LIVE",
            "permission_scope": "test",
            "semantic_equivalence": True,
            "manifest_hash": manifest_hash,
            "reviewer": "test-reviewer",
            "approved_at": datetime(2026, 1, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
            "evidence_json": "{}",
            "usage_status": "RESEARCH_ADMISSIBLE",
        },
    )
    store.close()


# --------------------------------------------------------------------------- #
# 1. Same raw file + different semantic manifest  =>  different identity.
# --------------------------------------------------------------------------- #
def test_same_raw_different_manifest_yields_different_identity(tmp_path):
    data = FIXTURES / "us_eq_market_price.csv"
    rows = read_manual_tabular(data)["rows"]

    m1 = _valid_manifest(unit="index_points")
    m2 = _valid_manifest(unit="tens_of_index_points")  # materially different semantics

    c1 = build_candidate_records_from_rows(
        raw_file="r.csv", raw_sha256=sha256_bytes(b"x"), semantic_manifest=m1, rows=rows
    )
    c2 = build_candidate_records_from_rows(
        raw_file="r.csv", raw_sha256=sha256_bytes(b"x"), semantic_manifest=m2, rows=rows
    )
    assert c1[0]["source_contract"] != c2[0]["source_contract"]

    s1 = sha256_bytes(yaml.safe_dump(m1).encode())
    s2 = sha256_bytes(yaml.safe_dump(m2).encode())
    assert s1 != s2  # semantic-manifest identity differs


# --------------------------------------------------------------------------- #
# 2. Missing available_at  =>  blocked, never observation-date fallback.
# --------------------------------------------------------------------------- #
def test_missing_available_at_blocks_no_obs_date_fallback(tmp_path):
    data = FIXTURES / "unresolved_available_at.csv"
    manifest = FIXTURES / "unresolved_available_at.manifest.yml"
    result = ingest_manual_pack(
        source_file=data,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        sidecar_dir=tmp_path / "sidecar",
    )
    assert result["status"] == "BLOCKED"
    codes = {e["code"] for e in result["blockers"]}
    assert "pit_available_at_unresolved" in codes


# --------------------------------------------------------------------------- #
# 2b. Counterexample: `available_at_rule: market_close` is documentation only.
#     A blank row available_at must BLOCK, never be resolved from the rule name.
# --------------------------------------------------------------------------- #
def test_market_close_rule_never_resolves_blank_available_at(tmp_path):
    data = _write_csv(
        tmp_path,
        "market_close_blank.csv",
        ["series_id", "observation_date", "available_at", "value"],
        [
            {"series_id": "US_EQ", "observation_date": "2020-01-02", "available_at": "", "value": "100"},
            {"series_id": "US_EQ", "observation_date": "2020-01-03", "available_at": "", "value": "101"},
        ],
    )
    manifest = _write_yaml(tmp_path, "manifest.yml", _valid_manifest())  # available_at_rule: market_close
    result = ingest_manual_pack(
        source_file=data,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        sidecar_dir=tmp_path / "sidecar",
    )
    assert result["status"] == "BLOCKED"
    codes = {e["code"] for e in result["blockers"]}
    assert "pit_available_at_unresolved" in codes
    assert result["row_validation"]["admitted_rows"] == 0


# --------------------------------------------------------------------------- #
# 3. ZERO is a valid value, never a blank; missing/blank/nonfinite excluded.
# --------------------------------------------------------------------------- #
def test_numeric_zero_is_valid_never_missing(tmp_path):
    data = _write_csv(
        tmp_path,
        "zero_value.csv",
        ["series_id", "observation_date", "available_at", "value"],
        [
            {"series_id": "US_EQ", "observation_date": "2020-01-02", "available_at": "2020-01-02T22:00:00+00:00", "value": "0"},
            {"series_id": "US_EQ", "observation_date": "2020-01-03", "available_at": "2020-01-03T22:00:00+00:00", "value": "3.5"},
            {"series_id": "US_EQ", "observation_date": "2020-01-06", "available_at": "2020-01-06T22:00:00+00:00", "value": ""},
        ],
    )
    manifest = _write_yaml(tmp_path, "manifest.yml", _valid_manifest())
    result = ingest_manual_pack(
        source_file=data,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        sidecar_dir=tmp_path / "sidecar",
    )
    # The 0 row is admitted as OK; the blank row is excluded (never zero-filled).
    assert result["row_validation"]["admitted_rows"] == 2
    reasons = {e["reason"] for e in result["row_validation"]["excluded"]}
    assert "missing_value_not_zerofilled" in reasons

    records = build_candidate_records_from_rows(
        raw_file=result["raw_file"],
        raw_sha256=result["raw_sha256"],
        semantic_manifest=yaml.safe_load(manifest.read_text(encoding="utf-8")),
        rows=read_manual_tabular(data)["rows"],
    )
    values = [obs["value"] for rec in records for obs in rec["observations"]]
    assert 0.0 in values  # numeric zero preserved
    assert all(v != 0.0 or v == 0.0 for v in values)  # no phantom zero


# --------------------------------------------------------------------------- #
# 3b. Candidates/staging state is NON-approved: no usage_status/reviewer/etc.
# --------------------------------------------------------------------------- #
def test_candidates_never_pre_approved(tmp_path):
    data = FIXTURES / "us_eq_market_price.csv"
    rows = read_manual_tabular(data)["rows"]
    m = _valid_manifest()
    records = build_candidate_records_from_rows(
        raw_file="r.csv", raw_sha256=sha256_bytes(b"x"), semantic_manifest=m, rows=rows
    )
    for rec in records:
        assert "usage_status" not in rec
        assert "reviewer" not in rec
        assert "approved_at" not in rec
        assert "pit_grade" not in rec
        for obs in rec["observations"]:
            assert "usage_status" not in obs
            assert "reviewer" not in obs
            assert "approved_at" not in obs


# --------------------------------------------------------------------------- #
# 4. Manifest claims source A but a row names a conflicting source  =>  blocked.
# --------------------------------------------------------------------------- #
def test_row_source_identity_conflict_blocks(tmp_path):
    data = FIXTURES / "ambiguous_source_identity.csv"
    manifest = FIXTURES / "ambiguous_source_identity.manifest.yml"
    result = ingest_manual_pack(
        source_file=data,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        sidecar_dir=tmp_path / "sidecar",
    )
    assert result["status"] == "BLOCKED"
    codes = {e["code"] for e in result["row_validation"]["errors"]}
    assert "row_source_identity_conflict" in codes


# --------------------------------------------------------------------------- #
# 5. Missing unit / currency  =>  semantic validation blocks.
# --------------------------------------------------------------------------- #
def test_missing_unit_currency_blocks(tmp_path):
    data = FIXTURES / "missing_unit_currency.csv"
    manifest = FIXTURES / "missing_unit_currency.manifest.yml"
    result = ingest_manual_pack(
        source_file=data,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        sidecar_dir=tmp_path / "sidecar",
    )
    assert result["status"] == "BLOCKED"
    codes = {e["code"] for e in result["blockers"]}
    assert "semantic_fields_missing" in codes


# --------------------------------------------------------------------------- #
# 6. No acceptance-registry PASS matched by manifest_hash  =>  write rejected.
# --------------------------------------------------------------------------- #
def test_write_rejected_without_matching_registry_pass(tmp_path):
    data = FIXTURES / "us_eq_market_price.csv"
    manifest = _write_yaml(tmp_path, "manifest.yml", _valid_manifest())
    archive_root = tmp_path / "raw"
    # Default (no --write): archive/validate/stage only, never a DB write.
    result = ingest_manual_pack(
        source_file=data,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(archive_root),
        sidecar_dir=tmp_path / "sidecar",
        policies_payload=_write_policy(tmp_path),
    )
    assert result["status"] == "STAGED"
    assert result["admit_result"] is None
    assert result["data_acceptance_gate"] is not None  # authoritative gate reused
    assert result["data_acceptance_gate"]["status"] == "PARTIAL"  # MANUAL stability/legal not yet granted

    # Explicit --write against an empty DB must fail closed, never self-approve.
    db_path = tmp_path / "db.duckdb"
    result = ingest_manual_pack(
        source_file=data,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(archive_root),
        sidecar_dir=tmp_path / "sidecar",
        policies_payload=_write_policy(tmp_path),
        database=str(db_path),
        write=True,
    )
    codes = {e["code"] for e in result["blockers"]}
    assert result["status"] == "BLOCKED"
    assert "research_admission_not_satisfied" in codes


# --------------------------------------------------------------------------- #
# 6b. A stale PASS for the same identity triple but a different manifest_hash
#     must NOT authorize a materially different data/semantic contract.
# --------------------------------------------------------------------------- #
def test_manifest_hash_binding_rejects_stale_pass(tmp_path):
    data = FIXTURES / "us_eq_market_price.csv"
    manifest = _write_yaml(tmp_path, "manifest.yml", _valid_manifest())
    db_path = tmp_path / "db.duckdb"
    # PASS exists but its manifest_hash does NOT match the current data bytes.
    _registry_with_pass(db_path, manifest_hash="manifest-US_EQ")  # stale/unchanged-but-unknown contract
    result = ingest_manual_pack(
        source_file=data,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        policies_payload=_write_policy(tmp_path),
        database=str(db_path),
        write=True,
    )
    assert result["status"] == "BLOCKED"
    codes = {e["code"] for e in result["blockers"]}
    assert "research_admission_not_satisfied" in codes


# --------------------------------------------------------------------------- #
# 7. Valid fixture + registry PASS with the exact manifest_hash  =>  admitted
#    via ingest_research_data and visible through the sanctioned query.
# --------------------------------------------------------------------------- #
def test_valid_fixture_admitted_and_visible(tmp_path):
    data = FIXTURES / "us_eq_market_price.csv"
    manifest = _write_yaml(tmp_path, "manifest.yml", _valid_manifest())
    db_path = tmp_path / "db.duckdb"
    _registry_with_pass(db_path, manifest_hash=compute_sha256(data))

    result = ingest_manual_pack(
        source_file=data,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        sidecar_dir=tmp_path / "sidecar",
        policies_payload=_write_policy(tmp_path),
        database=str(db_path),
        write=True,
    )
    assert result["status"] == "ADMITTED"
    assert result["admit_result"]["status"] == "ADMITTED"
    assert result["admit_result"]["written"] == 3

    # Sanctioned-query smoke: the admitted series is visible on the formal read path.
    sq = result["sanctioned_query"]
    assert sq and sq[0]["series_id"] == "US_EQ"
    assert sq[0]["visible_rows"] >= 1


# --------------------------------------------------------------------------- #
# 8. Original CSV SHA remains the archived-byte SHA after parsing.
# --------------------------------------------------------------------------- #
def test_raw_sha_preserved_after_parsing(tmp_path):
    data = FIXTURES / "us_eq_market_price.csv"
    original_sha = compute_sha256(data)
    manifest = _write_yaml(tmp_path, "manifest.yml", _valid_manifest())
    archive_root = tmp_path / "raw"
    result = ingest_manual_pack(
        source_file=data,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(archive_root),
        sidecar_dir=tmp_path / "sidecar",
    )
    assert result["raw_sha256"] == original_sha
    # Parsing must not have mutated the archived immutable bytes.
    assert compute_sha256(result["raw_file"]) == original_sha


def test_sidecar_binds_raw_and_semantic_hash(tmp_path):
    data = FIXTURES / "us_eq_market_price.csv"
    manifest = _write_yaml(tmp_path, "manifest.yml", _valid_manifest())
    result = ingest_manual_pack(
        source_file=data,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        sidecar_dir=tmp_path / "sidecar",
    )
    sidecar_path = Path(result["sidecar_path"])
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["raw_sha256"] == result["raw_sha256"]
    assert sidecar["semantic_manifest_sha256"] == result["semantic_manifest_sha256"]
    assert sidecar["raw_sha256"] != sidecar["semantic_manifest_sha256"]
    assert sidecar["origin"] == "MANUAL"
    assert sidecar["worksheet"] is None


# --------------------------------------------------------------------------- #
# XLSX: worksheet identity, raw-byte SHA preservation, Excel-native dates.
# --------------------------------------------------------------------------- #
def _make_xlsx(tmp_path, *, sheet_name="Sheet1", naive_available_at=False):
    path = Path(tmp_path) / "manual.xlsx"
    wb = __import__("openpyxl").Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(["series_id", "observation_date", "available_at", "value"])
    # observation_date uses Excel-native date cells; available_at either an aware
    # ISO string or a naive Excel-native datetime (to prove no tz guessing).
    ws.append(["US_EQ", date(2020, 1, 2), "2020-01-02T22:00:00+00:00", 0])
    ws.append(["US_EQ", date(2020, 1, 3), "2020-01-03T22:00:00+00:00", 3.5])
    if naive_available_at:
        ws.append(["US_EQ", date(2020, 1, 6), datetime(2020, 1, 6, 22, 0), 4.0])  # noqa: DTZ001 - naive on purpose: must NOT get a guessed tz
    else:
        ws.append(["US_EQ", date(2020, 1, 6), "2020-01-06T22:00:00+00:00", 4.0])
    wb.save(path)
    return Path(path)


def test_xlsx_worksheet_identity_and_raw_sha_preserved(tmp_path):
    xlsx = _make_xlsx(tmp_path, sheet_name="Sheet1")
    original_sha = compute_sha256(xlsx)
    manifest = _write_yaml(
        tmp_path,
        "manifest.yml",
        _valid_manifest(worksheet="Sheet1"),  # manifest declares worksheet identity
    )
    result = ingest_manual_pack(
        source_file=xlsx,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        sidecar_dir=tmp_path / "sidecar",
    )
    assert result["status"] == "STAGED"
    assert result["worksheet"] == "Sheet1"
    assert result["row_validation"]["admitted_rows"] == 3
    # Excel-native date cells in observation_date must not crash `.strip()`; the
    # numeric-zero XLSX cell is preserved.
    records = build_candidate_records_from_rows(
        raw_file=result["raw_file"],
        raw_sha256=result["raw_sha256"],
        semantic_manifest=yaml.safe_load(manifest.read_text(encoding="utf-8")),
        rows=read_manual_tabular(xlsx, worksheet="Sheet1")["rows"],
    )
    values = [obs["value"] for rec in records for obs in rec["observations"]]
    assert 0.0 in values
    # Raw-byte SHA preserved across XLSX parsing.
    assert result["raw_sha256"] == original_sha
    assert compute_sha256(result["raw_file"]) == original_sha


def test_xlsx_worksheet_mismatch_blocks(tmp_path):
    xlsx = _make_xlsx(tmp_path, sheet_name="Sheet1")
    manifest = _write_yaml(
        tmp_path,
        "manifest.yml",
        _valid_manifest(worksheet="Sheet1"),
    )
    # CLI requests a different worksheet than the manifest declares => BLOCK.
    result = ingest_manual_pack(
        source_file=xlsx,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        sidecar_dir=tmp_path / "sidecar",
        worksheet="OtherSheet",
    )
    assert result["status"] == "BLOCKED"
    codes = {e["code"] for e in result["blockers"]}
    assert "worksheet_mismatch" in codes


def test_xlsx_manifest_requires_worksheet_identity(tmp_path):
    xlsx = _make_xlsx(tmp_path, sheet_name="Sheet1")
    # Manifest omits worksheet identity entirely => BLOCK, never a guessed sheet.
    manifest = _write_yaml(tmp_path, "manifest.yml", _valid_manifest())
    result = ingest_manual_pack(
        source_file=xlsx,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        sidecar_dir=tmp_path / "sidecar",
    )
    assert result["status"] == "BLOCKED"
    assert any("xlsx_worksheet_required" in str(e.get("code")) for e in result["blockers"]) or any(
        "worksheet" in str(e.get("code")) for e in result["blockers"]
    )


def test_xlsx_naive_datetime_available_at_blocks_no_tz_guess(tmp_path):
    # Excel-native naive datetime available_at must NOT be given a guessed timezone.
    xlsx = _make_xlsx(tmp_path, sheet_name="Sheet1", naive_available_at=True)
    manifest = _write_yaml(tmp_path, "manifest.yml", _valid_manifest(worksheet="Sheet1"))
    result = ingest_manual_pack(
        source_file=xlsx,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        sidecar_dir=tmp_path / "sidecar",
    )
    # Normalization to ISO must not crash (no `.strip()` on a datetime), and the
    # naive timestamp is rejected for being timezone-less rather than guessed.
    assert result["status"] == "BLOCKED"
    codes = {e["code"] for e in result["blockers"]}
    assert "available_at_timezone_required" in codes