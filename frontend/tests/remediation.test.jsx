import { describe, expect, it, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import App from '../src/App.jsx'
import HeatmapPage from '../src/pages/HeatmapPage.jsx'
import OverviewPage from '../src/pages/OverviewPage.jsx'
import { FreshnessChip } from '../src/components/primitives.jsx'

afterEach(cleanup)

/* =====================================================================
 * #118 UI-AUDIT remediation regressions (second收口).
 * The legal DashboardSnapshotV0 producer contract permits nullable cluster
 * score / weekly_delta, Contributor objects for top_positive/top_negative,
 * and four quadrant enums. These regressions prove the UI consumes that
 * contract without crashing, without inventing values, and without using
 * directional colors on non-directional states.
 * ===================================================================== */

/* ---- UI-AUDIT-01: nullable heatmap values + Contributor objects ---- */

function heatmapSnapshot() {
  return {
    clusters: [{
      id: 'F@CYCLICAL',
      family: 'F',
      familyLabel: 'Factor',
      horizon: 'CYCLICAL',
      direction: 'FLAT',
      score: null,
      weekly_delta: null,
      confidence: 0.5,
      coverage: null,
      freshness: 'PARTIAL',
      freshness_status: 'PARTIAL',
      top_positive: [{ factor_id: 'US_ISM_PMI', contribution: 0.12 }],
      top_negative: [{ factor_id: 'CN_MFG_PMI', contribution: -0.3 }],
      missing_factors: [],
      stale_factors: [],
    }],
  }
}

describe('UI-AUDIT-01 — nullable cluster values and Contributor objects do not crash the Heatmap', () => {
  it('primary heatmap cells render null score/delta as unavailable, never as zero', () => {
    render(<HeatmapPage snapshot={heatmapSnapshot()} selectedCluster={null} setSelectedCluster={() => {}} />)
    const cell = screen.getAllByTestId('heatmap-cell')[0]
    expect(cell).toBeInTheDocument()
    expect(cell).not.toHaveTextContent('0.00') // null must not degrade to 0
  })

  it('drill-down consumes Contributor objects and keeps null values unavailable', () => {
    render(
      <HeatmapPage snapshot={heatmapSnapshot()} selectedCluster="F@CYCLICAL" setSelectedCluster={() => {}} />,
    )
    const dd = screen.getByTestId('heatmap-drilldown')
    expect(dd).toBeInTheDocument()
    expect(dd).toHaveTextContent('us ism pmi')   // Contributor.factor_id consumed
    expect(dd).toHaveTextContent('cn mfg pmi')
    expect(dd).not.toHaveTextContent('0.000')     // null score not 0
    expect(dd.textContent).toContain('—')         // explicit unavailable dash
  })
})

/* ---- UI-AUDIT-02: all four producer quadrant enums render + activate ---- */

function overviewSnapshot(quadrantLabel) {
  const climateComp = { state: 'NEUTRAL', direction: 'FLAT', confidence: 0.5, coverage: 1 }
  return {
    macro_climate: { state: 'x', direction: 'FLAT', score: 0, confidence: 0.5, coverage: 1, summary: 'test summary' },
    investment_climate: { state: 'NEUTRAL', direction: 'FLAT', confidence: 0.5, coverage: 1 },
    climate: {
      POLICY_LIQUIDITY: climateComp,
      FINANCIAL_CONDITIONS: climateComp,
      MARKET_CONFIRMATION: climateComp,
      RISK_APPETITE: climateComp,
    },
    regime: {
      quadrant_label: quadrantLabel,
      growth_state: 'NEUTRAL',
      growth_direction: 'FLAT',
      inflation_state: 'NEUTRAL',
      inflation_direction: 'FLAT',
      dwell_weeks: 1,
      transition: false,
      confidence: 0.5,
      coverage: 1,
      lens_disagreement: { flag: false, summary: '' },
    },
    asset_views: [],
    weekly_change: { events: [], information_status: 'UPDATED', stale_factors: [], market_moves: [] },
    executive_brief: { what_changed: '', why_it_matters: '', what_to_watch: [] },
  }
}

const QUADRANT_TO_CELL = {
  GOLDILOCKS: 'soft landing',
  REFLATION: 'expansion',
  STAGFLATION_RISK: 'stagnation',
  DISINFLATIONARY_SLUMP: 'contraction',
}
const QUADRANT_TO_SHORT = {
  GOLDILOCKS: 'Goldilocks',
  REFLATION: 'Reflation',
  STAGFLATION_RISK: 'Stagflation',
  DISINFLATIONARY_SLUMP: 'Disinfl. slump',
}

describe('UI-AUDIT-02 — all four producer quadrant enums render and activate the correct cell', () => {
  for (const [label, cellLabel] of Object.entries(QUADRANT_TO_CELL)) {
    it(`renders ${label} and activates the ${cellLabel} quadrant`, () => {
      render(<OverviewPage snapshot={overviewSnapshot(label)} setSelectedAsset={() => {}} />)
      expect(screen.getByTestId('regime-focal')).toHaveTextContent(QUADRANT_TO_SHORT[label])
      // exactly one quadrant active, and it is the correct one (no missing state)
      const allActive = document.querySelectorAll('[data-active="true"]')
      expect(allActive.length).toBe(1)
      expect(allActive[0].getAttribute('data-quadrant')).toBe(cellLabel)
    })
  }
})

/* ---- UI-AUDIT-03: NO_NEW_INFORMATION shell rollup is neutral, not warning ---- */

describe('UI-AUDIT-03 — NO_NEW_INFORMATION shell rollup uses a neutral path, distinct from STALE', () => {
  it('no-new-information chip is neutral (zinc) while stale/blocked chips are warning amber', () => {
    render(<App />) // tightening fixture: 4 NO_NEW_INFORMATION, 3 stale, 3 missing, 1 blocked
    const rollup = screen.getByTestId('stale-blocked-summary')
    const chips = Array.from(rollup.querySelectorAll('[data-health-tone]'))

    const nni = chips.find((c) => c.getAttribute('data-health-tone') === 'neutral')
    expect(nni).toBeTruthy()
    expect(nni.className).toContain('zinc')
    expect(nni.className).not.toContain('amber')
    expect(nni.className).not.toContain('status-warning')

    const warnChips = chips.filter((c) => c.getAttribute('data-health-tone') === 'warn' && c.textContent.match(/stale|missing|blocked/))
    expect(warnChips.length).toBeGreaterThan(0)
    const warnCls = warnChips.map((c) => c.className).join(' ')
    expect(warnCls).toContain('status-warning')
    expect(warnCls).not.toContain('text-emerald')
  })
})

/* ---- UI-AUDIT-04: PARTIAL and STALE differ in a non-text visual attribute ---- */

describe('UI-AUDIT-04 — PARTIAL and STALE are visually distinct (not just label)', () => {
  it('PARTIAL uses a dashed amber border while STALE uses a solid amber border', () => {
    const p = render(<FreshnessChip status="PARTIAL" />)
    const pc = p.container.firstChild
    expect(pc.className).toContain('border-dashed')

    cleanup()
    const s = render(<FreshnessChip status="STALE" />)
    const sc = s.container.firstChild
    expect(sc.className).not.toContain('border-dashed')
    expect(sc.className).toContain('border-solid')

    expect(pc.className).not.toEqual(sc.className)
  })
})

/* ---- UI-AUDIT-06: non-directional colors stay non-directional ---- */

describe('UI-AUDIT-06 — structural / data surfaces must not carry directional red-green', () => {
  it('Overview "Genuine market-condition move" heading is neutral, not positive green', () => {
    render(<App />) // Overview default tightening
    const heading = screen.getByText('Genuine market-condition move')
    expect(heading.className).not.toContain('text-status-positive')
    expect(heading.className).not.toContain('text-emerald')
  })

  it('data / contract surfaces carry no rose/red structural color', () => {
    render(<App />)
    const ribbon = screen.getByTestId('status-ribbon')
    const classes = Array.from(ribbon.querySelectorAll('*')).map((n) => n.className ?? '').join(' ')
    // contract error + shell must never look bearish (no rose/red)
    expect(classes).not.toContain('rose-')
    expect(classes).not.toContain('text-red')
    expect(classes).not.toContain('border-red')
  })
})