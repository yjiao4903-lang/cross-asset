import {
  Bar, BarChart, Cell, ResponsiveContainer, ReferenceLine, XAxis, YAxis, Tooltip,
} from 'recharts'
import { Card, ConfidenceBadge, DirectionArrow, FreshnessChip, StanceChip } from '../components/primitives.jsx'
import { fmtBackendMove, shortDate, directionSign } from '../lib/format.js'

const POS = '#34d399'
const NEG = '#fb7185'

function ReleasesPanel({ weeklyChange }) {
  return (
    <div>
      <ul className="space-y-1.5 text-[11px]">
        {weeklyChange.events.map((e) => (
          <li key={e.factor_id + String(e.observation_date)} className="flex items-start gap-2 rounded border border-ink-800 bg-ink-850 px-2 py-1.5">
            <FreshnessChip status={e.status} />
            <div className="min-w-0 flex-1">
              <div className="text-zinc-200">
                {e.factor_id.replaceAll('_', ' ').toLowerCase()} · {e.event_type.replaceAll('_', ' ').toLowerCase()}
                {e.surprise && (
                  <span className="ml-1.5 text-[10px] text-ink-500" title={`surprise ${e.surprise.value} vs ${e.surprise.baseline}`}>
                    surprise ({e.surprise.method})
                  </span>
                )}
              </div>
              <div className="text-ink-500">{e.note} — series {e.series_id}</div>
            </div>
            <div className="shrink-0 text-right text-[10px] text-ink-500">{shortDate(e.observation_date)}</div>
          </li>
        ))}
      </ul>
      {weeklyChange.stale_factors.length > 0 && (
        <p className="mt-2 text-[10px] text-amber-300/90">
          stale factors (flagged, not zero-filled): {weeklyChange.stale_factors.join(', ')}
        </p>
      )}
    </div>
  )
}

function ClusterDeltaChart({ clusters }) {
  const data = clusters
    .filter((c) => c.horizon !== 'STRUCTURAL_CONTEXT')
    .map((c) => ({ name: `${c.familyLabel.replaceAll(' & ', ' & ').split(' / ')[0]}@${c.horizon.slice(0, 4)}`, delta: c.weekly_delta }))
  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
          <XAxis dataKey="name" tick={{ fill: '#5b6b8c', fontSize: 8 }} interval={0} angle={-30} textAnchor="end" height={58} />
          <YAxis tick={{ fill: '#5b6b8c', fontSize: 9 }} />
          <Tooltip contentStyle={{ background: '#141926', border: '1px solid #263047', fontSize: 11 }} />
          <ReferenceLine y={0} stroke="#263047" />
          <Bar dataKey="delta" isAnimationActive={false} radius={[2, 2, 0, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.delta > 0 ? POS : d.delta < 0 ? NEG : '#5b6b8c'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function CrossAssetMatrix({ pulse }) {
  return (
    <table className="w-full border-collapse text-[11px] tabular-nums">
      <thead>
        <tr className="text-right text-[9px] uppercase tracking-wider text-ink-500">
          <th className="text-left font-medium">Asset</th>
          <th className="font-medium">1W</th>
          <th className="font-medium">1M</th>
          <th className="font-medium">3M</th>
          <th className="font-medium">Momentum</th>
        </tr>
      </thead>
      <tbody>
        {pulse.entries.map((r) => (
          <tr key={r.asset} className="border-t border-ink-800">
            <td className="py-1 text-left text-zinc-200">{r.label}</td>
            {[r.r1w, r.r1m, r.r3m].map((v, i) => (
              <td key={i} className={`py-1 text-right font-medium ${v > 0 ? 'text-emerald-400' : v < 0 ? 'text-rose-400' : 'text-zinc-400'}`}>
                {v > 0 ? '+' : ''}{v.toFixed(1)}%
              </td>
            ))}
            <td className="py-1 text-right text-[10px] text-ink-300">{String(r.momentum_label ?? '').toLowerCase()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ViewDeltasPanel({ entries }) {
  return (
    <ul className="space-y-1.5 text-[11px]">
      {entries.map((d) => {
        const changed = d.current_stance !== d.previous_stance
        return (
          <li key={d.asset} className="rounded border border-ink-800 bg-ink-850 px-2 py-1.5">
            <div className="flex items-center gap-2">
              <span className="w-20 shrink-0 font-medium text-zinc-200">{d.asset.replaceAll('_', ' ')}</span>
              <StanceChip stance={d.previous_stance} />
              <DirectionArrow sign={changed ? (d.delta > 0 ? 'UP' : 'DOWN') : 'FLAT'} />
              <StanceChip stance={d.current_stance} />
              <span className={`text-[10px] tabular-nums ${d.confidence_delta > 0 ? 'text-sky-300' : d.confidence_delta < 0 ? 'text-amber-300' : 'text-ink-500'}`}>
                conf {d.confidence_delta > 0 ? '+' : ''}{d.confidence_delta}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {d.reason_tags.map((t) => (
                <span key={t} className="rounded bg-ink-800 px-1.5 py-0.5 text-[9px] text-ink-300">{t}</span>
              ))}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function MacroStateDeltaPanel({ entries }) {
  return (
    <ul className="space-y-1 text-[11px]">
      {entries.map((e) => (
        <li key={e.factor_id} className="flex items-center gap-2">
          <span className="w-44 shrink-0 truncate text-zinc-200">{e.factor_id.replaceAll('_', ' ').toLowerCase()}</span>
          <span className="tabular-nums text-ink-500">{e.previous} → {e.current}</span>
          <DirectionArrow sign={directionSign(e.delta > 0 ? 'RISING' : e.delta < 0 ? 'FALLING' : 'FLAT')} />
          <span className={`w-12 shrink-0 text-right font-semibold tabular-nums ${e.delta > 0 ? 'text-emerald-400' : e.delta < 0 ? 'text-rose-400' : 'text-zinc-500'}`}>
            {e.delta > 0 ? '+' : ''}{e.delta.toFixed(2)}
          </span>
          <span className={`rounded px-1.5 py-0.5 text-[9px] ${e.cause === 'NEW_INFORMATION' ? 'bg-sky-500/10 text-sky-300' : 'bg-zinc-500/10 text-zinc-400'}`}>
            {e.cause.replaceAll('_', ' ')}
          </span>
        </li>
      ))}
    </ul>
  )
}

export default function WeeklyPulsePage({ snapshot }) {
  const wc = snapshot.weekly_change
  return (
    <div data-testid="weekly-pulse-page" className="h-full overflow-auto p-2">
      <div className="grid grid-cols-2 gap-2">
        <Card title="New macro releases / revisions since prior snapshot"
          right={<span className="text-[10px] text-ink-500">information set: {String(wc.information_status).replaceAll('_', ' ')}</span>}>
          <ReleasesPanel weeklyChange={wc} />
        </Card>
        <Card title="Genuine weekly market-condition moves">
          <ul className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
            {wc.market_moves.map((m) => (
              <li key={m.instrument} className="flex items-center justify-between border-b border-ink-800 py-1">
                <span className="text-zinc-200">
                  {m.instrument}
                  <span className="ml-1 text-[9px] text-ink-500">{m.unit === 'BPS' ? 'bps' : m.unit === 'POINT' ? 'pt' : '%'} · {m.metric_class.toLowerCase()}</span>
                </span>
                <span className={`font-semibold tabular-nums ${m.weekly_change > 0 ? 'text-emerald-400' : m.weekly_change < 0 ? 'text-rose-400' : 'text-zinc-400'}`}>
                  {fmtBackendMove(m)}
                </span>
              </li>
            ))}
          </ul>
          <h3 className="mb-1 mt-3 text-[10px] font-semibold uppercase tracking-wider text-ink-300">
            Cluster weekly delta (backend weekly_delta)
          </h3>
          <ClusterDeltaChart clusters={snapshot.clusters} />
        </Card>

        <Card title="Cross-asset 1W / 1M / 3M matrix + momentum"
          right={<span className="text-[10px] text-ink-500">producer V0 emits 1W/1M/3M only — no YTD invented</span>}>
          <CrossAssetMatrix pulse={snapshot.cross_asset_pulse} />
        </Card>
        <Card title="Asset stance / confidence changes">
          <ViewDeltasPanel entries={wc.asset_view_delta} />
          <h3 className="mb-1 mt-3 text-[10px] font-semibold uppercase tracking-wider text-ink-300">
            Macro state delta (cause-tagged by producer)
          </h3>
          <MacroStateDeltaPanel entries={wc.macro_state_delta} />
        </Card>
      </div>
    </div>
  )
}
