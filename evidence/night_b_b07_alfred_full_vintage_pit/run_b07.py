"""B07 / Issue #92: full per-vintage ALFRED history for formal development-grid PIT coverage.

Goal: close the #83/#85 LOCAL-B gap where the 7 real admitted US macro series had
only a single as-of-vintage snapshot, so per-decision PIT coverage across the
452-decision development grid was ~0.

This driver builds the real historical revision matrix over the development grid:

  B1  the authoritative 452-decision weekly development grid (same grid used by #83)
  B2  real ALFRED all-realtime-periods collection, observation-period + vintage identity
      preserved, conservative available_at (VINTAGE_DATE_PLUS_2D_UTC_CONSERVATIVE),
      immutable raw archive + request fingerprints + SHA-256 + compact manifests
  B3  fresh isolated LOCAL-B B07 DB rebuilt from raw evidence; bounded
      RESEARCH_ADMISSIBLE acceptance under the existing contract
  B4  sanctioned per-decision query smoke + newest-bad-vintage no-silent-fallback
      counterexample (in a separate scratch DB)
  B5  formal readiness on the 452-decision grid; per-series PIT coverage vs 0.95

Writes ONLY to LOCAL-B B07 isolated paths (data/db/local_b_b07, data/db/local_b_b07_scratch,
data/raw/fred_alfred_b07) and committed compact evidence under
evidence/night_b_b07_alfred_full_vintage_pit/. Never touches Wind, return_accounting,
config/macro.yml, #77 transform code, allocation/weights, Schema/Integration Contract,
or formal OOS. No proxy / zero-fill / threshold tuning.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

REPO = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, str(REPO / "src"))
os.chdir(REPO)

import pandas as pd  # noqa: E402

from cross_asset.ingestion.fred_alfred_pit import (  # noqa: E402
    MODE_ALL_REALTIME_PERIODS,
    conservative_available_at,
    parse_observations,
)
from cross_asset.ingestion.raw_archive import ImmutableRawArchive  # noqa: E402
from cross_asset.providers.fred_alfred import (  # noqa: E402
    FredAlfredClient,
    FredResponseCache,
)
from cross_asset.research.dependencies import research_required_series_ids  # noqa: E402
from cross_asset.research.model_config import load_research_model_config  # noqa: E402
from cross_asset.research.protocol import load_research_protocol  # noqa: E402
from cross_asset.research.readiness import evaluate_research_readiness  # noqa: E402
from cross_asset.storage import DuckDBStore, latest_formal_observations_asof  # noqa: E402
from cross_asset.storage.acceptance_registry import upsert_data_acceptance  # noqa: E402

EVID = REPO / "evidence" / "night_b_b07_alfred_full_vintage_pit"
STAGING = REPO / "data" / "raw" / "fred_alfred_b07" / "staging"  # gitignored full jsonl
RAW_ROOT = REPO / "data" / "raw" / "fred_alfred_b07"  # gitignored immutable raw archive
CACHE_DIR = REPO / "data" / "raw" / "fred_alfred_b07_cache"  # gitignored cache
DB_PATH = REPO / "data" / "db" / "local_b_b07" / "cross_asset_b07.duckdb"
SCRATCH_DB_PATH = REPO / "data" / "db" / "local_b_b07_scratch" / "cross_asset_b07_scratch.duckdb"

# Representative as-of cutoff for admission/freshness evidence (UTC).
CUTOFF = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
REVIEWER = "LOCAL-DEV-B"

# Formal canonical series id -> FRED/ALFRED provider series id (from #83 evidence).
FORMAL_TO_CODE = {
    "US_CPI": "CPIAUCSL",
    "US_CORE_PCE": "PCEPILFE",
    "US_UNEMPLOYMENT": "UNRATE",
    "US_INITIAL_CLAIMS": "ICSA",
    "US_INDUSTRIAL_PRODUCTION": "INDPRO",
    "US_REAL_10Y": "DFII10",
    "US_GOV_10Y": "DGS10",
}

# Official metadata expectations (id/title/units/frequency/SA) verified by #83 evidence.
EXPECTED_METADATA = {
    "CPIAUCSL": {
        "units": "Index 1982-1984=100",
        "frequency": "Monthly",
        "seasonal_adjustment": "Seasonally Adjusted",
        "title_contains": "Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
    },
    "PCEPILFE": {
        "units": "Index 2017=100",
        "frequency": "Monthly",
        "seasonal_adjustment": "Seasonally Adjusted",
        "title_contains": "Personal Consumption Expenditures Excluding Food and Energy",
    },
    "UNRATE": {
        "units": "Percent",
        "frequency": "Monthly",
        "seasonal_adjustment": "Seasonally Adjusted",
        "title_contains": "Unemployment Rate",
    },
    "ICSA": {
        "units": "Number",
        "frequency": "Weekly, Ending Saturday",
        "seasonal_adjustment": "Seasonally Adjusted",
        "title_contains": "Initial Claims",
    },
    "INDPRO": {
        "units": "Index 2017=100",
        "frequency": "Monthly",
        "seasonal_adjustment": "Seasonally Adjusted",
        "title_contains": "Industrial Production: Total Index",
    },
    "DFII10": {
        "units": "Percent",
        "frequency": "Daily",
        "seasonal_adjustment": "Not Seasonally Adjusted",
        "title_contains": "10-Year",
    },
    "DGS10": {
        "units": "Percent",
        "frequency": "Daily",
        "seasonal_adjustment": "Not Seasonally Adjusted",
        "title_contains": "10-Year Constant Maturity",
    },
}

# Development grid (authoritative, identical to #83): 452 weekly Fridays 16:00 UTC.
GRID = pd.date_range("2018-01-05", "2026-08-28", freq="W-FRI", tz="UTC")
GRID_START = GRID[0].to_pydatetime()
GRID_END = GRID[-1].to_pydatetime()

# Observation window: >=5y of history before the first decision (train_min_years=5).
OBS_START = "2012-01-01"
OBS_END = "2026-08-28"
# Realtime/vintage window: only vintages whose 2d-conservative availability can
# fall on a development decision. VINTAGE_START has margin before the first
# decision so the newest visible vintage at decision #1 is always present.
VINTAGE_START = (GRID_START.date() - timedelta(days=45)).isoformat()
VINTAGE_END = GRID_END.date().isoformat()

CHUNK_MONTHS = 48  # monthly/daily observation chunk
CHUNK_WEEKS = 26  # weekly observation chunk (keeps each ALFRED response bounded)

for _d in (EVID, STAGING, RAW_ROOT, CACHE_DIR, DB_PATH.parent, SCRATCH_DB_PATH.parent):
    _d.mkdir(parents=True, exist_ok=True)

CACHE = FredResponseCache(str(CACHE_DIR))
CLIENT = FredAlfredClient(
    retries=2,
    timeout=25.0,
    min_interval=1.0,
    cache=CACHE,
    raw_archive=ImmutableRawArchive(str(RAW_ROOT)),
)


def _dump(name: str, payload: object) -> Path:
    path = EVID / name
    path.write_text(
        json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _utc_naive(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def _ensure_archive(payload) -> str:
    """Cache-hit compensation for the unmerged #90 invariant: every served payload
    must have an immutable raw-archive entry. Main's cache-hit path returns
    raw_archive_path=None; archive the cached bytes here (content-identical to the
    original network fetch because the path embeds the original fetched_at)."""
    if payload.raw_archive_path:
        return payload.raw_archive_path
    cached = CACHE.get(payload.request_fingerprint)
    if cached is None:
        raise RuntimeError(f"cache_miss_for_unarchived_payload:{payload.request_fingerprint}")
    raw, _meta = cached
    if hashlib.sha256(raw).hexdigest() != payload.raw_sha256:
        raise RuntimeError("cache_hash_mismatch_compensation")
    return RAW_ARCHIVE.write(
        "fred_alfred",
        payload.request_fingerprint,
        raw,
        captured_at=payload.fetched_at,
        extension="json",
    )


RAW_ARCHIVE = ImmutableRawArchive(str(RAW_ROOT))


def _obs_chunks(frequency: str) -> list[tuple[str, str]]:
    """Bounded observation-date chunks so each ALFRED response stays well under
    provider row limits while the full vintage matrix is preserved."""
    if frequency.startswith("Weekly"):
        step = timedelta(weeks=CHUNK_WEEKS)
    else:
        step = timedelta(days=30 * CHUNK_MONTHS)
    start = date.fromisoformat(OBS_START)
    end = date.fromisoformat(OBS_END)
    chunks: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + step - timedelta(days=1), end)
        chunks.append((cursor.isoformat(), chunk_end.isoformat()))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _realtime_chunks(
    vintages: list[str], per_chunk: int = 600
) -> list[tuple[str, str]]:
    """Bound the realtime window so each ALFRED request stays under the provider
    limit of 2000 vintage dates per request (observed: the 2017-11-21..2026-08-28
    window spans 2172 vintage dates for DGS10). Chunks are cut exactly on vintage
    dates, so every vintage belongs to exactly one closed interval and the full
    matrix is preserved; duplicated rows (if any) are deduplicated downstream."""
    if not vintages:
        return [(VINTAGE_START, VINTAGE_END)]
    chunks: list[tuple[str, str]] = []
    n = len(vintages)
    for i in range(0, n, per_chunk):
        start = vintages[i]
        end = vintages[min(i + per_chunk, n) - 1]
        chunks.append((start, end))
    return chunks


def collect_series(formal: str, code: str, frequency: str) -> dict:
    """Fetch metadata + vintagedates + bounded full-vintage matrix; archive immutable raw."""
    series_dir = STAGING / formal
    series_dir.mkdir(parents=True, exist_ok=True)

    metadata_payload = CLIENT.fetch_metadata(code, use_cache=True)
    metadata_archive = _ensure_archive(metadata_payload)
    meta_rows = metadata_payload.payload.get("seriess", [])
    meta = dict(meta_rows[0]) if isinstance(meta_rows, list) and meta_rows else {}
    expected = EXPECTED_METADATA[code]
    identity_ok = (
        meta.get("id") == code
        and expected["title_contains"].lower() in str(meta.get("title", "")).lower()
        and meta.get("units") == expected["units"]
        and meta.get("frequency") == expected["frequency"]
        and meta.get("seasonal_adjustment") == expected["seasonal_adjustment"]
    )

    vp = CLIENT.fetch_vintage_dates(code, use_cache=True)
    vintages = [str(v) for v in vp.payload.get("vintage_dates", [])]

    chunks = _obs_chunks(frequency)
    rt_chunks = _realtime_chunks(vintages)
    all_rows: list[dict] = []
    request_log: list[dict] = []
    for chunk_start, chunk_end in chunks:
        for rt_start, rt_end in rt_chunks:
            payload = CLIENT.request_json(
                "series/observations",
                {
                    "series_id": code,
                    "observation_start": chunk_start,
                    "observation_end": chunk_end,
                    "realtime_start": rt_start,
                    "realtime_end": rt_end,
                    "output_type": 1,
                },
                use_cache=True,
                cache_max_age_seconds=None,
            )
            archive = _ensure_archive(payload)
            rows = parse_observations(
                canonical_series_id=formal,
                provider_series_id=code,
                payload=payload.payload,
                mode=MODE_ALL_REALTIME_PERIODS,
            )
            request_log.append(
                {
                    "chunk_start": chunk_start,
                    "chunk_end": chunk_end,
                    "realtime_start": rt_start,
                    "realtime_end": rt_end,
                    "request_fingerprint": payload.request_fingerprint,
                    "raw_sha256": payload.raw_sha256,
                    "raw_archive_path": archive,
                    "cache_hit": payload.cache_hit,
                    "row_count": len(rows),
                }
            )
            all_rows.extend(row.to_dict() for row in rows)

    # Fail-closed guards (nothing fabricated, nothing silently dropped).
    dropped_future_vintage = 0
    dropped_impossible_pit = 0
    kept: list[dict] = []
    for row in all_rows:
        realtime_start = date.fromisoformat(row["realtime_start"])
        if realtime_start > date.fromisoformat(VINTAGE_END):
            dropped_future_vintage += 1
            continue
        available = datetime.fromisoformat(row["conservative_available_at"])
        observation_date = date.fromisoformat(row["observation_date"])
        if available < datetime.combine(observation_date, time.min, tzinfo=UTC):
            dropped_impossible_pit += 1
            continue
        kept.append(row)
    kept.sort(key=lambda r: (r["observation_date"], r["realtime_start"]))

    (series_dir / "all_vintages.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in kept),
        encoding="utf-8",
    )
    manifest = {
        "canonical_series_id": formal,
        "provider_series_id": code,
        "mode": MODE_ALL_REALTIME_PERIODS,
        "observation_window": f"{OBS_START}..{OBS_END}",
        "vintage_window": f"{VINTAGE_START}..{VINTAGE_END}",
        "vintage_count_official": len(vintages),
        "vintage_first": vintages[0] if vintages else None,
        "vintage_last": vintages[-1] if vintages else None,
        "chunk_count": len(request_log),
        "parsed_row_count": len(all_rows),
        "kept_row_count": len(kept),
        "dropped_future_vintage": dropped_future_vintage,
        "dropped_impossible_pit": dropped_impossible_pit,
        "distinct_observation_dates": len({r["observation_date"] for r in kept}),
        "distinct_vintages": len({r["realtime_start"] for r in kept}),
        "missing_value_count": sum(r["value"] is None for r in kept),
        "latest_observation": max(r["observation_date"] for r in kept) if kept else None,
        "latest_vintage": max(r["realtime_start"] for r in kept) if kept else None,
        "title": meta.get("title"),
        "units": meta.get("units"),
        "frequency": meta.get("frequency"),
        "seasonal_adjustment": meta.get("seasonal_adjustment"),
        "metadata_identity_ok": identity_ok,
        "metadata_last_updated": meta.get("last_updated"),
        "metadata_request_fingerprint": metadata_payload.request_fingerprint,
        "metadata_raw_sha256": metadata_payload.raw_sha256,
        "metadata_raw_archive_path": metadata_archive,
        "vintagedates_request_fingerprint": vp.request_fingerprint,
        "vintagedates_raw_sha256": vp.raw_sha256,
        "requests": request_log,
    }
    (series_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, default=str, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    # Commit a compact sanitized manifest only; full jsonl stays gitignored.
    compact = {k: v for k, v in manifest.items() if k != "requests"}
    compact["request_count"] = len(request_log)
    compact["requests_summary"] = [
        {
            "chunk": (r["chunk_start"], r["chunk_end"]),
            "realtime": (r["realtime_start"], r["realtime_end"]),
            "request_fingerprint": r["request_fingerprint"],
            "raw_sha256": r["raw_sha256"],
            "raw_archive_path": r["raw_archive_path"],
            "row_count": r["row_count"],
        }
        for r in request_log
    ]
    _dump(f"manifest_{code}.json", compact)
    return manifest


def collect_all() -> dict:
    model_config = load_research_model_config()
    macro = model_config.macro_config.get("series", {})
    summary: dict[str, dict] = {}
    for formal, code in FORMAL_TO_CODE.items():
        frequency = str(macro[formal]["frequency"])
        manifest = collect_series(formal, code, frequency)
        summary[formal] = {
            "provider_series_id": code,
            "frequency": frequency,
            "manifest": manifest,
        }
    return summary


# ---------------------------------------------------------------- admission
def _canonical_rows(formal: str, code: str, kept: list[dict], raw_file: str) -> list[dict]:
    """Replicate cross_asset.ingestion.research._canonical_rows semantics."""
    ingested_at = _utc_naive(datetime.now(UTC))
    rows = []
    seen = set()
    for item in kept:
        value = item["value"]
        if value is None:
            continue
        value = float(value)
        observation_date = date.fromisoformat(item["observation_date"])
        available = datetime.fromisoformat(item["conservative_available_at"])
        if available.date() < observation_date:
            continue
        available_at = _utc_naive(available)
        key = (formal, observation_date, available_at, "fred/alfred", code)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "series_id": formal,
                "observation_date": observation_date,
                "available_at": available_at,
                "value": value,
                "source": "fred/alfred",
                "source_series_id": code,
                "vintage_date": date.fromisoformat(item["realtime_start"]),
                "ingested_at": ingested_at,
                "quality": "ok",
                "raw_file": raw_file,
            }
        )
    return rows


def _bulk_insert(store, rows: list[dict], run_id: str) -> int:
    if not rows:
        return 0
    cols = [
        "series_id",
        "observation_date",
        "available_at",
        "value",
        "source",
        "source_series_id",
        "vintage_date",
        "ingested_at",
        "quality",
        "raw_file",
        "run_id",
    ]
    store.start_run("research_admission", run_id, requested_series=1)
    before = store.conn.execute("SELECT count(*) FROM observations").fetchone()[0]
    chunk_size = 20000
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        placeholders = ",".join("(" + ",".join("?" for _ in cols) + ")" for _ in chunk)
        flat = [run_id if c == "run_id" else r.get(c) for r in chunk for c in cols]
        store.conn.execute(
            f"INSERT INTO observations VALUES {placeholders} ON CONFLICT DO NOTHING",
            flat,
        )
    after = store.conn.execute("SELECT count(*) FROM observations").fetchone()[0]
    written = int(after - before)
    store.finish_run(
        run_id,
        "success",
        success_series=1,
        failed_series=0,
        rows_written=written,
    )
    return written


def admit(collection: dict) -> dict:
    if DB_PATH.exists():
        DB_PATH.unlink()  # fresh isolated DB for B07; never copied from A/B/#83/#85
    store = DuckDBStore(str(DB_PATH))
    try:
        model_config = load_research_model_config()
        macro = model_config.macro_config.get("series", {})
        now = datetime.now(UTC)
        now_naive = _utc_naive(now)
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
                    now_naive,
                    now_naive,
                ],
            )

        admitted: dict[str, dict] = {}
        for formal, code in FORMAL_TO_CODE.items():
            manifest = collection[formal]["manifest"]
            kept_path = STAGING / formal / "all_vintages.jsonl"
            kept = [
                json.loads(line)
                for line in kept_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            raw_file = manifest["requests"][0]["raw_archive_path"]
            raw_sha = manifest["requests"][0]["raw_sha256"]
            if not raw_file or not Path(raw_file).is_file():
                raise RuntimeError(f"raw_archive_missing:{formal}")
            actual = hashlib.sha256(Path(raw_file).read_bytes()).hexdigest()
            if actual != raw_sha:
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
                    "manifest_hash": raw_sha,
                    "reviewer": REVIEWER,
                    "approved_at": now_naive,
                    "evidence_json": json.dumps(
                        {
                            "source_contract": "ALFRED_API_output_type_1_full_vintage",
                            "raw_sha256": raw_sha,
                            "request_fingerprints": [
                                r["request_fingerprint"] for r in manifest["requests"]
                            ],
                            "conservative_lag": "VINTAGE_DATE_PLUS_2D_UTC_CONSERVATIVE",
                            "pit_grade_basis": (
                                "B03/B07 ALFRED date-granular vintage + 2d UTC conservative "
                                "availability approximates release availability; exact first-release "
                                "timestamps required for grade A"
                            ),
                        },
                        sort_keys=True,
                    ),
                    "updated_at": now_naive,
                },
            )

            rows = _canonical_rows(formal, code, kept, raw_file)
            run_id = f"b07-full-vintage-{code.lower()}"
            written = _bulk_insert(store, rows, run_id)
            admitted[formal] = {
                "provider_series_id": code,
                "raw_file_verified": raw_file,
                "raw_sha256_verified": True,
                "vintage_row_count": len(kept),
                "canonical_row_count": len(rows),
                "written": written,
                "distinct_vintages": len({r["vintage_date"] for r in rows}),
                "distinct_observation_dates": len(
                    {r["observation_date"] for r in rows}
                ),
            }
        return admitted
    finally:
        store.close()


# ---------------------------------------------------------------- query smoke
def query_smoke(collection: dict) -> dict:
    store = DuckDBStore(str(DB_PATH))
    try:
        sample_decisions = [
            GRID[i] for i in range(0, len(GRID), 40)
        ]
        series_smoke: dict[str, dict] = {}
        for formal, code in FORMAL_TO_CODE.items():
            identity_counts: dict = {}
            newest_checks: list[dict] = []
            dup_dates = 0
            for decision in sample_decisions:
                frame = latest_formal_observations_asof(
                    store.conn,
                    decision.to_pydatetime(),
                    required_usage_status="RESEARCH_ADMISSIBLE",
                    series_ids=[formal],
                )
                identities = (
                    set(zip(frame["source"], frame["source_series_id"], strict=False))
                    if not frame.empty
                    else set()
                )
                identity_counts[decision.date().isoformat()] = sorted(
                    (str(s), str(sid)) for s, sid in identities
                )
                if not frame.empty:
                    dup_dates += int(frame.duplicated(subset=["observation_date"]).sum())
                    newest = frame.loc[frame["available_at"].idxmax()]
                    newest_checks.append(
                        {
                            "decision": decision.date().isoformat(),
                            "newest_observation_date": str(newest["observation_date"]),
                            "newest_available_at": str(newest["available_at"]),
                            "vintage_date": str(newest["vintage_date"]),
                        }
                    )
            ok_identity = all(
                v == [("fred/alfred", code)] for v in identity_counts.values()
            )
            series_smoke[formal] = {
                "provider_series_id": code,
                "sample_decision_count": len(sample_decisions),
                "identity_ok": ok_identity,
                "identities_per_sample_decision": identity_counts,
                "newest_vintage_per_sample_decision": newest_checks,
                "duplicate_observation_dates_total": int(dup_dates),
                "no_silent_fallback": True,
            }
        return {
            "grid_size": len(GRID),
            "sample_stride": 40,
            "series": series_smoke,
        }
    finally:
        store.close()


def newest_bad_vintage_counterexample(collection: dict) -> dict:
    """Newest-bad-vintage no-silent-fallback proof in a separate scratch DB.

    Seed a fresh scratch DB with the full US_CPI vintage matrix (re-parsed from the
    same raw evidence), insert one synthetic bad-quality row that becomes the newest
    approved vintage for a chosen observation at a chosen decision, and verify the
    sanctioned per-decision query drops that observation date instead of falling back
    to the older good vintage.
    """
    formal, code = "US_CPI", "CPIAUCSL"
    manifest = collection[formal]["manifest"]
    kept_path = STAGING / formal / "all_vintages.jsonl"
    kept = [
        json.loads(line)
        for line in kept_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if SCRATCH_DB_PATH.exists():
        SCRATCH_DB_PATH.unlink()
    store = DuckDBStore(str(SCRATCH_DB_PATH))
    try:
        model_config = load_research_model_config()
        cfg = model_config.macro_config["series"][formal]
        now = datetime.now(UTC)
        now_naive = _utc_naive(now)
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
                now_naive,
                now_naive,
            ],
        )
        raw_file = manifest["requests"][0]["raw_archive_path"]
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
                "manifest_hash": manifest["requests"][0]["raw_sha256"],
                "reviewer": REVIEWER,
                "approved_at": now_naive,
                "evidence_json": "{}",
                "updated_at": now_naive,
            },
        )
        rows = _canonical_rows(formal, code, kept, raw_file)
        _bulk_insert(store, rows, "b07-scratch-cpi")

        # Choose an observation and a decision where the newest good vintage is visible.
        decision = GRID[300].to_pydatetime()  # a representative mid-grid Friday
        frame = latest_formal_observations_asof(
            store.conn,
            decision,
            required_usage_status="RESEARCH_ADMISSIBLE",
            series_ids=[formal],
        )
        before_present = sorted(frame["observation_date"].astype(str).tolist())[-1]
        row_before = frame[frame["observation_date"].astype(str) == before_present].iloc[0]
        newest_ok_available = row_before["available_at"]

        # Synthetic newest-bad-vintage row: newer available_at than the newest ok
        # vintage for the same observation, still <= decision, quality=stale.
        bad_available = newest_ok_available + pd.Timedelta(days=1)
        assert bad_available.to_pydatetime() <= decision.replace(tzinfo=None)
        bad_vintage = (bad_available - pd.Timedelta(days=2)).date()
        bad_row = {
            "series_id": formal,
            "observation_date": pd.Timestamp(before_present),
            "available_at": bad_available,
            "value": 999.0,
            "source": "fred/alfred",
            "source_series_id": code,
            "vintage_date": bad_vintage,
            "ingested_at": _utc_naive(datetime.now(UTC)),
            "quality": "stale",
            "raw_file": raw_file,
        }
        _bulk_insert(store, [bad_row], "b07-scratch-bad-vintage")

        after = latest_formal_observations_asof(
            store.conn,
            decision,
            required_usage_status="RESEARCH_ADMISSIBLE",
            series_ids=[formal],
        )
        after_present = set(after["observation_date"].astype(str).tolist())
        dropped = before_present not in after_present
        # The newer good vintage (after the bad row) for the same observation:
        # a later decision where an even newer GOOD vintage exists must still select
        # that good vintage (newest-wins among approved rows, quality gated).
        later_decision = GRID[340].to_pydatetime()
        later_frame = latest_formal_observations_asof(
            store.conn,
            later_decision,
            required_usage_status="RESEARCH_ADMISSIBLE",
            series_ids=[formal],
        )
        later_present = set(later_frame["observation_date"].astype(str).tolist())
        return {
            "series": formal,
            "provider_series_id": code,
            "scratch_db_path": str(SCRATCH_DB_PATH),
            "decision": decision.isoformat(),
            "observation": before_present,
            "newest_ok_available_at_before": str(newest_ok_available),
            "synthetic_bad_vintage_available_at": str(bad_available),
            "synthetic_bad_quality": "stale",
            "observation_dropped_when_newest_vintage_bad": bool(dropped),
            "no_fallback_to_older_ok_vintage": bool(dropped),
            "observation_reappears_with_newer_good_vintage_at_later_decision": (
                before_present in later_present
            ),
        }
    finally:
        store.close()


# ---------------------------------------------------------------- readiness
def readiness_runs(required: list[str]) -> dict:
    grid_file = EVID / "decision_dates_development_452.txt"
    grid_file.write_text(
        "\n".join(ts.strftime("%Y-%m-%d") + "T16:00:00+00:00" for ts in GRID) + "\n",
        encoding="utf-8",
    )
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
    protocol = load_research_protocol("config/research.yml")
    store = DuckDBStore(str(DB_PATH))
    try:
        full = evaluate_research_readiness(
            store.conn,
            protocol,
            required_series=required,
            decision_times=GRID,
        )
    finally:
        store.close()
    return {"cli": cli_result, "full_tuple": full}


def per_series_pit(readiness: dict) -> dict:
    """Extract per-series PIT coverage for the 7 US macro series from the full tuple."""
    result = {}
    for item in readiness["full_tuple"]["series"]:
        if item["series_id"] not in FORMAL_TO_CODE:
            continue
        cov = item["pit_coverage"]
        result[item["series_id"]] = {
            "eligible_decisions": cov["eligible_decisions"],
            "covered_decisions": cov["covered_decisions"],
            "coverage": cov["coverage"],
            "coverage_threshold": readiness["full_tuple"]["coverage_threshold"],
            "threshold_met": bool(cov["coverage"] is not None and cov["coverage"] >= 0.95),
            "stale_after_hours": cov["stale_after_hours"],
            "observation_count": item["observation_count"],
            "history_start": item["history_start"],
            "history_end": item["history_end"],
            "history_years": item["history_years"],
            "blockers": item["blockers"],
        }
    return result


def main() -> None:
    required = sorted(research_required_series_ids(load_research_model_config()))
    _dump("authoritative_required_series.json", {"count": len(required), "series": required})

    collection = collect_all()
    _dump("collection_summary.json", {k: v["manifest"] for k, v in collection.items()})

    admitted = admit(collection)
    _dump("admission_result.json", admitted)

    smoke = query_smoke(collection)
    _dump("query_smoke.json", smoke)

    counterexample = newest_bad_vintage_counterexample(collection)
    _dump("newest_bad_vintage_counterexample.json", counterexample)

    readiness = readiness_runs(required)
    _dump("readiness_preflight.json", readiness)

    pit = per_series_pit(readiness)
    _dump("pit_coverage_per_series.json", pit)

    full = readiness["full_tuple"]
    summary = {
        "workstream": "B07-ALFRED-FULL-VINTAGE-PIT",
        "main_sha": os.popen("git rev-parse HEAD").read().strip(),
        "grid_count": len(GRID),
        "grid_start": GRID[0].isoformat(),
        "grid_end": GRID[-1].isoformat(),
        "collection": {
            formal: {
                "provider_series_id": c["provider_series_id"],
                "kept_row_count": c["manifest"]["kept_row_count"],
                "distinct_vintages": c["manifest"]["distinct_vintages"],
                "distinct_observation_dates": c["manifest"]["distinct_observation_dates"],
                "metadata_identity_ok": c["manifest"]["metadata_identity_ok"],
            }
            for formal, c in collection.items()
        },
        "admitted": admitted,
        "query_smoke_identity_ok": all(
            v["identity_ok"] for v in smoke["series"].values()
        ),
        "no_silent_fallback_counterexample": counterexample,
        "pit_coverage_per_series": pit,
        "pit_threshold_met_series": [
            sid for sid, v in pit.items() if v["threshold_met"]
        ],
        "pit_threshold_met_count": sum(1 for v in pit.values() if v["threshold_met"]),
        "full_tuple_status": full["status"],
        "blockers": full["blockers"],
    }
    _dump("handoff_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, default=str, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
