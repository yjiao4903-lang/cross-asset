import { Card, DirectionArrow, FreshnessChip, ConfidenceBadge } from '../components/primitives.jsx'
import { directionSign } from '../lib/format.js'

const REGIONS = ['US', 'CN', 'GLOBAL']

/* heatmap cells: state color is semantic (direction), freshness is a chip.
 * NO_NEW_INFORMATION cells are visually distinct (dashed gray, not stale-amber). */
function HeatCell({ cluster, region, onClick }) {
  const active = cluster.region === region || region === 'GLOBAL'
  const noNewInfo = cluster.freshness === 'NO_NEW_INFORMATION'
  return (
    <button type="button"
      disabled={!active}
      onClick={onClick}
      title={`${cluster.label} — ${region}${noNewInfo ? ' (no new information this week)' : ''}`}
      className={`flex h-16 flex-col items-start justify-between rounded border p-1.5 text-left ${
        !active ? 'cursor-not-allowed border-ink-800 bg-ink-950/40 opacity-30'
        : noNewInfo ? 'cursor-pointer border-zinc-600/40 border-dashed bg-zinc-500/5 hover:bg-zinc-500/10'
        : 'cursor-pointer border-ink-700 bg-ink-850 hover:bg-ink-800'
      }`}>
      <span className={`text-[10px] font-semibold ${noNewInfo ? 'text-zinc-400' : 'text-zinc-200'}`}>
        {cluster.state.replace(/_/g, ' ')}
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
      <p className="text-[11px] text-ink-500">Select a factor family to inspect contributors and method.</p>
    )
  }
  const sorted = [...cluster.contributors].sort((a, b) => b.contribution - a.contribution)
  const maxAbs = Math.max(...sorted.map((c) => Math.abs(c.contribution)), 0.01)
  return (
    <div data-testid="heatmap-drilldown">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs font-semibold text-zinc-100">{cluster.label}</span>
        <span className="text-[10px] uppercase tracking-wider text-ink-500">{cluster.horizon} · {cluster.region}</span>
        <ConfidenceBadge confidence={cluster.confidence} />
        <FreshnessChip status={cluster.freshness} />
      </div>
      <ul className="space-y-1">
        {sorted.map((c) => {
          const width = Math.abs(c.contribution) / maxAbs * 50
          return (
            <li key={c.label} className="flex items-center gap-2 text-[11px]">
              <span className="w-56 shrink-0 truncate text-zinc-200">{c.label}</span>
              <div className="relative h-3 flex-1">
                <div className="absolute left-1/2 top-0 h-full w-px bg-ink-700" />
                {c.contribution !== 0 && (
                  <div
                    className={`absolute top-0.5 h-2 rounded-sm ${c.contribution > 0 ? 'bg-emerald-500/70' : 'bg-rose-500/70'}`}
                    style={c.contribution > 0 ? { left: '50%', width: `${width}%` } : { right: '50%', width: `${width}%` }}
                  />
                )}
              </div>
              <span className={`w-12 shrink-0 text-right tabular-nums font-semibold ${c.contribution > 0 ? 'text-emerald-400' : c.contribution < 0 ? 'text-rose-400' : 'text-zinc-500'}`}>
                {c.contribution > 0 ? '+' : ''}{c.contribution.toFixed(2)}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default function HeatmapPage({ snapshot, selectedCluster, setSelectedCluster }) {
  const selected = snapshot.clusters.find((c) => c.id === selectedCluster) ?? null
  return (
    <div data-testid="heatmap-page" className="flex h-full flex-col gap-2 overflow-auto p-2">
      <Card title="Macro factor heatmap — state + direction + freshness (click a cell to drill down)">
        <table className="w-full border-collapse">
          <thead>
            <tr className="text-left text-[9px] uppercase tracking-wider text-ink-500">
              <th className="w-56 pb-1 font-medium">Factor family</th>
              {REGIONS.map((r) => (
                <th key={r} className="pb-1 font-medium">{r}</th>
              ))}
              <th className="w-24 pb-1 font-medium">Horizon</th>
              <th className="w-28 pb-1 font-medium">WoW Δ</th>
            </tr>
          </thead>
          <tbody>
            {snapshot.clusters.map((c) => (
              <tr key={c.id} className="border-t border-ink-800">
                <td className="py-1.5 pr-2 text-xs text-zinc-200">{c.label}</td>
                {REGIONS.map((r) => (
                  <td key={r} className="py-1.5 pr-1">
                    <HeatCell cluster={c} region={r} onClick={() => setSelectedCluster(c.id)} />
                  </td>
                ))}
                <td className="py-1.5 text-[10px] text-ink-300">{c.horizon}</td>
                <td className={`py-1.5 text-[11px] font-semibold tabular-nums ${c.weekly_delta > 0 ? 'text-emerald-400' : c.weekly_delta < 0 ? 'text-rose-400' : 'text-zinc-500'}`}>
                  {c.weekly_delta > 0 ? '+' : ''}{c.weekly_delta.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[10px] text-ink-500">
          Gray dashed = <span className="text-zinc-400">NO_NEW_INFORMATION</span> (low-frequency series awaiting next print — not stale, not bearish).
          Amber = stale / missing / blocked data-health problem. Cells outside a family's region are inactive.
        </p>
      </Card>
      <Card title="Drill-down — components / contributors" className="min-h-0 flex-1" bodyClassName="overflow-auto">
        <DrillDown cluster={selected} />
      </Card>
    </div>
  )
}
