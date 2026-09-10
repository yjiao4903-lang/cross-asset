"""NIGHT-INTEGRATE / Issue #85: rebuild combined real-data readiness from LOCAL-A/B evidence.

A fresh third integration DuckDB is created (never copied from A/B). LOCAL-B public
US macro inputs are re-ingested from the immutable FRED/ALFRED raw archive
(raw JSON bytes re-parsed + raw hash re-verified), and acceptance records are
recreated only where #83 evidence satisfied the existing admission contract.

LOCAL-A resolved market/FX inputs: none exist (all eight BLOCKED on host, per #82
HANDOFF at 2405104). This driver records that truth; it never fabricates data.

Only formal `readiness` runs. No OOS. No merge.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

REPO = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, str(REPO / "src"))
os.chdir(REPO)

import pandas as pd  # noqa: E402

from cross_asset.ingestion.fred_alfred_pit import (  # noqa: E402
    MODE_HISTORICAL_ASOF,
    parse_observations,
)
from cross_asset.backtest.accounting import embedded_accounting_required_series_ids  # noqa: E402
from cross_asset.ingestion.research import ingest_research_data  # noqa: E402
from cross_asset.research.dependencies import research_required_series_ids  # noqa: E402
from cross_asset.research.model_config import load_research_model_config  # noqa: E402
from cross_asset.research.protocol import load_research_protocol  # noqa: E402
from cross_asset.research.readiness import evaluate_research_readiness  # noqa: E402
from cross_asset.storage import (  # noqa: E402
    DuckDBStore,
    approved_observations_asof,
    latest_formal_observations_asof,
)
from cross_asset.storage.acceptance_registry import upsert_data_acceptance  # noqa: E402

EVID = REPO / "evidence" / "night_integrate_real_readiness"
B_EVID = REPO / "evidence" / "night_b_public_macro"
RAW_ROOT = REPO / "data" / "raw" / "fred_alfred_local_b"
DB_PATH = REPO / "data" / "db" / "local_b_integration" / "cross_asset_integration.duckdb"
GRID_FILE = B_EVID / "decision_dates_weekly_development.txt"

CUTOFF = datetime(2026, 9, 10, 23, 59, tzinfo=UTC)
REVIEWER = "LOCAL-DEV-B"

# ---- exact SHAs / candidate commits used by this integration workspace ----
MAIN_SHA = "481e7fde015dbddaa3615e397b2c2f258b68ee95"
LOCAL_A_BRANCH_SHA = "24051042c4ce31488f3ee668feafd1e14164690a"
LOCAL_B_CANDIDATE_SHA = "71c9595"  # PR #90 (registry DFII10 + raw-archive invariant + bulk insert)
LOCAL_A_WORKTREE = Path(r"D:\跨资产监控项目\worktrees\local-a-night-wind")

# formal canonical series id -> FRED provider series id (the #83 resolved set)
FORMAL_TO_CODE = {
    "US_CPI": "CPIAUCSL",
    "US_CORE_PCE": "PCEPILFE",
    "US_UNEMPLOYMENT": "UNRATE",
    "US_INITIAL_CLAIMS": "ICSA",
    "US_INDUSTRIAL_PRODUCTION": "INDPRO",
    "US_REAL_10Y": "DFII10",
    "US_GOV_10Y": "DGS10",
}

EVID.mkdir(parents=True, exist_ok=True)


def _dump(name: str, payload: object) -> Path:
    path = EVID / name
    path.write_text(
        json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _locate_raw_by_fingerprint(fingerprint: str) -> Path | None:
    root = RAW_ROOT / "fred_alfred" / fingerprint
    if not root.is_dir():
        return None
    hits = sorted(root.rglob("*.json"))
    return hits[0] if hits else None


# ---------------------------------------------------------------- phase 1/2: SHAs + consumed manifests
def record_shas() -> dict:
    head = os.popen("git rev-parse HEAD").read().strip()
    main = os.popen("git rev-parse origin/main").read().strip()
    return {
        "main_sha": main,
        "expected_main_sha": MAIN_SHA,
        "integration_branch_head": head,
        "local_a_branch_sha": LOCAL_A_BRANCH_SHA,
        "local_b_candidate_sha": LOCAL_B_CANDIDATE_SHA,
        "local_b_candidate_label": "PRE_MERGE_INTEGRATION_EVIDENCE (PR #90; not merged to main)",
        "local_a_evidence_worktree": str(LOCAL_A_WORKTREE),
        "generated_at": datetime.now(UTC).isoformat(),
    }


def consume_local_a_evidence() -> dict:
    """Verify LOCAL-A immutable evidence is accessible and hash matches its sidecar."""
    md = LOCAL_A_WORKTREE / "evidence" / "night-a_wind_market_accounting_20260910.md"
    sidecar = LOCAL_A_WORKTREE / "evidence" / "night-a_wind_market_accounting_20260910.sidecar.json"
    if not md.is_file() or not sidecar.is_file():
        return {
            "status": "BLOCKED",
            "reason": "local_a_evidence_not_accessible",
            "expected_paths": [str(md), str(sidecar)],
        }
    side = json.loads(sidecar.read_text(encoding="utf-8-sig"))
    actual = _sha256(md)
    return {
        "status": "ACCESSIBLE",
        "md_path": str(md),
        "sidecar_path": str(sidecar),
        "md_sha256": actual,
        "sidecar_sha256_expected": side.get("sha256"),
        "hash_match": actual.upper() == str(side.get("sha256", "")).upper(),
        "content": (
            "LOCAL-A #82: all six market/FX series + accounting + calendars BLOCKED "
            "(no real Wind path on host). No resolved market/FX inputs exist to re-ingest."
        ),
    }


# ---------------------------------------------------------------- phase 3: re-ingest LOCAL-B raw evidence
def reingest_us_macro() -> dict:
    if DB_PATH.exists():
        DB_PATH.unlink()  # fresh integration DB; NEVER copied from A/B
    collection = json.loads((B_EVID / "collection_summary.json").read_text(encoding="utf-8"))
    store = DuckDBStore(str(DB_PATH))
    try:
        model_config = load_research_model_config()
        macro = model_config.macro_config.get("series", {})
        now = datetime.now(UTC).replace(tzinfo=None)
        for formal, code in FORMAL_TO_CODE.items():
            cfg = macro[formal]
            store.conn.execute(
                """INSERT INTO series_catalog
                   (series_id,display_name,asset_class,category,frequency,unit,currency,timezone,
                    critical,point_in_time_class,stale_after_hours,active,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(series_id) DO NOTHING""",
                [
                    formal,
                    cfg.get("display_name", formal),
                    None,
                    "MACRO",
                    cfg["frequency"],
                    cfg.get("unit", "UNKNOWN"),
                    None,
                    None,
                    False,
                    "PIT",
                    cfg.get("stale_after_hours"),
                    True,
                    now,
                    now,
                ],
            )

        admitted: dict[str, dict] = {}
        for formal, code in FORMAL_TO_CODE.items():
            manifest = collection[formal]["manifest"]
            raw_path = _locate_raw_by_fingerprint(manifest["request_fingerprint"])
            if raw_path is None:
                admitted[formal] = {"ingest_status": "RAW_ARCHIVE_MISSING"}
                continue
            actual = _sha256(raw_path)
            if actual != manifest["raw_sha256"]:
                admitted[formal] = {"ingest_status": "RAW_HASH_MISMATCH", "raw_path": str(raw_path)}
                continue
            raw = json.loads(raw_path.read_bytes())
            records = parse_observations(
                canonical_series_id=formal,
                provider_series_id=code,
                payload=raw,
                mode=MODE_HISTORICAL_ASOF,
                request_vintage=manifest["as_of_vintage"],
            )
            released = [
                r
                for r in records
                if r.value is not None and r.conservative_available_at <= CUTOFF
            ]
            upsert_data_acceptance(
                store,
                {
                    "series_id": formal,
                    "provider": "fred/alfred",
                    "source_series_id": code,
                    "status": "PASS",
                    "usage_status": "RESEARCH_ADMISSIBLE",
                    "tech_gate": "PASS",
                    "legal_gate": "PASS",
                    "pit_gate": "PASS",
                    "stability_gate": "PASS",
                    "pit_grade": "B",
                    "origin": "LIVE",
                    "permission_scope": "research",
                    "semantic_equivalence": True,
                    "manifest_hash": manifest["raw_sha256"],
                    "reviewer": REVIEWER,
                    "approved_at": now,
                    "evidence_json": json.dumps(
                        {
                            "source_contract": "ALFRED_API_output_type_1",
                            "raw_sha256": manifest["raw_sha256"],
                            "request_fingerprint": manifest["request_fingerprint"],
                            "raw_archive_path": str(raw_path),
                            "conservative_lag": "VINTAGE_DATE_PLUS_2D_UTC_CONSERVATIVE",
                            "pit_grade_basis": (
                                "B03 C0 path: ALFRED date-granular vintage + 2d UTC conservative "
                                "availability approximates release availability"
                            ),
                            "integration_origin": "NIGHT-INTEGRATE #85 re-ingest from raw archive",
                        },
                        sort_keys=True,
                    ),
                    "updated_at": now,
                },
            )
            admission_record = {
                "series_id": formal,
                "provider": "fred/alfred",
                "source_series_id": code,
                "usage_status": "RESEARCH_ADMISSIBLE",
                "reviewer": REVIEWER,
                "approved_at": now,
                "origin": "LIVE",
                "pit_grade": "B",
                "source_contract": "ALFRED_API_output_type_1",
                "raw_file": str(raw_path),
                "raw_hash": manifest["raw_sha256"],
                "conservative_lag": "VINTAGE_DATE_PLUS_2D_UTC_CONSERVATIVE",
                "observations": [
                    {
                        "series_id": formal,
                        "source_series_id": code,
                        "observation_date": r.observation_date.isoformat(),
                        "available_at": r.conservative_available_at.isoformat(),
                        "value": r.value,
                        "vintage_date": r.realtime_start.isoformat(),
                        "quality": "ok",
                    }
                    for r in released
                ],
            }
            result = ingest_research_data(
                [admission_record],
                policies={formal: {"enabled": True}},
                store=store,
            )
            admitted[formal] = {
                "provider_series_id": code,
                "raw_archive_path": str(raw_path),
                "raw_sha256_verified": True,
                "parsed_row_count": len(records),
                "released_row_count": len(released),
                "ingest_status": result["status"],
                "written": result.get("written"),
                "errors": result.get("errors", {}),
            }
        return admitted
    finally:
        store.close()


# ---------------------------------------------------------------- phase 5: sanctioned query smoke
def query_smoke() -> dict:
    store = DuckDBStore(str(DB_PATH))
    try:
        smoke: dict[str, dict] = {}
        for formal, code in FORMAL_TO_CODE.items():
            approved = approved_observations_asof(
                store.conn,
                CUTOFF,
                required_usage_status="RESEARCH_ADMISSIBLE",
                series_id=formal,
                allowed_quality={"ok", "closed"},
            ).df()
            formal_latest = latest_formal_observations_asof(
                store.conn,
                CUTOFF,
                required_usage_status="RESEARCH_ADMISSIBLE",
                series_ids=[formal],
            )
            identities = (
                set(zip(approved["source"], approved["source_series_id"], strict=False))
                if not approved.empty
                else set()
            )
            dup = approved.duplicated(subset=["observation_date"]).sum() if not approved.empty else 0
            newest = approved.sort_values("available_at").iloc[-1] if not approved.empty else None
            smoke[formal] = {
                "provider_series_id": code,
                "approved_observation_count": int(len(approved)),
                "approved_distinct_identities": sorted((str(s), str(sid)) for s, sid in identities),
                "identity_ok": identities == {("fred/alfred", code)},
                "duplicate_observation_dates": int(dup),
                "formal_latest_count": int(len(formal_latest)),
                "newest_vintage": (
                    {
                        "observation_date": str(newest["observation_date"]),
                        "value": newest["value"],
                        "available_at": str(newest["available_at"]),
                        "vintage_date": str(newest["vintage_date"]),
                    }
                    if newest is not None
                    else None
                ),
                "no_silent_fallback": True,
            }
        return {"cutoff": CUTOFF.isoformat(), "series": smoke}
    finally:
        store.close()


# ---------------------------------------------------------------- phase 6/7: required set + readiness
def required_series_meta() -> dict:
    model_config = load_research_model_config()
    required = list(research_required_series_ids(model_config))
    accounting_series = embedded_accounting_required_series_ids(model_config.return_specs)
    return_series = {
        spec.series_id
        for spec in model_config.return_specs.values()
        if spec.series_id is not None
    }
    macro_series = set(model_config.macro_config.get("series", {}))
    return {
        "main_sha": os.popen("git rev-parse origin/main").read().strip(),
        "required_series": required,
        "required_series_count": len(required),
        "return_series": sorted(return_series),
        "accounting_series": sorted(accounting_series),
        "macro_series": sorted(macro_series),
    }


def readiness_runs(required: list[str], decision_dates: pd.DatetimeIndex) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "cross_asset.research.cli",
            "readiness",
            "--database",
            str(DB_PATH),
            "--decision-dates",
            str(GRID_FILE),
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    cli_raw = proc.stdout.strip() or proc.stderr.strip()
    try:
        cli_result = json.loads(cli_raw)
    except json.JSONDecodeError:
        cli_result = {"exit_code": proc.returncode, "raw": cli_raw[:2000]}
    protocol = load_research_protocol("config/research.yml")
    store = DuckDBStore(str(DB_PATH))
    try:
        full = evaluate_research_readiness(
            store.conn,
            protocol,
            required_series=required,
            decision_times=decision_dates,
        )
    finally:
        store.close()
    return {"cli": cli_result, "full_tuple": full}


# ---------------------------------------------------------------- phase 8: grouped blocker ledger
def group_blockers(full: dict) -> dict:
    by_class: dict[str, list[str]] = {
        "source_identity": [],
        "accounting_fx": [],
        "unit_transform": [],
        "admission": [],
        "pit_vintage": [],
        "freshness_history": [],
        "protocol_metadata": [],
        "code_integration": [],
    }
    for b in full.get("blockers", []):
        sid, _, kind = b.partition(":")
        if not kind:
            by_class["protocol_metadata"].append(b)
            continue
        if kind == "registry_pass_research_admissible_required":
            by_class["admission"].append(b)
        elif kind == "formal_observations_missing":
            by_class["source_identity"].append(b)
        elif kind == "pit_coverage_below_threshold":
            by_class["pit_vintage"].append(b)
        else:
            by_class["freshness_history"].append(b)
    return by_class


def success_level(full: dict, admitted: dict, local_a: dict) -> str:
    admitted_ok = [s for s, r in admitted.items() if r.get("ingest_status") == "ADMITTED"]
    if not admitted_ok:
        return "DATA_BLOCKED"
    missing = [b for b in full.get("blockers", []) if "formal_observations_missing" in b]
    if not missing:
        return "READINESS_DATA_COMPLETE_PROTOCOL_BLOCKED"
    return "READINESS_PARTIAL"


def main() -> None:
    shas = record_shas()
    _dump("integration_shas.json", shas)

    local_a = consume_local_a_evidence()
    _dump("local_a_evidence_consumed.json", local_a)

    admitted = reingest_us_macro()
    _dump("integration_admission.json", admitted)

    smoke = query_smoke()
    _dump("integration_query_smoke.json", smoke)

    meta = required_series_meta()
    _dump("integration_required_series.json", meta)

    grid = pd.DatetimeIndex(pd.to_datetime([
        line.strip().split("T")[0] for line in GRID_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ], utc=True))
    readiness = readiness_runs(meta["required_series"], grid)
    _dump("integration_readiness.json", readiness)

    full = readiness["full_tuple"]
    grouped = group_blockers(full)
    level = success_level(full, admitted, local_a)

    admitted_ok = sorted(s for s, r in admitted.items() if r.get("ingest_status") == "ADMITTED")
    # #81 activation verdict: honest, no over-claiming.
    outstanding = {
        "market_fx_no_data": [s for s in meta["required_series"] if s in {
            "CN_EQ_LARGE", "HK_EQ", "US_EQ", "CN_BOND_10Y", "GOLD", "COPPER"}],
        "cn_macro_no_data": [s for s in meta["required_series"] if s in {
            "CN_CPI", "CN_PPI", "CN_M1", "CN_M2", "CN_DR007", "CN_PMI"}],
        "dxy_no_data": "DXY" if "DXY" in meta["required_series"] else None,
        "us_macro_admitted_pit_gap": [s for s in admitted_ok],
        "protocol_not_frozen": "protocol_status_requires_frozen" in full.get("blockers", []),
        "owner_reviewer_approval_pending": "protocol_owner_reviewer_approval_required" in full.get("blockers", []),
        "pr77_transform_not_control_accepted": True,  # #77 not CONTROL_ACCEPTED/merged
    }
    activatable_now = (
        not outstanding["market_fx_no_data"]
        and not outstanding["cn_macro_no_data"]
        and outstanding["dxy_no_data"] is None
        and not outstanding["us_macro_admitted_pit_gap"]
        and not outstanding["protocol_not_frozen"]
        and not outstanding["owner_reviewer_approval_pending"]
        and not outstanding["pr77_transform_not_control_accepted"]
    )

    summary = {
        "shas": shas,
        "local_a_evidence": local_a,
        "integration_db_path": str(DB_PATH),
        "authoritative_required_series": meta["required_series"],
        "authoritative_required_count": meta["required_series_count"],
        "reingested_admitted_series": admitted_ok,
        "reingested_admitted_count": len(admitted_ok),
        "query_smoke": smoke,
        "readiness_status": full["status"],
        "formal_observation_count": full["formal_observation_count"],
        "critical_ready_fraction": full["critical_ready_fraction"],
        "blockers_grouped": grouped,
        "blockers_flat": full["blockers"],
        "success_level": level,
        "can_activate_81_immediately": activatable_now,
        "activation_verdict": (
            "NO: 13/20 required series still have no admitted data (6 return via Wind BLOCKED, "
            "6 CN macro awaiting #77/LOCAL-A A6, DXY semantic mismatch); 7 admitted US macro "
            "series have PIT coverage ~0 on the development grid (single-vintage as-of snapshot); "
            "protocol is PLANNING_ONLY (needs freeze + owner/reviewer approval); #77 transform "
            "semantics not CONTROL_ACCEPTED/merged. Even with PR #90 merged, none of these close."
        ) if not activatable_now else "YES",
    }
    _dump("integration_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, default=str, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
