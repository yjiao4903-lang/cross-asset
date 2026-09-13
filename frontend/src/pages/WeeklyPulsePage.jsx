import {
  Bar, BarChart, Cell, ResponsiveContainer, ReferenceLine, XAxis, YAxis, Tooltip,
} from 'recharts'
import { Card, ConfidenceBadge, DirectionArrow, FreshnessChip, StanceChip } from '../components/primitives.jsx'
import { fmtPct, fmtMove, shortDate, directionSign } from '../lib/format.js'

const POS = '#34d399'
const NEG = '#fb7185'

function ReleasesPanel({ informationSet }) {
  return (
    <ul className="space-y-1.5 text-[11px]">
      {informationSet.map((e) => (
        <li key={e.id} className="flex items-start gap-2 rounded border border-ink-800 bg-ink-850 px-2 py-1.5">
          <FreshnessChip status={e.status} />
          <div className="min-w-0 flex-1">
            <div className="text-zinc-200">{e.label}</div>
            <div className="text-ink-500">{e.detail}</div>
          </div>
          <div className="shrink-0 text-right text-[10px] text-ink-500">
            <div>{shortDate(e.release_date)}</div>
            {e.revised && <div className="text-sky-300">revised</div>}
          </div>
        </li>
      ))}
    </ul>
  )
}

function ClusterDeltaChart({ clusters }) {
  const data = clusters.map((c) => ({ name: c.label.replace(/ & .*/, '').replace(/ \/ .*/, ''), delta: c.weekly_delta }))
  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
          <XAxis dataKey="name" tick={{ fill: '#5b6b8c', fontSize: 9 }} interval={0} angle={-30} textAnchor="end" height={58} />
          <YAxis tick={{ fill: '#5b6b8c', fontSize: 9 }} domain={[-0.5, 0.5]} />
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
          <th className="font-medium">YTD</th>
        </tr>
      </thead>
      <tbody>
        {pulse.matrix.map((r) => (
          <tr key={r.asset} className="border-t border-ink-800">
            <td className="py-1 text-left text-zinc-200">{r.asset.replace('_', ' ')}</td>
            {[r.r1w, r.r1m, r.r3m, r.ytd].map((v, i) => (
              <td key={i} className={`py-1 text-right font-medium ${v > 0 ? 'text-emerald-400' : v < 0 ? 'text-rose-400' : 'text-zinc-400'}`}>
                {fmtPct(v)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ViewDeltasPanel({ assetViewDelta }) {
  return (
    <ul className="space-y-1.5 text-[11px]">
      {assetViewDelta.map((d) => {
        const changed = d.current_stance !== d.prior_stance
        return (
          <li key={d.asset} className="flex items-center gap-2 rounded border border-ink-800 bg-ink-850 px-2 py-1.5">
            <span className="w-20 shrink-0 font-medium text-zinc-200">{d.asset.replace('_', ' ')}</span>
            <StanceChip stance={d.prior_stance} />
            <DirectionArrow sign={changed ? (d.current_stance > d.prior_stance ? 'UP' : 'DOWN') : 'FLAT'} />
            <StanceChip stance={d.current_stance} />
            <span className="min-w-0 flex-1 truncate text-ink-300">{d.reason}</span>
          </li>
        )
      })}
    </ul>
  )
}

export default function WeeklyPulsePage({ snapshot }) {
  const wc = snapshot.weekly_change
  return (
    <div data-testid="weekly-pulse-page" className="h-full overflow-auto p-2">
      <div className="grid grid-cols-2 gap-2">
        <Card title="New macro releases / revisions since prior snapshot">
          <ReleasesPanel informationSet={wc.information_set_delta} />
        </Card>
        <Card title="Genuine weekly market-condition moves">
          <ul className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
            {wc.market_condition_delta.map((m) => (
              <li key={m.asset + m.label} className="flex items-center justify-between border-b border-ink-800 py-1">
                <span className="text-zinc-200">{m.label}</span>
                <span className={`font-semibold tabular-nums ${m.move > 0 ? 'text-emerald-400' : m.move < 0 ? 'text-rose-400' : 'text-zinc-400'}`}>
                  {fmtMove(m)}
                </span>
              </li>
            ))}
          </ul>
          <h3 className="mb-1 mt-3 text-[10px] font-semibold uppercase tracking-wider text-ink-300">
            Cluster state change (weekly delta)
          </h3>
          <ClusterDeltaChart clusters={snapshot.clusters} />
        </Card>

        <Card title="Cross-asset 1W / 1M / 3M / YTD matrix"
          right={<span className="text-[10px] text-ink-500">{snapshot.cross_asset_pulse.notes}</span>}>
          <CrossAssetMatrix pulse={snapshot.cross_asset_pulse} />
        </Card>
        <Card title="Asset stance / confidence changes">
          <ViewDeltasPanel assetViewDelta={wc.asset_view_delta} />
          <h3 className="mb-1 mt-3 text-[10px] font-semibold uppercase tracking-wider text-ink-300">
            Macro state delta (caused by new information only)
          </h3>
          <ul className="space-y-1 text-[11px]">
            {wc.macro_state_delta.map((d) => (
              <li key={d.cluster} className="flex items-center gap-2">
                <span className="w-36 capitalize text-zinc-200">{d.cluster.replace(/_/g, ' ')}</span>
                <DirectionArrow sign={directionSign(d.delta > 0 ? 'IMPROVING' : d.delta < 0 ? 'DETERIORATING' : 'FLAT')} />
                <span className={`tabular-nums font-semibold ${d.delta > 0 ? 'text-emerald-400' : d.delta < 0 ? 'text-rose-400' : 'text-zinc-500'}`}>
                  {d.delta > 0 ? '+' : ''}{d.delta.toFixed(2)}
                </span>
                <span className="min-w-0 flex-1 truncate text-ink-500">{d.note}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}
