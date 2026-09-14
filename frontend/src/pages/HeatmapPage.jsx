import { Card, ConfidenceBadge, DirectionArrow, FreshnessChip } from '../components/primitives.jsx'
import { directionSign } from '../lib/format.js'

const HORIZONS = ['CYCLICAL', 'TACTICAL', 'STRUCTURAL_CONTEXT']

/* Null-safe numeric formatting. Legal DashboardSnapshotV0 producer payloads may
 * emit score / weekly_delta / coverage as null (data unavailable). Those must
 * render as an explicit unavailable dash — never silently become zero. */
const NA = '—'
function fmtNum(v, digits, signed = false) {
  if (v === null || v === undefined || !Number.isFinite(v)) return NA
  const sign = signed && v > 0 ? '+' : ''
  return `${sign}${v.toFixed(digits)}`
}

/* Contributor object per the producer contract is { factor_id, contribution }.
 * A contributed factor may also arrive as a plain string id. Consume safely. */
function contributorLabel(t) {
  if (t === null || t === undefined) return ''
  if (typeof t === 'object') {
    const name = String(t.factor_id ?? '').replaceAll('_', ' ').toLowerCase()
    const c = t.contribution
    const val = typeof c === 'number' && Number.isFinite(c) ? ` (${fmtNum(c, 2, true)})` : ''
    return `${name}${val}`
  }
  return String(t).replaceAll('_', ' ').toLowerCase()
}
function contributorList(items) {
  if (!Array.isArray(items) || items.length === 0) return '—'
  return items.map(contributorLabel).filter(Boolean).join(', ') || '—'
}

/* Cell surface styling distinguishes every data state. The key invariant:
 * NO_NEW_INFORMATION is a gray dashed no-change state, never the amber used
 * for PARTIAL / STALE / MISSING — so NO_NEW_INFORMATION != STALE visually. */
const CELL_STATE_CLASSES = {
  FRESH: 'border-border-1 bg-surface-2/40 hover:bg-surface-hover text-txt-secondary',
  UPDATED: 'border-status-info/25 bg-status-info/5 hover:bg-surface-hover text-txt-secondary',
  NO_NEW_INFORMATION: 'border-dashed border-border-2 bg-surface-1 hover:bg-surface-hover text-txt-muted',
  PARTIAL: 'border-amber-500/30 bg-amber-500/5 hover:bg-amber-500/10 text-amber-200/90',
  STALE: 'border-amber-500/50 bg-amber-500/10 hover:bg-amber-500/15 text-amber-200',
  MISSING: 'border-dashed border-amber-500/40 bg-amber-500/5 hover:bg-amber-500/10 text-amber-200/80',
  BLOCKED: 'border-amber-500/60 bg-amber-500/15 hover:bg-amber-500/20 text-amber-100',
  UNKNOWN: 'border-dashed border-border-2 bg-surface-1 text-txt-muted',
}

function HeatCell({ cluster, selected, onClick }) {
  const state = CELL_STATE_CLASSES[cluster.freshness] ?? CELL_STATE_CLASSES.FRESH
  return (
    <button type="button"
      onClick={onClick}
      aria-pressed={selected}
      title={`${cluster.id} — score ${fmtNum(cluster.score, 2)}, direction ${cluster.direction}, ${cluster.freshness}`}
      data-testid="heatmap-cell"
      className={`flex h-14 w-full flex-col items-start justify-between rounded-md border p-1.5 text-left transition-colors duration-75 ${
        selected ? 'ring-2 ring-status-accent ring-offset-1 ring-offset-surface-1 ' : ''
      }${state}`}>
      <span className="flex w-full items-center justify-between gap-1 text-[10.5px] font-semibold">
        <span className="truncate">{cluster.direction.replaceAll('_', ' ')}</span>
        <span className="tabular-nums text-txt-metadata">{fmtNum(cluster.score, 2, true)}</span>
      </span>
      <span className="flex w-full items-center justify-between gap-1">
        <DirectionArrow sign={directionSign(cluster.direction)} />
        <span className={`text-[10px] tabular-nums ${cluster.freshness === 'PARTIAL' || cluster.freshness === 'STALE' || cluster.freshness === 'MISSING' || cluster.freshness === 'BLOCKED' ? 'text-amber-300/80' : 'text-txt-metadata'}`}>
          Δ{fmtNum(cluster.weekly_delta, 2, true)}
        </span>
      </span>
    </button>
  )
}

function Field({ label, children, warn }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="cx-label pt-0.5">{label}</span>
      <span className={`text-right text-[11.5px] ${warn ? 'text-amber-300' : 'text-txt-secondary'}`}>{children}</span>
    </div>
  )
}

function DrillDown({ cluster }) {
  if (!cluster) {
    return <p className="text-[11.5px] text-txt-muted">Select a family × horizon cell to inspect producer-owned cluster detail.</p>
  }
  return (
    <div data-testid="heatmap-drilldown" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 border-b border-divider pb-2">
        <span className="text-[13px] font-semibold text-txt-primary">{cluster.familyLabel}</span>
        <span className="text-[10px] uppercase tracking-wider text-txt-metadata">{cluster.horizon} · {cluster.id}</span>
        <ConfidenceBadge confidence={cluster.confidence} />
        <FreshnessChip status={cluster.freshness} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Field label="score"><span className="tabular-nums">{fmtNum(cluster.score, 3)}</span></Field>
        <Field label="weekly_delta"><span className="tabular-nums">{fmtNum(cluster.weekly_delta, 3, true)}</span></Field>
        <Field label="direction">{cluster.direction}</Field>
        <Field label="coverage"><span className="tabular-nums">{
          cluster.coverage === null || cluster.coverage === undefined || !Number.isFinite(cluster.coverage)
            ? NA : `${Math.round(cluster.coverage * 100)}%`
        }</span></Field>
        <Field label="top_positive">{contributorList(cluster.top_positive)}</Field>
        <Field label="top_negative">{contributorList(cluster.top_negative)}</Field>
        <Field label="missing_factors" warn={cluster.missing_factors.length > 0}>
          {cluster.missing_factors.length ? cluster.missing_factors.join(', ') : '—'}
        </Field>
        <Field label="stale_factors" warn={cluster.stale_factors.length > 0}>
          {cluster.stale_factors.length ? cluster.stale_factors.join(', ') : '—'}
        </Field>
      </div>
    </div>
  )
}

export default function HeatmapPage({ snapshot, selectedCluster, setSelectedCluster }) {
  const selected = snapshot.clusters.find((c) => c.id === selectedCluster) ?? null
  const families = [...new Set(snapshot.clusters.map((c) => c.family))]
  const byKey = new Map(snapshot.clusters.map((c) => [`${c.family}@${c.horizon}`, c]))
  return (
    <div data-testid="heatmap-page" className="flex h-full gap-2 overflow-hidden p-2">
      {/* Dense matrix — the primary surface */}
      <Card title="Macro factor heatmap — family × horizon"
        right={<span className="cx-label">direction + score · Δ weekly · click to inspect</span>}
        className="min-w-0 flex-1" bodyClassName="overflow-auto">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-10">
            <tr className="text-left text-[10px] uppercase tracking-wider text-txt-muted"
              style={{ background: 'var(--color-surface-1)' }}>
              <th className="sticky left-0 w-52 py-1 pr-2 font-semibold" style={{ background: 'var(--color-surface-1)' }}>
                Factor family / horizon →
              </th>
              {HORIZONS.map((h) => (
                <th key={h} className="py-1 font-semibold">{h.replaceAll('_', ' ')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {families.map((family) => (
              <tr key={family} className="border-t border-divider">
                <td className="sticky left-0 py-1.5 pr-2 text-[11.5px] font-medium text-txt-secondary"
                  style={{ background: 'var(--color-surface-1)' }}>
                  {snapshot.clusters.find((c) => c.family === family).familyLabel}
                </td>
                {HORIZONS.map((h) => {
                  const c = byKey.get(`${family}@${h}`)
                  return (
                    <td key={h} className="py-1.5 pr-1 align-top">
                      {c ? (
                        <HeatCell cluster={c} selected={c.id === selectedCluster}
                          onClick={() => setSelectedCluster(c.id)} />
                      ) : (
                        <div className="flex h-14 items-center justify-center rounded-md border border-dashed border-border-1 text-[10px] text-txt-metadata">
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
        <p className="mt-2 text-[10px] leading-snug text-txt-metadata">
          Amber = PARTIAL / STALE / MISSING / BLOCKED data state; gray dashed = NO_NEW_INFORMATION (a no-change
          state) — never a bearish signal. Cell text is the producer-owned direction; no client-side inference.
        </p>
      </Card>

      {/* Coherent side/detail area — selected cluster */}
      <Card title="Cluster detail"
        className="w-80 shrink-0" bodyClassName="overflow-auto">
        <DrillDown cluster={selected} />
      </Card>
    </div>
  )
}