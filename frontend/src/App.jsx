import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CalendarClock, CircleSlash, RefreshCw } from 'lucide-react'
import { SCENARIOS, DEFAULT_SCENARIO_ID, loadSnapshot } from './snapshot/fixtures/index.js'
import { validateSnapshot } from './snapshot/schema.js'
import { confidenceLabel, shortDate } from './lib/format.js'
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

export default function App() {
  const [scenarioId, setScenarioId] = useState(DEFAULT_SCENARIO_ID)
  const [reloadNonce, setReloadNonce] = useState(0)
  const [page, setPage] = useState(1)
  const [selectedAsset, setSelectedAsset] = useState(null)
  const [selectedCluster, setSelectedCluster] = useState(null)

  const snapshot = useMemo(() => loadSnapshot(scenarioId), [scenarioId, reloadNonce])
  const problems = useMemo(() => validateSnapshot(snapshot), [snapshot])

  // Keyboard: `1`..`5` page navigation, `r` reload snapshot/fixture.
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

  const counts = snapshot.data_health_summary?.counts ?? {}
  const rollup = [
    { label: 'stale', value: counts.stale ?? 0, Icon: AlertTriangle },
    { label: 'missing', value: counts.missing ?? 0, Icon: CircleSlash },
    { label: 'blocked', value: counts.blocked ?? 0, Icon: AlertTriangle },
    { label: 'no new info', value: counts.no_new_information ?? 0, Icon: CalendarClock },
  ]

  const PageComponent = PAGES.find((p) => p.id === page)?.component ?? OverviewPage
  const common = { snapshot, selectedAsset, setSelectedAsset, selectedCluster, setSelectedCluster }

  return (
    <div className="flex h-full flex-col bg-ink-950 text-zinc-200">
      {/* Header / status ribbon */}
      <header data-testid="status-ribbon"
        className="flex h-12 shrink-0 items-center gap-3 border-b border-ink-700 bg-ink-900 px-3">
        <span className="text-sm font-bold tracking-tight text-zinc-100">MACRO WORKBENCH</span>
        <LaneBadge lane={snapshot.metadata.lane} />
        <div className="flex items-baseline gap-2 whitespace-nowrap text-xs text-ink-300">
          <span className="font-medium text-zinc-300">as of {shortDate(snapshot.metadata.as_of)}</span>
          <span className="text-ink-500">·</span>
          <span>decision {snapshot.metadata.decision_time}</span>
          <span className="text-ink-500">·</span>
          <span title="run / model identity">{snapshot.metadata.run_id}</span>
        </div>
        <span data-testid="overall-confidence"
          className={`rounded border px-2 py-0.5 text-[11px] font-semibold tabular-nums ${
            confidenceLabel(snapshot.metadata.overall_confidence) === 'LOW'
              ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
              : 'border-sky-500/30 bg-sky-500/10 text-sky-300'
          }`}>
          CONFIDENCE {Math.round(snapshot.metadata.overall_confidence * 100)}%
        </span>
        <div data-testid="stale-blocked-summary" className="flex items-center gap-2 text-[11px]">
          {rollup.map(({ label, value, Icon }) => (
            <span key={label}
              className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 ${
                value > 0
                  ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                  : 'border-zinc-700 bg-zinc-800/40 text-zinc-500'
              }`}>
              <Icon className="h-3 w-3" aria-hidden />
              {value} {label}
            </span>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <select
            aria-label="fixture scenario"
            value={scenarioId}
            onChange={(e) => setScenarioId(e.target.value)}
            className="rounded border border-ink-700 bg-ink-850 px-2 py-1 text-[11px] text-zinc-300">
            {SCENARIOS.map((s) => (
              <option key={s.id} value={s.id}>{s.label}</option>
            ))}
          </select>
          <button type="button" aria-label="reload fixture (r)"
            onClick={() => setReloadNonce((n) => n + 1)}
            className="inline-flex items-center gap-1 rounded border border-ink-700 bg-ink-850 px-2 py-1 text-[11px] text-zinc-300 hover:bg-ink-800">
            <RefreshCw className="h-3 w-3" aria-hidden /> reload
          </button>
        </div>
      </header>

      {/* Page navigation */}
      <nav data-testid="page-nav" className="flex h-8 shrink-0 items-center gap-1 border-b border-ink-700 bg-ink-950 px-3">
        {PAGES.map((p) => (
          <button key={p.id} type="button"
            onClick={() => setPage(p.id)}
            className={`rounded px-2.5 py-1 text-[11px] font-medium ${
              page === p.id ? 'bg-ink-800 text-zinc-100 border border-ink-700' : 'text-ink-300 hover:text-zinc-200'
            }`}>
            <kbd className="mr-1 text-[9px] text-ink-500">{p.key}</kbd>{p.label}
          </button>
        ))}
        {problems.length > 0 && (
          <span data-testid="snapshot-contract-errors" role="alert"
            className="ml-2 rounded border border-rose-500/40 bg-rose-500/10 px-2 py-0.5 text-[10px] text-rose-300">
            snapshot contract violations: {problems.join('; ')}
          </span>
        )}
      </nav>

      <main className="min-h-0 flex-1 overflow-hidden">
        <PageComponent {...common} />
      </main>
    </div>
  )
}
