"""Data-origin classification and evidence gates (non-destructive)."""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class DataOrigin(str, Enum):
    LIVE = "LIVE"
    MANUAL = "MANUAL"
    FIXTURE = "FIXTURE"
    SIMULATED = "SIMULATED"
    UNAVAILABLE = "UNAVAILABLE"

@dataclass(frozen=True)
class OriginEvidence:
    origin: DataOrigin
    provider: str | None = None
    file_hash: str | None = None
    template_id: str | None = None
    verified_at: str | None = None
    raw_file: str | None = None
    provider_attempt_id: str | None = None
    available_at: str | None = None
    notes: str | None = None
    def safe_dict(self):
        return {"origin":self.origin.value,"provider":self.provider,"file_hash":self.file_hash,"template_id":self.template_id,"available_at":self.available_at,"verified_at":self.verified_at,"raw_file":self.raw_file,"provider_attempt_id":self.provider_attempt_id,"notes":_redact(self.notes or "")}

def origin_from_observation(observation: Any) -> DataOrigin:
    metadata=getattr(observation,"metadata",None) or (observation.get("metadata",{}) if isinstance(observation,dict) else {})
    value=metadata.get("origin", metadata.get("data_origin", DataOrigin.UNAVAILABLE))
    try: return DataOrigin(str(value).upper())
    except ValueError: return DataOrigin.UNAVAILABLE

def summarize_origins(items: Iterable[Any]) -> dict[str, Any]:
    origins=[origin_from_observation(x) for x in items]; counts={o.value:origins.count(o) for o in DataOrigin if origins.count(o)}
    return {"counts":counts,"mixed":len(counts)>1,"origin":next(iter(counts)) if len(counts)==1 else ("MIXED" if counts else DataOrigin.UNAVAILABLE.value)}

def validate_origin_evidence(evidence: OriginEvidence, *, manifest: bool = True) -> tuple[bool, list[str]]:
    errors=[]; o=evidence.origin
    if o in (DataOrigin.FIXTURE,DataOrigin.SIMULATED) and manifest: errors.append("fixture_or_simulated_cannot_produce_live_manifest")
    if o is DataOrigin.MANUAL:
        if not evidence.file_hash: errors.append("manual_file_hash_required")
        if not evidence.template_id: errors.append("manual_template_id_required")
        if not evidence.available_at: errors.append("manual_available_at_required")
    if o is DataOrigin.LIVE:
        if not evidence.provider_attempt_id: errors.append("live_provider_attempt_required")
        if not evidence.verified_at: errors.append("live_verified_at_required")
        if not evidence.raw_file: errors.append("live_raw_file_required")
    return not errors, errors

def validate_run_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return safe validation result; legacy records are never guessed as live."""
    origin=str(manifest.get("origin", "UNAVAILABLE")).upper()
    try: evidence=OriginEvidence(DataOrigin(origin), provider=manifest.get("provider"), file_hash=manifest.get("file_hash"), template_id=manifest.get("template_id"), verified_at=manifest.get("verified_at"), raw_file=manifest.get("raw_file"), provider_attempt_id=manifest.get("provider_attempt_id"), available_at=manifest.get("available_at"), notes=manifest.get("notes"))
    except ValueError: evidence=OriginEvidence(DataOrigin.UNAVAILABLE)
    _ok, errors = validate_origin_evidence(evidence)
    if manifest.get("legacy") and origin not in ("UNAVAILABLE",): errors.append("legacy_origin_must_not_be_inferred")
    return {"valid":not errors,"origin":evidence.origin.value,"errors":errors,"evidence":evidence.safe_dict()}

def _redact(text: str) -> str:
    return re.sub(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+", r"\1=<redacted>", text)
