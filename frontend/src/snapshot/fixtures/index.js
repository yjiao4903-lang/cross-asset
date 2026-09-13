import { benignMixed } from './benignMixed.js'
import { deterioratingTightening } from './deterioratingTightening.js'

export const SCENARIOS = [
  { id: 'benign', label: 'A — Benign / Mixed Confirmation', snapshot: benignMixed },
  { id: 'stress', label: 'B — Deteriorating / Stagflation Risk', snapshot: deterioratingTightening },
]

const byId = new Map(SCENARIOS.map((s) => [s.id, s]))

export const DEFAULT_SCENARIO_ID = 'stress'

/**
 * Deterministic snapshot loader for the fixture mode. Returns a fresh
 * structured clone so `r` (reload) always restarts from identical state.
 */
export function loadSnapshot(scenarioId = DEFAULT_SCENARIO_ID) {
  const scenario = byId.get(scenarioId) ?? byId.get(DEFAULT_SCENARIO_ID)
  return structuredClone(scenario.snapshot)
}
