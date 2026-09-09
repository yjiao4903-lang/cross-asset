"""Optional claim/scenario annex for the weekly brief.

The annex records human claims and transparent shock maths. It never
changes weekly stance, strategic weights, or trade authorization.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cross_asset.research.event_ledger import (
    ClaimLedger,
    EventObservation,
    ResearchClaim,
)
from cross_asset.research.scenarios import ScenarioSpec, evaluate_scenario


def _load(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {"status": "MISSING_INPUT"}
    raw = Path(path)
    if not raw.exists():
        return {"status": "MISSING_INPUT", "path": str(raw)}
    payload = json.loads(raw.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"status": "INVALID_INPUT"}


def _claim_kwargs(raw: dict[str, Any]) -> dict[str, Any]:
    item = dict(raw)
    item["evidence_refs"] = tuple(item.get("evidence_refs") or ())
    item["alternative_explanations"] = tuple(
        item.get("alternative_explanations") or ()
    )
    return item


def evaluate_claims_payload(
    payload: dict[str, Any],
    *,
    now: str,
) -> dict[str, Any]:
    if payload.get("status") == "MISSING_INPUT":
        return {"status": "SKIPPED", "claims": [], "evaluations": []}
    ledger = ClaimLedger()
    for raw in payload.get("claims") or []:
        ledger = ledger.add(ResearchClaim(**_claim_kwargs(raw)))
    observations = {
        key: EventObservation(**dict(value))
        for key, value in (payload.get("observations") or {}).items()
    }
    evaluations = []
    for claim_id in {item["claim_id"] for item in ledger.records()}:
        observation = observations.get(claim_id)
        ledger, record = ledger.evaluate(claim_id, now=now, observation=observation)
        evaluations.append(asdict(record))
    return {
        "status": payload.get("status", "DEVELOPMENT_PRIOR"),
        "claims": ledger.records(),
        "evaluations": evaluations,
    }


def evaluate_scenarios_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") == "MISSING_INPUT":
        return {"status": "SKIPPED", "results": []}
    results = []
    for raw in payload.get("scenarios") or []:
        item = dict(raw)
        item["evidence_refs"] = tuple(item.get("evidence_refs") or ())
        item["assumptions"] = tuple(item.get("assumptions") or ())
        evaluated = asdict(evaluate_scenario(ScenarioSpec(**item)))
        required = ["baseline", "unit", "as_of", "cost_bps", "evidence_refs"]
        if item.get("kind") == "bond_duration":
            required.extend(["shock", "duration"])
        elif item.get("kind") == "foreign_asset":
            required.extend(
                [
                    "local_price_shock",
                    "fx_shock",
                    "base_currency",
                    "quote_currency",
                    "quote_convention",
                ]
            )
        missing = [key for key in required if item.get(key) in (None, "", [])]
        evaluated["missing_fields"] = missing
        if missing:
            evaluated["reason"] = f"missing:{','.join(missing)}"
        elif evaluated["status"] == "UNESTIMATED":
            evaluated["reason"] = "invalid_input_contract"
        else:
            evaluated["reason"] = "formula"
        results.append(evaluated)
    return {
        "status": payload.get("status", "DEVELOPMENT_PRIOR"),
        "results": results,
    }


def render_annex_markdown(
    claims: dict[str, Any],
    scenarios: dict[str, Any],
) -> str:
    lines = [
        "",
        "## 观点账本与情景附件",
        "",
        "本附件只记录观点与冲击计算，不改变本周立场，也不构成交易授权。",
        "",
    ]
    if claims.get("status") == "SKIPPED":
        lines.append("- 未提供观点账本。")
    else:
        rows = claims.get("evaluations") or []
        if not rows:
            lines.append("- 观点已登记，但本周没有可评价观测。")
        for row in rows:
            lines.append(
                f"- 观点 `{row['claim_id']}` r{row['claim_revision']}："
                f"{row['status']} @ {row['evaluated_at']}"
            )
    lines.append("")
    if scenarios.get("status") == "SKIPPED":
        lines.append("- 未提供情景计算。")
    else:
        for row in scenarios.get("results") or []:
            value = row.get("value")
            reason = row.get("reason") or "未计算"
            lines.append(
                f"- 情景 `{row['scenario_id']}`：{row['status']} "
                f"value={value} reason={reason}"
            )
    return "\n".join(lines) + "\n"


def build_weekly_annex(
    *,
    now: str,
    claims_json: str | Path | None = None,
    scenarios_json: str | Path | None = None,
) -> dict[str, Any]:
    claims = evaluate_claims_payload(_load(claims_json), now=now)
    scenarios = evaluate_scenarios_payload(_load(scenarios_json))
    return {
        "claims": claims,
        "scenarios": scenarios,
        "markdown": render_annex_markdown(claims, scenarios),
    }


__all__ = [
    "build_weekly_annex",
    "evaluate_claims_payload",
    "evaluate_scenarios_payload",
    "render_annex_markdown",
]
