import { confidenceLabel, directionSign, fmtMove, shortDate } from '../lib/format.js'
import { Card, ConfidenceBadge, DirectionArrow, FreshnessChip, StanceChip, ConfirmationChip } from '../components/primitives.jsx'

function ClimatePill({ title, state, direction, confidence }) {
  const sign = directionSign(direction)
  return (
    <div data-testid="climate-pill" className="flex min-w-0 flex-1 flex-col justify-center rounded-lg border border-ink-700 bg-ink-900 px-3 py-2">
      <div className="truncate text-[10px] font-semibold uppercase tracking-wider text-ink-300">{title}</div>
      <div className="mt-0.5 flex items-center gap-1.5">
        <span className="truncate text-[13px] font-semibold text-zinc-100">{state.replace(/_/g, ' ')}</span>
        <DirectionArrow sign={sign} />
      </div>
      <div className="mt-0.5"><ConfidenceBadge confidence={confidence} /></div>
    </div>
  )
}

function RegimePanel({ regime }) {
  const { quadrant } = regime
  const g = quadrant.growth === 'IMPROVING' ? 1 : -1
  const i = quadrant.inflation === 'ACCELERATING' ? 1 : -1 // rows: accelerating on top
  const cellCls = (active) =>
    `relative rounded ${active ? 'bg-sky-500/25 ring-1 ring-sky-400/60' : 'bg-ink-850'}`
  const dotCls = 'absolute inset-0 flex items-center justify-center text-[9px] font-bold text-sky-200'
  return (
    <div className="flex h-full min-h-0 gap-3">
      {/* 2D navigation quadrant */}
      <div className="flex w-44 shrink-0 flex-col">
        <div className="grid grid-cols-2 grid-rows-2 gap-1 text-[9px] text-ink-500" style={{ aspectRatio: '2.4/1' }}>
          <div className={`${cellCls(g === 1 && i === 1)} ${dotCls}`}>{g === 1 && i === 1 ? '●' : ''}<span className="absolute left-1 top-0.5">Refl.</span></div>
          <div className={`${cellCls(g === -1 && i === 1)} ${dotCls}`}>{g === -1 && i === 1 ? '●' : ''}<span className="absolute left-1 top-0.5">Stagfl.</span></div>
          <div className={`${cellCls(g === 1 && i === -1)} ${dotCls}`}>{g === 1 && i === -1 ? '●' : ''}<span className="absolute left-1 bottom-0.5">Goldilocks</span></div>
          <div className={`${cellCls(g === -1 && i === -1)} ${dotCls}`}>{g === -1 && i === -1 ? '●' : ''}<span className="absolute left-1 bottom-0.5">Slowdown</span></div>
        </div>
        <div className="mt-1 text-[9px] leading-tight text-ink-500">
          top: inflation accelerating · bottom: decelerating<br />
          left: growth improving · right: deteriorating
        </div>
      </div>
      {/* regime facts */}
      <div className="flex min-w-0 flex-1 flex-col justify-center gap-1 text-xs">
        <div className="flex items-center gap-2">
          <span className="rounded border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[12px] font-bold text-sky-200">
            {regime.label.replace(/_/g, ' ')}
          </span>
          {regime.transition && (
            <span className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">
              TRANSITION
            </span>
          )}
          {regime.hysteresis_held && (
            <span className="text-[10px] text-ink-300">hysteresis held</span>
          )}
        </div>
        <div className="text-[11px] text-ink-300">
          prior: {regime.prior_label.replace(/_/g, ' ')} · dwell {regime.dwell_weeks}w
          {regime.lens_disagreement?.flag && (
            <span className="ml-2 text-amber-300">lens disagreement: {regime.lens_disagreement.summary}</span>
          )}
        </div>
        <div><ConfidenceBadge confidence={regime.confidence} /></div>
      </div>
    </div>
  )
}

function AssetBoard({ snapshot, onSelectAsset }) {
  return (
    <div data-testid="asset-board" className="flex h-full min-h-0 flex-col">
      <table className="w-full table-fixed border-collapse text-xs">
        <thead>
          <tr className="text-left text-[9px] uppercase tracking-wider text-ink-500">
            <th className="w-[18%] pb-1 font-medium">Asset</th>
            <th className="w-[14%] pb-1 font-medium">Stance</th>
            <th className="w-[10%] pb-1 text-center font-medium">WoW</th>
            <th className="w-[12%] pb-1 font-medium">Conf</th>
            <th className="w-[13%] pb-1 font-medium">Gate</th>
            <th className="pb-1 font-medium">Top driver</th>
            <th className="w-[9%] pb-1 text-right font-medium">Data</th>
          </tr>
        </thead>
        <tbody>
          {snapshot.asset_views.map((v) => {
            const delta = v.stance - v.prior_stance
            const topDriver = [...v.drivers].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))[0]
            return (
              <tr key={v.asset}
                onClick={() => onSelectAsset(v.asset)}
                className="cursor-pointer border-t border-ink-800 hover:bg-ink-850">
                <td className="py-1 font-medium text-zinc-200">{v.label}</td>
                <td className="py-1"><StanceChip stance={v.stance} /></td>
                <td className="py-1 text-center">
                  {delta !== 0 ? (
                    <span className="inline-flex items-center gap-0.5 text-[11px] font-semibold">
                      <DirectionArrow sign={delta > 0 ? 'UP' : 'DOWN'} />
                      <span className={delta > 0 ? 'text-emerald-400' : 'text-rose-400'}>{delta > 0 ? `+${delta}` : delta}</span>
                    </span>
                  ) : (
                    <span className="text-ink-500">—</span>
                  )}
                </td>
                <td className="py-1"><ConfidenceBadge confidence={v.confidence} /></td>
                <td className="py-1"><ConfirmationChip value={v.market_confirmation} /></td>
                <td className="truncate py-1 text-[11px] text-ink-300">
                  {topDriver.label}
                  <span className={topDriver.contribution > 0 ? ' text-emerald-400' : topDriver.contribution < 0 ? ' text-rose-400' : ''}>
                    {' '}{topDriver.contribution > 0 ? '+' : ''}{topDriver.contribution}
                  </span>
                </td>
                <td className="py-1 text-right"><FreshnessChip status={v.data_health} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function WhatChangedPanel({ weeklyChange }) {
  const info = weeklyChange.information_set_delta
  const mkt = weeklyChange.market_condition_delta
  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div>
        <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-300">
          Macro information / release changes
        </h3>
        <ul className="space-y-1">
          {info.map((e) => (
            <li key={e.id} className="flex items-start gap-2 text-[11px]">
              <FreshnessChip status={e.status} />
              <span className="min-w-0 flex-1">
                <span className="text-zinc-200">{e.label}</span>
                <span className="block truncate text-ink-500">{e.detail}</span>
              </span>
              <span className="shrink-0 text-[10px] text-ink-500">{shortDate(e.release_date)}</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-300">
          Market-condition moves (genuine weekly)
        </h3>
        <ul className="space-y-1">
          {mkt.map((m) => {
            const pos = m.move > 0
            return (
              <li key={m.asset + m.label} className="flex items-center justify-between text-[11px]">
                <span className="text-zinc-200">{m.label}</span>
                <span className={`font-semibold tabular-nums ${pos ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {fmtMove(m)}
                </span>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}

function ExecutiveBrief({ brief }) {
  const rows = [
    { label: 'What changed', text: brief.what_changed },
    { label: 'Why it matters', text: brief.why_it_matters },
    { label: 'Watch next', text: brief.watch_next },
  ]
  return (
    <div className="space-y-1.5 text-[11px] leading-snug">
      {rows.map((r) => (
        <p key={r.label}>
          <span className="font-semibold uppercase tracking-wide text-ink-300">{r.label}: </span>
          <span className="text-zinc-200">{r.text}</span>
        </p>
      ))}
    </div>
  )
}

export default function OverviewPage({ snapshot, setSelectedAsset }) {
  const { macro_climate, investment_climate, regime } = snapshot
  return (
    /* 1440×900 zero-scroll cockpit: fixed column layout, page never scrolls */
    <div data-testid="overview-page" className="flex h-full flex-col gap-2 p-2">
      {/* Four climate pills */}
      <div className="grid shrink-0 grid-cols-4 gap-2">
        <ClimatePill title="1 · Cyclical Macro" state={macro_climate.state} direction={macro_climate.direction} confidence={macro_climate.confidence} />
        <ClimatePill title="2 · Policy / Liquidity + Fin. Cond." state={investment_climate.financial_conditions} direction={regime.quadrant.growth === 'IMPROVING' ? 'EASING' : 'TIGHTENING'} confidence={investment_climate.confidence} />
        <ClimatePill title="3 · Market Confirmation / Risk Appetite" state={investment_climate.market_confirmation} direction={investment_climate.direction} confidence={macro_climate.confidence} />
        <ClimatePill title="4 · Investment Climate" state={investment_climate.state} direction={investment_climate.direction} confidence={investment_climate.confidence} />
      </div>

      {/* 60% / 40% main body */}
      <div className="grid min-h-0 flex-1 grid-cols-[3fr_2fr] gap-2">
        {/* Left 60%: regime panel + 8-asset stance board */}
        <div className="flex min-h-0 flex-col gap-2">
          <Card title="Regime / Navigation — Growth × Inflation" className="shrink-0">
            <RegimePanel regime={regime} />
          </Card>
          <Card title="Asset Stance Board — 8 assets (click for Asset Lens)"
            right={<span className="text-[10px] text-ink-500">stance −2…+2 · WoW change</span>}
            className="min-h-0 flex-1" bodyClassName="overflow-auto">
            <AssetBoard snapshot={snapshot} onSelectAsset={(asset) => setSelectedAsset(asset)} />
          </Card>
        </div>

        {/* Right 40%: what changed + executive brief */}
        <div className="flex min-h-0 flex-col gap-2">
          <Card title="What changed this week" className="min-h-0 flex-1" bodyClassName="overflow-auto">
            <WhatChangedPanel weeklyChange={snapshot.weekly_change} />
          </Card>
          <Card title="Executive brief" className="shrink-0">
            <ExecutiveBrief brief={snapshot.executive_brief} />
          </Card>
        </div>
      </div>
    </div>
  )
}
