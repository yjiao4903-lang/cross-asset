"""CLI contracts. Implementations are lazy-imported to keep parallel modules optional."""
import atexit
import json

import typer

from .logging import configure_logging
from .settings import get_settings
from .weekly_cli import register_weekly_commands

app = typer.Typer(name="cross-asset", help="Local cross-asset allocation decision engine")
register_weekly_commands(app)

@app.command("validate-data-file")
def validate_data_file(file: str = typer.Argument(...), manifest: str | None = typer.Option(None, "--manifest"), output: str | None = typer.Option(None, "--output")):
    from .ingestion.acceptance import exit_code
    from .ingestion.acceptance import validate_data_file as validate
    result = validate(file, manifest)
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
    if output:
        from pathlib import Path
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)
    raise typer.Exit(exit_code(result))

@app.command("register-data-acceptance")
def register_data_acceptance(result_json: str = typer.Argument(...), database: str | None = typer.Option(None, "--database")):
    """Explicitly persist a validated acceptance result; never registers FAIL."""
    from .settings import get_settings
    from .storage import init_db
    from .storage.acceptance_registry import candidate_registry_record, upsert_data_acceptance
    payload = json.loads(__import__("pathlib").Path(result_json).read_text(encoding="utf-8"))
    record = candidate_registry_record(payload)
    store = init_db(database or get_settings().database_path)
    try:
        saved = upsert_data_acceptance(store, record)
        typer.echo(json.dumps(saved, ensure_ascii=False, default=str, sort_keys=True))
    finally:
        store.close()

@app.command("coverage-report")
def coverage_report(database: str | None = typer.Option(None, "--database"), as_of: str | None = typer.Option(None, "--as-of"), output: str | None = typer.Option(None, "--output")):
    """Emit a read-only PIT-scoped series coverage report."""
    from .reports.coverage import generate_coverage_report
    from .storage import init_db
    db = init_db(database or get_settings().database_path)
    try:
        result = generate_coverage_report(db.conn, as_of=as_of, output=output)
        if output:
            typer.echo(json.dumps(result[1], ensure_ascii=False, default=str, sort_keys=True))
        else:
            typer.echo(json.dumps(result, ensure_ascii=False, default=str, sort_keys=True))
    finally:
        db.close()

@app.command("backup")
def backup(destination: str = typer.Option("artifacts/backups", "--destination")):
    from .operations import create_backup
    typer.echo(f"Backup: {create_backup('.', destination)}")

@app.command("verify-backup")
def verify_backup(path: str = typer.Argument(...)):
    from .operations import verify_backup as verify
    result=verify(path); typer.echo(json.dumps(result, ensure_ascii=False, default=str));
    if not result['valid']: raise typer.Exit(1)

@app.command("shadow-run")
def shadow_run_command():
    from .operations import shadow_run
    typer.echo(json.dumps(shadow_run(), ensure_ascii=False))

@app.command("weekly-shadow-report")
def weekly_shadow_report():
    from .operations.shadow import weekly_shadow_report as generate
    path, report = generate()
    typer.echo(json.dumps({'path': str(path), **report}, ensure_ascii=False, default=str))


def _not_implemented(command: str) -> None:
    typer.echo(f"{command}: interface reserved; implementation is not installed yet.")


@app.callback()
def main(log_level: str | None = typer.Option(None, "--log-level")) -> None:
    configure_logging(log_level or get_settings().cross_asset_log_level)


@app.command("init-db")
def init_db() -> None:
    """Initialize the local database (storage module supplies implementation)."""
    try:
        from .storage import init_db as initialize_database  # type: ignore
    except ImportError:
        _not_implemented("init-db")
        return
    initialize_database(get_settings().database_path)

@app.command("qa-baseline")
def qa_baseline() -> None:
    from .operations.qa_baseline import generate_qa_baseline
    result = generate_qa_baseline()
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))

@app.command("ingest-research-data")
def ingest_research_data_command(input_json: str = typer.Argument(...)) -> None:
    from pathlib import Path

    from .ingestion.research import ingest_research_data
    payload = json.loads(Path(input_json).read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else payload
    policies = payload.get("policies", {}) if isinstance(payload, dict) else {}
    result = ingest_research_data(records, policies=policies)
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["status"] != "ADMISSIBLE":
        raise typer.Exit(1)


@app.command("ingest-production-csv")
def ingest_production_csv_command(
    file: str = typer.Argument(...),
    database: str | None = typer.Option(None, "--database"),
    raw_dir: str | None = typer.Option(None, "--raw-dir"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Validate or import one canonical production CSV."""
    from .ingestion.production_csv import ProductionCSVError, ingest_production_csv

    try:
        result = ingest_production_csv(
            file,
            database=database,
            raw_dir=raw_dir,
            dry_run=dry_run,
        )
    except ProductionCSVError as exc:
        typer.echo(
            json.dumps(
                {"status": "FAIL", "dry_run": dry_run, "file": file, "errors": exc.errors},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    # EMPTY/PARTIAL provider-level outcomes are never reported as plain SUCCESS;
    # a dry-run VALIDation stays a successful exit.
    if str(result.get("status", "FAIL")).upper() not in {"SUCCESS", "VALID"}:
        raise typer.Exit(1)


@app.command("canonicalize-wind-export")
def canonicalize_wind_export_command(
    file: str = typer.Argument(..., help="Wind raw Excel or CSV export."),
    mapping: str = typer.Option(
        "config/wind_canonical_mapping.yml",
        "--mapping",
        help="Approved Wind-to-canonical mapping configuration.",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        help="Canonical production CSV path; omitted for dry-run/stdout-only operation.",
    ),
    report: str | None = typer.Option(
        None,
        "--report",
        help="Conversion report JSON path.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Parse and validate without writing CSV or invoking ingestion/DB.",
    ),
) -> None:
    """Convert an approved Wind raw export to the canonical production CSV contract."""
    import importlib

    try:
        canonicalizer = importlib.import_module("cross_asset.ingestion.wind_canonicalizer")
        convert = canonicalizer.canonicalize_wind_export
        result = convert(
            file,
            mapping=mapping,
            output=output,
            report=report,
            dry_run=dry_run,
        )
    except Exception as exc:
        typer.echo(
            json.dumps(
                {
                    "status": "FAIL",
                    "dry_run": dry_run,
                    "input_file": file,
                    "errors": [{"code": "canonicalization_failed", "message": str(exc)}],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        raise typer.Exit(1) from exc

    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    status = str(result.get("status", "FAIL")).upper() if isinstance(result, dict) else "FAIL"
    if status == "PARTIAL":
        raise typer.Exit(2)
    if status not in {"READY", "VALID", "SUCCESS"}:
        raise typer.Exit(1)

@app.command("data-readiness")
def data_readiness() -> None:
    from .reports.readiness import generate_readiness
    from .storage import init_db
    db = init_db(get_settings().database_path)
    try:
        typer.echo(json.dumps(generate_readiness(db), ensure_ascii=False, sort_keys=True))
    finally:
        db.close()


@app.command("explain-run")
def explain_run_command(run_id: str = typer.Argument(...)) -> None:
    """Explain one persisted experiment from snapshot through allocation."""
    from .storage import explain_run, init_db

    db = init_db(get_settings().database_path)
    try:
        typer.echo(json.dumps(explain_run(db.conn, run_id), ensure_ascii=False, default=str, sort_keys=True))
    finally:
        db.close()


@app.command("research-brief")
def research_brief_command(
    input_json: str = typer.Argument(..., help="Structured research facts JSON."),
    output: str = typer.Option("artifacts/reports/research_brief.md", "--output"),
) -> None:
    """Render a traceable personal research brief for human review."""
    from pathlib import Path

    from .reports.research_brief import generate_research_brief

    payload = json.loads(Path(input_json).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise typer.BadParameter("research brief input must be a JSON object")
    path = generate_research_brief(output=output, **payload)
    typer.echo(json.dumps({"status": "SUCCESS", "output": str(path)}, ensure_ascii=False))


@app.command("current-state")
def current_state_command(
    run_tests: bool = typer.Option(False, "--run-tests"),
    output: str = typer.Option("artifacts/current_state/generated", "--output"),
) -> None:
    """Generate canonical Git/DB/run/test state from live project evidence."""
    from .reports.current_state import generate_current_state
    from .storage import init_db

    db = init_db(get_settings().database_path)
    try:
        result = generate_current_state(db, output=output, run_tests=run_tests)
        typer.echo(json.dumps(result, ensure_ascii=False, default=str, sort_keys=True))
    finally:
        db.close()


@app.command("run-wind-evidence-shadow")
def run_wind_evidence_shadow_command(
    as_of: str | None = typer.Option(None, "--as-of"),
    output: str = typer.Option("artifacts/wind_import/WIND_ENGINEERING_SHADOW.json", "--output"),
) -> None:
    """Run feature engines on Wind staging with trading and research disabled."""
    from datetime import datetime

    from .ingestion.evidence_shadow import run_wind_evidence_shadow
    from .storage import init_db

    db = init_db(get_settings().database_path)
    try:
        result = run_wind_evidence_shadow(
            db.conn,
            decision_time=datetime.fromisoformat(as_of) if as_of else None,
            output=output,
        )
        typer.echo(json.dumps(result, ensure_ascii=False, default=str, sort_keys=True))
    finally:
        db.close()


@app.command("run-wind-local-experiment")
def run_wind_local_experiment_command(
    as_of: str | None = typer.Option(None, "--as-of"),
    output: str = typer.Option("artifacts/local_experiment/WIND_LOCAL_EXPERIMENT.json", "--output"),
) -> None:
    """Run the local Wind model loop with broker and order paths disabled."""
    from datetime import datetime

    from .ingestion.evidence_shadow import run_wind_local_experiment
    from .storage import init_db

    db = init_db(get_settings().database_path)
    try:
        result = run_wind_local_experiment(
            db.conn,
            decision_time=datetime.fromisoformat(as_of) if as_of else None,
            output=output,
            store=db,
            persist=True,
            project_root=".",
        )
        typer.echo(json.dumps(result, ensure_ascii=False, default=str, sort_keys=True))
    finally:
        db.close()

@app.command("calendar-readiness")
def calendar_readiness() -> None:
    from .reports.calendar_readiness import generate_calendar_readiness
    typer.echo(json.dumps(generate_calendar_readiness(), ensure_ascii=False, sort_keys=True))

@app.command("research-admission-review")
def research_admission_review() -> None:
    from .reports.research_admission import build_candidates
    result = build_candidates()
    typer.echo(json.dumps({"status": result["status"], "series": [{"series_id": x["series_id"], "status": x["status"], "errors": x["errors"], "blockers": x["blockers"]} for x in result["series"]]}, ensure_ascii=False, sort_keys=True))


@app.command("probe-data")
def probe_data(live: bool = typer.Option(False, "--live", help="Perform opt-in network probes.")) -> None:
    """Probe configured data providers and write a capability report."""
    try:
        from .providers import (  # type: ignore
            FREDProvider,
            IfindProvider,
            ManualProvider,
            TushareProvider,
            WindProvider,
            YahooProvider,
        )
        from .reports.capability import generate_capability_report  # type: ignore
    except ImportError:
        _not_implemented("probe-data")
        return
    settings = get_settings()
    if live:
        from .providers.live import probe_fred, probe_yahoo
        from .reports.live_capability import write_live_capability
        records = [probe_fred(settings.fred_api_key), probe_yahoo()]
        # SDK providers are reported from local facts; no implicit login or scraping.
        for name, module, enabled in (("tushare", "tushare", bool(settings.tushare_token)), ("wind", "WindPy", settings.wind_enabled), ("ifind", "iFinDPy", settings.ifind_enabled)):
            try:
                __import__(module)
                dep = True
            except ImportError:
                dep = False
            records.append({"provider": name, "authenticated": bool(enabled and dep), "reachable": False,
                "historical_query": False, "latest_query": False, "latency_ms": None,
                "earliest_date": None, "latest_date": None, "quota_info_if_available": None,
                "error_type": None if (enabled and dep) else ("MISSING_CREDENTIALS" if not enabled else "MISSING_DEPENDENCY"),
                "safe_error": None if (enabled and dep) else ("credential or token not configured" if not enabled else "SDK not installed"),
                "verified_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()})
        paths = write_live_capability(records)
        typer.echo(f"Live capability report: {paths[0]} / {paths[1]}")
        return
    providers = [
        FREDProvider(api_key=settings.fred_api_key),
        YahooProvider(),
        TushareProvider(token=settings.tushare_token),
        WindProvider(enabled=settings.wind_enabled),
        IfindProvider(enabled=settings.ifind_enabled),
        ManualProvider(),
    ]
    paths = generate_capability_report((provider.probe() for provider in providers), "artifacts")
    typer.echo(f"Capability report: {paths[0]} / {paths[1]}")

@app.command("probe-fred")
def probe_fred(fetch_sample: bool = typer.Option(False, "--fetch-sample"), public_csv: bool = typer.Option(False, "--public-csv"), macro: bool = typer.Option(False, "--macro"), priority: bool = typer.Option(False, "--priority"), alfred_cpi: bool = typer.Option(False, "--alfred-cpi"), alfred_macro: bool = typer.Option(False, "--alfred-macro"), alfred_rates: bool = typer.Option(False, "--alfred-rates"), database: str | None = typer.Option(None, "--database"), raw_dir: str | None = typer.Option(None, "--raw-dir"), output: str | None = typer.Option(None, "--output")):
    """Probe only FRED DGS10/DFII10 metadata without printing credentials."""
    from pathlib import Path

    from .providers.fred import FREDProvider
    if fetch_sample:
        from datetime import UTC, date, datetime

        from .ingestion.raw_archive import ImmutableRawArchive
        from .providers.base import DataRequest
        from .storage import init_db
        settings = get_settings()
        db = init_db(database or settings.database_path)
        try:
            provider = FREDProvider(store=db, raw_archive=ImmutableRawArchive(raw_dir or settings.raw_dir), timeout=20, retries=0, min_interval=1.0)
            if alfred_rates:
                rates_map = {"US_GOV_10Y": "DGS10", "US_REAL_10Y": "DFII10", "EFFR": "EFFR"}
                result = {"status": "PARTIAL", "series": {}}
                failures = set()
                for sid, code in rates_map.items():
                    if len(failures) >= 2:
                        result["series"][sid] = {"source_series_id": code, "status": "BLOCKED", "error": {"code": "stopped_after_controlled_failures"}}
                        continue
                    item = provider.fetch_alfred_cpi_once(series_id=sid, source_series_id=code)
                    result["series"][sid] = item
                    if item.get("status") == "FAILED":
                        failures.add(item.get("error", {}).get("code", "failed"))
                        if len(failures) >= 2:
                            result["status"] = "BLOCKED"
            elif alfred_macro:
                macro_map = {"US_CPI": "CPIAUCSL", "US_CORE_PCE": "PCEPILFE", "US_UNEMPLOYMENT": "UNRATE", "US_INITIAL_CLAIMS": "ICSA", "US_INDUSTRIAL_PRODUCTION": "INDPRO"}
                result = {"status": "PARTIAL", "series": {}}
                failures = set()
                for sid, code in macro_map.items():
                    if len(failures) >= 2:
                        result["series"][sid] = {"source_series_id": code, "status": "BLOCKED", "error": {"code": "stopped_after_controlled_failures"}}
                        continue
                    item = provider.fetch_alfred_cpi_once(series_id=sid, source_series_id=code)
                    result["series"][sid] = item
                    if item.get("status") == "FAILED":
                        failures.add(item.get("error", {}).get("code", "failed"))
                        if len(failures) >= 2:
                            result["status"] = "BLOCKED"
            elif alfred_cpi:
                result = provider.fetch_alfred_cpi_once()
            else:
                series_ids = (["US_CPI", "US_CORE_PCE", "US_UNEMPLOYMENT", "US_INITIAL_CLAIMS", "US_INDUSTRIAL_PRODUCTION"] if macro else list(provider.PRIORITY_SERIES) if priority else ["US_GOV_10Y", "US_REAL_10Y"])
                request = DataRequest(series_ids=series_ids, start=date(2024, 1, 1), end=datetime.now(UTC).date())
                result = provider.fetch_public_csv_sample(request) if public_csv else provider.fetch_sample(request)
        finally:
            db.close()
    else:
        result = FREDProvider().probe().model_dump(mode="json")
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
    if output:
        path = Path(output); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)


@app.command("data-health")
def data_health_report(as_of: str | None = typer.Option(None, "--as-of")):
    from datetime import datetime

    from .reports.data_health import generate_data_health_report
    from .storage import init_db

    settings = get_settings()
    db = init_db(settings.database_path)
    when = datetime.fromisoformat(as_of) if as_of else None
    paths = generate_data_health_report(db.conn, when, offline_fixture=True)
    typer.echo(f"Data health report (offline fixture): {paths[0]} / {paths[1]}")


@app.command("run-live")
def run_live(retry: bool = typer.Option(False, "--retry", help="Explicitly rerun with a new idempotency key.")) -> None:
    """Run a safe live vertical slice; unavailable inputs never become fixtures."""
    import json
    from datetime import UTC, datetime
    from uuid import uuid4

    from .domain.models import DataRequest
    from .ingestion.raw_archive import ImmutableRawArchive
    from .live.locks import RunLock
    from .providers.live import probe_fred, probe_yahoo, yahoo_fetch
    from .storage import ProvenanceStore, code_version, config_hash, init_db

    settings = get_settings(); today = datetime.now(UTC).date().isoformat()
    lock = RunLock(settings.cross_asset_data_dir / '.run.lock', f'LIVE_DAILY_{today.replace("-","")}')
    lock.acquire()
    atexit.register(lock.release)
    out = __import__("pathlib").Path("artifacts/live") / today; out.mkdir(parents=True, exist_ok=True)
    run_key = f"LIVE_DAILY_{today.replace('-', '')}"
    marker = out / "run_manifest.json"
    if marker.exists() and not retry:
        typer.echo(f"Live run already exists (safe no-op): {run_key}"); return
    if retry:
        run_key = f"{run_key}_RETRY_{datetime.now(UTC).strftime('%H%M%S')}"
        marker = out / f"run_manifest_{run_key.lower()}.json"
    series = ["US_EQ", "GOLD", "COPPER", "OIL", "DXY", "USDCNH", "HK_EQ", "US_GOV_10Y"]
    capabilities = [probe_fred(settings.fred_api_key), probe_yahoo()]
    (out / "capability.json").write_text(json.dumps({"providers": capabilities}, indent=2), encoding="utf-8")
    store = init_db(settings.database_path); archive = ImmutableRawArchive(settings.raw_dir)
    now = datetime.now(UTC).replace(tzinfo=None)
    request = DataRequest(series_ids=series)
    fetch_status = "BLOCKED_LIVE"; rows = []
    try:
        rows = yahoo_fetch(request, timeout=2)
        fetch_status = "LIVE" if rows else "BLOCKED_LIVE"
    except Exception:  # noqa: BLE001 - provider failures are converted to degraded status
        fetch_status = "BLOCKED_LIVE"
    if rows:
        from .ingestion.normalization import normalize_observation
        normalized = [normalize_observation(r).model_dump(mode="json") for r in rows]
        raw = archive.write("yahoo", "observations", normalized)
        for row in normalized: row["raw_file"] = raw
        written = store.insert_observations(normalized, run_id=run_key)
    else: written = 0
    for sid_name in series:
        store.record_provider_attempt({"attempt_id": str(uuid4()), "provider": "yahoo", "series_id": sid_name,
            "started_at": now,
            "finished_at": datetime.now(UTC).replace(tzinfo=None), "status": "SUCCESS" if any(r["series_id"] == sid_name for r in rows) else "BLOCKED_LIVE",
            "latency_ms": None, "error_message": None if rows else "Yahoo live fetch unavailable"})
    p = ProvenanceStore(store.conn)
    sid = p.create_snapshot(normalized if rows else [], data_cutoff=now)
    cfg_paths = [settings.cross_asset_config_dir / name for name in ("series.yml", "sources.yml", "factors.yml", "allocation.yml")]
    cfg_hash = config_hash([path for path in cfg_paths if path.exists()]) if any(path.exists() for path in cfg_paths) else "unavailable"
    rid = p.start_model_run("live_daily", now, "live_v0.1", cfg_hash, code_version("."), sid, now)
    p.finish_model_run(rid, "success" if rows else "partial", [fetch_status])
    modes = {s: ("LIVE" if any(r["series_id"] == s for r in rows) else "UNAVAILABLE") for s in series}
    payload = {"as_of": today, "source_mode": modes, "status": fetch_status, "series_count": len({r["series_id"] for r in rows}), "rows_written": written}
    for name in ("data_health", "market_state", "macro_state", "style_state", "asset_scores", "allocation"):
        (out / f"{name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (out / "daily.md").write_text(f"# Live Daily Report\n\nStatus: {fetch_status}\n\nSource modes: {modes}\n", encoding="utf-8")
    marker.write_text(json.dumps({"run_key": run_key, "run_id": rid, **payload}, indent=2), encoding="utf-8")
    typer.echo(f"Live run: {fetch_status}; series={payload['series_count']}; artifacts={out}")
    lock.release()


def _as_naive_utc(value):
    """Normalize a timestamp cell from DuckDB/pandas to naive UTC datetime."""
    import pandas as pd

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.to_pydatetime()


def _reserved(name: str):
    def command() -> None:
        _not_implemented(name)

    command.__name__ = name.replace("-", "_")
    return command


@app.command("validate-integration")
def validate_integration_command(
    integration_dir: str = typer.Option(..., "--integration-dir"),
    as_of: str | None = typer.Option(None, "--as-of"),
) -> None:
    """Validate the authoritative Marco Integration Contract v1 bundle."""
    from datetime import date

    from .integration.marco_provider import MarcoProvider

    when = date.fromisoformat(as_of[:10]) if as_of else None
    report = MarcoProvider(integration_dir).validate(at=when)
    typer.echo(
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    if report.exit_code:
        raise typer.Exit(report.exit_code)


@app.command("run-daily")
def run_daily_command(
    macro_source: str = typer.Option("legacy", "--macro-source"),
    integration_dir: str | None = typer.Option(None, "--integration-dir"),
    as_of: str | None = typer.Option(None, "--as-of"),
    database: str | None = typer.Option(None, "--database"),
    calendar_config: str = typer.Option("config/calendars.yml", "--calendar-config"),
    series_calendar_config: str = typer.Option(
        "config/series_calendars.yml", "--series-calendar-config"
    ),
    brief_output: str = typer.Option(
        "artifacts/reports/daily_research_brief.md", "--brief-output",
        help="Write the accompanying human-review brief.",
    ),
) -> None:
    """Run the daily Cross model chain with an explicit macro source.

    Market observations are consumed only through the shared formal selection:
    approved acceptance provenance, formal row quality, PIT availability and
    the market-data cutoff. Any required series that is unapproved, stale,
    unhealthy or calendar-blocked fails closed to DATA_BLOCKED.
    """
    from dataclasses import asdict
    from datetime import date, datetime, time
    from pathlib import Path

    import yaml

    source = macro_source.strip().lower()
    if source == "legacy":
        _not_implemented("run-daily")
        return
    if source != "marco":
        raise typer.BadParameter("--macro-source must be legacy or marco")
    if integration_dir is None:
        raise typer.BadParameter(
            "--integration-dir is required when --macro-source marco"
        )

    from .backtest.replay import FullModelStrategy
    from .engines.freshness import evaluate_freshness
    from .integration.marco_provider import MarcoIntegrationError, MarcoProvider
    from .storage import init_db, latest_formal_observations_asof

    requested_date = date.fromisoformat(as_of[:10]) if as_of else None
    provider = MarcoProvider(integration_dir)
    try:
        bundle = provider.load_bundle(at=requested_date)
    except MarcoIntegrationError as exc:
        report = exc.report or provider.validate(at=requested_date)
        typer.echo(
            json.dumps(
                {
                    "status": "FAIL",
                    "as_of": as_of,
                    "macro_source": "marco",
                    "contract_status": report.status,
                    "asset_scores": {},
                    "allocation": None,
                    "allocation_status": "FAIL",
                    "data_cutoff": None,
                    "warnings": [*report.errors, *report.warnings],
                    "legacy_fallback_used": False,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        raise typer.Exit(1) from exc

    decision_date = requested_date or bundle.manifest.as_of
    decision_time = datetime.combine(decision_date, time.max)

    def write_brief(status, cutoff, warnings, facts=None, computed=None):
        from .reports.research_brief import generate_research_brief

        generate_research_brief(
            output=brief_output,
            as_of=decision_date.isoformat(),
            data_cutoff=cutoff,
            sources=["run-daily:marco"],
            completeness=status,
            limitations=warnings or "未发现结构化限制",
            market_facts=facts or [],
            computed_signals=computed or [],
        )

    settings = get_settings()
    config_dir = Path(settings.cross_asset_config_dir)
    allocation_path = config_dir / "allocation.yml"
    allocation_cfg = yaml.safe_load(
        allocation_path.read_text(encoding="utf-8")
    )
    strategic_weights = dict(allocation_cfg["strategic_weights"])
    assets = list(strategic_weights)
    asset_signal_map = allocation_cfg.get("asset_signal_map", {})
    # Daily and formal research paths must consume the same explicit return
    # contract.  A missing contract is a hard configuration error; silently
    # treating a yield or total-return proxy as a price is economically unsafe.
    from .backtest.returns import AssetReturnSpec

    universe_cfg = yaml.safe_load(
        (config_dir / "research_universe.yml").read_text(encoding="utf-8")
    )
    universe_assets = universe_cfg.get("assets", {})
    return_specs = {
        asset: AssetReturnSpec(
            **{
                key: value
                for key, value in dict(universe_assets.get(asset, {})).items()
                if key != "market"
            }
        )
        for asset in assets
    }
    if any(spec.series_id is None and spec.kind != "cash" for spec in return_specs.values()):
        raise typer.BadParameter("research_universe return contract missing for non-cash asset")
    asset_series_map = {
        asset: asset_signal_map.get(asset, {}).get("trend")
        for asset in assets
    }

    required_series = sorted(
        {
            series_id
            for series_id in asset_series_map.values()
            if series_id is not None
        }
    )

    db = init_db(database or settings.database_path)
    try:
        observations = latest_formal_observations_asof(
            db.conn,
            decision_time,
            required_usage_status="LIVE_VERIFIED",
            series_ids=required_series,
            market_data_cutoff=bundle.manifest.data_cutoff,
        )
        stale_after_hours = {
            row[0]: row[1]
            for row in db.conn.execute(
                "SELECT series_id, stale_after_hours FROM series_catalog "
                "WHERE stale_after_hours IS NOT NULL"
            ).fetchall()
        }
    finally:
        db.close()

    if observations.empty:
        counts = {}
        latest_dates = {}
        latest_available = {}
    else:
        counts = (
            observations.groupby("series_id")["observation_date"]
            .nunique()
            .to_dict()
        )
        latest_dates = {
            series_id: (group["observation_date"].max().date())
            for series_id, group in observations.groupby("series_id")
        }
        latest_available = {
            series_id: (group["available_at"].max())
            for series_id, group in observations.groupby("series_id")
        }

    minimum_market_observations = 22
    blocked: dict[str, str] = {}
    for series_id in required_series:
        count = int(counts.get(series_id, 0))
        if count < minimum_market_observations:
            blocked[series_id] = (
                f"insufficient_approved_observations: {series_id}="
                f"{count}/{minimum_market_observations}"
            )
            continue
        freshness = evaluate_freshness(
            [series_id],
            latest_observation_dates={
                series_id: latest_dates.get(series_id)
            },
            market_data_cutoff=bundle.manifest.data_cutoff,
            calendar_config=calendar_config,
            series_calendar_config=series_calendar_config,
        )[series_id]
        if not freshness.healthy:
            blocked[series_id] = (
                f"freshness_blocked: {series_id}="
                f"{freshness.status}:{freshness.reason}"
            )
            continue
        threshold = stale_after_hours.get(series_id)
        latest_at = latest_available.get(series_id)
        if threshold is not None and latest_at is not None:
            age_hours = (
                decision_time - _as_naive_utc(latest_at)
            ).total_seconds() / 3600.0
            if age_hours > float(threshold):
                blocked[series_id] = (
                    f"stale_observations: {series_id}={age_hours:.1f}h>"
                    f"{float(threshold)}h"
                )

    cross_cutoff = None
    if not observations.empty:
        cross_cutoff = str(observations["observation_date"].max())[:10]

    if blocked:
        warnings = [
            *bundle.report.warnings,
            *(blocked[series_id] for series_id in required_series if series_id in blocked),
        ]
        write_brief(
            "DATA_BLOCKED",
            {"marco": bundle.manifest.data_cutoff.isoformat(), "cross_market": cross_cutoff},
            warnings,
        )
        typer.echo(
            json.dumps(
                {
                    "status": "DATA_BLOCKED",
                    "as_of": decision_date.isoformat(),
                    "macro_source": "marco",
                    "contract_status": bundle.report.status,
                    "signal_status": bundle.report.signal_status,
                    "asset_scores": {},
                    "allocation": None,
                    "allocation_status": "DATA_BLOCKED",
                    "data_cutoff": {
                        "marco": bundle.manifest.data_cutoff.isoformat(),
                        "cross_market": cross_cutoff,
                    },
                    "warnings": warnings,
                    "legacy_fallback_used": False,
                    "brief_output": brief_output,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        raise typer.Exit(1)

    strategy = FullModelStrategy(
        assets,
        strategic_weights=strategic_weights,
        asset_series_map=asset_series_map,
        return_specs=return_specs,
        asset_signal_map=asset_signal_map,
        component_weights=allocation_cfg.get("component_weights"),
        allocation_config=allocation_cfg,
        critical_assets=[
            asset
            for asset, series_id in asset_series_map.items()
            if series_id is not None
        ],
    )
    try:
        # Every required series already passed the formal approval, quality,
        # freshness and history gates above; the verified-healthy state is
        # passed explicitly instead of relying on the strategy default.
        strategy(
            observations,
            decision_time,
            health=True,
            macro_snapshot=bundle.macro_snapshot,
            fundamental_asset_view=bundle.fundamental_asset_view,
            structural_snapshot=bundle.structural_snapshot,
        )
    except (KeyError, TypeError, ValueError) as exc:
        typer.echo(
            json.dumps(
                {
                    "status": "FAIL",
                    "as_of": decision_date.isoformat(),
                    "macro_source": "marco",
                    "contract_status": bundle.report.status,
                    "signal_status": bundle.report.signal_status,
                    "asset_scores": {},
                    "allocation": None,
                    "allocation_status": "FAIL",
                    "data_cutoff": {
                        "marco": bundle.manifest.data_cutoff.isoformat(),
                        "cross_market": cross_cutoff,
                    },
                    "warnings": [*bundle.report.warnings, str(exc)],
                    "legacy_fallback_used": False,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        raise typer.Exit(1) from exc

    state = strategy.last_decision
    allocation = state["allocation"]
    payload = {
        "status": (
            "SUCCESS"
            if allocation.status == "ACTIVE"
            else "DEGRADED"
        ),
        "as_of": decision_date.isoformat(),
        "macro_source": "marco",
        "contract_status": bundle.report.status,
        "signal_status": bundle.report.signal_status,
        "asset_scores": {
            asset: asdict(score)
            for asset, score in state["asset_scores"].items()
        },
        "allocation": dict(allocation.weights),
        "allocation_status": allocation.status,
        "data_cutoff": {
            "marco": bundle.manifest.data_cutoff.isoformat(),
            "cross_market": cross_cutoff,
        },
        "warnings": [
            *bundle.report.warnings,
            *allocation.warnings,
        ],
        "legacy_fallback_used": False,
        "brief_output": brief_output,
    }
    write_brief(
        payload["status"],
        payload["data_cutoff"],
        payload["warnings"],
        [
            {
                "label": str(row.series_id),
                "value": row.value,
                "unit": "raw",
                "period": str(row.observation_date),
                "source": f"{row.source}/{row.source_series_id}; available_at={row.available_at}",
            }
            for row in observations.head(5).itertuples()
        ],
        [
            {
                "label": f"{asset} total score",
                "value": score.score,
                "unit": "score",
                "period": decision_date.isoformat(),
                "source": "run-daily:marco:computed",
            }
            for asset, score in state["asset_scores"].items()
        ],
    )
    typer.echo(
        json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
            sort_keys=True,
            indent=2,
        )
    )


@app.command("report-daily")
def report_daily(as_of: str | None = typer.Option(None, "--as-of")):
    from .reports.daily import generate_daily_report

    p = generate_daily_report(as_of=as_of, offline_fixture=True)
    typer.echo(f"Daily report (offline fixture): {p}")


report_app = typer.Typer(help="Generate reports")
app.add_typer(report_app, name="report")


@report_app.command("daily")
def report_daily_nested(as_of: str | None = typer.Option(None, "--as-of")):
    report_daily(as_of)


def _pipeline_command(name):
    def command(as_of: str | None = typer.Option(None, "--as-of")):
        typer.echo(
            f"{name}: offline pipeline stage; as_of={as_of or 'latest'}; no live provider call"
        )

    command.__name__ = name.replace("-", "_")
    return command


for _name in (
    "build-features",
    "score-market",
    "score-macro",
    "score-style",
    "score-assets",
    "allocate",
    "replay",
):
    app.command(_name)(_pipeline_command(_name))


@app.command("backtest")
def backtest(
    model: str = typer.Option("static", "--model"),
    cost_bps: float = typer.Option(0.0, "--cost-bps"),
):
    from .reports.backtest import generate_backtest_report

    p = generate_backtest_report(
        {}, offline_fixture=True, assumptions=[f"model={model}", f"cost_bps={cost_bps}"]
    )
    typer.echo(f"Backtest report (offline fixture; not real returns): {p}")


@app.command("import-manual")
def import_manual(
    file: str = typer.Argument(...),
    manifest: str = typer.Argument(..., help="Explicit semantic manifest (YAML/JSON). "),
    database: str | None = typer.Option(None, "--database"),
    archive_root: str = typer.Option("data/raw", "--archive-root"),
    sidecar_dir: str | None = typer.Option(None, "--sidecar-dir"),
    worksheet: str | None = typer.Option(None, "--worksheet"),
    source_label: str = typer.Option("manual_export", "--source-label"),
    export_timestamp: str | None = typer.Option(None, "--export-timestamp"),
    policies: str | None = typer.Option(None, "--policies", help="JSON/YAML enabled-policy payload."),
    write: bool = typer.Option(False, "--write", help="Single explicit opt-in for formal DB write; requires an existing acceptance-registry PASS matching the current data contract."),
) -> None:
    """Lane-B: provider-neutral manual file intake -> existing research admission.

    Default (no flags) archives, hashes, validates and stages only - it never
    writes to the DB. ``--write`` is the one unmistakable formal write opt-in:
    without it nothing is persisted, and even with it the write succeeds only
    when an existing acceptance-registry PASS (with matching manifest_hash) and
    an enabled policy are satisfied. It never self-approves.
    """
    from .ingestion.manual_intake import ingest_manual_pack
    from .ingestion.raw_archive import ImmutableRawArchive

    result = ingest_manual_pack(
        source_file=file,
        manifest_path=manifest,
        raw_archive=ImmutableRawArchive(archive_root),
        sidecar_dir=sidecar_dir,
        worksheet=worksheet,
        source_label=source_label,
        export_timestamp=export_timestamp,
        policies_payload=policies,
        database=database,
        write=write,
    )
    typer.echo(json.dumps(result, ensure_ascii=False, default=str, sort_keys=True, indent=2))
    if result.get("status") not in {"STAGED", "ADMITTED"}:
        raise typer.Exit(1)


for _name in (
    "ingest",
    "quality-check",
    "score",
    "ui",
):
    app.command(_name)(_reserved(_name))


if __name__ == "__main__":
    app()
