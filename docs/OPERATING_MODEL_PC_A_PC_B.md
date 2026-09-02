# Operating Model: PC-A Primary / PC-B Data Ingress

## Status

Effective after repository transfer to `yjiao4903-lang/cross-asset`.

Accepted migration baseline:

- repository: `yjiao4903-lang/cross-asset`
- accepted Consumer v1 baseline: `68e63a7f225022cd3099d16c752da9620ea312eb`
- `Marco-economic` remains a separate repository and the authoritative macro/fundamental/structural/regime provider
- `cross-asset` remains the Cross-Asset Decision & Allocation consumer

This operating model does **not** create a monorepo.

## Authority model

### PC-A / `yjiao4903-lang`

PC-A is the single authoritative development and runtime node for:

- GitHub repository ownership and PR/merge workflow
- source code and configuration
- canonical datasets
- DuckDB state
- Marco snapshot export
- Cross model execution
- replay/backtest
- local UI/runtime acceptance

There must be only one authoritative canonical/runtime state: PC-A.

### PC-B

PC-B is a low-frequency **data ingress / transfer node** only.

PC-B may:

- obtain data from Wind or other local data sources
- export raw Excel/CSV files
- place raw inputs into the agreed transfer/inbox location

PC-B must not become a second runtime authority. In particular, it should not independently maintain authoritative copies of:

- canonical datasets
- DuckDB databases
- model state
- production integration snapshots
- source/config changes

## Data-transfer rule

**Synchronize inputs, never synchronize runtime database state.**

Allowed transfer surface:

```text
raw/
manual_inbox/
imports/
producer integration snapshots when explicitly needed
```

Do not synchronize between PCs:

```text
*.duckdb
DuckDB WAL/lock files
canonical runtime database state
venv/
__pycache__/
cache/
model runtime state
```

PC-A performs ingestion and rebuild/update of canonical/DuckDB state after receiving new raw inputs.

## Recommended PC-B export convention

Use timestamped immutable source files. Example:

```text
YYYYMMDD_HHMMSS_WIND_PCB_<dataset>.xlsx
YYYYMMDD_HHMMSS_WIND_PCB_<dataset>.csv
```

Do not overwrite a previously transferred raw file. If the source data is corrected, export a new timestamped file.

## Normal data flow

```text
PC-B / external source
        ↓
raw Excel / CSV export
        ↓
shared sync / inbox
        ↓
PC-A ingest
        ↓
canonical data
        ↓
DuckDB
        ↓
Marco export
        ↓
Marco Contract v1 bundle
        ↓
Cross run / replay / backtest
```

## Marco / Cross boundary

The repositories remain independent and communicate through Marco Integration Contract v1:

- `macro_snapshot.json`
- `structural_snapshot.json`
- `fundamental_asset_view.json`
- `integration_manifest.json`

Do not re-introduce hidden cross-repository coupling or direct shared database state.

## Local repository remotes

When each machine is next available, update retained clones to the transferred repository:

```powershell
git remote set-url origin https://github.com/yjiao4903-lang/cross-asset.git
git remote -v
```

This local remote update is operational housekeeping and is not a blocker for online development.

## Current acceptance boundary

Online acceptance is complete for:

- Marco Provider v1 contract/export
- Cross Consumer v1 contract loading and validation
- exact-byte manifest SHA-256 verification
- PIT safeguards
- asset-boundary mapping
- Marco fundamental input into Cross AssetScore
- Ubuntu/Windows CI

PC-A Cross real-data E2E remains a local runtime acceptance item and no longer blocks repository ownership consolidation or online development.

## Deferred work

- no Marco/Cross monorepo merge
- no legacy `macro_v0.2` deletion yet
- no cross-PC DuckDB synchronization
- do not merge the existing OOS research PR until it is reassessed against the post-Consumer main baseline
