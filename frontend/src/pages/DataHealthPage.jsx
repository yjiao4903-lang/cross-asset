import { AlertTriangle, CheckCircle2, CircleSlash, Lock } from 'lucide-react'
import { Card, FreshnessChip, SectionHeading } from '../components/primitives.jsx'

/* Data & Evidence Health (#118 Workstream G) — an OPERATIONAL / evidence surface.
 * Amber/gray/blue only. Red/green (directional colors) never appear here, so a
 * data-health failure can never be misread as a bearish market signal. */

const OVERALL_CLASSES = {
  OK: 'border-status-info/30 bg-status-info/10 text-status-info',
  COMPLETE: 'border-status-info/30 bg-status-info/10 text-status-info',
  PARTIAL: 'border-status-warning/40 bg-status-warning/10 text-status-warning-fg',
  BLOCKED: 'border-status-warning/50 bg-status-warning/10 text-status-warning-fg',
}

/* severity-ordered status groups for the evidence surface */
const STATUS_GROUP_ORDER = ['BLOCKED', 'MISSING', 'STALE', 'PARTIAL', 'NO_NEW_INFORMATION', 'UPDATED', 'FRESH']
const STATUS_GROUP_LABEL = {
  BLOCKED: 'Blocked', MISSING: 'Missing', STALE: 'Stale', PARTIAL: 'Partial',
  NO_NEW_INFORMATION: 'No new information', UPDATED: 'Updated', FRESH: 'Fresh',
}

function Counter({ value, label, cls, icon }) {
  return (
    <div className={`flex flex-1 items-center gap-2 rounded-md border px-3 py-2 ${cls}`}>
      {icon}
      <div>
        <div className="text-lg font-bold tabular-nums leading-tight">{value}</div>
        <div className="text-[10px] uppercase tracking-wider opacity-90">{label}</div>
      </div>
    </div>
  )
}

function groupFamilyStatus(map) {
  const groups = {}
  for (const [family, raw] of Object.entries(map ?? {})) {
    const status = raw === 'NO_NEW_INFORMATION' ? 'NO_NEW_INFORMATION'
      : raw === 'PARTIAL' ? 'PARTIAL'
        : raw === 'STALE' ? 'STALE'
          : raw === 'MISSING' ? 'MISSING'
            : raw === 'BLOCKED' ? 'BLOCKED'
              : raw === 'OK' || raw === 'FRESH' ? 'FRESH'
                : 'UPDATED'
    ;(groups[status] ??= []).push(family)
  }
  return groups
}

export default function DataHealthPage({ snapshot }) {
  const dh = snapshot.data_health_summary
  const families = groupFamilyStatus(dh.family_information_status)
  const staleSet = new Set(dh.stale_components)
  const missingSet = new Set(dh.missing_components)

  return (
    <div data-testid="data-health-page" className="h-full overflow-auto p-2">
      <div className="flex flex-col gap-2">
        {/* operational truth — never a directional signal */}
        <Card title="Pipeline / data truth (evidence state, not market signal)">
          <div data-testid="health-counters" className="flex gap-2">
            <Counter value={dh.overall ?? 'N/A'} label="overall" cls={OVERALL_CLASSES[dh.overall] ?? OVERALL_CLASSES.PARTIAL} icon={<span className="text-2xl leading-none">◐</span>} />
            <Counter value={dh.stale_components.length} label="stale components"
              cls="border-status-warning/40 bg-status-warning/10 text-status-warning-fg" icon={<AlertTriangle className="h-5 w-5" />} />
            <Counter value={dh.missing_components.length} label="missing components"
              cls="border-status-warning/30 bg-status-warning/5 text-status-warning-fg" icon={<CircleSlash className="h-5 w-5" />} />
            <Counter value={dh.blockers.length} label="blockers"
              cls="border-status-warning/50 bg-status-warning/10 text-status-warning-fg" icon={<Lock className="h-5 w-5" />} />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-[11.5px]">
            <div className="rounded-md border border-border-1 bg-surface-2/40 px-2 py-1.5">
              <div className="cx-label">Evidence lane</div>
              <div className="mt-0.5 font-semibold text-violet-300">{snapshot.metadata.lane}</div>
            </div>
            <div className="rounded-md border border-border-1 bg-surface-2/40 px-2 py-1.5">
              <div className="cx-label">FORMAL eligibility</div>
              <div className="mt-0.5 text-txt-muted">not disclosed by producer V0</div>
            </div>
            <div className="rounded-md border border-border-1 bg-surface-2/40 px-2 py-1.5">
              <div className="cx-label">Status</div>
              <div className="mt-0.5 flex items-center gap-1 text-txt-secondary">
                <CheckCircle2 className="h-3.5 w-3.5 text-status-info" aria-hidden />
                {dh.overall === 'OK' || dh.overall === 'COMPLETE' ? 'operational' : 'attention needed'}
              </div>
            </div>
          </div>
          <p className="mt-2 text-[10px] leading-snug text-txt-metadata">
            {snapshot.metadata.lane === 'MONITORING'
              ? 'This is a MONITORING surface — not FORMAL_OOS evidence.'
              : `Lane ${snapshot.metadata.lane}.`}
            {' '}Amber flags describe pipeline health only and must never be read as a bearish market signal.
          </p>
        </Card>

        {/* status grouping — scanning by severity */}
        <Card title="Status grouping">
          <div className="grid grid-cols-3 gap-2">
            {STATUS_GROUP_ORDER.map((s) => {
              const isComponentStatus = s === 'STALE' || s === 'MISSING'
              const items = isComponentStatus
                ? (s === 'STALE' ? staleSet : missingSet)
                : new Set(families[s] ?? [])
              return (
                <div key={s}
                  className={`rounded-md border px-2 py-1.5 ${
                    s === 'BLOCKED' ? 'border-status-warning/50 bg-status-warning/10'
                      : s === 'MISSING' || s === 'STALE' ? 'border-status-warning/30 bg-status-warning/5'
                        : s === 'PARTIAL' ? 'border-status-warning/25 bg-status-warning/5'
                          : s === 'NO_NEW_INFORMATION' ? 'border-border-2 border-dashed bg-surface-1'
                            : s === 'FRESH' ? 'border-status-info/25 bg-status-info/5'
                              : 'border-border-1 bg-surface-1'
                  }`}>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="cx-section">{STATUS_GROUP_LABEL[s]}</span>
                    <span className="text-[11px] font-semibold tabular-nums text-txt-secondary">{items.size}</span>
                  </div>
                  {items.size === 0 ? (
                    <span className="text-[10.5px] text-txt-metadata">none</span>
                  ) : (
                    <ul className="space-y-1" style={{ maxHeight: 88, overflow: 'auto' }}>
                      {[...items].map((it) => (
                        <li key={it} className="flex items-center justify-between gap-1">
                          <span className="truncate text-[10.5px] text-txt-muted" title={it}>{it.replaceAll('_', ' ').toLowerCase()}</span>
                          <FreshnessChip status={s} className="shrink-0" />
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        </Card>

        {/* blockers detail */}
        <Card title="Blockers / unresolved contracts">
          {dh.blockers.length === 0 ? (
            <p className="text-[11.5px] text-txt-muted">No blockers disclosed in this snapshot.</p>
          ) : (
            <ul className="space-y-1 text-[11.5px]">
              {dh.blockers.map((b) => (
                <li key={b} className="rounded-md border border-status-warning/50 bg-status-warning/10 px-2 py-1.5 text-status-warning-fg">{b}</li>
              ))}
            </ul>
          )}
          {(snapshot.details?.gate_blockers && Object.keys(snapshot.details.gate_blockers).length > 0) ? (
            <div className="mt-2">
              <SectionHeading className="mb-1">per-asset gate blockers</SectionHeading>
              <ul className="space-y-0.5 text-[11px] text-txt-muted">
                {Object.entries(snapshot.details.gate_blockers).map(([asset, list]) => (
                  <li key={asset}>
                    <span className="font-medium text-txt-secondary">{asset}</span>{': '}
                    {list.map((g) => `${g.source} — ${g.reason}`).join(' · ')}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </Card>

        {/* provenance / semantics */}
        <Card title="Provenance & evidence metadata">
          <div className="grid grid-cols-2 gap-x-6 gap-y-0.5 text-[11.5px]">
            <div className="flex justify-between gap-3 border-b border-divider py-0.5">
              <span className="cx-label self-center">lineage</span><span className="text-right text-txt-secondary">{snapshot.details?.lineage_note ?? '—'}</span>
            </div>
            <div className="flex justify-between gap-3 border-b border-divider py-0.5">
              <span className="cx-label self-center">taxonomy_version</span><span className="tabular-nums text-txt-secondary">{String(snapshot.details?.taxonomy_version)}</span>
            </div>
            <div className="flex justify-between gap-3 border-b border-divider py-0.5">
              <span className="cx-label self-center">parameter_status</span><span className="text-right text-txt-secondary">{String(snapshot.details?.parameter_status ?? '—')}</span>
            </div>
            <div className="flex justify-between gap-3 border-b border-divider py-0.5">
              <span className="cx-label self-center">released factors</span>
              <span className="text-right text-txt-muted">{(snapshot.details?.released_factors ?? []).length}</span>
            </div>
          </div>

          {Array.isArray(snapshot.details?.released_factors) && snapshot.details.released_factors.length > 0 && (
            <div className="mt-2">
              <SectionHeading className="mb-1">released this period</SectionHeading>
              <div className="flex flex-wrap gap-1">
                {snapshot.details.released_factors.map((f) => (
                  <span key={f} className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-txt-muted">{f.replaceAll('_', ' ')}</span>
                ))}
              </div>
            </div>
          )}

          {snapshot.details?.subfactor_scores_current && Object.keys(snapshot.details.subfactor_scores_current).length > 0 && (
            <div className="mt-2">
              <SectionHeading className="mb-1">subfactor scores (current)</SectionHeading>
              <div className="grid grid-cols-2 gap-x-6 text-[11px]">
                {Object.entries(snapshot.details.subfactor_scores_current).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between border-b border-divider py-0.5">
                    <span className="truncate pr-2 text-txt-muted">{k.replaceAll('_', ' ')}</span>
                    <span className={`tabular-nums ${v === null ? 'text-txt-metadata' : 'text-txt-secondary'}`}>{v === null ? 'n/a' : v > 0 ? `+${v.toFixed(2)}` : v.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}