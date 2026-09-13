import { Card, FreshnessChip } from '../components/primitives.jsx'
import { shortDate } from '../lib/format.js'

const SEVERITY_CLASSES = {
  HIGH: 'border-amber-500/50 bg-amber-500/10 text-amber-300',
  MEDIUM: 'border-amber-500/30 bg-amber-500/5 text-amber-200/90',
  LOW: 'border-ink-700 bg-ink-850 text-ink-300',
}

function HealthCounters({ counts }) {
  const items = [
    { label: 'Fresh', value: counts.fresh, cls: 'text-sky-300 border-sky-500/30 bg-sky-500/10' },
    { label: 'No new info', value: counts.no_new_information, cls: 'text-zinc-400 border-zinc-600/40 bg-zinc-500/5' },
    { label: 'Stale', value: counts.stale, cls: 'text-amber-300 border-amber-500/40 bg-amber-500/10' },
    { label: 'Missing', value: counts.missing, cls: 'text-amber-300 border-amber-500/30 bg-amber-500/5' },
    { label: 'Blocked', value: counts.blocked, cls: 'text-amber-300 border-amber-500/50 bg-amber-500/10' },
  ]
  return (
    <div data-testid="health-counters" className="flex gap-2">
      {items.map((i) => (
        <div key={i.label} className={`flex-1 rounded border px-3 py-2 ${i.cls}`}>
          <div className="text-lg font-bold tabular-nums">{i.value}</div>
          <div className="text-[10px] uppercase tracking-wider opacity-80">{i.label}</div>
        </div>
      ))}
    </div>
  )
}

export default function DataHealthPage({ snapshot }) {
  const dh = snapshot.data_health_summary
  return (
    <div data-testid="data-health-page" className="h-full overflow-auto p-2">
      <div className="flex flex-col gap-2">
        <div className="grid grid-cols-[1fr_1.4fr] gap-2">
          <Card title="Pipeline / data truth (separate from investment signal)">
            <HealthCounters counts={dh.counts} />
            <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
              <div className="rounded border border-ink-700 bg-ink-850 px-2 py-1.5">
                <div className="text-[10px] uppercase tracking-wider text-ink-500">Evidence lane</div>
                <div className="mt-0.5 font-semibold text-violet-300">{dh.lane}</div>
              </div>
              <div className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5">
                <div className="text-[10px] uppercase tracking-wider text-ink-500">FORMAL_OOS eligibility</div>
                <div className="mt-0.5 font-semibold text-amber-300">{dh.formal_eligibility.replace(/_/g, ' ')}</div>
              </div>
            </div>
            <p className="mt-2 text-[10px] leading-snug text-ink-500">
              Amber/gray badges describe pipeline health only — they must never be read as a bearish market signal.
              MONITORING views on this snapshot are not FORMAL_OOS evidence.
            </p>
          </Card>
          <Card title="Unresolved semantic / source contracts">
            <ul className="space-y-1.5">
              {dh.unresolved_contracts.map((c) => (
                <li key={c.id} className={`rounded border px-2 py-1.5 text-[11px] ${SEVERITY_CLASSES[c.severity] ?? SEVERITY_CLASSES.LOW}`}>
                  <span className="font-semibold">{c.id}</span>
                  <span className="ml-2 opacity-90">{c.note}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <Card title="Provenance / series detail">
          <table className="w-full border-collapse text-[11px]">
            <thead>
              <tr className="text-left text-[9px] uppercase tracking-wider text-ink-500">
                <th className="pb-1 font-medium">Series</th>
                <th className="pb-1 font-medium">Source</th>
                <th className="pb-1 font-medium">Status</th>
                <th className="pb-1 font-medium">Last observation</th>
                <th className="pb-1 font-medium">Available at (PIT)</th>
                <th className="pb-1 font-medium">Note</th>
              </tr>
            </thead>
            <tbody>
              {dh.items.map((it) => (
                <tr key={it.series} className="border-t border-ink-800">
                  <td className="py-1 font-medium text-zinc-200">{it.series}</td>
                  <td className="py-1 text-ink-300">{it.source}</td>
                  <td className="py-1"><FreshnessChip status={it.status} /></td>
                  <td className="py-1 tabular-nums text-ink-300">{shortDate(it.last_observation)}</td>
                  <td className="py-1 tabular-nums text-ink-300">{it.available_at ?? '—'}</td>
                  <td className="py-1 text-ink-500">{it.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        {snapshot.details?.method_notes && (
          <Card title="Method notes (drill-down)">
            <ul className="list-inside list-disc text-[11px] text-ink-300">
              {snapshot.details.method_notes.map((n) => <li key={n}>{n}</li>)}
            </ul>
          </Card>
        )}
      </div>
    </div>
  )
}
