import { directionSign, fmtBackendMove, shortDate } from '../lib/format.js'
import {
  Card, StanceChip, StanceDelta, ConfidenceBadge, FreshnessChip,
  ConfirmationChip, DirectionArrow, SectionHeading, DeltaText,
} from '../components/primitives.jsx'

/* =====================================================================
 * OverviewPage (#118 Workstream C) — decision cockpit for three questions:
 *   1. What regime are we in?
 *   2. What changed this week?
 *   3. What does it imply for assets?
 * Producer-owned fields only; no client-side economic inference.
 * 1440×900 zero-scroll: fixed rows, the page itself never scrolls.
 * =====================================================================
 */

/* Quadrant cell per backend quadrant_label (producer-owned classification).
 * Four legal enum values only — GOLDILOCKS / REFLATION / STAGFLATION_RISK /
 * DISINFLATIONARY_SLUMP. No frontend semantic alias such as SLOWDOWN. */
const QUADRANT_CELLS = {
  GOLDILOCKS: [1, -1],                       // growth expanding × inflation decelerating
  REFLATION: [1, 1],                         // growth expanding × inflation accelerating
  STAGFLATION_RISK: [-1, 1],                 // growth contracting × inflation accelerating
  DISINFLATIONARY_SLUMP: [-1, -1],           // growth contracting × inflation decelerating
}
const QUADRANT_SHORT = {
  GOLDILOCKS: 'Goldilocks',
  REFLATION: 'Reflation',
  STAGFLATION_RISK: 'Stagflation',
  DISINFLATIONARY_SLUMP: 'Disinfl. slump',   // human-readable display; enum identity unchanged
}

function QuadCell({ label, short, active }) {
  return (
    <div data-quadrant={label} data-active={active ? 'true' : 'false'}
      className={`relative flex items-center justify-center rounded-md border text-[12px] font-semibold transition-colors duration-75 ${
      active
        ? 'border-status-accent/70 bg-surface-sel text-sky-100'
        : 'border-border-1 bg-surface-2/40 text-txt-metadata'
    }`}>
      <span className={active ? 'text-sky-200' : ''}>{short}</span>
      {active && (
        <span aria-label="current quadrant"
          className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full border border-app-bg bg-status-accent shadow" />
      )}
      <span className="absolute left-1 top-0.5 text-[8.5px] font-medium tracking-wide opacity-70">{label}</span>
    </div>
  )
}

/* Dominant regime / macro-climate focal area — answers "what regime are we in". */
function RegimeFocal({ regime, macroClimate }) {
  const cell = QUADRANT_CELLS[regime.quadrant_label] ?? null
  const g = cell ? cell[0] : 0   // +1 expanding (right), -1 contracting (left)
  const i = cell ? cell[1] : 0   // +1 rising (top row), -1 falling (bottom row)
  const belief = Math.round((regime.coverage ?? 0) * 100)
  return (
    <div data-testid="regime-focal" className="flex shrink-0 gap-3 rounded-lg border border-border-1 bg-surface-1 p-2.5">
      {/* Growth × Inflation quadrant */}
      <div className="flex w-72 shrink-0 flex-col">
        <div className="grid h-full grid-cols-2 grid-rows-2 flex-1 gap-1 pb-2">
          <QuadCell label="stagnation" short="Stagfl. risk" active={g === -1 && i === 1} />
          <QuadCell label="expansion" short="Reflation" active={g === 1 && i === 1} />
          <QuadCell label="contraction" short="Disinfl. slump" active={g === -1 && i === -1} />
          <QuadCell label="soft landing" short="Goldilocks" active={g === 1 && i === -1} />
        </div>
        <div className="flex items-center justify-between border-t border-divider pt-1 text-[10px] text-txt-metadata">
          <span>← growth contracting · expanding →</span>
          <span>inflation ↓ / ↑</span>
        </div>
      </div>

      {/* Regime facts */}
      <div className="flex min-w-0 flex-1 flex-col justify-center gap-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-txt-metadata">Current regime</span>
          <span className="rounded border border-status-accent/40 bg-status-accent/10 px-2 py-0.5 text-[15px] font-bold text-sky-100">
            {QUADRANT_SHORT[regime.quadrant_label] ?? String(regime.quadrant_label ?? 'N/A').replace(/_/g, ' ')}
          </span>
          {regime.transition && (
            <span className="inline-flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[11px] font-semibold tracking-wide text-amber-300">
              ● TRANSITION
            </span>
          )}
          <ConfidenceBadge confidence={regime.confidence} />
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
          <span className="inline-flex items-center gap-1.5">
            <span className="text-txt-muted">growth</span>
            <span className="font-semibold text-txt-secondary">{String(regime.growth_state ?? '').replace(/_/g, ' ').toLowerCase()}</span>
            <DirectionArrow sign={directionSign(regime.growth_direction)} />
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="text-txt-muted">inflation</span>
            <span className="font-semibold text-txt-secondary">{String(regime.inflation_state ?? '').replace(/_/g, ' ').toLowerCase()}</span>
            <DirectionArrow sign={directionSign(regime.inflation_direction)} />
          </span>
          <span className="text-txt-muted">dwell {regime.dwell_weeks}w</span>
          <span className="text-txt-muted">coverage {belief}%</span>
          {regime.lens_disagreement?.flag && (
            <span className="text-amber-300" title={regime.lens_disagreement.summary}>lens disagreement</span>
          )}
        </div>

        {macroClimate?.summary && (
          <p className="text-[12px] leading-snug text-txt-secondary">{macroClimate.summary}</p>
        )}
      </div>
    </div>
  )
}

/* Compact supporting climate strip — secondary to the regime focal area. */
function ClimateStrip({ macroClimate, investmentClimate, climate, regime }) {
  const policy = climate.POLICY_LIQUIDITY
  const finCond = climate.FINANCIAL_CONDITIONS
  const marketConf = climate.MARKET_CONFIRMATION
  const riskAppetite = climate.RISK_APPETITE
  const items = [
    { title: '1 · Cyclical Macro', state: String(regime.quadrant_label ?? 'N/A').replace(/_/g, ' '), direction: macroClimate.direction, confidence: macroClimate.confidence, coverage: macroClimate.coverage },
    { title: '2 · Policy / Liquidity + Fin. Cond.', state: `${policy.state} / ${finCond.state}`, direction: finCond.direction, confidence: finCond.confidence, coverage: finCond.coverage },
    { title: '3 · Market Confirmation / Risk Appetite', state: `${marketConf.state} · ${riskAppetite.state}`, direction: marketConf.direction, confidence: marketConf.confidence, coverage: marketConf.coverage },
    { title: '4 · Investment Climate', state: String(investmentClimate.state ?? 'N/A').replace(/_/g, ' '), direction: investmentClimate.direction, confidence: investmentClimate.confidence, coverage: investmentClimate.coverage },
  ]
  return (
    <div className="grid shrink-0 grid-cols-4 gap-2">
      {items.map(({ title, state, direction, confidence, coverage }) => {
        const sign = directionSign(direction)
        return (
          <div data-testid="climate-pill" key={title}
            className="flex min-w-0 flex-col justify-center rounded-md border border-border-1 bg-surface-1 px-3 py-1.5">
            <div className="cx-label truncate">{title}</div>
            <div className="mt-0.5 flex items-center gap-1.5">
              <span className="truncate text-[12.5px] font-semibold text-txt-primary">{String(state).replace(/_/g, ' ')}</span>
              <DirectionArrow sign={sign} />
            </div>
            <div className="mt-0.5 flex items-center gap-1.5">
              <ConfidenceBadge confidence={confidence} />
              {typeof coverage === 'number' && (
                <span className="text-[10px] tabular-nums text-txt-metadata">cov {Math.round(coverage * 100)}%</span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* 8-asset stance board — decision matrix. Click row → Asset Lens. */
function AssetBoard({ snapshot, onSelectAsset }) {
  return (
    <div data-testid="asset-board" className="flex h-full min-h-0 flex-col">
      <table className="cx-table">
        <thead>
          <tr className="text-left">
            <th className="w-[20%]">Asset</th>
            <th className="w-[13%]">Stance</th>
            <th className="w-[11%] text-center">WoW</th>
            <th className="w-[13%]">Conf</th>
            <th className="w-[13%]">Gate</th>
            <th>Top driver</th>
            <th className="w-[10%] text-right">Data</th>
          </tr>
        </thead>
        <tbody>
          {snapshot.asset_views.map((v) => {
            const numeric = v.drivers.filter((d) => d.contribution !== null)
            const topDriver = [...numeric].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))[0]
              ?? v.drivers[0]
              ?? null
            return (
              <tr key={v.asset}
                onClick={() => onSelectAsset(v.asset)}
                onKeyDown={(e) => e.key === 'Enter' && onSelectAsset(v.asset)}
                tabIndex={0}
                aria-label={`${v.label}, stance ${v.stance}, open asset lens`}
                className="cx-row">
                <td className="py-1 font-medium text-txt-primary">{v.label}</td>
                <td className="py-1"><StanceChip stance={v.stance} /></td>
                <td className="py-1 text-center"><StanceDelta delta={v.stance_delta} /></td>
                <td className="py-1"><ConfidenceBadge confidence={v.confidence} /></td>
                <td className="py-1"><ConfirmationChip value={v.confirmation_display} /></td>
                <td className="truncate py-1 text-[11.5px] text-txt-muted">
                  {topDriver ? (
                    <>
                      <span className="text-txt-secondary">{topDriver.label.replace(/[_%]/g, ' ').toLowerCase()}</span>
                      {topDriver.contribution !== null && (
                        <DeltaText value={topDriver.contribution} />
                      )}
                    </>
                  ) : (
                    <span className="text-txt-muted">no driver data</span>
                  )}
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

/* What changed — macro-information/release moves visually separated from
 * genuine market-condition moves. NO_NEW_INFORMATION stays a gray data-state,
 * never a neutral directional move. */
function WhatChangedPanel({ weeklyChange }) {
  const noNew = weeklyChange.information_status === 'NO_NEW_INFORMATION'
  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* A — macro information / release change */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="mb-1 flex items-center justify-between">
          <SectionHeading>Macro information / release change</SectionHeading>
          <FreshnessChip status={noNew ? 'NO_NEW_INFORMATION' : 'UPDATED'} />
        </div>
        <ul className="min-h-0 flex-1 space-y-0.5 overflow-auto pr-0.5">
          {weeklyChange.events.map((e) => (
            <li key={e.factor_id + String(e.observation_date)}
              className="flex items-start gap-2 rounded px-1 py-0.5 text-[11.5px]">
              <FreshnessChip status={e.status} />
              <span className="min-w-0 flex-1">
                <span className="text-txt-secondary">{e.factor_id.replaceAll('_', ' ').toLowerCase()}</span>
                <span className="mx-1 text-txt-metadata">·</span>
                <span className="text-txt-muted">{String(e.event_type ?? '').replaceAll('_', ' ').toLowerCase()}</span>
                <span className="block truncate text-txt-metadata">{e.note}</span>
              </span>
              <span className="shrink-0 text-[10px] text-txt-metadata">{shortDate(e.observation_date)}</span>
            </li>
          ))}
        </ul>
        {weeklyChange.stale_factors.length > 0 && (
          <p className="mt-1 text-[10px] text-amber-300/90">
            stale (flagged, not zero-filled): {weeklyChange.stale_factors.join(', ')}
          </p>
        )}
      </div>

      <div className="my-1 border-t border-divider" aria-hidden />

      {/* B — genuine market-condition move */}
      <div className="flex shrink-0 flex-col">
        <div className="mb-1">
          <SectionHeading>Genuine market-condition move</SectionHeading>
        </div>
        <ul className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11.5px]">
          {weeklyChange.market_moves.map((m) => (
            <li key={m.instrument} className="flex items-center justify-between">
              <span className="truncate text-txt-secondary">{m.instrument}</span>
              <span className={`font-semibold tabular-nums ${
                m.weekly_change > 0 ? 'text-status-positive' : m.weekly_change < 0 ? 'text-status-negative' : 'text-txt-muted'
              }`} title={m.metric_class}>
                {fmtBackendMove(m)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function ExecutiveBrief({ brief }) {
  return (
    <div className="grid grid-cols-3 gap-3 text-[11.5px] leading-snug">
      <div className="min-w-0">
        <div className="cx-label mb-0.5">What changed</div>
        <p className="text-txt-secondary">{brief.what_changed}</p>
      </div>
      <div className="min-w-0 border-l border-divider pl-3">
        <div className="cx-label mb-0.5">Why it matters</div>
        <p className="text-txt-secondary">{brief.why_it_matters}</p>
      </div>
      <div className="min-w-0 border-l border-divider pl-3">
        <div className="cx-label mb-0.5">Watch next</div>
        <p className="text-txt-secondary">{brief.what_to_watch.join(' · ')}</p>
      </div>
    </div>
  )
}

export default function OverviewPage({ snapshot, setSelectedAsset }) {
  const { macro_climate, investment_climate, climate, regime } = snapshot
  return (
    <div data-testid="overview-page" className="flex h-full flex-col gap-2 p-2">
      {/* Q1 — dominant regime focal area */}
      <RegimeFocal regime={regime} macroClimate={macro_climate} />
      {/* supporting climate strip */}
      <ClimateStrip
        macroClimate={macro_climate} investmentClimate={investment_climate}
        climate={climate} regime={regime} />

      {/* Q2 + Q3 body */}
      <div className="grid min-h-0 flex-1 grid-cols-[5fr_4fr] gap-2">
        <Card title="Asset stance board — 8 assets (click a row for Asset Lens)"
          right={<span className="cx-label">stance −2…+2 · WoW change</span>}
          className="min-h-0" bodyClassName="p-1.5">
          <AssetBoard snapshot={snapshot} onSelectAsset={(asset) => setSelectedAsset(asset)} />
        </Card>

        <div className="flex min-h-0 flex-col gap-2">
          <Card title="What changed this week" className="min-h-0 flex-1" bodyClassName="overflow-hidden">
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