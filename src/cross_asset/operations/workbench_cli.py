"""Issue #20 CLI surfaces installed over later-registered top-level commands."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import typer


def _echo_run_and_exit(run) -> None:
    typer.echo(json.dumps(run.to_dict(), ensure_ascii=False, default=str))
    raise typer.Exit(run.exit_code)


def shadow_run_command(
    source_mode: str = typer.Option("SIMULATED", "--source-mode"),
    database: str | None = typer.Option(None, "--database"),
    output_root: str = typer.Option("artifacts/shadow", "--output-root"),
    workbench_root: str = typer.Option("artifacts/workbench", "--workbench-root"),
    as_of: str | None = typer.Option(None, "--as-of"),
) -> None:
    """Run a shadow loop. Missing store/inputs fail closed; never KeyError.

    LIVE is not invented from an empty fetcher. FIXTURE/SIMULATED never seed
    formal previous-valid allocation state.
    """
    from .workbench_run import (
        blocked_run,
        from_pipeline_payload,
        persist_and_maybe_record,
        persist_run,
    )

    mode = source_mode.strip().upper()
    if mode not in {"LIVE", "FIXTURE", "SIMULATED"}:
        raise typer.BadParameter("--source-mode must be LIVE, FIXTURE, or SIMULATED")
    if database is None:
        run = blocked_run(
            run_kind="shadow",
            source_mode=mode,
            blockers=["store_required"],
            status="DATA_BLOCKED",
            config_identity="shadow-run",
        )
        if mode == "LIVE":
            from .workbench_run import apply_frozen_from_previous_valid

            apply_frozen_from_previous_valid(run, workbench_root, reason="store_required")
        persist_run(run, workbench_root)
        _echo_run_and_exit(run)
    if mode == "LIVE":
        from .workbench_run import apply_frozen_from_previous_valid

        run = blocked_run(
            run_kind="shadow",
            source_mode="LIVE",
            blockers=["live_fetcher_not_configured"],
            status="DATA_BLOCKED",
            config_identity="shadow-run",
        )
        apply_frozen_from_previous_valid(run, workbench_root, reason="live_fetcher_not_configured")
        persist_run(run, workbench_root)
        _echo_run_and_exit(run)

    from ..storage import init_db
    from . import shadow_run

    store = init_db(database)
    try:
        payload = shadow_run(
            store=store,
            output_root=output_root,
            source_mode=mode,
            as_of=date.fromisoformat(as_of[:10]) if as_of else datetime.now(UTC).date(),
            fetcher=lambda _series: [],
        )
    except Exception as exc:  # noqa: BLE001 - CLI must not leak raw KeyError
        run = blocked_run(
            run_kind="shadow",
            source_mode=mode,
            blockers=[f"shadow_failed:{type(exc).__name__}"],
            status="FAILED",
            config_identity="shadow-run",
        )
        persist_run(run, workbench_root)
        _echo_run_and_exit(run)
    finally:
        store.close()

    run = from_pipeline_payload(payload, run_kind="shadow", source_mode=mode)
    if not payload.get("series_count"):
        run.status = "DATA_BLOCKED"
        run.blockers = list(run.blockers) + ["empty_fetcher_or_no_rows"]
    persist_and_maybe_record(run, workbench_root)
    typer.echo(json.dumps({**payload, "workbench": run.to_dict()}, ensure_ascii=False, default=str))
    raise typer.Exit(run.exit_code)


def explain_run_command(
    run_id: str = typer.Argument(...),
    workbench_root: str = typer.Option("artifacts/workbench", "--workbench-root"),
) -> None:
    """Explain one persisted workbench run, else a DB experiment run."""
    from ..reports.workbench_trace import explain_workbench_run
    from ..settings import get_settings
    from .workbench_run import load_run

    try:
        run = load_run(run_id, workbench_root)
    except FileNotFoundError:
        run = None
    if run is not None:
        typer.echo(
            json.dumps(explain_workbench_run(run), ensure_ascii=False, default=str, sort_keys=True)
        )
        if run.status in {"FAILED", "DATA_BLOCKED"}:
            raise typer.Exit(run.exit_code)
        return
    from ..storage import explain_run, init_db

    db = init_db(get_settings().database_path)
    try:
        typer.echo(
            json.dumps(explain_run(db.conn, run_id), ensure_ascii=False, default=str, sort_keys=True)
        )
    except KeyError as exc:
        typer.echo(
            json.dumps(
                {"status": "FAILED", "run_id": run_id, "blockers": ["run_not_found"]},
                ensure_ascii=False,
            )
        )
        raise typer.Exit(1) from exc
    finally:
        db.close()


def data_health_command(
    as_of: str | None = typer.Option(None, "--as-of"),
    run_id: str | None = typer.Option(None, "--run-id"),
    workbench_root: str = typer.Option("artifacts/workbench", "--workbench-root"),
    output: str = typer.Option("artifacts/reports/data_health_run.json", "--output"),
) -> None:
    """Data-health for one persisted run, else FIXTURE_ONLY offline research."""
    if run_id:
        from ..reports.workbench_trace import data_health_from_run
        from .workbench_run import load_run

        try:
            run = load_run(run_id, workbench_root)
        except FileNotFoundError as exc:
            typer.echo(
                json.dumps(
                    {"status": "FAILED", "run_id": run_id, "blockers": ["run_not_found"]},
                    ensure_ascii=False,
                )
            )
            raise typer.Exit(1) from exc
        payload = data_health_from_run(run, output)
        typer.echo(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
        if run.status in {"FAILED", "DATA_BLOCKED"}:
            raise typer.Exit(run.exit_code)
        return
    from datetime import datetime as dt

    from ..reports.data_health import generate_data_health_report
    from ..settings import get_settings
    from ..storage import init_db

    settings = get_settings()
    db = init_db(settings.database_path)
    when = dt.fromisoformat(as_of) if as_of else None
    paths = generate_data_health_report(db.conn, when, offline_fixture=True)
    typer.echo(f"Data health report (offline fixture): {paths[0]} / {paths[1]}")


def report_daily_command(
    as_of: str | None = typer.Option(None, "--as-of"),
    run_id: str | None = typer.Option(None, "--run-id"),
    workbench_root: str = typer.Option("artifacts/workbench", "--workbench-root"),
    output: str = typer.Option("artifacts/reports/daily.md", "--output"),
) -> None:
    """Daily report for one persisted run, else FIXTURE_ONLY offline research."""
    if run_id:
        from ..reports.workbench_trace import daily_report_from_run
        from .workbench_run import load_run

        try:
            run = load_run(run_id, workbench_root)
        except FileNotFoundError as exc:
            typer.echo(
                json.dumps(
                    {"status": "FAILED", "run_id": run_id, "blockers": ["run_not_found"]},
                    ensure_ascii=False,
                )
            )
            raise typer.Exit(1) from exc
        path = daily_report_from_run(run, output)
        typer.echo(
            json.dumps(
                {
                    "status": run.status,
                    "run_id": run.run_id,
                    "source_mode": run.source_mode,
                    "output": str(path),
                },
                ensure_ascii=False,
            )
        )
        if run.status in {"FAILED", "DATA_BLOCKED"}:
            raise typer.Exit(run.exit_code)
        return
    from ..reports.daily import generate_daily_report

    path = generate_daily_report(as_of=as_of, offline_fixture=True)
    typer.echo(f"Daily report (offline fixture): {path}")
