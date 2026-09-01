"""CLI contracts. Implementations are lazy-imported to keep parallel modules optional."""
import atexit
import json

import typer

from .logging import configure_logging
from .settings import get_settings

app = typer.Typer(name="cross-asset", help="Local cross-asset allocation decision engine")

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


def _reserved(name: str):
    def command() -> None:
        _not_implemented(name)

    command.__name__ = name.replace("-", "_")
    return command


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


for _name in (
    "ingest",
    "import-manual",
    "quality-check",
    "score",
    "run-daily",
    "ui",
):
    app.command(_name)(_reserved(_name))


if __name__ == "__main__":
    app()
