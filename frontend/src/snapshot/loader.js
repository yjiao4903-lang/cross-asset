import { adaptSnapshot } from './adapt.js'
import { validateSnapshot } from './schema.js'
import { loadRawSnapshot } from './fixtures/index.js'

export class SnapshotLoadError extends Error {
  constructor(message, problems = []) {
    super(message)
    this.name = 'SnapshotLoadError'
    this.problems = problems
  }
}

export function defaultSnapshotMode() {
  // Vitest is an explicit test/demo surface. Normal dev/build runtime is API-first.
  return import.meta.env.MODE === 'test' ? 'demo' : 'api'
}

export async function fetchLatestSnapshot(fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== 'function') {
    throw new SnapshotLoadError('snapshot API unavailable: fetch is not available')
  }
  let response
  try {
    response = await fetchImpl('/api/snapshot/latest', {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
  } catch (error) {
    throw new SnapshotLoadError(`snapshot API unavailable: ${error?.message ?? 'network error'}`)
  }
  if (!response.ok) {
    throw new SnapshotLoadError(`snapshot API returned HTTP ${response.status}`)
  }
  const raw = await response.json()
  const problems = validateSnapshot(raw)
  if (problems.length > 0) {
    throw new SnapshotLoadError('snapshot API payload violates DashboardSnapshotV0', problems)
  }
  return { raw, snapshot: adaptSnapshot(raw), source: 'api' }
}

export function loadDemoSnapshot(scenarioId) {
  const raw = loadRawSnapshot(scenarioId)
  const problems = validateSnapshot(raw)
  if (problems.length > 0) {
    throw new SnapshotLoadError('demo snapshot violates DashboardSnapshotV0', problems)
  }
  return { raw, snapshot: adaptSnapshot(raw), source: 'demo' }
}
