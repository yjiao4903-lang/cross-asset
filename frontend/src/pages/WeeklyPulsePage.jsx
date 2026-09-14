import {
  Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  Card, StanceChip, DirectionArrow, FreshnessChip,
} from '../components/primitives.jsx'
import { fmtBackendMove, shortDate, directionSign } from '../lib/format.js'

const POS = '#34d399'
const NEG = '#fb7185'
const NEU = '#5b6b8c'

const TOOLTIP = { background: '#151c2b', border: '1px solid #34425f', fontSize: 11, borderRadius: 6 }

/* 1 — ranked weekly changes (most important first). Cluster weekly_delta is a
 * change (delta), so red/green direction color is appropriate here. */
function RankedDeltaChart({ clusters }) {
  const data = clusters
    .filter((c) => c.horizon !== 'STRUCTURAL_CONTEXT')
    .map((c) => ({
      name: `${c.familyLabel.replace(' / ', ' ')} @ ${c.horizon.slice(0, 4)}`,
      delta: c.weekly_delta,
      id: c.id,
    }))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    .slice(0, 12)
  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 24, left: 0, bottom: 0 }}>
          <XAxis type="number" tick={{ fill: '#6b7a9c', fontSize: 9 }} />
          <YAxis type="category" dataKey="name" width={190} tick={{ fill: '#8a99b8', fontSize: 10 }} />
          <Tooltip contentStyle={TOOLTIP} cursor={{ fill: '#1a2131' }} />
          <ReferenceLine x={0} stroke="#263047" />
          <Bar dataKey="delta" isAnimationActive={false} radius={[0, 2, 2, 0]} barSize={11}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.delta > 0 ? POS : d.delta < 0 ? NEG : NEU} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="cx-label mt-1">Weekly change (delta) by cluster — direction colored · zero line = no change</p>
    </div>
  )
}

/* 2 — cross-asset trailing levels: 1W / 1M / 3M + momentum trend state.
 * Trailing returns are LEVELS, shown separately from the delta surfaces above. */
function CrossAssetMatrix({ pulse }) {
  return (
    <div>
      <table className="cx-table">
        <thead>
          <tr className="text-right">
            <th className="text-left">Asset</th>
            <th>1W</th>
            <th>1M</th>
            <th>3M</th>
            <th className="text-left">Trend</th>
          </tr>
        </thead>
        <tbody>
          {pulse.entries.map((r) => (
            <tr key={r.asset} className={r.r1w === 0 && r.r1m === 0 && r.r3m === 0 ? 'opacity-80' : undefined}>
              <td className="py-1 text-left font-medium text-txt-primary">{r.label}</td>
              {[r.r1w, r.r1m, r.r3m].map((v, i) => (
                <td key={i} className={`py-1 text-right font-medium ${
                  v > 0 ? 'text-status-positive' : v < 0 ? 'text-status-negative' : 'text-txt-muted'
                }`}>
                  {v > 0 ? '+' : ''}{v.toFixed(1)}%
                </td>
              ))}
              <td className="py-1 text-left text-[11px] text-txt-muted">{String(r.momentum_label ?? '').replace(/_/g, ' ').toLowerCase()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="cx-label mt-1">Trailing-return levels (producer V0 emits 1W/1M/3M only — no YTD invented) · momentum = trend state, not a change</p>
    </div>
  )
}

/* 3 — macro state delta (cause-tagged by producer: NEW_INFORMATION vs NO_NEW_INFORMATION) */
function MacroStateDeltaPanel({ entries }) {
  return (
    <ul className="space-y-0.5 text-[11.5px]">
      {entries.map((e) => (
        <li key={e.factor_id} className="flex items-center gap-2">
          <span className="w-44 shrink-0 truncate text-txt-secondary">{e.factor_id.replaceAll('_', ' ').toLowerCase()}</span>
          <span className="tabular-nums text-txt-metadata">{e.previous} → {e.current}</span>
          <DirectionArrow sign={directionSign(e.delta > 0 ? 'RISING' : e.delta < 0 ? 'FALLING' : 'FLAT')} />
          <span className={`ml-auto shrink-0 text-right font-semibold tabular-nums ${
            e.delta > 0 ? 'text-status-positive' : e.delta < 0 ? 'text-status-negative' : 'text-txt-metadata'
          }`}>
            {e.delta > 0 ? '+' : ''}{e.delta.toFixed(2)}
          </span>
          <span className={`shrink-0 px-1.5 py-0.5 text-[10px] ${
            e.cause === 'NEW_INFORMATION' ? 'bg-status-info/10 text-status-info' : 'bg-zinc-500/10 text-txt-muted'
          }`}>
            {String(e.cause ?? '').replaceAll('_', ' ')}
          </span>
        </li>
      ))}
    </ul>
  )
}

/* 4 — macro releases / revisions since prior snapshot */
function ReleasesPanel({ weeklyChange }) {
  return (
    <div>
      <ul className="space-y-1 text-[11.5px]">
        {weeklyChange.events.map((e) => (
          <li key={e.factor_id + String(e.observation_date)}
            className="flex items-start gap-2 rounded border border-divider bg-surface-2/40 px-2 py-1">
            <FreshnessChip status={e.status} />
            <div className="min-w-0 flex-1">
              <div className="text-txt-secondary">
                {e.factor_id.replaceAll('_', ' ').toLowerCase()}
                <span className="mx-1 text-txt-metadata">·</span>
                <span className="text-txt-muted">{String(e.event_type ?? '').replaceAll('_', ' ').toLowerCase()}</span>
                {e.surprise && (
                  <span className="ml-1.5 text-[10px] text-txt-metadata" title={`surprise ${e.surprise.value} vs ${e.surprise.baseline}`}>
                    surprise ({e.surprise.method})
                  </span>
                )}
              </div>
              <div className="text-txt-metadata">{e.note} — series {e.series_id}</div>
            </div>
            <div className="shrink-0 text-right text-[10px] text-txt-metadata">{shortDate(e.observation_date)}</div>
          </li>
        ))}
      </ul>
      {weeklyChange.stale_factors.length > 0 && (
        <p className="mt-1.5 text-[10px] text-amber-300/90">
          stale (flagged, not zero-filled): {weeklyChange.stale_factors.join(', ')}
        </p>
      )}
    </div>
  )
}

/* 5 — genuine market-condition moves */
function MarketMovesPanel({ moves }) {
  return (
    <ul className="space-y-0.5 text-[11.5px]">
      {moves.map((m) => (
        <li key={m.instrument} className="flex items-center justify-between border-b border-divider py-1">
          <span className="text-txt-secondary">
            {m.instrument}
            <span className="ml-1 text-[10px] text-txt-metadata">
              {m.unit === 'BPS' ? 'bps' : m.unit === 'POINT' ? 'pt' : '%'} · {String(m.metric_class ?? '').toLowerCase()}
            </span>
          </span>
          <span className={`font-semibold tabular-nums ${
            m.weekly_change > 0 ? 'text-status-positive' : m.weekly_change < 0 ? 'text-status-negative' : 'text-txt-muted'
          }`}>
            {fmtBackendMove(m)}
          </span>
        </li>
      ))}
    </ul>
  )
}

/* 6 — asset stance / confidence changes */
function StanceChangesPanel({ entries }) {
  return (
    <ul className="space-y-1 text-[11.5px]">
      {entries.map((d) => {
        const changed = d.current_stance !== d.previous_stance
        return (
          <li key={d.asset} className="rounded border border-divider bg-surface-2/40 px-2 py-1.5">
            <div className="flex items-center gap-2">
              <span className="w-20 shrink-0 font-medium text-txt-primary">{d.asset.replaceAll('_', ' ')}</span>
              <StanceChip stance={d.previous_stance} />
              <DirectionArrow sign={changed ? (d.delta > 0 ? 'UP' : 'DOWN') : 'FLAT'} />
              <StanceChip stance={d.current_stance} />
              <span className={`ml-auto text-[10px] tabular-nums ${
                d.confidence_delta > 0 ? 'text-status-info' : d.confidence_delta < 0 ? 'text-status-warning-fg' : 'text-txt-metadata'
              }`}>
                conf {d.confidence_delta > 0 ? '+' : ''}{d.confidence_delta}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {d.reason_tags.map((t) => (
                <span key={t} className="rounded bg-surface-2 px-1.5 py-0.5 text-[9.5px] text-txt-muted">{t.replaceAll('_', ' ')}</span>
              ))}
            </div>
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
      <div className="flex flex-col gap-2">
        {/* 1 — largest weekly changes (changes dominate) */}
        <Card title="Largest weekly changes by factor cluster"
          right={<span className="cx-label">change (delta), ranked by magnitude</span>}>
          <RankedDeltaChart clusters={snapshot.clusters} />
        </Card>

        {/* 2 — cross-asset matrix (levels) */}
        <Card title="Cross-asset performance matrix — trailing levels"
          right={<span className="cx-label">level (1W / 1M / 3M)</span>}>
          <CrossAssetMatrix pulse={snapshot.cross_asset_pulse} />
        </Card>

        {/* lower section: releases + moves (changes) vs macro-state delta + stance changes */}
        <div className="grid grid-cols-2 gap-2">
          <Card title="Macro releases / revisions since prior snapshot" bodyClassName="overflow-auto">
            <ReleasesPanel weeklyChange={wc} />
          </Card>
          <Card title="Genuine weekly market-condition moves" bodyClassName="overflow-auto">
            <MarketMovesPanel moves={wc.market_moves} />
          </Card>
          <Card title="Macro state delta (cause-tagged by producer)" bodyClassName="overflow-auto">
            <MacroStateDeltaPanel entries={wc.macro_state_delta} />
          </Card>
          <Card title="Asset stance / confidence changes" bodyClassName="overflow-auto">
            <StanceChangesPanel entries={wc.asset_view_delta} />
          </Card>
        </div>
      </div>
    </div>
  )
}