from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PORTS = {"frontend": 8765, "backend": 8008}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _port_owner(port: int) -> dict:
    """Best-effort Windows port ownership via PowerShell (no elevation required)."""
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        "$rows=Get-NetTCPConnection -LocalPort @port -State Listen | "
        "ForEach-Object { $p=Get-CimInstance Win32_Process -Filter \"ProcessId=$($_.OwningProcess)\"; "
        "[pscustomobject]@{ pid=$_.OwningProcess; name=$p.Name; cmd=(($p.CommandLine -replace '\\s+',' ') ) } }; "
        "$rows | ConvertTo-Json -Depth 3"
    ).replace("@port", str(port))
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        data = json.loads(proc.stdout or "") if (proc.stdout or "").strip() else []
    except (OSError, ValueError, subprocess.SubprocessError):
        data = []
    if isinstance(data, dict):
        data = [data]
    for row in data:
        cmd = str(row.get("cmd") or "")
        if len(cmd) > 240:
            row["cmd"] = cmd[:240]
    return {"port": port, "listening": bool(data), "owners": data}


def _launcher_runtime_state() -> dict:
    launcher_dir = REPO_ROOT / "launcher"
    pid_file = launcher_dir / ".runtime" / "servers.pid"
    meta = None
    if pid_file.exists():
        try:
            meta = json.loads(pid_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {"error": "unreadable servers.pid"}
    return {
        "pid_file": str(pid_file),
        "pid_metadata": meta,
        "logs_present": sorted(
            p.name for p in (launcher_dir / "logs").glob("*")
        )
        if (launcher_dir / "logs").exists()
        else [],
    }


def _tool_version(command: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (proc.stdout or proc.stderr).strip().splitlines()
    return output[0] if output else None


def _proxy_state() -> dict:
    env_keys = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy")
    env = {key: os.getenv(key) for key in env_keys if os.getenv(key)}
    # Windows registry proxy (per-user): host:port only, never credentials.
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                "$i=Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings'; "
                    "ConvertTo-Json @{ proxyEnable=[int]$i.ProxyEnable; proxyServer=[string]$i.ProxyServer }"
                )
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        registry = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        registry = {}
    return {
        "process_env": env,
        "windows_registry": {
            "proxy_enable": registry.get("proxyEnable"),
            # Sanitized: only scheme://host:port is meaningful for diagnostics.
            "proxy_server": registry.get("proxyServer"),
        },
    }


def _path_state(path: Path) -> dict:
    return {"exists": path.exists(), "path": str(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Native Windows environment census for #140")
    parser.add_argument("--artifact-root", default="artifacts/windows_uat_v2")
    args = parser.parse_args()
    root = REPO_ROOT / args.artifact_root
    root.mkdir(parents=True, exist_ok=True)

    venv_python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    payload = {
        "contract": "WINDOWS-REAL-SNAPSHOT-SOAK-UAT-V2",
        "generated_at": _now(),
        "windows": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "python": {
            "chosen_interpreter": str(venv_python if venv_python.exists() else sys.executable),
            "version": platform.python_version(),
            "venv_python_present": venv_python.exists(),
            "path_python": shutil.which("python"),
            "py_launcher": shutil.which("py"),
        },
        "node": {
            "tools_node": str(REPO_ROOT / "tools" / "node" / "node.exe"),
            "tools_node_present": (REPO_ROOT / "tools" / "node" / "node.exe").exists(),
            "tools_node_version": _tool_version(
                [str(REPO_ROOT / "tools" / "node" / "node.exe"), "--version"]
            ),
            "path_node": shutil.which("node"),
        },
        "npm": {
            "tools_npm_cmd": str(REPO_ROOT / "tools" / "node" / "npm.cmd"),
            "tools_npm_present": (REPO_ROOT / "tools" / "node" / "npm.cmd").exists(),
            "path_npm": shutil.which("npm"),
        },
        "repo": {
            "root": str(REPO_ROOT),
            "git_head": _tool_version(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"]),
            "venv": _path_state(REPO_ROOT / ".venv"),
            "node_modules": _path_state(REPO_ROOT / "frontend" / "node_modules"),
            "dist": _path_state(REPO_ROOT / "frontend" / "dist"),
        },
        "proxy_environment": _proxy_state(),
        "ports": {name: _port_owner(port) for name, port in PORTS.items()},
        "launcher_runtime": _launcher_runtime_state(),
        "artifact_roots": {
            "uat_root": str(root),
            "default_snapshot_root": str(REPO_ROOT / "artifacts" / "dashboard_snapshots"),
            "workbench_runs_root": str(REPO_ROOT / "artifacts" / "workbench_runs"),
        },
    }

    (root / "ENVIRONMENT.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md = [
        "# Windows Environment Census (WINDOWS-REAL-SNAPSHOT-SOAK-UAT-V2)",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        f"- Windows: `{payload['windows']['platform']}`",
        f"- Chosen Python: `{payload['python']['chosen_interpreter']}` ({payload['python']['version']})",
        f"- Node (user-space tools/node): `{payload['node']['tools_node_version']}`",
        f"- Repo: `{payload['repo']['root']}` head `{payload['repo']['git_head']}`",
        (
        f"- .venv present: `{payload['repo']['venv']['exists']}`; "
        f"node_modules: `{payload['repo']['node_modules']['exists']}`; "
        f"dist: `{payload['repo']['dist']['exists']}`"),
        ("- Registry proxy: "
         f"`{payload['proxy_environment']['windows_registry']}` "
         "(process env proxy keys: "
         f"`{sorted(payload['proxy_environment']['process_env'])}`)"),
        "",
        "## Port ownership at census time",
        "",
    ]
    for name, item in payload["ports"].items():
        owners = ", ".join(
            f"pid={o.get('pid')} {o.get('name')}" for o in item["owners"]
        ) or "none"
        md.append(f"- {name} :{item['port']} — listening=`{item['listening']}` owners: {owners}")
    md += [
        "",
        "## Launcher runtime state",
        "",
        f"- pid metadata: `{json.dumps(payload['launcher_runtime']['pid_metadata'])}`",
        "- no credentials or secrets are recorded in this census.",
        "",
    ]
    (root / "ENVIRONMENT.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"artifact_root": str(root)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
