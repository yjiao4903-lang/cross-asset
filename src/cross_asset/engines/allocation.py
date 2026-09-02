"""Constrained strategic-plus-tactical allocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import tanh


@dataclass(frozen=True)
class AllocationResult:
    weights: dict[str, float]
    status: str
    as_of: object = None
    data_cutoff: object = None
    model_version: str = "allocation_v0.1"
    attribution: dict[str, dict] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


def bounded_projection(values, minimum, maximum, total=1.0):
    keys = list(values)
    n = len(keys)
    if n * minimum > total + 1e-12 or n * maximum < total - 1e-12:
        raise ValueError("infeasible allocation constraints")
    out = {key: max(minimum, min(maximum, float(values[key]))) for key in keys}
    for _ in range(n * 4 + 10):
        diff = total - sum(out.values())
        if abs(diff) < 1e-10:
            return out
        free = [
            key
            for key in keys
            if minimum + 1e-12 < out[key] < maximum - 1e-12
            or (diff > 0 and out[key] < maximum - 1e-12)
            or (diff < 0 and out[key] > minimum + 1e-12)
        ]
        if not free:
            break
        step = diff / len(free)
        for key in free:
            out[key] = max(minimum, min(maximum, out[key] + step))
    if abs(total - sum(out.values())) > 1e-8:
        raise ValueError("allocation constraints cannot satisfy sum=1")
    return out


def allocate(
    scores,
    strategic_weights,
    *,
    max_tilt=0.10,
    min_weight=0.0,
    max_weight=0.5,
    health=True,
    previous_valid_weight=None,
    as_of=None,
    data_cutoff=None,
    model_version="allocation_v0.1",
):
    keys = list(strategic_weights)
    if set(scores) - set(keys):
        raise ValueError("scores contain unknown assets")
    unhealthy = health is False or str(health).upper() in (
        "UNHEALTHY",
        "FAILED",
        "STALE",
    )
    attr = {}
    raw = {}
    for key in keys:
        signal = scores.get(key)
        score = getattr(signal, "score", signal)
        conf = float(getattr(signal, "confidence", 1.0) if signal is not None else 0.0)
        raw_tilt = 0.0 if score is None else max_tilt * tanh(float(score) / 1.25)
        adjusted_tilt = raw_tilt * max(0.0, min(1.0, conf))
        raw[key] = float(strategic_weights[key]) + adjusted_tilt
        attr[key] = {
            "strategic_weight": float(strategic_weights[key]),
            "raw_tilt": raw_tilt,
            "confidence_adjusted_tilt": adjusted_tilt,
            "pre_projection_weight": raw[key],
            "confidence": conf,
            "score": score,
        }

    if unhealthy:
        base = previous_valid_weight or strategic_weights
        weights = bounded_projection(base, min_weight, max_weight)
        for key in keys:
            attr[key]["projection_adjustment"] = weights[key] - float(base[key])
            attr[key]["constraint_adjusted_tilt"] = (
                weights[key] - float(strategic_weights[key])
            )
        return AllocationResult(
            weights=weights,
            status="FROZEN",
            as_of=as_of,
            data_cutoff=data_cutoff,
            model_version=model_version,
            attribution=attr,
            warnings=("critical data unhealthy",),
        )

    weights = bounded_projection(raw, min_weight, max_weight)
    for key in keys:
        attr[key]["projection_adjustment"] = weights[key] - raw[key]
        attr[key]["constraint_adjusted_tilt"] = weights[key] - float(
            strategic_weights[key]
        )
    return AllocationResult(
        weights=weights,
        status="ACTIVE",
        as_of=as_of,
        data_cutoff=data_cutoff,
        model_version=model_version,
        attribution=attr,
    )
