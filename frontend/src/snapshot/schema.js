/**
 * DashboardSnapshotV0 — frontend render contract.
 *
 * The authoritative producer is the #117 decision-support core (accepted at
 * commit c64ae88d4851dc5ee1847a20e24a6cce00b5942f). Contract/version identity
 * is owned by the producer: `metadata.snapshot_version === "DashboardSnapshotV0"`.
 * The frontend consumes backend field shapes via a presentation-only adapter
 * (src/snapshot/adapt.js) and invents no competing fields.
 * The authoritative golden payloads are byte-equivalent copies under
 * src/snapshot/golden/ (see golden/manifest.json and RECONCILIATION.md).
 */
export const SNAPSHOT_VERSION_V0 = 'DashboardSnapshotV0'

export const REQUIRED_SECTIONS = [
  'metadata',
  'macro_climate',
  'investment_climate',
  'climate_components',
  'clusters',
  'weekly_change',
  'regime',
  'asset_views',
  'cross_asset_pulse',
  'executive_brief',
  'data_health_summary',
]

export const OPTIONAL_SECTIONS = ['details']

export const MARKET_CONFIRMATIONS = ['CONFIRMED', 'DIVERGENT', 'COUNTER_TREND', 'UNKNOWN']

/**
 * Structural validation of a producer payload against the frozen V0 render
 * contract. Returns human-readable problems; empty list = valid.
 * Everything the UI does not render must live under `details`.
 */
export function validateSnapshot(snapshot) {
  const problems = []
  if (!snapshot || typeof snapshot !== 'object') {
    return ['snapshot is not an object']
  }
  if (snapshot.contract !== undefined) {
    problems.push('top-level "contract" is not part of the producer contract; version identity is metadata.snapshot_version')
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
  for (const field of ['snapshot_version', 'snapshot_id', 'as_of', 'decision_time', 'lane', 'run_id', 'model_version']) {
    if (!meta[field]) problems.push(`metadata.${field} is required`)
  }
  if (meta.snapshot_version && meta.snapshot_version !== SNAPSHOT_VERSION_V0) {
    problems.push(`metadata.snapshot_version must be "${SNAPSHOT_VERSION_V0}" (producer-owned), got "${meta.snapshot_version}"`)
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
  const cc = snapshot.climate_components ?? []
  for (const component of ['POLICY_LIQUIDITY', 'FINANCIAL_CONDITIONS', 'MARKET_CONFIRMATION', 'RISK_APPETITE', 'INVESTMENT_CLIMATE']) {
    const entry = cc.find((c) => c.component === component)
    if (!entry) problems.push(`climate_components: missing ${component}`)
    else if (typeof entry.confidence !== 'number') {
      problems.push(`climate_components.${component}.confidence must be numeric`)
    }
  }
  const wc = snapshot.weekly_change ?? {}
  if (!wc.information_set_delta || typeof wc.information_set_delta !== 'object' || Array.isArray(wc.information_set_delta)) {
    problems.push('weekly_change.information_set_delta must be an object {status, events, stale_factors}')
  }
  for (const key of ['macro_state_delta', 'market_condition_delta', 'asset_view_delta']) {
    if (!wc[key] || typeof wc[key] !== 'object' || !Array.isArray(wc[key].entries ?? wc[key].moves)) {
      problems.push(`weekly_change.${key} must be an object with an entries/moves list`)
    }
  }
  const regime = snapshot.regime ?? {}
  for (const field of ['quadrant_label', 'growth_state', 'growth_direction', 'inflation_state', 'inflation_direction', 'dwell_weeks', 'transition_flag', 'confidence', 'coverage']) {
    if (!(field in regime)) problems.push(`regime.${field} is required (producer-owned shape)`)
  }
  return problems
}
