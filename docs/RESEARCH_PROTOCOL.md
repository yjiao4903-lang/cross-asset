# Research Protocol v0.1

Status: `PLANNING_ONLY`; Owner: TBD; Reviewer: TBD; Approved at: TBD. This protocol must be approved before any real-data result is interpreted.

## Frozen design

- Training minimum: 5 years.
- Test window: 12 months.
- Walk-forward step: 3 months.
- Final holdout: last 20% of the eligible chronological sample.
- Coverage threshold: TBD (must be set before viewing results); no zero imputation.
- Rebalance/report cadence: weekly.
- Transaction-cost sensitivity: 0, 5, 10, 20, 30 bps.
- Benchmarks/challengers: `STATIC`, `TREND_ONLY`, `MACRO_ONLY`, `RISK_ONLY`, `FULL_MODEL`.
- Benchmark interfaces are READY for offline research: `MACRO_ONLY` consumes only macro fields; `RISK_ONLY` consumes only risk/volatility fields. This is an interface contract, not OOS validation or an investment-validity claim.
- MACRO_ONLY requires an explicit `macro_weights` asset mapping; RISK_ONLY uses only explicit per-asset volatility/risk scores with inverse-risk normalization. Missing mappings use a marked strategic fallback and do not claim alpha. Parameters are uncalibrated and OOS validation remains pending.
- All decisions consume only `available_at <= decision_time`; data snapshot, config hash, code version, origin and cutoff are persisted.

## Verdict rules

`ACCEPT` requires frozen split/benchmark/cost inputs, complete provenance, no unresolved PIT violation, and predeclared metrics passing the research threshold. `REJECT` applies to a reproducible PIT/lookahead, semantic, provenance or safety failure, or a predeclared failure threshold. `INCONCLUSIVE` applies when coverage, sample length, permission or statistical power is insufficient; it must not be narrated as success.

No parameter tuning, benchmark substitution, split movement or cost omission is permitted after viewing results. This contract does not claim investment validity or production readiness.
