/**
 * DashboardSnapshotV0 — frontend render contract.
 *
 * #114 (PRODUCT-DEV) owns the Python source of truth and the contract identity:
 * version identity lives in `metadata.snapshot_version` (frozen by #114). The
 * frontend consumes that contract and invents no competing top-level fields.
 * Until a #114 fixture lands on main, the JSON objects under
 * src/snapshot/fixtures are an ISOLATED, clearly-labelled frontend mirror used
 * for UI development only. Reconciliation expectations are documented in
 * src/snapshot/RECONCILIATION.md.
 */
export const SNAPSHOT_VERSION_V0 = '0'

export const REQUIRED_SECTIONS = [
  'metadata',
  'macro_climate',
  'investment_climate',
  'clusters',
  'weekly_change',
  'regime',
  'asset_views',
  'cross_asset_pulse',
  'executive_brief',
  'data_health_summary',
]

export const OPTIONAL_SECTIONS = ['details']

export const DATA_STATUSES = ['FRESH', 'NO_NEW_INFORMATION', 'STALE', 'MISSING', 'BLOCKED']

export const MARKET_CONFIRMATIONS = ['CONFIRMED', 'DIVERGENT', 'COUNTER_TREND']

/**
 * Structural validation of a snapshot object against the frozen V0 render
 * contract. Returns a list of human-readable problems; empty list = valid.
 * The frontend renders only the sections listed above; everything else in a
 * future #114 payload must live under `details`.
 */
export function validateSnapshot(snapshot) {
  const problems = []
  if (!snapshot || typeof snapshot !== 'object') {
    return ['snapshot is not an object']
  }
  if (snapshot.contract !== undefined) {
    problems.push('top-level "contract" is not part of the frozen contract; version identity is metadata.snapshot_version')
  }
  for (const section of REQUIRED_SECTIONS) {
    if (!(section in snapshot)) problems.push(`missing required section: ${section}`)
  }
  for (const key of Object.keys(snapshot)) {
    if (![...REQUIRED_SECTIONS, ...OPTIONAL_SECTIONS].includes(key)) {
      problems.push(`unexpected top-level section (belongs under \`details\`): ${key}`)
    }
  }
  const meta = snapshot.metadata ?? {}
  for (const field of ['snapshot_version', 'as_of', 'decision_time', 'lane', 'run_id']) {
    if (!meta[field]) problems.push(`metadata.${field} is required`)
  }
  if (meta.snapshot_version && String(meta.snapshot_version) !== SNAPSHOT_VERSION_V0) {
    problems.push(`frontend renders DashboardSnapshotV0 only (metadata.snapshot_version must be "${SNAPSHOT_VERSION_V0}")`)
  }
  if (meta.lane && !['MONITORING', 'RESEARCH', 'FORMAL_OOS'].includes(meta.lane)) {
    problems.push(`metadata.lane "${meta.lane}" is not a known evidence lane`)
  }
  for (const view of snapshot.asset_views ?? []) {
    if (!Number.isInteger(view.stance) || view.stance < -2 || view.stance > 2) {
      problems.push(`asset_views[${view.asset}].stance must be an integer in [-2, +2]`)
    }
    if (!MARKET_CONFIRMATIONS.includes(view.market_confirmation)) {
      problems.push(`asset_views[${view.asset}].market_confirmation "${view.market_confirmation}" invalid`)
    }
  }
  const checkItems = (items, where) => {
    for (const item of items ?? []) {
      if (item.status && !DATA_STATUSES.includes(item.status)) {
        problems.push(`${where}: unknown data status "${item.status}"`)
      }
    }
  }
  checkItems(snapshot.data_health_summary?.items, 'data_health_summary.items')
  return problems
}
