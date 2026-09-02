# Research Protocol v0.2

Status: `PLANNING_ONLY`; Owner: TBD; Reviewer: TBD; Approved at: TBD. This protocol must be approved before any real-data result is interpreted.

## Frozen design

- Training minimum: 5 years.
- Test window: 12 months.
- Walk-forward step: 3 months.
- Default walk-forward mode: expanding. Rolling windows require an explicit rolling-year horizon.
- Window boundaries are calendar offsets applied to an explicit ordered decision-date set. The implementation must never synthesize missing trading dates.
- Final holdout: last 20% of the eligible chronological sample.
- Coverage threshold: TBD (must be set before viewing results); no zero imputation.
- Rebalance/report cadence: weekly.
- Transaction-cost sensitivity: 0, 5, 10, 20, 30 bps.
- Turnover convention: `two_sided_notional`.
- Initial allocation cost: disabled by default for the frozen Sprint 2 protocol.
- Terminal decision: no realized holding-period return without a next decision boundary.
- Benchmarks/challengers: `STATIC`, `TREND_ONLY`, `MACRO_ONLY`, `RISK_ONLY`, `FULL_MODEL`.
- Signal-model baseline: `full_model_v0.2`; market `market_v0.2`, macro `macro_v0.2`, asset score `asset_score_v0.2`.
- All benchmark market histories must use the same asset return semantics as FULL_MODEL. Yield proxies must be converted to a duration-based return index before trend/risk calculations.
- `TREND_ONLY` uses the same normalized multi-horizon trend family as FULL_MODEL.
- `RISK_ONLY` uses return-index volatility rather than percentage changes of raw yield levels.
- `MACRO_ONLY` consumes only macro inputs. A missing required macro mapping makes that benchmark unavailable; it must not be silently replaced with a tuned proxy.
- `FULL_MODEL` may consume macro, trend, valuation, carry, risk and structure components, but missing optional components remain missing. No zero imputation or synthetic factor is permitted.
- All decisions consume only `available_at <= decision_time`; data snapshot, config hash, code version, origin and cutoff are persisted.
- For revised macro observations, only the latest revision released by the decision time may represent a given observation_date in transforms.

## Signal normalization

Raw quantities with incompatible units must not be directly aggregated. A component entering Asset Score must either already be dimensionless or pass through a declared causal normalization. Causal normalization baselines use observations strictly prior to the value being scored. Future observations and future revisions must not alter a historical score.

Default development priors:

- Trend: risk-adjusted 1M/3M/6M/12M log moves, clipped to [-2, 2].
- Risk: negative causal z-score of 20-day realized volatility.
- Macro: declared transform followed, where configured, by a causal z-score with series-appropriate history/freshness.
- Valuation / Carry / Structure: unavailable until an explicit, auditable data and transform contract exists.

These are development priors, not validated alpha parameters.

## Health and freeze rules

A critical missing trend signal or unhealthy/stale upstream state must prevent a new ACTIVE tactical allocation. The allocator returns `FROZEN`, reusing the most recent valid ACTIVE allocation when available; otherwise it uses the strategic allocation subject to declared constraints.

## Verdict rules

`ACCEPT` requires frozen split/benchmark/cost inputs, complete provenance, no unresolved PIT violation, and predeclared metrics passing the research threshold. `REJECT` applies to a reproducible PIT/lookahead, semantic, provenance or safety failure, or a predeclared failure threshold. `INCONCLUSIVE` applies when coverage, sample length, permission or statistical power is insufficient; it must not be narrated as success.

No parameter tuning, benchmark substitution, split movement or cost omission is permitted after viewing results. This contract does not claim investment validity or production readiness.
