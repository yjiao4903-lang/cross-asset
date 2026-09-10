"""Isolated C0 contract for Treasury FiscalData + NY Fed liquidity staging.

This surface is RESEARCH_STAGING_ONLY. It must not write approved observations,
change allocation, or reuse FRED / Wind / CFTC providers.
"""

from __future__ import annotations

C0_GATE = "C0"
C0_USAGE = "RESEARCH_STAGING_ONLY"
PRODUCTION_ADMISSION = False
ALLOCATION_SIGNAL = False
WORKSTREAM_ID = "C67-TREASURY-NYFED-LIQUIDITY-C0"
DEFAULT_REGISTRY_PATH = "config/treasury_nyfed_c0.yml"
DEFAULT_TIMEZONE = "America/New_York"


def require_c0_only() -> dict[str, object]:
    return {
        "gate": C0_GATE,
        "usage": C0_USAGE,
        "production_admission": PRODUCTION_ADMISSION,
        "allocation_signal": ALLOCATION_SIGNAL,
        "workstream": WORKSTREAM_ID,
        "approved_observations": False,
        "directional_alpha": False,
    }


__all__ = [
    "ALLOCATION_SIGNAL",
    "C0_GATE",
    "C0_USAGE",
    "DEFAULT_REGISTRY_PATH",
    "DEFAULT_TIMEZONE",
    "PRODUCTION_ADMISSION",
    "WORKSTREAM_ID",
    "require_c0_only",
]
