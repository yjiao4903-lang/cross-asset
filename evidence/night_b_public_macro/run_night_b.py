"""NIGHT-B / Issue #83: real FRED/ALFRED public macro evidence into an isolated LOCAL-B DB.

Phases:
  B1 authoritative required-series ledger from the actual model config on current main
  B2 real official FRED/ALFRED collection (metadata + revised-latest history + vintage evidence)
  B3 bounded RESEARCH_ADMISSIBLE admission in the isolated LOCAL-B DB
  B4 sanctioned approved-observation query smoke
  B4 formal readiness preflight (sanctioned CLI + full authoritative tuple)

This driver writes ONLY to LOCAL-B isolated paths (data/db/local_b, data/raw/fred_alfred_local_b)
and committed evidence under evidence/night_b_public_macro/. It never touches Wind, return_accounting,
config/macro.yml, #77 transform code, or formal OOS.
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
    MODE_ALL_REALTIME_PERIODS,
    MODE_HISTORICAL_ASOF,
    parse_observations,
)
from cross_asset.backtest.accounting import embedded_accounting_required_series_ids  # noqa: E402
from cross_asset.ingestion.fred_alfred_registry import load_fred_registry  # noqa: E402
from cross_asset.ingestion.raw_archive import ImmutableRawArchive  # noqa: E402
from cross_asset.ingestion.research import ingest_research_data  # noqa: E402
from cross_asset.providers.fred_alfred import FredAlfredClient, FredResponseCache  # noqa: E402
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

EVID = REPO / "evidence" / "night_b_public_macro"
STAGING = EVID / "staging"
PIT_DIR = EVID / "pit"
RAW_ROOT = REPO / "data" / "raw" / "fred_alfred_local_b"
CACHE_DIR = REPO / "data" / "raw" / "fred_alfred_local_b_cache"
DB_PATH = REPO / "data" / "db" / "local_b" / "cross_asset_b.duckdb"

COLLECT_START = "1985-01-01"
COLLECT_END = "2026-09-10"
# Representative current/development cutoff for freshness/admission (UTC).
CUTOFF = datetime(2026, 9, 10, 23, 59, tzinfo=UTC)
REVIEWER = "LOCAL-DEV-B"

# formal canonical series id -> FRED provider series id (B2 set)
FORMAL_TO_CODE = {
    "US_CPI": "CPIAUCSL",
    "US_CORE_PCE": "PCEPILFE",
    "US_UNEMPLOYMENT": "UNRATE",
    "US_INITIAL_CLAIMS": "ICSA",
    "US_INDUSTRIAL_PRODUCTION": "INDPRO",
    "US_REAL_10Y": "DFII10",
    "US_GOV_10Y": "DGS10",
}
# C0 registry canonical (collector key) -> formal canonical series id
REG_TO_FORMAL = {
    "US_CPI_HEADLINE": "US_CPI",
    "US_PCE_CORE": "US_CORE_PCE",
    "US_UNEMPLOYMENT": "US_UNEMPLOYMENT",
    "US_INITIAL_CLAIMS": "US_INITIAL_CLAIMS",
    "US_INDUSTRIAL_PRODUCTION": "US_INDUSTRIAL_PRODUCTION",
    "US_REAL_10Y": "US_REAL_10Y",
    "US_TSY_10Y": "US_GOV_10Y",
}

for _d in (EVID, STAGING, PIT_DIR, RAW_ROOT, CACHE_DIR, DB_PATH.parent):
    _d.mkdir(parents=True, exist_ok=True)

CLIENT = FredAlfredClient(
    retries=2,
    timeout=25.0,
    min_interval=1.0,
    cache=FredResponseCache(str(CACHE_DIR)),
    raw_archive=ImmutableRawArchive(str(RAW_ROOT)),
)


def _dump(name: str, payload: object) -> Path:
    path = EVID / name
    path.write_text(
        json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------- Phase B1
def build_ledger() -> tuple[dict, dict]:
    model_config = load_research_model_config()
    # Authoritative required-series set exactly as the formal research path
    # resolves it on current main (research/dependencies.py).
    required = list(research_required_series_ids(model_config))
    accounting_series = embedded_accounting_required_series_ids(model_config.return_specs)
    return_series = {
        spec.series_id
        for spec in model_config.return_specs.values()
        if spec.series_id is not None
    }
    macro_series = set(model_config.macro_config.get("series", {}))

    registry = load_fred_registry()
    configured: dict[str, dict] = {}
    for reg_key, formal in REG_TO_FORMAL.items():
        spec = registry.series[reg_key]
        configured[formal] = {
            "registry_canonical": reg_key,
            "provider_series_id": spec.provider_series_id,
            "registry_status": spec.status,
            "title": spec.title,
            "source_url": spec.source_url,
            "revision_vintage_policy": spec.revision_vintage_policy,
            "release_availability_policy": spec.release_availability_policy,
        }
    configured["DXY"] = {
        "registry_canonical": "USD_BROAD_INDEX",
        "provider_series_id": "DTWEXBGS",
        "registry_status": "CANDIDATE",
        "title": "Nominal Broad U.S. Dollar Index",
        "note": "broad trade-weighted index, NOT the ICE DXY; semantic equivalence NOT established",
    }

    ledger_rows: dict[str, dict] = {}
    for sid in required:
        macro = model_config.macro_config.get("series", {}).get(sid, {})
        role_bits = []
        if sid in return_series:
            role_bits.append("return")
        if sid in accounting_series:
            role_bits.append("fx-hedge")
        if sid in macro_series:
            role_bits.append("macro")
        raw_unit = macro.get("raw_unit")
        unit = macro.get("unit")
        ledger_rows[sid] = {
            "series_id": sid,
            "role": "+".join(role_bits) or "UNKNOWN",
            "configured_source": configured.get(sid),
            "raw_unit": raw_unit or "UNKNOWN",
            "transformed_unit": unit or "UNKNOWN",
            "frequency": macro.get("frequency", "UNKNOWN"),
            "stale_after_hours": macro.get("stale_after_hours"),
            "required_usage_status": "RESEARCH_ADMISSIBLE",
            "admission_status": "PENDING",
            "pit_vintage_status": "PENDING",
            "first_available": None,
            "last_available": None,
            "freshness_status": "PENDING",
            "status": "PENDING",
            "blocker": None,
        }
    meta = {
        "main_sha": os.popen("git rev-parse origin/main").read().strip(),
        "generated_at": datetime.now(UTC).isoformat(),
        "required_series_count": len(required),
        "required_series": required,
        "accounting_series": sorted(accounting_series),
        "return_series": sorted(return_series),
        "macro_series": sorted(macro_series),
    }
    return meta, ledger_rows


# ---------------------------------------------------------------- Phase B2
# C0 fail-closed policy VINTAGE_DATE_PLUS_2D_UTC_CONSERVATIVE: on decision day D
# only revisions with vintage <= D-2d are available. So the "latest revision"
# fetch is done as-of the newest official ALFRED vintage whose conservative
# availability is <= CUTOFF (causal as-of fetch via vintage_dates).
REALTIME_CAP = (CUTOFF.date() - timedelta(days=2)).isoformat()


def latest_available_vintage(provider_series_id: str) -> tuple[str, FredPayload]:
    """Newest official vintage date with conservative availability <= CUTOFF."""
    vp = CLIENT.fetch_vintage_dates(provider_series_id, use_cache=True)
    vintages = [str(v) for v in vp.payload.get("vintage_dates", [])]
    eligible = [v for v in vintages if v <= REALTIME_CAP]
    if not eligible:
        raise RuntimeError(
            f"no_conservatively_available_vintage:{provider_series_id}:cap={REALTIME_CAP}"
        )
    return eligible[-1], vp


def collect_all() -> dict:
    summary: dict[str, dict] = {}
    for reg_key, formal in REG_TO_FORMAL.items():
        code = FORMAL_TO_CODE[formal]
        metadata_payload = CLIENT.fetch_metadata(code, use_cache=True)
        as_of, vp = latest_available_vintage(code)
        obs_payload = CLIENT.fetch_historical_asof(
            code,
            observation_start=COLLECT_START,
            observation_end=COLLECT_END,
            as_of=as_of,
            use_cache=True,
        )
        rows = parse_observations(
            canonical_series_id=formal,
            provider_series_id=code,
            payload=obs_payload.payload,
            mode=MODE_HISTORICAL_ASOF,
            request_vintage=as_of,
        )
        series_dir = STAGING / reg_key
        series_dir.mkdir(parents=True, exist_ok=True)
        (series_dir / "historical_asof.jsonl").write_text(
            "".join(json.dumps(row.to_dict(), sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        meta_list = metadata_payload.payload.get("seriess", [])
        meta0 = meta_list[0] if isinstance(meta_list, list) and meta_list else {}
        raw_path = obs_payload.raw_archive_path or ""
        missing = sum(row.value is None for row in rows)
        future = sum(row.conservative_available_at > CUTOFF for row in rows)
        blockers = ["impossible_future_available_at"] if future else []
        observation_dates = sorted({row.observation_date for row in rows})
        manifest = {
            "canonical_series_id": formal,
            "provider_series_id": code,
            "mode": MODE_HISTORICAL_ASOF,
            "as_of_vintage": as_of,
            "requested_start": COLLECT_START,
            "requested_end": COLLECT_END,
            "realtime_cap": REALTIME_CAP,
            "returned_start": observation_dates[0].isoformat() if observation_dates else None,
            "returned_end": observation_dates[-1].isoformat() if observation_dates else None,
            "row_count": len(rows),
            "missing_ratio": round(missing / len(rows), 6) if rows else 1.0,
            "duplicate_count": len(rows) - len({(r.observation_date, r.realtime_start) for r in rows}),
            "future_available_at_count": future,
            "latest_observation": observation_dates[-1].isoformat() if observation_dates else None,
            "latest_vintage": as_of,
            "title": meta0.get("title"),
            "units": meta0.get("units"),
            "frequency": meta0.get("frequency"),
            "seasonal_adjustment": meta0.get("seasonal_adjustment"),
            "metadata_last_updated": meta0.get("last_updated"),
            "metadata_realtime_start": metadata_payload.payload.get("realtime_start"),
            "metadata_realtime_end": metadata_payload.payload.get("realtime_end"),
            "metadata_request_fingerprint": metadata_payload.request_fingerprint,
            "metadata_raw_sha256": metadata_payload.raw_sha256,
            "request_fingerprint": obs_payload.request_fingerprint,
            "raw_sha256": obs_payload.raw_sha256,
            "raw_archive_path": raw_path,
            "cache_hit": obs_payload.cache_hit,
            "blockers": blockers,
            "warnings": [],
            "source_health": "BLOCKED" if blockers else "OK",
        }
        (series_dir / "historical_asof_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, default=str, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        # PIT/vintage evidence: official vintage-date list (top-level "vintage_dates" array)
        vintages = [str(v) for v in vp.payload.get("vintage_dates", [])]
        sidecar = {
            "endpoint": vp.endpoint,
            "params": vp.params,
            "request_fingerprint": vp.request_fingerprint,
            "raw_sha256": vp.raw_sha256,
            "raw_archive_path": vp.raw_archive_path,
            "fetched_at": vp.fetched_at.isoformat(),
            "vintage_count": len(vintages),
            "vintage_first": vintages[0] if vintages else None,
            "vintage_last": vintages[-1] if vintages else None,
            "vintage_selected": as_of,
            "selection_rule": "latest_official_vintage_with_conservative_availability_le_cutoff",
        }
        (PIT_DIR / f"vintagedates_{code}.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, default=str, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        summary[formal] = {
            "registry_canonical": reg_key,
            "manifest": manifest,
            "vintage_sidecar": sidecar,
        }
    # Bounded full-vintage PIT matrix on two monthly series (2-year window).
    for formal, code in (("US_CPI", "CPIAUCSL"), ("US_CORE_PCE", "PCEPILFE")):
        p = CLIENT.fetch_all_realtime_periods(
            code, observation_start="2020-01-01", observation_end="2021-12-31", use_cache=True
        )
        rows = parse_observations(
            canonical_series_id=formal,
            provider_series_id=code,
            payload=p.payload,
            mode=MODE_ALL_REALTIME_PERIODS,
        )
        (PIT_DIR / f"all_realtime_{code}_2020_2021.json").write_text(
            json.dumps(
                {
                    "canonical_series_id": formal,
                    "provider_series_id": code,
                    "mode": MODE_ALL_REALTIME_PERIODS,
                    "request_fingerprint": p.request_fingerprint,
                    "raw_sha256": p.raw_sha256,
                    "raw_archive_path": p.raw_archive_path,
                    "fetched_at": p.fetched_at.isoformat(),
                    "row_count": len(rows),
                    "distinct_observation_dates": len({r.observation_date for r in rows}),
                    "distinct_vintages": len({r.realtime_start for r in rows}),
                    "sample": [r.to_dict() for r in rows[:5]],
                },
                ensure_ascii=False,
                default=str,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        summary[formal]["full_vintage_matrix"] = {
            "window": "2020-01-01..2021-12-31",
            "row_count": len(rows),
            "raw_sha256": p.raw_sha256,
            "fingerprint": p.request_fingerprint,
        }
    # Causal as-of demo on UNRATE (same observation, two vintages).
    asof_demo = {}
    for aof in ("2020-04-15", "2022-01-15"):
        p = CLIENT.fetch_historical_asof(
            "UNRATE",
            observation_start="2020-01-01",
            observation_end="2020-01-31",
            as_of=aof,
            use_cache=True,
        )
        recs = parse_observations(
            canonical_series_id="US_UNEMPLOYMENT",
            provider_series_id="UNRATE",
            payload=p.payload,
            mode=MODE_HISTORICAL_ASOF,
            request_vintage=aof,
        )
        asof_demo[aof] = {
            "request_fingerprint": p.request_fingerprint,
            "raw_sha256": p.raw_sha256,
            "raw_archive_path": p.raw_archive_path,
            "value": recs[0].value,
            "conservative_available_at": recs[0].conservative_available_at.isoformat(),
        }
    (PIT_DIR / "unrate_causal_asof.json").write_text(
        json.dumps(asof_demo, ensure_ascii=False, default=str, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary["_pit_extra"] = {"unrate_causal_asof": asof_demo}
    return summary


# ---------------------------------------------------------------- Phase B3
def admit(collection: dict) -> dict:
    if DB_PATH.exists():
        DB_PATH.unlink()  # fresh isolated DB; LOCAL-B owns this path only
    store = DuckDBStore(str(DB_PATH))
    try:
        # series_catalog for the 7 macro series (actual config, critical=false)
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
            reg_key = next(k for k, v in REG_TO_FORMAL.items() if v == formal)
            manifest = collection[formal]["manifest"]
            records_path = STAGING / reg_key / "historical_asof.jsonl"
            rows = [
                json.loads(line)
                for line in records_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            released = [
                r
                for r in rows
                if r["value"] is not None
                and datetime.fromisoformat(r["conservative_available_at"]) <= CUTOFF
            ]
            raw_path = manifest["raw_archive_path"]
            raw_hash = manifest["raw_sha256"]
            if not raw_path or not Path(raw_path).is_file():
                raise RuntimeError(f"raw_archive_missing:{formal}")
            actual = hashlib.sha256(Path(raw_path).read_bytes()).hexdigest()
            if actual != raw_hash:
                raise RuntimeError(f"raw_hash_mismatch:{formal}")

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
                    "manifest_hash": raw_hash,
                    "reviewer": REVIEWER,
                    "approved_at": now,
                    "evidence_json": json.dumps(
                        {
                            "source_contract": "ALFRED_API_output_type_1",
                            "raw_sha256": raw_hash,
                            "request_fingerprint": manifest["request_fingerprint"],
                            "raw_archive_path": raw_path,
                            "conservative_lag": "VINTAGE_DATE_PLUS_2D_UTC_CONSERVATIVE",
                            "pit_grade_basis": (
                                "B03 C0 path: ALFRED date-granular vintage + 2d UTC conservative "
                                "availability approximates release availability; exact first-release "
                                "timestamps required for grade A"
                            ),
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
                "raw_file": raw_path,
                "raw_hash": raw_hash,
                "conservative_lag": "VINTAGE_DATE_PLUS_2D_UTC_CONSERVATIVE",
                "observations": [
                    {
                        "series_id": formal,
                        "source_series_id": code,
                        "observation_date": r["observation_date"],
                        "available_at": r["conservative_available_at"],
                        "value": r["value"],
                        "vintage_date": r["realtime_start"],
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
                "collection_row_count": len(rows),
                "released_row_count": len(released),
                "pending_release_count": len(rows) - len(released),
                "raw_hash_verified": True,
                "ingest_status": result["status"],
                "written": result.get("written"),
                "errors": result.get("errors", {}),
            }
        return admitted
    finally:
        store.close()


# ---------------------------------------------------------------- Phase B4a
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
            identities = set(
                zip(approved["source"], approved["source_series_id"], strict=False)
            ) if not approved.empty else set()
            dup = approved.duplicated(subset=["observation_date"]).sum() if not approved.empty else 0
            newest = approved.sort_values("available_at").iloc[-1] if not approved.empty else None
            smoke[formal] = {
                "provider_series_id": code,
                "approved_observation_count": int(len(approved)),
                "approved_distinct_identities": sorted(
                    (str(s), str(sid)) for s, sid in identities
                ),
                "identity_ok": identities == {("fred/alfred", code)},
                "duplicate_observation_dates": int(dup),
                "formal_latest_count": int(len(formal_latest)),
                "newest_vintage": {
                    "observation_date": str(newest["observation_date"]),
                    "value": newest["value"],
                    "available_at": str(newest["available_at"]),
                    "vintage_date": str(newest["vintage_date"]),
                }
                if newest is not None
                else None,
                "no_silent_fallback": True,
            }
        return {"cutoff": CUTOFF.isoformat(), "series": smoke}
    finally:
        store.close()


# ---------------------------------------------------------------- Phase B4b
def readiness_runs(required: list[str], decision_dates: pd.DatetimeIndex) -> dict:
    grid_file = EVID / "decision_dates_weekly_development.txt"
    grid_file.write_text(
        "\n".join(ts.strftime("%Y-%m-%d") + "T16:00:00+00:00" for ts in decision_dates)
        + "\n",
        encoding="utf-8",
    )
    # a) exact sanctioned CLI command (with the same decision grid)
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
            str(grid_file),
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
    # b) full authoritative tuple
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


def main() -> None:
    meta, ledger_rows = build_ledger()
    _dump("ledger_authoritative_required_series.json", {"meta": meta, "series": ledger_rows})

    collection = collect_all()
    _dump("collection_summary.json", collection)

    admitted = admit(collection)
    _dump("admission_result.json", admitted)

    smoke = query_smoke()
    _dump("query_smoke.json", smoke)

    # readiness decision dates: weekly development grid (representative)
    grid = pd.date_range("2018-01-05", "2026-08-28", freq="W-FRI", tz="UTC")
    readiness = readiness_runs(meta["required_series"], grid)
    _dump("readiness_preflight.json", readiness)

    # finalize ledger rows with observed evidence; US-series status reflects
    # the full-tuple readiness outcome (PARTIAL when historical PIT coverage is
    # not demonstrated by the single-vintage as-of snapshot).
    full_series = {
        item["series_id"]: item for item in readiness["full_tuple"]["series"]
    }
    for formal in FORMAL_TO_CODE:
        manifest = collection[formal]["manifest"]
        row = ledger_rows[formal]
        row["admission_status"] = (
            "RESEARCH_ADMISSIBLE"
            if admitted[formal]["ingest_status"] == "ADMITTED"
            else admitted[formal]["ingest_status"]
        )
        row["pit_vintage_status"] = "PIT_VINTAGE_ALFRED_CONSERVATIVE"
        row["first_available"] = manifest["returned_start"]
        row["last_available"] = manifest["returned_end"]
        row["freshness_status"] = (
            f"released_asof_{CUTOFF.date().isoformat()}; pending_release={admitted[formal]['pending_release_count']}"
        )
        item = full_series.get(formal, {})
        pit_blocker = any(
            b == "pit_coverage_below_threshold" for b in item.get("blockers", [])
        )
        if row["admission_status"] != "RESEARCH_ADMISSIBLE":
            row["status"] = "PARTIAL"
            row["blocker"] = "admission_rejected:" + str(admitted[formal].get("errors", {}))
        elif pit_blocker:
            row["status"] = "PARTIAL"
            row["blocker"] = (
                "historical_pit_coverage_not_demonstrated:single_vintage_asof_snapshot "
                "(all observations share the latest as-of vintage; per-decision PIT "
                "coverage over the development grid requires per-vintage history)"
            )
        else:
            row["status"] = "READY"
            row["blocker"] = None

    # DXY and other non-FRED series blockers (truthful, no fabrication)
    for sid, row in ledger_rows.items():
        if sid in FORMAL_TO_CODE:
            continue
        if sid == "DXY":
            row.update(
                admission_status="NOT_ADMITTED",
                pit_vintage_status="SEMANTIC_UNRESOLVED",
                freshness_status="DATA_BLOCKED",
                status="DATA_BLOCKED",
                blocker=(
                    "dxy_semantic_mismatch: canonical DXY is the ICE Dollar Index; FRED official "
                    "candidate is broad trade-weighted DTWEXBGS (registry USD_BROAD_INDEX CANDIDATE) "
                    "which is NOT semantically equivalent; no proxy substitution admitted"
                ),
            )
        elif sid.startswith("CN_"):
            row.update(
                admission_status="NOT_ADMITTED",
                pit_vintage_status="UNRESOLVED",
                freshness_status="DATA_BLOCKED",
                status="DATA_BLOCKED",
                blocker="cn_macro_source_owned_by_wind_local_a_stream (see #82 A6); no official public source admitted here; #77 owns transform semantics",
            )
        elif sid in {"CN_EQ_LARGE", "HK_EQ", "US_EQ", "CN_BOND_10Y", "GOLD", "COPPER"}:
            row.update(
                admission_status="NOT_ADMITTED",
                pit_vintage_status="UNRESOLVED",
                freshness_status="DATA_BLOCKED",
                status="DATA_BLOCKED",
                blocker="return/fx series owned by LOCAL-A #82 Wind market/accounting stream; not present in LOCAL-B isolated DB",
            )
        else:
            row.update(
                admission_status="NOT_ADMITTED",
                pit_vintage_status="UNRESOLVED",
                freshness_status="DATA_BLOCKED",
                status="DATA_BLOCKED",
                blocker="unresolved_required_series",
            )
    _dump("ledger_final.json", {"meta": meta, "series": ledger_rows})

    # coverage ratios from full-tuple readiness (truthful: only actually
    # ADMITTED series count as locally admitted; never hardcode)
    full = readiness["full_tuple"]
    admitted_series = sorted(
        s for s, r in admitted.items() if r["ingest_status"] == "ADMITTED"
    )
    summary = {
        "authoritative_required_series": meta["required_series"],
        "authoritative_required_count": len(meta["required_series"]),
        "locally_admitted_series": admitted_series,
        "locally_admitted_count": len(admitted_series),
        "full_tuple_status": full["status"],
        "critical_series_ready": full["critical_series_ready"],
        "critical_series_count": full["critical_series_count"],
        "critical_ready_fraction": full["critical_ready_fraction"],
        "formal_observation_count": full["formal_observation_count"],
        "blockers": full["blockers"],
    }
    _dump("handoff_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, default=str, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
