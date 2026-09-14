import {
  Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { Card, ConfidenceBadge, ConfirmationChip, DirectionArrow, FreshnessChip, StanceChip } from '../components/primitives.jsx'
import { confidenceLabel } from '../lib/format.js'

const POS = '#34d399'
const NEG = '#fb7185'

function DriverBars({ drivers }) {
  const numeric = drivers.filter((d) => d.contribution !== null)
  const qualitative = drivers.filter((d) => d.contribution === null)
  const data = numeric.map((d) => ({ name: d.label.replaceAll('_', ' ').toLowerCase(), contribution: d.contribution }))
  const height = Math.max(data.length * 34, 48)
  const maxAbs = Math.max(...numeric.map((d) => Math.abs(d.contribution)), 1)
  return (
    <div>
      {data.length > 0 ? (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            {/* bars plot the producer-emitted driver values verbatim — no recomputation */}
            <BarChart data={data} layout="vertical" domain={[0, 'dataMax']} margin={{ top: 0, right: 24, left: 0, bottom: 0 }}>
              <XAxis type="number" domain={[-maxAbs, maxAbs]} tick={{ fill: '#5b6b8c', fontSize: 9 }} />
              <YAxis type="category" dataKey="name" width={170} tick={{ fill: '#9fb0cf', fontSize: 10 }} />
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
      ) : (
        <p className="text-[11px] text-ink-500">No numeric driver decomposition in this snapshot.</p>
      )}
      {qualitative.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[11px] text-ink-300">
          {qualitative.map((d) => (
            <li key={d.label} className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-ink-500" aria-hidden />
              {d.label.replaceAll('_', ' ').toLowerCase()} <span className="text-ink-500">(qualitative, producer-emitted)</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function AssetLensPage({ snapshot, selectedAsset, setSelectedAsset }) {
  const view = snapshot.asset_views.find((v) => v.asset === selectedAsset) ?? snapshot.asset_views[0]
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
              <StanceChip stance={view.stance} className="text-xs" />
              {view.stance_delta !== 0 ? (
                <span className="flex items-center gap-1 text-xs font-semibold">
                  <DirectionArrow sign={view.stance_delta > 0 ? 'UP' : 'DOWN'} />
                  <span className={view.stance_delta > 0 ? 'text-emerald-400' : 'text-rose-400'}>
                    from prior stance {view.prior_stance > 0 ? `+${view.prior_stance}` : view.prior_stance} ({view.stance_delta > 0 ? '+' : ''}{view.stance_delta})
                  </span>
                </span>
              ) : (
                <span className="text-[11px] text-ink-500">unchanged from prior stance</span>
              )}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-[10px] uppercase tracking-wider text-ink-500">macro bias</span>
              <StanceChip stance={view.macro_bias} />
              <span className="ml-2 text-[10px] uppercase tracking-wider text-ink-500">gate</span>
              <ConfirmationChip value={view.confirmation_display} />
              <ConfidenceBadge confidence={view.confidence} />
              <FreshnessChip status={view.data_health} />
            </div>
            <p className="mt-1.5 text-[11px] text-ink-300">
              <span className="text-[10px] uppercase tracking-wider text-ink-500">valuation: </span>
              {view.valuation_tag}
            </p>
          </Card>

          <Card title="Drivers / counter-signals (producer-emitted)" className="min-h-0 flex-1" bodyClassName="overflow-auto">
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
          <Card title="Stance transition (producer emits current + prior)">
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase tracking-wider text-ink-500">prior</span>
              <StanceChip stance={view.prior_stance} />
              <DirectionArrow sign={view.stance_delta > 0 ? 'UP' : view.stance_delta < 0 ? 'DOWN' : 'FLAT'} />
              <span className="text-[10px] uppercase tracking-wider text-ink-500">current</span>
              <StanceChip stance={view.stance} />
            </div>
            <p className="mt-2 text-[10px] text-ink-500">
              DashboardSnapshotV0 emits current and prior stance only; a multi-week history is not invented by the UI.
            </p>
          </Card>
          <Card title="Invalidators / watch conditions" className="min-h-0 flex-1">
            <div className="rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1.5 text-[11px] text-amber-200/90">
              <span className="font-semibold uppercase tracking-wide text-amber-300">Invalidates view: </span>
              {view.invalidator}
            </div>
            <p className="mt-2 text-[11px] text-ink-500">
              View confidence is {confidenceLabel(view.confidence).toLowerCase()} ({Math.round(view.confidence * 100)}%).
              {view.data_health === 'FRESH'
                ? ' Underlying data health is OK; confidence reflects producer assessment only.'
                : ` A data-health problem (${view.data_health_status}) is flagged by the producer — it is a pipeline state, not a directional signal.`}
            </p>
          </Card>
        </div>
      </div>
    </div>
  )
}
