from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import ssl
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import requests

from cross_asset.domain.models import DataRequest
from cross_asset.providers.monitoring import FREDMonitoringProvider, YahooMonitoringProvider

PROVIDERS = {
    "fred": {
        "host": "fred.stlouisfed.org",
        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10&cosd=2026-09-01",
        "series": "US_REAL_10Y",
    },
    "yahoo": {
        "host": "query1.finance.yahoo.com",
        "url": "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=5d&interval=1d",
        "series": "US_EQ",
    },
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_text(value: object, limit: int = 240) -> str | None:
    if value is None:
        return None
    text = str(value).split("?")[0]
    key = os.getenv("FRED_API_KEY")
    if key:
        text = text.replace(key, "<redacted>")
    return text[:limit]


def _proxy_env() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ):
        raw = os.getenv(name)
        if not raw:
            result[name] = None
            continue
        if name.lower() in {"no_proxy"}:
            result[name] = _safe_text(raw, 200)
            continue
        try:
            parts = urlsplit(raw)
            if parts.hostname:
                port = f":{parts.port}" if parts.port else ""
                result[name] = f"{parts.scheme or 'proxy'}://{parts.hostname}{port}"
            else:
                result[name] = "configured"
        except ValueError:
            result[name] = "configured"
    return result


def _dns(host: str) -> dict:
    try:
        rows = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        return {"ok": False, "error": _safe_text(exc), "ipv4": [], "ipv6": []}
    ipv4 = sorted({row[4][0] for row in rows if row[0] == socket.AF_INET})
    ipv6 = sorted({row[4][0] for row in rows if row[0] == socket.AF_INET6})
    return {"ok": bool(rows), "error": None, "ipv4": ipv4, "ipv6": ipv6}


def _tcp_one(address: str, family: int, port: int = 443, timeout: float = 4.0) -> dict:
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        target = (address, port) if family == socket.AF_INET else (address, port, 0, 0)
        sock.connect(target)
        return {"ok": True, "error": None}
    except OSError as exc:
        return {"ok": False, "error": _safe_text(exc)}
    finally:
        sock.close()


def _family_connectivity(dns: dict) -> dict:
    out: dict[str, dict] = {}
    for label, family, addresses in (
        ("ipv4", socket.AF_INET, dns.get("ipv4") or []),
        ("ipv6", socket.AF_INET6, dns.get("ipv6") or []),
    ):
        if not addresses:
            out[label] = {
                "attempted": False,
                "ok": None,
                "address": None,
                "error": None,
            }
            continue
        probe = _tcp_one(addresses[0], family)
        out[label] = {"attempted": True, "address": addresses[0], **probe}
    return out


def _tls(host: str, timeout: float = 5.0) -> dict:
    try:
        with socket.create_connection((host, 443), timeout=timeout) as raw:
            context = ssl.create_default_context()
            with context.wrap_socket(raw, server_hostname=host) as wrapped:
                cert = wrapped.getpeercert() or {}
                return {
                    "ok": True,
                    "version": wrapped.version(),
                    "subject": cert.get("subject"),
                    "not_after": cert.get("notAfter"),
                    "error": None,
                }
    except (OSError, ssl.SSLError) as exc:
        return {
            "ok": False,
            "version": None,
            "subject": None,
            "not_after": None,
            "error": _safe_text(exc),
        }


def _http(url: str, *, trust_env: bool, timeout: float = 8.0) -> dict:
    session = requests.Session()
    session.trust_env = trust_env
    try:
        response = session.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "cross-asset-engine/0.1"},
        )
        return {
            "ok": response.status_code < 400,
            "status": response.status_code,
            "bytes": len(response.content),
            "content_type": response.headers.get("content-type"),
            "error": None,
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "status": None,
            "bytes": 0,
            "content_type": None,
            "error": _safe_text(exc),
        }
    finally:
        session.close()


def _repo_probe(provider_name: str, series_id: str) -> dict:
    request = DataRequest(
        series_ids=[series_id],
        start=date.today() - timedelta(days=40),
        end=date.today(),
    )
    provider = (
        FREDMonitoringProvider(timeout=8)
        if provider_name == "fred"
        else YahooMonitoringProvider(timeout=8)
    )
    try:
        rows = list(provider.fetch(request) or [])
        error = getattr(provider, "last_error", None)
        return {
            "ok": bool(rows),
            "row_count": len(rows),
            "latest_observation_date": max(
                (str(row.observation_date) for row in rows), default=None
            ),
            "source_series_ids": sorted(
                {
                    str(row.source_series_id)
                    for row in rows
                    if row.source_series_id
                }
            ),
            "error_code": getattr(error, "code", None),
            "error": _safe_text(getattr(error, "message", error)),
        }
    except Exception as exc:  # noqa: BLE001 - operational diagnostic only
        return {
            "ok": False,
            "row_count": 0,
            "latest_observation_date": None,
            "source_series_ids": [],
            "error_code": type(exc).__name__,
            "error": _safe_text(exc),
        }


def _classify(item: dict) -> tuple[str, str]:
    if item["repository_provider_path"].get("ok"):
        return "LIVE_REACHABLE", "repository provider path returned real rows"
    dns = item["dns"]
    tls = item["tls"]
    env_http = item["https_trust_env"]
    direct_http = item["https_no_proxy"]
    if not dns.get("ok") or not tls.get("ok"):
        return (
            "NETWORK_BLOCKED",
            "DNS/TLS path failed before repository provider semantics",
        )
    if not env_http.get("ok") and direct_http.get("ok"):
        return (
            "NETWORK_BLOCKED",
            "proxy/environment path blocks HTTPS while no-proxy HTTPS succeeds",
        )
    statuses = {env_http.get("status"), direct_http.get("status")}
    if statuses & {401, 403, 429}:
        return (
            "PROVIDER_BLOCKED",
            "provider returned an explicit access/rate response",
        )
    if env_http.get("ok") or direct_http.get("ok"):
        return (
            "CODE_PATH_DEFECT",
            "public endpoint is reachable but repository provider path returned no real rows",
        )
    return (
        "NETWORK_BLOCKED",
        "public HTTPS requests failed despite DNS/TLS diagnostics",
    )


def _md(payload: dict) -> str:
    lines = [
        "# Provider Connectivity V2",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        "## Environment",
        "",
        f"- platform: `{payload['platform']}`",
        f"- python: `{payload['python']}`",
        "- proxy variables are sanitized; credentials are never emitted.",
        "",
    ]
    for name, item in payload["providers"].items():
        repo = item["repository_provider_path"]
        lines += [
            f"## {name.upper()}",
            "",
            f"- classification: **{item['classification']}**",
            f"- reason: {item['classification_reason']}",
            f"- DNS: `{item['dns']['ok']}`",
            f"- TLS: `{item['tls']['ok']}`",
            f"- HTTPS trust-env: `{item['https_trust_env'].get('status')}` / ok=`{item['https_trust_env']['ok']}`",
            f"- HTTPS no-proxy: `{item['https_no_proxy'].get('status')}` / ok=`{item['https_no_proxy']['ok']}`",
            f"- repository provider rows: `{repo['row_count']}`",
            f"- repository error: `{repo.get('error_code') or ''}` {repo.get('error') or ''}",
            "",
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Native/public provider connectivity diagnostics for #140"
    )
    parser.add_argument("--artifact-root", default="artifacts/windows_uat_v2")
    args = parser.parse_args()
    root = Path(args.artifact_root)
    root.mkdir(parents=True, exist_ok=True)

    payload = {
        "contract": "WINDOWS-REAL-SNAPSHOT-SOAK-UAT-V2",
        "generated_at": _now(),
        "platform": platform.platform(),
        "python": sys.executable,
        "proxy_environment": _proxy_env(),
        "providers": {},
    }
    for name, cfg in PROVIDERS.items():
        dns = _dns(cfg["host"])
        item = {
            "host": cfg["host"],
            "dns": dns,
            "tcp_family_diagnostics": _family_connectivity(dns),
            "tls": _tls(cfg["host"]),
            "https_trust_env": _http(cfg["url"], trust_env=True),
            "https_no_proxy": _http(cfg["url"], trust_env=False),
            "repository_provider_path": _repo_probe(name, cfg["series"]),
        }
        item["classification"], item["classification_reason"] = _classify(item)
        payload["providers"][name] = item

    (root / "PROVIDER_CONNECTIVITY.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (root / "PROVIDER_CONNECTIVITY.md").write_text(
        _md(payload), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                name: item["classification"]
                for name, item in payload["providers"].items()
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
