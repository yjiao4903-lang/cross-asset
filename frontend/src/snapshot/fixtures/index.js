import benignGolden from '../golden/snapshot_benign.json?raw'
import tighteningGolden from '../golden/snapshot_tightening.json?raw'
import manifest from '../golden/manifest.json'
import { adaptSnapshot } from '../adapt.js'

export { manifest as GOLDEN_MANIFEST }

export const SCENARIOS = [
  { id: 'benign', label: 'A — Benign (authoritative #117 golden)', raw: benignGolden },
  { id: 'tightening', label: 'B — Tightening (authoritative #117 golden)', raw: tighteningGolden },
]

const byId = new Map(SCENARIOS.map((s) => [s.id, s]))

export const DEFAULT_SCENARIO_ID = 'tightening'

/**
 * Deterministic snapshot loader: parses the authoritative producer golden JSON
 * and adapts it for rendering (presentation-only). `r` (reload) always
 * restarts from identical state.
 */
export function loadSnapshot(scenarioId = DEFAULT_SCENARIO_ID) {
  const scenario = byId.get(scenarioId) ?? byId.get(DEFAULT_SCENARIO_ID)
  return adaptSnapshot(JSON.parse(scenario.raw))
}

/** Raw (unadapted) producer payload, for contract/regression tests. */
export function loadRawSnapshot(scenarioId = DEFAULT_SCENARIO_ID) {
  const scenario = byId.get(scenarioId) ?? byId.get(DEFAULT_SCENARIO_ID)
  return JSON.parse(scenario.raw)
}
