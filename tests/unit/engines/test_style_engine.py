import numpy as np
import pandas as pd

from cross_asset.engines.style import StyleEngine


def _s(values, start="2025-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values)))


def test_missing_axes_are_unavailable_and_size_uses_inner_dates():
    e = StyleEngine({"SIZE": {"semantic_definition": "small versus large"}})
    result = e.build(
        {
            "SIZE": {
                "lhs": _s(np.arange(80) + 1),
                "rhs": _s(np.arange(70) + 1, start="2025-01-11"),
            },
            "GROWTH": {},
        }
    )
    assert result["SIZE"].status == "AVAILABLE"
    assert result["GROWTH"].status == "UNAVAILABLE"


def test_contributions_sum_to_clipped_score_and_confidence_is_missing_aware():
    e = StyleEngine({"SIZE": {"semantic_definition": "small versus large"}})
    r = e.compute_axis(
        "SIZE", lhs=_s(np.arange(100) + 1), rhs=_s(np.arange(100) + 1), macro=10, risk_appetite=None
    )
    assert -2 <= r.score <= 2 and np.isclose(sum(r.contributions.values()), r.score)
    assert r.confidence == 2 / 3


def test_cutoff_is_explicit_and_does_not_drift():
    e = StyleEngine({"SIZE": {"semantic_definition": "small versus large"}})
    r = e.compute_axis(
        "SIZE", lhs=_s(np.arange(80) + 1), rhs=_s(np.arange(80) + 2), data_cutoff="2025-02-01"
    )
    assert r.data_cutoff == "2025-02-01" and r.model_version == "style_v0.1"
