import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from '../src/App.jsx'
import { loadRawSnapshot } from '../src/snapshot/fixtures/index.js'
import {
  SnapshotLoadError,
  defaultSnapshotMode,
  fetchLatestSnapshot,
  loadDemoSnapshot,
} from '../src/snapshot/loader.js'


describe('REAL-SNAPSHOT-V1 frontend loader', () => {
  it('uses explicit demo mode under tests and labels it visibly', () => {
    expect(defaultSnapshotMode()).toBe('demo')
    render(<App mode="demo" />)
    expect(screen.getByTestId('demo-mode-badge')).toHaveTextContent('DEMO / GOLDEN')
    expect(screen.getByLabelText('fixture scenario')).toBeInTheDocument()
  })

  it('normal API loader validates and adapts DashboardSnapshotV0', async () => {
    const raw = loadRawSnapshot('benign')
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => raw,
    })
    const loaded = await fetchLatestSnapshot(fakeFetch)
    expect(fakeFetch).toHaveBeenCalledWith('/api/snapshot/latest', expect.any(Object))
    expect(loaded.source).toBe('api')
    expect(loaded.raw.metadata.snapshot_id).toBe(raw.metadata.snapshot_id)
    expect(loaded.snapshot.metadata.snapshot_id).toBe(raw.metadata.snapshot_id)
  })

  it('API failure is explicit and never falls back to a golden fixture', async () => {
    const loadLatest = vi.fn().mockRejectedValue(new SnapshotLoadError('snapshot API returned HTTP 503'))
    render(<App mode="api" loadLatest={loadLatest} />)
    const unavailable = await screen.findByTestId('snapshot-unavailable')
    expect(unavailable).toHaveTextContent('snapshot API returned HTTP 503')
    expect(unavailable).toHaveTextContent('does not fall back to demo fixtures')
    expect(screen.queryByTestId('demo-mode-badge')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('fixture scenario')).not.toBeInTheDocument()
  })

  it('API mode renders the existing cockpit when latest snapshot resolves', async () => {
    const loadLatest = vi.fn().mockResolvedValue(loadDemoSnapshot('benign'))
    render(<App mode="api" loadLatest={loadLatest} />)
    expect(await screen.findByTestId('overview-page')).toBeInTheDocument()
    expect(screen.getByTestId('lane-badge')).toHaveTextContent('MONITORING')
    expect(screen.queryByTestId('demo-mode-badge')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('fixture scenario')).not.toBeInTheDocument()
  })
})
