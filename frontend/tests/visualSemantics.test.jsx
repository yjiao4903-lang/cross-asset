import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ConfidenceBadge, FreshnessChip, StanceChip, ConfirmationChip } from '../src/components/primitives.jsx'

/* Visual semantics frozen by #112:
 * - red/green ONLY for market/stance direction
 * - amber = warning / low confidence / data-health problem
 * - gray = unavailable / NO_NEW_INFORMATION
 * - a data-health failure must never look like a bearish signal */

describe('data-health visual semantics', () => {
  it('renders NO_NEW_INFORMATION as neutral gray, distinct from stale', () => {
    render(<FreshnessChip status="NO_NEW_INFORMATION" />)
    const el = screen.getByTestId('freshness-chip')
    expect(el.className).toContain('text-zinc-400')
    expect(el.className).not.toContain('amber')
    expect(el.className).not.toContain('rose')
    expect(el).toHaveTextContent('NO NEW INFO')
  })

  it('renders stale/missing/blocked as amber — never bearish red', () => {
    for (const status of ['STALE', 'MISSING', 'BLOCKED']) {
      const { getByTestId, unmount } = render(<FreshnessChip status={status} />)
      const el = getByTestId('freshness-chip')
      expect(el.className).toContain('amber')
      expect(el.className).not.toContain('rose')
      unmount()
    }
  })

  it('renders fresh as informational blue, not directional green', () => {
    render(<FreshnessChip status="FRESH" />)
    const el = screen.getByTestId('freshness-chip')
    expect(el.className).toContain('sky')
    expect(el.className).not.toContain('emerald')
  })

  it('low confidence is an amber warning, not a bearish signal', () => {
    render(<ConfidenceBadge confidence={0.35} />)
    const el = screen.getByTestId('confidence-badge')
    expect(el.getAttribute('data-level')).toBe('LOW')
    expect(el.className).toContain('amber')
    expect(el.className).not.toContain('rose')
  })
})

describe('stance direction semantics', () => {
  it('encodes positive/negative stance with green/red allowed', () => {
    const { getByTestId, rerender } = render(<StanceChip stance={2} />)
    expect(getByTestId('stance-chip').className).toContain('emerald')
    rerender(<StanceChip stance={-2} />)
    expect(getByTestId('stance-chip').className).toContain('rose')
    rerender(<StanceChip stance={0} />)
    expect(getByTestId('stance-chip').className).toContain('zinc')
  })

  it('market confirmation COUNTER_TREND is amber (divergence warning), not bearish red', () => {
    render(<ConfirmationChip value="COUNTER_TREND" />)
    const el = screen.getByTestId('confirmation-chip')
    expect(el.className).toContain('amber')
    expect(el.className).not.toContain('rose')
  })

  it('UNKNOWN market confirmation is gray dashed data-state — never a direction', () => {
    render(<ConfirmationChip value="UNKNOWN" />)
    const el = screen.getByTestId('confirmation-chip')
    expect(el.getAttribute('data-confirmation')).toBe('UNKNOWN')
    expect(el.className).toContain('zinc')
    expect(el.className).not.toContain('rose')
    expect(el.className).not.toContain('emerald')
    expect(el.className).not.toContain('amber')
  })

  it('UPDATED information events render as informational blue, not directional', () => {
    render(<FreshnessChip status="UPDATED" />)
    const el = screen.getByTestId('freshness-chip')
    expect(el).toHaveTextContent('UPDATED')
    expect(el.className).toContain('sky')
    expect(el.className).not.toContain('emerald')
  })
})
