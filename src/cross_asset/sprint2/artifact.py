"""Strict Sprint 2 preliminary artifact writer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_ARTIFACTS = (
    "decisions.parquet",
    "returns.parquet",
    "scores.parquet",
    "allocations.parquet",
    "turnover.parquet",
    "costs.parquet",
    "summary.md",
)


def sha256_frame(frame: pd.DataFrame) -> str:
    payload = frame.sort_index(axis=1).to_json(
        date_format="iso", orient="split", default_handler=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    import duckdb

    connection = duckdb.connect()
    try:
        connection.register("_sprint2_frame", frame.reset_index(drop=True))
        connection.execute("COPY _sprint2_frame TO ? (FORMAT PARQUET)", [str(path)])
    finally:
        connection.close()


def write_artifacts(
    output_dir: str | Path, tables: dict[str, pd.DataFrame], summary: str
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_ARTIFACTS[:-1]:
        write_parquet(tables.get(name, pd.DataFrame()), root / name)
    (root / "summary.md").write_text(summary, encoding="utf-8")
    return {"output_dir": str(root), "artifacts": [str(root / name) for name in REQUIRED_ARTIFACTS]}


def protocol_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")
        ).encode()
    ).hexdigest()
