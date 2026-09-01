"""Constrained strategic-plus-tactical allocation."""

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
    out = {k: max(minimum, min(maximum, float(values[k]))) for k in keys}
    for _ in range(n * 4 + 10):
        diff = total - sum(out.values())
        if abs(diff) < 1e-10:
            return out
        free = [
            k
            for k in keys
            if minimum + 1e-12 < out[k] < maximum - 1e-12
            or (diff > 0 and out[k] < maximum - 1e-12)
            or (diff < 0 and out[k] > minimum + 1e-12)
        ]
        if not free:
            break
        step = diff / len(free)
        for k in free:
            out[k] = max(minimum, min(maximum, out[k] + step))
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
    unhealthy = health is False or str(health).upper() in ("UNHEALTHY", "FAILED", "STALE")
    attr = {}
    raw = {}
    for k in keys:
        s = scores.get(k)
        score = getattr(s, "score", s)
        conf = float(getattr(s, "confidence", 1.0) if s is not None else 0.0)
        raw_tilt = 0.0 if score is None else max_tilt * tanh(float(score) / 1.25)
        adj = raw_tilt * max(0.0, min(1.0, conf))
        raw[k] = strategic_weights[k] + adj
        attr[k] = {
            "strategic_weight": strategic_weights[k],
            "raw_tilt": raw_tilt,
            "confidence_adjusted_tilt": adj,
            "confidence": conf,
            "score": score,
        }
    if unhealthy:
        base = previous_valid_weight or strategic_weights
        weights = bounded_projection(base, min_weight, max_weight)
        for k in keys:
            attr[k]["constraint_adjusted_tilt"] = weights[k] - strategic_weights[k]
        return AllocationResult(
            weights, "FROZEN", as_of, data_cutoff, model_version, attr, ("critical data unhealthy",)
        )
    weights = bounded_projection(raw, min_weight, max_weight)
    for k in keys:
        attr[k]["constraint_adjusted_tilt"] = weights[k] - strategic_weights[k]
    return AllocationResult(weights, "ACTIVE", as_of, data_cutoff, model_version, attr)
