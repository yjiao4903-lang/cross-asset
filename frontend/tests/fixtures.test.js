import { createHash } from 'node:crypto'
import { describe, expect, it } from 'vitest'
import { GOLDEN_MANIFEST, SCENARIOS, loadRawSnapshot, loadSnapshot } from '../src/snapshot/fixtures/index.js'
import { validateSnapshot } from '../src/snapshot/schema.js'
import { mapConfirmation } from '../src/snapshot/adapt.js'

function sha256(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex')
}

describe('authoritative #117 golden fixtures', () => {
  it('are byte-equivalent to the accepted producer fixtures (sha256 vs manifest)', () => {
    for (const scenario of SCENARIOS) {
      const normalized = scenario.raw.replace(/\r\n/g, '\n')
      expect(sha256(normalized), scenario.id).toBe(GOLDEN_MANIFEST.sha256[`snapshot_${scenario.id}.json`])
    }
    expect(GOLDEN_MANIFEST.source_commit).toBe('c64ae88d4851dc5ee1847a20e24a6cce00b5942f')
  })

  it('both payloads pass the producer-owned V0 contract validation', () => {
    for (const scenario of SCENARIOS) {
      expect(validateSnapshot(loadRawSnapshot(scenario.id)), scenario.id).toEqual([])
    }
  })

  it('carries version identity in metadata.snapshot_version === "DashboardSnapshotV0"', () => {
    for (const scenario of SCENARIOS) {
      const raw = loadRawSnapshot(scenario.id)
      expect(raw).not.toHaveProperty('contract')
      expect(raw.metadata.snapshot_version).toBe('DashboardSnapshotV0')
    }
    const bad = { ...loadRawSnapshot('benign'), contract: 'DashboardSnapshotV0' }
    expect(validateSnapshot(bad).some((p) => p.includes('metadata.snapshot_version'))).toBe(true)
  })

  it('covers the eight target assets with bounded integer stances', () => {
    const raw = loadRawSnapshot('tightening')
    expect(raw.asset_views.map((v) => v.asset)).toEqual(
      ['CN_EQ', 'HK_EQ', 'US_EQ', 'CN_BOND', 'GOLD', 'COPPER', 'USD_CNY', 'CASH'],
    )
    for (const v of raw.asset_views) {
      expect(Number.isInteger(v.stance)).toBe(true)
      expect(v.stance).toBeGreaterThanOrEqual(-2)
      expect(v.stance).toBeLessThanOrEqual(2)
    }
  })
})

describe('producer semantic requirements (WEB-CONTROL 5654314322)', () => {
  it('FINANCIAL_CONDITIONS is EASING in benign and TIGHTENING in tightening (rendered directly)', () => {
    expect(loadRawSnapshot('benign').climate_components.find((c) => c.component === 'FINANCIAL_CONDITIONS').state).toBe('EASING')
    expect(loadRawSnapshot('tightening').climate_components.find((c) => c.component === 'FINANCIAL_CONDITIONS').state).toBe('TIGHTENING')
  })

  it('policy/liquidity is backend-owned and independent of growth direction', () => {
    // benign: growth EXPANDING/RISING while POLICY_LIQUIDITY is NEUTRAL/FLAT —
    // a growth-derived inference could never produce this combination
    const benign = loadRawSnapshot('benign')
    expect(benign.regime.growth_state).toBe('EXPANDING')
    expect(benign.regime.growth_direction).toBe('RISING')
    const policy = benign.climate_components.find((c) => c.component === 'POLICY_LIQUIDITY')
    expect(policy.state).toBe('NEUTRAL')
    expect(policy.direction).toBe('FLAT')
  })

  it('never substitutes a proxy for exact DXY (NO_PROXY_SUBSTITUTION = TRUE)', () => {
    for (const scenario of SCENARIOS) {
      const text = JSON.stringify(loadRawSnapshot(scenario.id)).toLowerCase()
      expect(text).not.toMatch(/proxy basket|proxy disclosed|disclosed proxy|dxy proxy/)
      // the displayed USD factor is its own identity (pulse entry USD_CNY), never DXY
      const raw = loadRawSnapshot(scenario.id)
      expect(raw.cross_asset_pulse.entries.some((e) => e.asset === 'USD_CNY')).toBe(true)
      expect(raw.cross_asset_pulse.entries.some((e) => e.asset === 'DXY')).toBe(false)
    }
  })

  it('NO_NEW_INFORMATION causes zero macro-state drift (no synthetic movement)', () => {
    const entries = loadRawSnapshot('tightening').weekly_change.macro_state_delta.entries
    const nnis = entries.filter((e) => e.cause === 'NO_NEW_INFORMATION')
    expect(nnis.length).toBeGreaterThan(0)
    for (const e of nnis) expect(e.delta).toBe(0)
  })

  it('UNKNOWN market confirmation is accepted vocabulary and adapts to a data-state, not a direction', () => {
    expect(mapConfirmation('CONFIRMED')).toBe('CONFIRMED')
    expect(mapConfirmation('DIVERGENT')).toBe('DIVERGENT')
    expect(mapConfirmation('COUNTER_TREND')).toBe('COUNTER_TREND')
    expect(mapConfirmation('UNKNOWN')).toBe('UNKNOWN')
    expect(mapConfirmation('UNAVAILABLE')).toBe('UNKNOWN')
    expect(mapConfirmation('SOMETHING_ELSE')).toBe('UNKNOWN')
  })
})

describe('presentation adapter (adapt.js)', () => {
  it('parses driver strings verbatim without recomputing values', () => {
    const view = loadSnapshot('benign').asset_views.find((v) => v.asset === 'CN_EQ')
    const numeric = view.drivers.filter((d) => d.contribution !== null)
    expect(numeric.length).toBeGreaterThan(0)
    // e.g. backend emits "CHINA_CYCLE:-0.22" → label CHINA_CYCLE, contribution -0.22 exactly
    expect(numeric.some((d) => d.label === 'CHINA_CYCLE' && d.contribution === -0.22)).toBe(true)
    // qualitative driver keeps null contribution — no economic value is fabricated
    const qualitative = loadSnapshot('benign').asset_views.flatMap((v) => v.drivers).filter((d) => d.contribution === null)
    for (const d of qualitative) expect(d.label).not.toBe('')
  })

  it('adapts freshness and data-health vocabulary to display states', () => {
    const tightening = loadSnapshot('tightening')
    // GOLD has data_health PARTIAL in the producer payload → amber STALE display state
    const gold = tightening.asset_views.find((v) => v.asset === 'GOLD')
    expect(gold.data_health_status).toBe('PARTIAL')
    expect(gold.data_health).toBe('STALE')
  })

  it('loader returns deterministic fresh adaptations', () => {
    const a = loadSnapshot('benign')
    const b = loadSnapshot('benign')
    expect(a).toEqual(b)
    expect(a).not.toBe(b)
  })
})
