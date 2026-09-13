import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import App from '../src/App.jsx'
import { loadSnapshot } from '../src/snapshot/fixtures/index.js'

function openApp() {
  return render(<App />)
}

describe('App shell', () => {
  it('renders the status ribbon with lane, confidence and stale/blocked rollup', () => {
    openApp()
    expect(screen.getByTestId('status-ribbon')).toHaveTextContent('MACRO WORKBENCH')
    expect(screen.getByTestId('lane-badge')).toHaveTextContent('MONITORING')
    expect(screen.getByTestId('overall-confidence')).toHaveTextContent('CONFIDENCE')
    expect(screen.getByTestId('stale-blocked-summary')).toHaveTextContent('stale')
  })

  it('shows no snapshot contract violations for the built-in fixtures', () => {
    openApp()
    expect(screen.queryByTestId('snapshot-contract-errors')).not.toBeInTheDocument()
  })

  it('renders the four climate pills and the eight-asset board on Overview', () => {
    openApp()
    expect(screen.getAllByTestId('climate-pill')).toHaveLength(4)
    expect(screen.getByTestId('overview-page')).toBeInTheDocument()
    const board = screen.getByTestId('asset-board')
    const snap = loadSnapshot('stress')
    for (const v of snap.asset_views) {
      expect(within(board).getByText(v.label)).toBeInTheDocument()
    }
  })

  it('renders climate pills from their own cluster fields, without cross-lens derivation', () => {
    openApp()
    const pills = screen.getAllByTestId('climate-pill')
    const snap = loadSnapshot('stress')
    const policy = snap.clusters.find((c) => c.id === 'policy_liquidity')
    const market = snap.clusters.find((c) => c.id === 'market_confirmation')
    // pill 2 shows the policy/liquidity cluster's own direction+confidence
    expect(pills[1]).toHaveTextContent(policy.state.replace(/_/g, ' '))
    expect(pills[1].textContent).toContain(`${Math.round(policy.confidence * 100)}%`)
    // pill 3 shows the market-confirmation cluster's own confidence, not macro_climate's
    expect(pills[2].textContent).toContain(`${Math.round(market.confidence * 100)}%`)
    expect(`${Math.round(snap.macro_climate.confidence * 100)}%`).not.toBe(`${Math.round(market.confidence * 100)}%`)
  })
})

describe('keyboard interaction (V1 contract: 1-5 navigate, r reload)', () => {
  it('navigates to pages 1-5 with number keys', () => {
    openApp()
    fireEvent.keyDown(window, { key: '2' })
    expect(screen.getByTestId('weekly-pulse-page')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: '3' })
    expect(screen.getByTestId('heatmap-page')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: '4' })
    expect(screen.getByTestId('asset-lens-page')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: '5' })
    expect(screen.getByTestId('data-health-page')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: '1' })
    expect(screen.getByTestId('overview-page')).toBeInTheDocument()
  })

  it('reloads the fixture with the r key (state resets deterministically)', () => {
    openApp()
    const select = screen.getByLabelText('fixture scenario')
    fireEvent.change(select, { value: 'benign' })
    fireEvent.change(select, { target: { value: 'benign' } })
    const before = screen.getByTestId('overall-confidence').textContent
    fireEvent.keyDown(window, { key: 'r' })
    expect(screen.getByTestId('overall-confidence').textContent).toBe(before)
  })
})

describe('drill-down interaction', () => {
  it('clicking an asset row on Overview opens that asset in Asset Lens', () => {
    openApp()
    fireEvent.click(within(screen.getByTestId('asset-board')).getByText('US Equity'))
    fireEvent.keyDown(window, { key: '4' })
    const page = screen.getByTestId('asset-lens-page')
    // the lens defaults to the selected asset (US Equity)
    expect(within(page).getAllByText('US Equity').length).toBeGreaterThan(0)
  })

  it('clicking a heatmap cell exposes the drill-down panel', () => {
    openApp()
    fireEvent.keyDown(window, { key: '3' })
    const cell = screen.getAllByTestId('heatmap-page')[0]
    fireEvent.click(within(cell).getByTitle(/Inflation & Cost Pressure — GLOBAL/))
    expect(screen.getByTestId('heatmap-drilldown')).toHaveTextContent('Inflation')
  })
})

describe('scenario switching', () => {
  it('switches between the two fixture states via the scenario selector', () => {
    openApp()
    const select = screen.getByLabelText('fixture scenario')
    fireEvent.change(select, { target: { value: 'benign' } })
    const board = screen.getByTestId('asset-board')
    // benign fixture: first board row is CN_EQ at NEUTRAL (0), changed from prior -1
    expect(within(board).getAllByTestId('stance-chip')[0].getAttribute('data-stance')).toBe('0')
  })
})
