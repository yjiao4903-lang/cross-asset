import { Card, ConfidenceBadge, DirectionArrow, FreshnessChip } from '../components/primitives.jsx'
import { directionSign } from '../lib/format.js'

const HORIZONS = ['CYCLICAL', 'TACTICAL', 'STRUCTURAL_CONTEXT']

/* Heatmap: rows = factor family, columns = horizon class (producer-owned).
 * Cell renders backend direction/score/freshness — no client-side inference.
 * freshness OK→FRESH, PARTIAL→amber, MISSING stays dashed-amber. */
function HeatCell({ cluster, onClick }) {
  const isPartial = cluster.freshness === 'STALE' || cluster.freshness === 'MISSING'
  return (
    <button type="button"
      onClick={onClick}
      title={`${cluster.id} — score ${cluster.score}, ${cluster.direction}, freshness ${cluster.freshness_status}`}
      data-testid="heatmap-cell"
      className={`flex h-16 w-full flex-col items-start justify-between rounded border p-1.5 text-left ${
        isPartial ? 'cursor-pointer border-amber-500/30 bg-amber-500/5 hover:bg-amber-500/10'
        : 'cursor-pointer border-ink-700 bg-ink-850 hover:bg-ink-800'
      }`}>
      <span className="text-[10px] font-semibold text-zinc-200">
        {cluster.direction.replaceAll('_', ' ')} <span className="text-ink-500">({cluster.score > 0 ? '+' : ''}{cluster.score.toFixed(2)})</span>
      </span>
      <span className="flex items-center gap-1">
        <DirectionArrow sign={directionSign(cluster.direction)} />
        <FreshnessChip status={cluster.freshness} />
      </span>
    </button>
  )
}

function DrillDown({ cluster }) {
  if (!cluster) {
    return (
      <p className="text-[11px] text-ink-500">Select a family/horizon cell to inspect producer-owned cluster detail.</p>
    )
  }
  return (
    <div data-testid="heatmap-drilldown" className="grid grid-cols-2 gap-x-6 gap-y-1 text-[11px]">
      <div className="col-span-2 mb-1 flex items-center gap-2">
        <span className="text-xs font-semibold text-zinc-100">{cluster.familyLabel}</span>
        <span className="text-[10px] uppercase tracking-wider text-ink-500">{cluster.horizon} · {cluster.id}</span>
        <ConfidenceBadge confidence={cluster.confidence} />
        <FreshnessChip status={cluster.freshness} />
      </div>
      <span className="text-ink-500">score</span><span className="tabular-nums text-zinc-200">{cluster.score.toFixed(3)}</span>
      <span className="text-ink-500">weekly_delta</span><span className="tabular-nums text-zinc-200">{cluster.weekly_delta > 0 ? '+' : ''}{cluster.weekly_delta.toFixed(3)}</span>
      <span className="text-ink-500">direction</span><span className="text-zinc-200">{cluster.direction}</span>
      <span className="text-ink-500">coverage</span><span className="tabular-nums text-zinc-200">{Math.round(cluster.coverage * 100)}%</span>
      <span className="text-ink-500">top_positive</span>
      <span className="text-zinc-200">{cluster.top_positive.length ? cluster.top_positive.map((t) => t.replaceAll('_', ' ').toLowerCase()).join(', ') : '—'}</span>
      <span className="text-ink-500">top_negative</span>
      <span className="text-zinc-200">{cluster.top_negative.length ? cluster.top_negative.map((t) => t.replaceAll('_', ' ').toLowerCase()).join(', ') : '—'}</span>
      <span className="text-ink-500">missing_factors</span>
      <span className={cluster.missing_factors.length ? 'text-amber-300' : 'text-zinc-200'}>
        {cluster.missing_factors.length ? cluster.missing_factors.join(', ') : '—'}
      </span>
      <span className="text-ink-500">stale_factors</span>
      <span className={cluster.stale_factors.length ? 'text-amber-300' : 'text-zinc-200'}>
        {cluster.stale_factors.length ? cluster.stale_factors.join(', ') : '—'}
      </span>
    </div>
  )
}

export default function HeatmapPage({ snapshot, selectedCluster, setSelectedCluster }) {
  const selected = snapshot.clusters.find((c) => c.id === selectedCluster) ?? null
  const families = [...new Set(snapshot.clusters.map((c) => c.family))]
  const byKey = new Map(snapshot.clusters.map((c) => [`${c.family}@${c.horizon}`, c]))
  return (
    <div data-testid="heatmap-page" className="flex h-full flex-col gap-2 overflow-auto p-2">
      <Card title="Macro factor heatmap — family × horizon (direction + score + freshness; click to drill down)">
        <table className="w-full border-collapse">
          <thead>
            <tr className="text-left text-[9px] uppercase tracking-wider text-ink-500">
              <th className="w-64 pb-1 font-medium">Factor family</th>
              {HORIZONS.map((h) => (
                <th key={h} className="pb-1 font-medium">{h.replaceAll('_', ' ')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {families.map((family) => (
              <tr key={family} className="border-t border-ink-800">
                <td className="py-1.5 pr-2 text-xs text-zinc-200">
                  {snapshot.clusters.find((c) => c.family === family).familyLabel}
                </td>
                {HORIZONS.map((h) => {
                  const c = byKey.get(`${family}@${h}`)
                  return (
                    <td key={h} className="py-1.5 pr-1 align-top">
                      {c ? (
                        <HeatCell cluster={c} onClick={() => setSelectedCluster(c.id)} />
                      ) : (
                        <div className="flex h-16 items-center justify-center rounded border border-dashed border-ink-800 text-[10px] text-ink-500">
                          not modeled
                        </div>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[10px] text-ink-500">
          Amber = PARTIAL freshness (missing/stale factors flagged by the producer — never zero-filled, never a bearish signal).
          Cell state text is the producer-owned direction; no client-side economic inference is applied.
        </p>
      </Card>
      <Card title="Drill-down — producer cluster detail" className="min-h-0 flex-1" bodyClassName="overflow-auto">
        <DrillDown cluster={selected} />
      </Card>
    </div>
  )
}
