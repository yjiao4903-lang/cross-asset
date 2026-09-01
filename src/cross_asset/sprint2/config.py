"""Load, validate, and hash the frozen Sprint 2 YAML manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .availability import AvailabilityPolicy, validate_availability_policies
from .protocol import Sprint2Protocol


def load_sprint2_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = (
        Path(path)
        if path
        else Path(__file__).resolve().parents[3] / "config" / "sprint2_protocol.yml"
    )
    with config_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    validate_sprint2_config(raw)
    return raw


def validate_sprint2_config(
    raw: dict[str, Any],
) -> tuple[Sprint2Protocol, tuple[AvailabilityPolicy, ...]]:
    if not isinstance(raw, dict) or set(raw) != {"protocol", "availability_policies"}:
        raise ValueError("sprint2_config_shape_invalid")
    protocol = Sprint2Protocol.from_mapping(raw["protocol"])
    policies = validate_availability_policies(raw["availability_policies"])
    return protocol, policies


def config_hash(raw: dict[str, Any] | None = None, path: str | Path | None = None) -> str:
    document = raw if raw is not None else load_sprint2_config(path)
    payload = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()
