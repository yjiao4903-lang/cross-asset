import {
  Bar, BarChart, Cell, ResponsiveContainer, ReferenceLine, XAxis, YAxis, Tooltip,
} from 'recharts'
import { Card, ConfidenceBadge, ConfirmationChip, DirectionArrow, FreshnessChip, StanceChip } from '../components/primitives.jsx'
import { confidenceLabel, stanceLabel } from '../lib/format.js'

const POS = '#34d399'
const NEG = '#fb7185'

function DriverBars({ drivers }) {
  const data = drivers.map((d) => ({ name: d.label, contribution: d.contribution }))
  const height = Math.max(data.length * 34, 60)
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 24, left: 0, bottom: 0 }}>
          <XAxis type="number" domain={[-2, 2]} tick={{ fill: '#5b6b8c', fontSize: 9 }} />
          <YAxis type="category" dataKey="name" width={200} tick={{ fill: '#9fb0cf', fontSize: 10 }} />
          <Tooltip contentStyle={{ background: '#141926', border: '1px solid #263047', fontSize: 11 }} />
          <ReferenceLine x={0} stroke="#263047" />
          <Bar dataKey="contribution" isAnimationActive={false} radius={[0, 2, 2, 0]} barSize={12}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.contribution > 0 ? POS : d.contribution < 0 ? NEG : '#5b6b8c'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function StanceHistory({ history }) {
  return (
    <div className="flex items-end gap-1.5">
      {history.map((h) => (
        <div key={h.week} className="flex flex-col items-center gap-1">
          <StanceChip stance={h.stance} />
          <span className="text-[9px] text-ink-500">{h.week.slice(5)}</span>
        </div>
      ))}
    </div>
  )
}

export default function AssetLensPage({ snapshot, selectedAsset, setSelectedAsset }) {
  const view = snapshot.asset_views.find((v) => v.asset === selectedAsset) ?? snapshot.asset_views[0]
  const delta = view.stance - view.prior_stance
  return (
    <div data-testid="asset-lens-page" className="flex h-full flex-col gap-2 p-2">
      {/* asset selector */}
      <div className="flex shrink-0 gap-1">
        {snapshot.asset_views.map((v) => (
          <button key={v.asset} type="button" onClick={() => setSelectedAsset(v.asset)}
            className={`rounded border px-2.5 py-1 text-[11px] font-medium ${
              v.asset === view.asset
                ? 'border-ink-500 bg-ink-800 text-zinc-100'
                : 'border-ink-700 bg-ink-900 text-ink-300 hover:text-zinc-200'
            }`}>
            {v.label}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-2 gap-2">
        <div className="flex min-h-0 flex-col gap-2">
          <Card title={`${view.label} — stance`}>
            <div className="flex items-center gap-3">
              <StanceChip stance={view.stance} label={stanceLabel(view.stance)} className="text-xs" />
              {delta !== 0 && (
                <span className="flex items-center gap-1 text-xs font-semibold">
                  <DirectionArrow sign={delta > 0 ? 'UP' : 'DOWN'} />
                  <span className={delta > 0 ? 'text-emerald-400' : 'text-rose-400'}>
                    from prior {stanceLabel(view.prior_stance)} ({delta > 0 ? '+' : ''}{delta})
                  </span>
                </span>
              )}
              {delta === 0 && <span className="text-[11px] text-ink-500">unchanged from prior week</span>}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-[10px] uppercase tracking-wider text-ink-500">macro bias</span>
              <StanceChip stance={view.macro_bias} />
              <span className="ml-2 text-[10px] uppercase tracking-wider text-ink-500">gate</span>
              <ConfirmationChip value={view.market_confirmation} />
              <span className="ml-2 text-[10px] uppercase tracking-wider text-ink-500">valuation</span>
              <span className="rounded border border-ink-700 bg-ink-850 px-1.5 py-0.5 text-[10px] text-ink-300">{view.valuation_tag}</span>
              <ConfidenceBadge confidence={view.confidence} />
              <FreshnessChip status={view.data_health} />
            </div>
          </Card>

          <Card title="Drivers / counter-signals" className="min-h-0 flex-1" bodyClassName="overflow-auto">
            <DriverBars drivers={view.drivers} />
            {view.counter_signals.length > 0 && (
              <div className="mt-2">
                <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-amber-300">Counter-signals</h3>
                <ul className="list-inside list-disc text-[11px] text-amber-200/90">
                  {view.counter_signals.map((s) => <li key={s}>{s}</li>)}
                </ul>
              </div>
            )}
          </Card>
        </div>

        <div className="flex min-h-0 flex-col gap-2">
          <Card title="Recent stance history (weekly)">
            <StanceHistory history={view.stance_history} />
          </Card>
          <Card title="Invalidators / watch conditions" className="min-h-0 flex-1">
            <div className="rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1.5 text-[11px] text-amber-200/90">
              <span className="font-semibold uppercase tracking-wide text-amber-300">Invalidates view: </span>
              {view.invalidator}
            </div>
            <p className="mt-2 text-[11px] text-ink-500">
              View confidence is {confidenceLabel(view.confidence).toLowerCase()} ({Math.round(view.confidence * 100)}%).
              {view.data_health === 'FRESH'
                ? ' Underlying data is fresh; confidence reflects evidence breadth only.'
                : ` A data-health problem (${view.data_health}) reduces confidence — it is not itself a directional signal.`}
            </p>
          </Card>
        </div>
      </div>
    </div>
  )
}
