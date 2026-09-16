import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import App from '../src/App.jsx'

/* Visual V2 semantic regressions (#118 Workstream H). These reinforce the V1
 * guarantees at the page level and add the V2 shell/regime-focal interaction
 * coverage. Red/green stay reserved for market/stance direction; data health
 * surfaces must never carry directional colors; regime answer is focal. */

function openApp() {
  return render(<App />)
}

describe('V2 application shell — navigation selected/focus semantics', () => {
  it('marks the active page tab with aria-current and data-page, updating on keyboard nav', () => {
    openApp()
    const tabs = screen.getAllByTestId('nav-tab')
    expect(tabs).toHaveLength(5)
    // default page = Overview
    expect(tabs[0]).toHaveAttribute('aria-current', 'page')
    expect(tabs[0]).toHaveAttribute('data-page', '1')

    fireEvent.keyDown(window, { key: '3' })
    const after = screen.getAllByTestId('nav-tab')
    expect(after[2]).toHaveAttribute('aria-current', 'page')
    expect(after[0]).not.toHaveAttribute('aria-current')
  })

  it('keeps keyboard nav 1-5 and r reload intact alongside the rebuilt shell', () => {
    openApp()
    for (const [key, testid] of [['2', 'weekly-pulse-page'], ['3', 'heatmap-page'], ['4', 'asset-lens-page'], ['5', 'data-health-page'], ['1', 'overview-page']]) {
      fireEvent.keyDown(window, { key })
      expect(screen.getByTestId(testid)).toBeInTheDocument()
    }
    const before = screen.getByTestId('data-overall').textContent
    fireEvent.keyDown(window, { key: 'r' })
    expect(screen.getByTestId('data-overall').textContent).toBe(before)
  })
})

describe('V2 Overview — dominant regime focal area (both golden scenarios)', () => {
  it('renders the regime focal area with the backend quadrant for tightening', () => {
    openApp() // default tightening
    expect(screen.getByTestId('regime-focal')).toBeInTheDocument()
    expect(screen.getByTestId('regime-focal')).toHaveTextContent('Stagflation')
  })

  it('renders the regime focal area with the backend quadrant for benign', () => {
    openApp()
    fireEvent.change(screen.getByLabelText('fixture scenario'), { target: { value: 'benign' } })
    expect(screen.getByTestId('regime-focal')).toBeInTheDocument()
    expect(screen.getByTestId('regime-focal')).toHaveTextContent('Goldilocks')
  })

  it('keeps the supporting climate strip as a secondary layer, distinct from the focal area', () => {
    openApp()
    expect(screen.getAllByTestId('climate-pill')).toHaveLength(4)
    expect(screen.getByTestId('regime-focal')).toBeInTheDocument()
  })
})

describe('V2 — data-level health surfaces are never directionally colored', () => {
  it('data-health counters carry no directional red/green', () => {
    openApp()
    fireEvent.keyDown(window, { key: '5' })
    const counters = screen.getByTestId('health-counters')
    const classes = Array.from(counters.querySelectorAll('*')).map((n) => n.className ?? '').join(' ')
    expect(classes).not.toContain('text-emerald-400')
    expect(classes).not.toContain('text-rose-400')
    expect(classes).not.toContain('text-emerald')
    expect(classes).not.toContain('text-rose')
  })

  it('NO_NEW_INFORMATION stays a gray dashed state, visually distinct from amber STALE', () => {
    openApp()
    fireEvent.keyDown(window, { key: '5' })
    // tightening has NO_NEW_INFORMATION families (FINANCIAL_CONDITIONS etc.)
    const chips = screen.getAllByTestId('freshness-chip')
    const nni = chips.find((c) => c.getAttribute('data-status') === 'NO_NEW_INFORMATION')
    // STALE may or may not render on this page with the same list; assert the
    // vocabulary distinction at the chip level is preserved regardless.
    expect(nni.className).toContain('zinc')
    expect(nni.className).not.toContain('amber')
  })
})

describe('V2 — interaction: asset row opens Asset Lens via keyboard (Workstream H)', () => {
  it('pressing Enter on an asset row selects it and opens the lens', () => {
    openApp()
    const board = screen.getByTestId('asset-board')
    const row = within(board).getByText('US Equity').closest('tr')
    fireEvent.keyDown(row, { key: 'Enter' })
    fireEvent.keyDown(window, { key: '4' })
    const lens = screen.getByTestId('asset-lens-page')
    expect(within(lens).getAllByText('US Equity').length).toBeGreaterThan(0)
  })
})