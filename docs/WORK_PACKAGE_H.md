# Work Package H — P0 missing-component policy + G0 factor registry

**Branch**: `feature/p0-component-coverage-registry-v1`  
**Base**: `main` @ `1c418793`  
**Status**: `DEVELOPMENT_PRIOR` / diagnostic only  
**Roadmap source**: `docs/CROSS_ASSET_RESEARCH_ENRICHMENT_ROADMAP_v1_20260909.md` §2.3 and §15–16

## Why this package exists

The enrichment roadmap says the first P0 job is not more series. It is to
make missing components visible as a first-class contract:

```text
effective_component_weights
missing_component_budget
component_coverage
research_grade
allocation_eligibility
```

Today `score_asset()` renormalizes available weights. With only macro+trend
wired that is economically ~45% / ~55%, while the report layer still looks
like a six-component model. This package records that fact instead of
silently changing production scoring.

## What landed

- `config/component_coverage.yml` — declared weights, dual policy, floors
- `config/factor_registry.yml` — G0 specs for current and planned factors
- `src/cross_asset/research/component_coverage.py` — diagnostic snapshot
- `src/cross_asset/research/factor_registry.py` — G0 load + audit
- `src/cross_asset/research/coverage_cli.py` — no-DB CLI
- unit tests that do not require market data

## Binding rules

1. `score_asset()` and `allocate()` are unchanged.
2. Production binding policy stays `renormalize_available_components`.
3. The reserved-weight policy is a diagnostic contrast only.
4. `PERSONAL_WEEKLY` never promotes a factor to `RESEARCH_ADMISSIBLE`.
5. Registry `production_allocation` is false for every G0 entry.
6. Roadmap G4 (factor OOS) is named `G4_FACTOR` so it is not confused with
   CI PR #54 G4 (dual-platform gate).

## How to run

```text
python -m cross_asset.research.coverage_cli snapshot
python -m cross_asset.research.coverage_cli snapshot --personal
python -m cross_asset.research.coverage_cli registry
```

Declared wiring from `config/allocation.yml` is enough. No Wind / iFinD /
FRED pull is required.

## Explicitly not in this package

- New market series or vendor pulls
- Flipping renormalize off in production
- Wiring valuation / carry / credit scores
- Weekly-review PRs #57–#60 (separate stack, still unmerged)
- Live data, auto-trading, optimizer changes

## Suggested next (still system-first)

1. Keep #57–#60 as the personal weekly stack; do not rebase this package onto it.
2. After this lands, specify P0-A rates/credit transforms against the registry
   without admitting series.
3. Only then attach user-supplied Wind / iFinD columns onto already specified
   canonical ids.
