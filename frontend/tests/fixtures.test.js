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

  it('carries version identity in metadata.snapshot_version, never a top-level marker', () => {
    for (const scenario of SCENARIOS) {
      expect(scenario.snapshot).not.toHaveProperty('contract')
      expect(String(scenario.snapshot.metadata.snapshot_version)).toBe('0')
    }
    // a #114 payload with a competing top-level contract marker is rejected
    const bad = { ...loadSnapshot('benign'), contract: 'DashboardSnapshotV0' }
    expect(validateSnapshot(bad).some((p) => p.includes('metadata.snapshot_version'))).toBe(true)
  })

  it('policy/liquidity direction is snapshot-provided, not derivable from growth', () => {
    // regression: growth improving must NOT imply EASING — the benign fixture
    // has an improving growth quadrant while policy/liquidity direction is FLAT
    const benign = loadSnapshot('benign')
    expect(benign.regime.quadrant.growth).toBe('IMPROVING')
    const policy = benign.clusters.find((c) => c.id === 'policy_liquidity')
    expect(policy.direction).toBe('FLAT')
    // every scenario provides render-ready policy/liquidity and market-confirmation values
    for (const scenario of SCENARIOS) {
      const p = scenario.snapshot.clusters.find((c) => c.id === 'policy_liquidity')
      const m = scenario.snapshot.clusters.find((c) => c.id === 'market_confirmation')
      expect(p).toBeDefined()
      expect(p.direction).toBeDefined()
      expect(p.confidence).toBeGreaterThan(0)
      expect(m.confidence).toBeGreaterThan(0)
    }
  })

  it('never substitutes a proxy for exact DXY (NO_PROXY_SUBSTITUTION = TRUE)', () => {
    for (const scenario of SCENARIOS) {
      const dh = scenario.snapshot.data_health_summary
      const dxy = dh.items.find((i) => i.series === 'DXY_EXACT')
      expect(dxy?.status).toBe('BLOCKED')
      const dxyNotes = [
        dxy?.note ?? '',
        ...dh.unresolved_contracts.filter((c) => c.id.includes('DXY')).map((c) => c.note),
      ].join(' ')
      expect(dxyNotes.toLowerCase()).toMatch(/no proxy substitution/)
      expect(dxyNotes.toLowerCase()).not.toMatch(/use a disclosed proxy|proxy basket|proxy disclosed/)
      // the displayed USD factor is its own identity and never claims DXY
      const usd = scenario.snapshot.asset_views.find((v) => v.asset === 'USD_CNY')
      for (const driver of usd.drivers) {
        expect(driver.label.toLowerCase()).not.toContain('dxy')
      }
    }
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
