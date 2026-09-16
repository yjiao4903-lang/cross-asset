import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import App from '../src/App.jsx'
import { loadSnapshot } from '../src/snapshot/fixtures/index.js'

function openApp() {
  return render(<App />)
}

describe('App shell', () => {
  it('renders the status ribbon with lane, producer data-overall and stale/blocked rollup', () => {
    openApp()
    expect(screen.getByTestId('status-ribbon')).toHaveTextContent('MACRO WORKBENCH')
    expect(screen.getByTestId('lane-badge')).toHaveTextContent('MONITORING')
    // producer emits no overall confidence; header shows backend data_health overall
    expect(screen.getByTestId('data-overall')).toHaveTextContent('DATA PARTIAL')
    expect(screen.getByTestId('stale-blocked-summary')).toHaveTextContent('stale')
  })

  it('shows no snapshot contract violations for the authoritative golden payloads', () => {
    openApp()
    expect(screen.queryByTestId('snapshot-contract-errors')).not.toBeInTheDocument()
  })

  it('renders the four climate pills and the eight-asset board on Overview', () => {
    openApp()
    expect(screen.getAllByTestId('climate-pill')).toHaveLength(4)
    expect(screen.getByTestId('overview-page')).toBeInTheDocument()
    const board = screen.getByTestId('asset-board')
    const snap = loadSnapshot('tightening')
    for (const v of snap.asset_views) {
      expect(within(board).getByText(v.label)).toBeInTheDocument()
    }
  })

  it('renders climate pills from backend climate_components for both golden scenarios', () => {
    const { unmount } = openApp()
    // default scenario = tightening: FINANCIAL_CONDITIONS must show TIGHTENING
    let pills = screen.getAllByTestId('climate-pill')
    expect(pills[1]).toHaveTextContent('TIGHTENING')
    unmount()

    openApp()
    const select = screen.getByLabelText('fixture scenario')
    fireEvent.change(select, { target: { value: 'benign' } })
    // benign: FINANCIAL_CONDITIONS must show EASING, POLICY_LIQUIDITY shows NEUTRAL —
    // a growth-derived inference (growth RISING ⇒ "EASING") could not produce "NEUTRAL / EASING"
    pills = screen.getAllByTestId('climate-pill')
    expect(pills[1]).toHaveTextContent('NEUTRAL / EASING')
    expect(pills[2]).toHaveTextContent('TRENDING UP')
    expect(pills[3]).toHaveTextContent('RISK ON')
  })
})

describe('golden regression — all five pages render for both scenarios', () => {
  for (const scenario of ['tightening', 'benign']) {
    it(`navigates pages 1-5 without contract errors or runtime exceptions (${scenario})`, () => {
      openApp()
      fireEvent.change(screen.getByLabelText('fixture scenario'), { target: { value: scenario } })
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
      expect(screen.queryByTestId('snapshot-contract-errors')).not.toBeInTheDocument()
    })
  }
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
    const before = screen.getByTestId('data-overall').textContent
    fireEvent.keyDown(window, { key: 'r' })
    expect(screen.getByTestId('data-overall').textContent).toBe(before)
  })
})

describe('drill-down interaction', () => {
  it('clicking an asset row on Overview opens that asset in Asset Lens', () => {
    openApp()
    fireEvent.click(within(screen.getByTestId('asset-board')).getByText('US Equity'))
    fireEvent.keyDown(window, { key: '4' })
    const page = screen.getByTestId('asset-lens-page')
    expect(within(page).getAllByText('US Equity').length).toBeGreaterThan(0)
  })

  it('clicking a heatmap cell exposes the drill-down panel', () => {
    openApp()
    fireEvent.keyDown(window, { key: '3' })
    const page = screen.getByTestId('heatmap-page')
    fireEvent.click(within(page).getAllByTestId('heatmap-cell')[0])
    expect(screen.getByTestId('heatmap-drilldown')).toHaveTextContent('weekly_delta')
  })
})

describe('scenario switching', () => {
  it('switches between the two authoritative golden states via the selector', () => {
    openApp()
    const select = screen.getByLabelText('fixture scenario')
    // default tightening: first board row is CN_EQ at -1 (changed from prior 0)
    let board = screen.getByTestId('asset-board')
    expect(within(board).getAllByTestId('stance-chip')[0].getAttribute('data-stance')).toBe('-1')
    fireEvent.change(select, { target: { value: 'benign' } })
    // benign golden: CN_EQ at 0
    board = screen.getByTestId('asset-board')
    expect(within(board).getAllByTestId('stance-chip')[0].getAttribute('data-stance')).toBe('0')
  })
})
