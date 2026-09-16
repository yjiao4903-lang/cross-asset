import {
  Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  Card, StanceChip, ConfirmationChip, DirectionArrow, FreshnessChip,
  ConfidenceBadge, StanceDelta,
} from '../components/primitives.jsx'
import { confidenceLabel } from '../lib/format.js'

const POS = '#34d399'
const NEG = '#fb7185'
const NEU = '#5b6b8c'
const TOOLTIP = { background: '#151c2b', border: '1px solid #34425f', fontSize: 11, borderRadius: 6 }

/* Consistent chart grammar with the Weekly Pulse delta chart: vertical layout,
 * zero reference line, same palette + tooltip. Producer-emitted contributions. */
function DriverBars({ drivers }) {
  const numeric = drivers.filter((d) => d.contribution !== null)
  const qualitative = drivers.filter((d) => d.contribution === null)
  const data = numeric.map((d) => ({ name: d.label.replaceAll('_', ' ').toLowerCase(), contribution: d.contribution }))
  const height = Math.max(data.length * 32, 52)
  const maxAbs = Math.max(...numeric.map((d) => Math.abs(d.contribution)), 1)
  return (
    <div>
      {data.length > 0 ? (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 0, right: 24, left: 0, bottom: 0 }}>
              <XAxis type="number" domain={[-maxAbs, maxAbs]} tick={{ fill: '#6b7a9c', fontSize: 9 }} />
              <YAxis type="category" dataKey="name" width={180} tick={{ fill: '#8a99b8', fontSize: 10 }} />
              <Tooltip contentStyle={TOOLTIP} cursor={{ fill: '#1a2131' }} />
              <ReferenceLine x={0} stroke="#263047" />
              <Bar dataKey="contribution" isAnimationActive={false} radius={[0, 2, 2, 0]} barSize={11}>
                {data.map((d, i) => (
                  <Cell key={i} fill={d.contribution > 0 ? POS : d.contribution < 0 ? NEG : NEU} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="text-[11.5px] text-txt-muted">No numeric driver decomposition in this snapshot.</p>
      )}
      {qualitative.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[11.5px] text-txt-muted">
          {qualitative.map((d) => (
            <li key={d.label} className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-txt-metadata" aria-hidden />
              {d.label.replaceAll('_', ' ').toLowerCase()}
              <span className="text-txt-metadata">(qualitative, producer-emitted)</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function AssetLensPage({ snapshot, selectedAsset, setSelectedAsset }) {
  const view = snapshot.asset_views.find((v) => v.asset === selectedAsset) ?? snapshot.asset_views[0]
  const changed = view.stance_delta !== 0
  return (
    <div data-testid="asset-lens-page" className="flex h-full flex-col gap-2 p-2">
      {/* asset selector */}
      <div className="flex shrink-0 flex-wrap gap-1">
        {snapshot.asset_views.map((v) => (
          <button key={v.asset} type="button" onClick={() => setSelectedAsset(v.asset)} role="tab"
            aria-selected={v.asset === view.asset}
            className={`rounded border px-2.5 py-1 text-[11.5px] font-medium transition-colors duration-75 ${
              v.asset === view.asset
                ? 'border-status-accent/60 bg-surface-sel text-txt-primary'
                : 'border-border-1 bg-surface-1 text-txt-muted hover:bg-surface-hover hover:text-txt-secondary'
            }`}>
            {v.label}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-2 gap-2">
        {/* Left: stance identity + drivers + counter-signals */}
        <div className="flex min-h-0 flex-col gap-2">
          {/* dominant stance heading */}
          <Card className="shrink-0">
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <h2 className="text-[13px] font-bold text-txt-primary">{view.label}</h2>
                <p className="cx-label mt-0.5">{view.asset}</p>
              </div>
              <StanceChip stance={view.stance} className="text-[14px]" />
              <div className="flex shrink-0 flex-col items-end gap-0.5">
                <StanceDelta delta={view.stance_delta} className="text-[12px]" />
                <span className="text-[10px] text-txt-metadata">
                  prior {view.prior_stance > 0 ? `+${view.prior_stance}` : view.prior_stance}
                </span>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-divider pt-1.5">
              <span className="cx-label self-center">confidence</span>
              <ConfidenceBadge confidence={view.confidence} />
              <span className="cx-label self-center">macro bias</span>
              <StanceChip stance={view.macro_bias} />
              <FreshnessChip status={view.data_health} />
              <span className="ml-auto text-[11px] text-txt-metadata">
                {changed ? 'stance changed this week' : 'stance unchanged this week'}
              </span>
            </div>
          </Card>

          <Card title="Drivers" right={<span className="cx-label">producer contribution</span>}
            className="min-h-0 flex-1" bodyClassName="overflow-auto">
            <DriverBars drivers={view.drivers} />
          </Card>

          {view.counter_signals.length > 0 && (
            <Card title="Counter-signals" className="shrink-0" bodyClassName="overflow-auto">
              <ul className="space-y-1 text-[11.5px]">
                {view.counter_signals.map((s) => (
                  <li key={s} className="flex items-start gap-1.5">
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-status-warning" aria-hidden />
                    <span className="text-amber-200/90">{s}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        {/* Right: gate + valuation overlay (contextual) + transition + invalidators */}
        <div className="flex min-h-0 flex-col gap-2">
          <Card title="Market confirmation & valuation" className="shrink-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="cx-label self-center">gate</span>
              <ConfirmationChip value={view.confirmation_display} />
              <span className="text-[11px] text-txt-muted">
                {view.market_confirmation === 'UNKNOWN' || view.market_confirmation === 'UNAVAILABLE'
                  ? 'confirmation state unresolved (data state, not a direction)'
                  : 'backend-owned confirmation against current stance'}
              </span>
            </div>
            {/* valuation as a contextual overlay, not an equal-weight badge */}
            <div className="mt-2 rounded-md border border-border-1 bg-surface-2/40 px-2 py-1.5">
              <span className="cx-label mr-2">valuation overlay</span>
              <span className="text-[11.5px] text-txt-secondary">{view.valuation_tag}</span>
            </div>
          </Card>

          <Card title="Stance transition" className="shrink-0">
            <div className="flex items-center gap-2.5">
              <span className="cx-label">prior</span>
              <StanceChip stance={view.prior_stance} />
              <DirectionArrow sign={changed ? (view.stance_delta > 0 ? 'UP' : 'DOWN') : 'FLAT'} />
              <span className="cx-label">current</span>
              <StanceChip stance={view.stance} />
              <span className="ml-auto text-[10px] text-txt-metadata">
                DashboardSnapshotV0 emits current + prior only; no multi-week history invented
              </span>
            </div>
          </Card>

          <Card title="Invalidators / watch" className="min-h-0 flex-1">
            <div className="flex h-full min-h-0 flex-col gap-2">
              <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-2 py-1.5 text-[11.5px] text-amber-200/90">
                <span className="font-semibold uppercase tracking-wide text-amber-300">Invalidates view: </span>
                {view.invalidator}
              </div>
              <p className="text-[11px] leading-snug text-txt-muted">
                View confidence is {confidenceLabel(view.confidence).toLowerCase()} ({Math.round(view.confidence * 100)}%).
                {view.data_health === 'FRESH'
                  ? ' Underlying data health is OK; confidence reflects producer assessment only.'
                  : ` A data-health problem (${view.data_health_status}) is flagged by the producer — a pipeline state, not a directional signal.`}
              </p>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}