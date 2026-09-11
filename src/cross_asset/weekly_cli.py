"""PERSONAL_WEEKLY CLI commands registered on the top-level app."""

from __future__ import annotations

import json

import typer


def register_weekly_commands(app: typer.Typer) -> None:
    @app.command("weekly-review")
    def weekly_review_command(
        as_of: str = typer.Option(..., "--as-of", help="Information cutoff date (ISO date)."),
        observations_json: str = typer.Option(..., "--observations-json", help="Observation JSON."),
        output: str = typer.Option("artifacts/reports/weekly_review.md", "--output"),
        prior_snapshot: str | None = typer.Option(None, "--prior-snapshot"),
        snapshot_output: str | None = typer.Option(None, "--snapshot-output"),
        config: str | None = typer.Option(None, "--config"),
        week_end: str | None = typer.Option(None, "--week-end", help="Observation week end date."),
        review_cutoff: str | None = typer.Option(
            None, "--review-cutoff", help="Information cutoff timestamp; never beyond Saturday noon."
        ),
    ) -> None:
        """Build the point-in-time weekly fact table and traceable brief."""
        from .research.weekly_review import run_weekly_review

        try:
            result = run_weekly_review(
                as_of=as_of,
                observations_json=observations_json,
                output=output,
                prior_snapshot=prior_snapshot,
                snapshot_output=snapshot_output,
                config_path=config,
                week_end_date=week_end,
                review_cutoff=review_cutoff,
            )
        except (FileNotFoundError, ValueError) as exc:
            typer.echo(json.dumps({"status": "CONFIG_BLOCKED", "error": str(exc)}, ensure_ascii=False))
            raise typer.Exit(1) from exc
        typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
        status = result.get("status")
        if status == "DATA_BLOCKED":
            raise typer.Exit(2)
        if status not in {"READY", "PARTIAL"}:
            raise typer.Exit(1)

    @app.command("claim-ledger")
    def claim_ledger_command(
        input_json: str = typer.Option(..., "--input", help="Claim/observation JSON fixture."),
        ledger_output: str = typer.Option("artifacts/research/claim_ledger.jsonl", "--ledger-output"),
        now: str = typer.Option(..., "--now", help="Evaluation cutoff timestamp (ISO-8601)."),
    ) -> None:
        """Append claims, evaluate due observations, and persist the JSONL ledger."""
        from dataclasses import asdict
        from pathlib import Path

        from .research.event_ledger import ClaimLedger, EventObservation, ResearchClaim

        payload = json.loads(Path(input_json).read_text(encoding="utf-8"))
        ledger_path = Path(ledger_output)
        ledger = (
            ClaimLedger.from_jsonl(ledger_path.read_text(encoding="utf-8"))
            if ledger_path.exists()
            else ClaimLedger()
        )
        for raw in payload.get("claims", []):
            raw = dict(raw)
            raw["evidence_refs"] = tuple(raw.get("evidence_refs", ()))
            raw["alternative_explanations"] = tuple(raw.get("alternative_explanations", ()))
            ledger = ledger.add(ResearchClaim(**raw))
        observations = {
            key: EventObservation(**dict(value))
            for key, value in payload.get("observations", {}).items()
        }
        evaluations = []
        for claim_id in {item["claim_id"] for item in ledger.records()}:
            if claim_id not in observations:
                continue
            ledger, record = ledger.evaluate(claim_id, now=now, observation=observations[claim_id])
            evaluations.append(asdict(record))
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(ledger.to_jsonl(), encoding="utf-8")
        typer.echo(
            json.dumps(
                {
                    "status": payload.get("status", "DEVELOPMENT_PRIOR"),
                    "ledger_output": str(ledger_path),
                    "claims": ledger.records(),
                    "evaluations": evaluations,
                },
                ensure_ascii=False,
            )
        )

    @app.command("scenario")
    def scenario_command(
        input_json: str = typer.Option(..., "--input", help="Scenario JSON fixture."),
        output: str = typer.Option("artifacts/reports/scenarios.json", "--output"),
    ) -> None:
        """Evaluate transparent assumptions and write JSON plus a readable report."""
        from dataclasses import asdict
        from pathlib import Path

        from .research.scenarios import ScenarioSpec, evaluate_scenario

        payload = json.loads(Path(input_json).read_text(encoding="utf-8"))
        results = []
        for raw in payload.get("scenarios", []):
            raw = dict(raw)
            raw["evidence_refs"] = tuple(raw.get("evidence_refs", ()))
            raw["assumptions"] = tuple(raw.get("assumptions", ()))
            result = asdict(evaluate_scenario(ScenarioSpec(**raw)))
            result["input_contract"] = {
                key: raw.get(key)
                for key in (
                    "asset",
                    "kind",
                    "baseline",
                    "shock",
                    "unit",
                    "duration",
                    "local_price_shock",
                    "fx_shock",
                    "currency",
                    "base_currency",
                    "quote_currency",
                    "quote_convention",
                    "cost_bps",
                    "as_of",
                    "evidence_refs",
                )
            }
            required = ["baseline", "unit", "as_of", "cost_bps", "evidence_refs"]
            if raw.get("kind") == "bond_duration":
                required.extend(["shock", "duration"])
            elif raw.get("kind") == "foreign_asset":
                required.extend(
                    ["local_price_shock", "fx_shock", "base_currency", "quote_currency", "quote_convention"]
                )
            missing = [key for key in required if raw.get(key) in (None, "", [])]
            result["missing_fields"] = missing
            if missing:
                result["status"] = "UNESTIMATED"
                result["reason"] = f"missing:{','.join(missing)}"
            else:
                result["reason"] = None if result["status"] != "UNESTIMATED" else "invalid_input_contract"
            results.append(result)
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {"status": payload.get("status", "DEVELOPMENT_PRIOR"), "results": results},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        report_path = output_path.with_suffix(".md")
        lines = ["# Scenario review", "", "状态：DEVELOPMENT_PRIOR；结果是计算情景，不是预测、概率或期望收益。", ""]
        for result in results:
            contract = result["input_contract"]
            lines.extend(
                [
                    f"## {result['scenario_id']} ({result['status']})",
                    "",
                    f"- value: {result['value']} (net return fraction)",
                    f"- formula: `{result['formula'] or '未计算'}`",
                    (
                        f"- inputs: baseline={contract['baseline']}, shock={contract['shock']}, "
                        f"unit={contract['unit']}, as_of={contract['as_of']}, cost_bps={contract['cost_bps']}"
                    ),
                    (
                        f"- FX convention: {contract['quote_convention'] or '不适用'} "
                        f"({contract['base_currency'] or '-'} / {contract['quote_currency'] or '-'})"
                    ),
                    f"- assumptions: {', '.join(result['assumptions']) or '未提供'}",
                    f"- evidence_refs: {', '.join(result['evidence_refs']) or '未提供'}",
                    f"- reason: {result['reason'] or '已按公式计算'}",
                    "",
                ]
            )
        report_path.write_text("\n".join(lines), encoding="utf-8")
        typer.echo(
            json.dumps(
                {
                    "status": payload.get("status", "DEVELOPMENT_PRIOR"),
                    "output": str(output_path),
                    "report_output": str(report_path),
                    "results": results,
                },
                ensure_ascii=False,
            )
        )
