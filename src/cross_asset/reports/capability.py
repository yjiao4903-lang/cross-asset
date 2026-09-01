"""Offline-safe capability report writer (JSON + Markdown)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from cross_asset.providers.base import ProviderCapability

_SECRET = re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^,;\s]+")


def _safe(value: Any) -> Any:
    if isinstance(value, str):
        return _SECRET.sub(lambda m: m.group(1) + "=<redacted>", value)
    if isinstance(value, dict):
        return {
            k: _safe(v)
            for k, v in value.items()
            if str(k).lower() not in {"api_key", "token", "secret", "password"}
        }
    if isinstance(value, list):
        return [_safe(v) for v in value]
    return value


def generate_capability_report(
    capabilities: Iterable[ProviderCapability], output_dir: str | Path = "artifacts"
) -> tuple[Path, Path]:
    caps = [_safe(c.to_dict() if hasattr(c, "to_dict") else c) for c in capabilities]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    jp = out / "data_capability_report.json"
    mp = out / "data_capability_report.md"
    jp.write_text(json.dumps({"providers": caps}, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "provider",
        "login",
        "price",
        "index",
        "bond",
        "macro",
        "valuation",
        "history",
        "notes",
    ]
    lines = [
        "# Data Capability Report",
        "",
        "> Offline capability assessment; no network probe was performed.",
        "",
        "| " + " | ".join(fields) + " |",
        "|" + "|".join(["---"] * len(fields)) + "|",
    ]
    for c in caps:
        lines.append("| " + " | ".join(str(c.get(f, "-")).replace("|", "/") for f in fields) + " |")
    lines += ["", "## Structured errors", ""]
    for c in caps:
        for e in c.get("errors", []):
            lines.append(
                f"- `{c.get('provider')}` `{e.get('code', 'unknown')}`: {e.get('message', '')}"
            )
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mp, jp
