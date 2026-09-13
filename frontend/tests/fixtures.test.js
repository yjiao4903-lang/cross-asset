import { describe, expect, it } from 'vitest'
import { SCENARIOS, loadSnapshot } from '../src/snapshot/fixtures/index.js'
import { validateSnapshot } from '../src/snapshot/schema.js'

describe('DashboardSnapshotV0 fixtures', () => {
  it('both scenarios pass the frozen V0 render contract', () => {
    for (const scenario of SCENARIOS) {
      expect(validateSnapshot(scenario.snapshot), scenario.id).toEqual([])
    }
  })

  it('exposes all required top-level sections and nothing else', () => {
    const snap = loadSnapshot('stress')
    for (const section of [
      'metadata', 'macro_climate', 'investment_climate', 'clusters', 'weekly_change',
      'regime', 'asset_views', 'cross_asset_pulse', 'executive_brief', 'data_health_summary',
    ]) {
      expect(snap).toHaveProperty(section)
    }
  })

  it('covers the eight target assets with bounded integer stances', () => {
    const snap = loadSnapshot('stress')
    const assets = snap.asset_views.map((v) => v.asset)
    expect(assets).toEqual(['CN_EQ', 'HK_EQ', 'US_EQ', 'CN_BOND', 'GOLD', 'COPPER', 'USD_CNY', 'CASH'])
    for (const v of snap.asset_views) {
      expect(Number.isInteger(v.stance)).toBe(true)
      expect(v.stance).toBeGreaterThanOrEqual(-2)
      expect(v.stance).toBeLessThanOrEqual(2)
    }
  })

  it('at least one fixture demonstrates the required edge states', () => {
    const snap = loadSnapshot('stress')
    const statuses = snap.data_health_summary.items.map((i) => i.status)
    expect(statuses).toContain('NO_NEW_INFORMATION')
    expect(statuses).toContain('STALE')
    expect(statuses).toContain('MISSING')
    expect(statuses).toContain('BLOCKED')

    // one stance change
    expect(snap.asset_views.some((v) => v.stance !== v.prior_stance)).toBe(true)
    // one counter-trend asset
    expect(snap.asset_views.some((v) => v.market_confirmation === 'COUNTER_TREND')).toBe(true)
    // one low-confidence view
    expect(snap.asset_views.some((v) => v.confidence < 0.45)).toBe(true)
    // NO_NEW_INFORMATION never produces synthetic weekly drift
    const nnis = snap.clusters.filter((c) => c.freshness === 'NO_NEW_INFORMATION')
    expect(nnis.length).toBeGreaterThan(0)
    for (const c of nnis) expect(c.weekly_delta).toBe(0)
  })

  it('market_condition_delta uses bps for yields and % for prices/fx', () => {
    const snap = loadSnapshot('stress')
    for (const m of snap.weekly_change.market_condition_delta) {
      if (m.metric === 'yield') expect(m.unit).toBe('bps')
      else expect(m.unit).toBe('%')
    }
  })

  it('loader returns deterministic deep copies', () => {
    const a = loadSnapshot('benign')
    const b = loadSnapshot('benign')
    expect(a).toEqual(b)
    expect(a).not.toBe(b)
    a.metadata.overall_confidence = 999
    expect(loadSnapshot('benign').metadata.overall_confidence).not.toBe(999)
  })

  it('lane is always a real evidence lane, never FORMAL_OOS by default', () => {
    for (const scenario of SCENARIOS) {
      expect(scenario.snapshot.metadata.lane).toBe('MONITORING')
      expect(scenario.snapshot.data_health_summary.formal_eligibility).toBe('NOT_ELIGIBLE')
    }
  })
})
