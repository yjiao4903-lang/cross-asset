"""Constrained strategic-plus-tactical allocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import tanh

_TOLERANCE = 1e-12


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
    return project_weights(
        values,
        {key: minimum for key in keys},
        {key: maximum for key in keys},
        total=total,
    )


def project_weights(values, lower_bounds, upper_bounds, total=1.0):
    keys = list(values)
    for key in keys:
        if lower_bounds[key] > upper_bounds[key] + _TOLERANCE:
            raise ValueError(f"infeasible allocation bounds for asset {key}")
    if sum(lower_bounds[key] for key in keys) > total + _TOLERANCE or sum(
        upper_bounds[key] for key in keys
    ) < total - _TOLERANCE:
        raise ValueError("infeasible allocation constraints")
    out = {
        key: max(lower_bounds[key], min(upper_bounds[key], float(values[key])))
        for key in keys
    }
    for _ in range(len(keys) * 4 + 10):
        diff = total - sum(out.values())
        if abs(diff) < 1e-10:
            return out
        free = [
            key
            for key in keys
            if lower_bounds[key] + _TOLERANCE < out[key] < upper_bounds[key] - _TOLERANCE
            or (diff > 0 and out[key] < upper_bounds[key] - _TOLERANCE)
            or (diff < 0 and out[key] > lower_bounds[key] + _TOLERANCE)
        ]
        if not free:
            break
        step = diff / len(free)
        for key in free:
            out[key] = max(
                lower_bounds[key], min(upper_bounds[key], out[key] + step)
            )
    if abs(total - sum(out.values())) > 1e-8:
        raise ValueError("allocation constraints cannot satisfy sum=1")
    return out


def tactical_bounds(strategic_weights, *, max_tilt, min_weight, max_weight):
    """Per-asset feasible band: absolute min/max intersected with strategic +/- tilt."""
    return {
        key: (
            max(min_weight, float(strategic_weights[key]) - max_tilt),
            min(max_weight, float(strategic_weights[key]) + max_tilt),
        )
        for key in strategic_weights
    }


def _within_bounds(weights, lower_bounds, upper_bounds, tolerance=1e-9):
    total = sum(weights.values())
    return abs(total - 1.0) <= tolerance and all(
        lower_bounds[key] - tolerance <= weights[key] <= upper_bounds[key] + tolerance
        for key in weights
    )


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
    strategic = {key: float(strategic_weights[key]) for key in keys}
    tilt = float(max_tilt)
    if tilt < 0:
        raise ValueError("max_tilt must be non-negative")
    bands = tactical_bounds(
        strategic,
        max_tilt=tilt,
        min_weight=min_weight,
        max_weight=max_weight,
    )
    lower_bounds = {key: bands[key][0] for key in keys}
    upper_bounds = {key: bands[key][1] for key in keys}

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
        raw_tilt = 0.0 if score is None else tilt * tanh(float(score) / 1.25)
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
        warnings = ["critical data unhealthy"]
        base = strategic
        if previous_valid_weight:
            previous = {
                key: float(value) for key, value in previous_valid_weight.items()
            }
            if set(previous) == set(keys):
                base = previous
                if not _within_bounds(previous, lower_bounds, upper_bounds):
                    warnings.append(
                        "previous_valid_allocation_outside_current_constraints_projected"
                    )
            else:
                warnings.append(
                    "previous_valid_allocation_keys_differ_from_current_universe"
                )
        weights = project_weights(base, lower_bounds, upper_bounds)
        for key in keys:
            attr[key]["projection_adjustment"] = weights[key] - float(base[key])
            attr[key]["constraint_adjusted_tilt"] = weights[key] - strategic[key]
        return AllocationResult(
            weights=weights,
            status="FROZEN",
            as_of=as_of,
            data_cutoff=data_cutoff,
            model_version=model_version,
            attribution=attr,
            warnings=tuple(warnings),
        )

    weights = project_weights(raw, lower_bounds, upper_bounds)
    for key in keys:
        attr[key]["projection_adjustment"] = weights[key] - raw[key]
        attr[key]["constraint_adjusted_tilt"] = weights[key] - strategic[key]
    return AllocationResult(
        weights=weights,
        status="ACTIVE",
        as_of=as_of,
        data_cutoff=data_cutoff,
        model_version=model_version,
        attribution=attr,
    )
