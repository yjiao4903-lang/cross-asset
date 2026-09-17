import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CalendarClock, CircleSlash, Layers, RefreshCw } from 'lucide-react'
import { SCENARIOS, DEFAULT_SCENARIO_ID } from './snapshot/fixtures/index.js'
import { defaultSnapshotMode, fetchLatestSnapshot, loadDemoSnapshot } from './snapshot/loader.js'
import { validateSnapshot } from './snapshot/schema.js'
import { shortDate } from './lib/format.js'
import { LaneBadge } from './components/primitives.jsx'
import OverviewPage from './pages/OverviewPage.jsx'
import WeeklyPulsePage from './pages/WeeklyPulsePage.jsx'
import HeatmapPage from './pages/HeatmapPage.jsx'
import AssetLensPage from './pages/AssetLensPage.jsx'
import DataHealthPage from './pages/DataHealthPage.jsx'

const PAGES = [
  { id: 1, key: '1', label: 'Overview', component: OverviewPage },
  { id: 2, key: '2', label: 'Weekly Pulse', component: WeeklyPulsePage },
  { id: 3, key: '3', label: 'Heatmap', component: HeatmapPage },
  { id: 4, key: '4', label: 'Asset Lens', component: AssetLensPage },
  { id: 5, key: '5', label: 'Data Health', component: DataHealthPage },
]

export default function App({ mode = defaultSnapshotMode(), loadLatest = fetchLatestSnapshot }) {
  const demoMode = mode === 'demo'
  const [scenarioId, setScenarioId] = useState(DEFAULT_SCENARIO_ID)
  const [reloadNonce, setReloadNonce] = useState(0)
  const [page, setPage] = useState(1)
  const [selectedAsset, setSelectedAsset] = useState(null)
  const [selectedCluster, setSelectedCluster] = useState(null)
  const [bundle, setBundle] = useState(() => (demoMode ? loadDemoSnapshot(DEFAULT_SCENARIO_ID) : null))
  const [loading, setLoading] = useState(!demoMode)
  const [loadError, setLoadError] = useState(null)

  useEffect(() => {
    let cancelled = false
    if (demoMode) {
      try {
        setBundle(loadDemoSnapshot(scenarioId))
        setLoadError(null)
      } catch (error) {
        setBundle(null)
        setLoadError(error)
      }
      setLoading(false)
      return () => { cancelled = true }
    }

    setLoading(true)
    setLoadError(null)
    loadLatest()
      .then((loaded) => {
        if (!cancelled) setBundle(loaded)
      })
      .catch((error) => {
        if (!cancelled) {
          // Fail visibly. Never substitute a golden/demo fixture for a failed API.
          setBundle(null)
          setLoadError(error)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [demoMode, scenarioId, reloadNonce, loadLatest])

  // Keyboard: `1`..`5` page navigation, `r` reload current source.
  useEffect(() => {
    const onKey = (event) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
      const hit = PAGES.find((p) => p.key === event.key)
      if (hit) {
        setPage(hit.id)
      } else if (event.key === 'r' || event.key === 'R') {
        setReloadNonce((n) => n + 1)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const snapshot = bundle?.snapshot ?? null
  const rawSnapshot = bundle?.raw ?? null
  const problems = useMemo(
    () => (rawSnapshot ? validateSnapshot(rawSnapshot) : []),
    [rawSnapshot],
  )

  if (!snapshot) {
    return (
      <div className="flex h-full min-h-screen items-center justify-center bg-app-bg text-txt-primary">
        <div data-testid="snapshot-unavailable" className="max-w-xl rounded border border-border-1 bg-surface-1 p-5">
          <div className="mb-2 flex items-center gap-2 text-sm font-bold">
            <Layers className="h-4 w-4 text-status-accent" aria-hidden />
            MACRO WORKBENCH
          </div>
          <p className="text-sm text-txt-secondary">
            {loading ? 'Loading latest MONITORING snapshot…' : 'Dashboard snapshot unavailable.'}
          </p>
          {loadError && (
            <p role="alert" className="mt-2 text-xs text-status-warning-fg">
              {loadError.message}
            </p>
          )}
          <p className="mt-3 text-[11px] text-txt-muted">
            Normal mode does not fall back to demo fixtures. Retry the snapshot API or explicitly launch demo/test mode.
          </p>
          <button type="button" onClick={() => setReloadNonce((n) => n + 1)}
            className="mt-3 inline-flex items-center gap-1 rounded border border-border-1 bg-input-bg px-2 py-1 text-xs text-txt-secondary">
            <RefreshCw className="h-3 w-3" aria-hidden /> retry
          </button>
        </div>
      </div>
    )
  }

  const dh = snapshot.data_health_summary ?? {}
  const noNewInfoCount = Object.values(dh.family_information_status ?? {})
    .filter((s) => s === 'NO_NEW_INFORMATION').length
  const rollup = [
    { label: 'stale', value: dh.stale_components?.length ?? 0, Icon: AlertTriangle, tone: 'warn' },
    { label: 'missing', value: dh.missing_components?.length ?? 0, Icon: CircleSlash, tone: 'warn' },
    { label: 'blocked', value: dh.blockers?.length ?? 0, Icon: AlertTriangle, tone: 'warn' },
    { label: 'no new info', value: noNewInfoCount, Icon: CalendarClock, tone: 'neutral' },
  ]

  const PageComponent = PAGES.find((p) => p.id === page)?.component ?? OverviewPage
  const common = { snapshot, selectedAsset, setSelectedAsset, selectedCluster, setSelectedCluster }

  return (
    <div className="flex h-full flex-col bg-app-bg text-txt-primary">
      <header data-testid="status-ribbon"
        className="flex h-12 shrink-0 items-center gap-2 border-b border-border-1 bg-surface-1 px-3">
        <div className="flex shrink-0 items-center gap-2">
          <span className="flex items-center gap-1.5 text-sm font-bold tracking-tight text-txt-primary">
            <Layers className="h-3.5 w-3.5 text-status-accent" aria-hidden />
            MACRO WORKBENCH
          </span>
          <LaneBadge lane={snapshot.metadata.lane} />
          {demoMode && (
            <span data-testid="demo-mode-badge"
              className="rounded border border-border-2 bg-surface-2 px-1.5 py-0.5 text-[9px] font-semibold tracking-wider text-txt-muted">
              DEMO / GOLDEN
            </span>
          )}
        </div>

        <nav data-testid="page-nav" className="flex items-center gap-0.5 rounded-md bg-surface-2/60 p-0.5"
          aria-label="Workbench pages">
          {PAGES.map((p) => {
            const active = page === p.id
            return (
              <button key={p.id} type="button" data-testid="nav-tab" data-page={p.id}
                aria-current={active ? 'page' : undefined}
                onClick={() => setPage(p.id)}
                className={`inline-flex items-center gap-1 rounded px-2 py-1 text-[11.5px] font-medium transition-colors duration-75 ${
                  active
                    ? 'bg-surface-sel text-txt-primary ring-1 ring-inset ring-border-2'
                    : 'text-txt-muted hover:bg-surface-hover hover:text-txt-secondary'
                }`}>
                <kbd className={`cx-kbd text-[9.5px] ${active ? 'text-status-accent' : ''}`}>{p.key}</kbd>
                {p.label}
              </button>
            )
          })}
          {problems.length > 0 && (
            <span data-testid="snapshot-contract-errors" role="alert"
              className="ml-1 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-300">
              contract: {problems.length}
            </span>
          )}
        </nav>

        <div className="flex min-w-0 items-baseline gap-1.5 whitespace-nowrap text-[11px] text-txt-muted">
          <span className="font-medium text-txt-secondary">as of {shortDate(snapshot.metadata.as_of)}</span>
          <span aria-hidden>·</span>
          <span>decision {snapshot.metadata.decision_time}</span>
          <span aria-hidden>·</span>
          <span className="truncate" title={`run/model: ${snapshot.metadata.run_id} / ${snapshot.metadata.model_version}`}>
            {snapshot.metadata.run_id}
          </span>
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-2">
          <span data-testid="data-overall"
            title="Producer-owned overall data health (no overall confidence is emitted by DashboardSnapshotV0)"
            className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] font-semibold tracking-wide ${
              dh.overall === 'OK' || dh.overall === 'COMPLETE'
                ? 'border-status-info/30 bg-status-info/10 text-status-info'
                : 'border-status-warning/40 bg-status-warning/10 text-status-warning-fg'
            }`}>
            <span className={`h-1.5 w-1.5 rounded-full ${
              dh.overall === 'OK' || dh.overall === 'COMPLETE' ? 'bg-status-info' : 'bg-status-warning'
            }`} aria-hidden />
            DATA {dh.overall ?? 'N/A'}
          </span>
          <div data-testid="stale-blocked-summary" className="flex items-center gap-1.5 text-[10.5px]">
            {rollup.map(({ label, value, Icon, tone }) => (
              <span key={label} data-health-tone={tone}
                className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 ${
                  value > 0
                    ? tone === 'warn'
                      ? 'bg-status-warning/10 text-status-warning-fg'
                      : 'bg-zinc-500/10 text-zinc-300'
                    : 'bg-surface-2/50 text-txt-metadata'
                }`}>
                <Icon className="h-3 w-3" aria-hidden />
                {value} {label}
              </span>
            ))}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5 opacity-70">
          {demoMode && (
            <>
              <span className="cx-label hidden xl:inline">scenario</span>
              <select
                aria-label="fixture scenario"
                value={scenarioId}
                onChange={(e) => setScenarioId(e.target.value)}
                className="rounded border border-border-1 bg-input-bg px-2 py-1 text-[11px] text-txt-secondary">
                {SCENARIOS.map((s) => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>
            </>
          )}
          <button type="button" aria-label={demoMode ? 'reload fixture (r)' : 'reload snapshot (r)'}
            onClick={() => setReloadNonce((n) => n + 1)}
            className="inline-flex items-center gap-1 rounded border border-border-1 bg-input-bg px-2 py-1 text-[11px] text-txt-secondary hover:bg-surface-hover">
            <RefreshCw className="h-3 w-3" aria-hidden /> reload
          </button>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-hidden">
        <PageComponent {...common} />
      </main>
    </div>
  )
}
