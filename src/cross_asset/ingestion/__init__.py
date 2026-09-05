# CFTC C0 parser compatibility gate.  The implementation remains isolated from
# #18 production admission; package initialization only hardens the existing
# parser so any caller-supplied publication timestamp must occur after the
# Tuesday report/reference date.  Actual release dates are still supplied by
# the source calendar and are never guessed here.
from . import cftc_positioning as _cftc_positioning
from .cftc_pit_guard import guard_parse_cftc_snapshot
from .normalization import normalize_observation, normalize_observations
from .origin import (
    DataOrigin,
    OriginEvidence,
    origin_from_observation,
    summarize_origins,
    validate_origin_evidence,
    validate_run_manifest,
)
from .quality import QualityEvent, assess_observations, freshness_status
from .runner import IngestionRunner, ingest

_cftc_positioning.parse_cftc_snapshot = guard_parse_cftc_snapshot(
    _cftc_positioning.parse_cftc_snapshot
)

__all__ = [
    "DataOrigin",
    "IngestionRunner",
    "OriginEvidence",
    "QualityEvent",
    "assess_observations",
    "freshness_status",
    "ingest",
    "normalize_observation",
    "normalize_observations",
    "origin_from_observation",
    "summarize_origins",
    "validate_origin_evidence",
    "validate_run_manifest",
]
