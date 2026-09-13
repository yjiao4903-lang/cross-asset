import { Card, FreshnessChip } from '../components/primitives.jsx'

const OVERALL_CLASSES = {
  OK: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
  COMPLETE: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
  PARTIAL: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  BLOCKED: 'border-amber-500/50 bg-amber-500/10 text-amber-300',
}

function FamilyStatusTable({ familyInformationStatus }) {
  const entries = Object.entries(familyInformationStatus ?? {})
  if (entries.length === 0) {
    return <p className="text-[11px] text-ink-500">Producer snapshot does not include per-family information status.</p>
  }
  return (
    <table className="w-full border-collapse text-[11px]">
      <thead>
        <tr className="text-left text-[9px] uppercase tracking-wider text-ink-500">
          <th className="pb-1 font-medium">Factor family</th>
          <th className="pb-1 font-medium">Information status</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([family, status]) => (
          <tr key={family} className="border-t border-ink-800">
            <td className="py-1 text-zinc-200">{family.replaceAll('_', ' ').toLowerCase()}</td>
            <td className="py-1">
              <FreshnessChip status={status === 'NO_NEW_INFORMATION' ? 'NO_NEW_INFORMATION' : status === 'UPDATED' ? 'UPDATED' : 'STALE'} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function DataHealthPage({ snapshot }) {
  const dh = snapshot.data_health_summary
  return (
    <div data-testid="data-health-page" className="h-full overflow-auto p-2">
      <div className="flex flex-col gap-2">
        <div className="grid grid-cols-2 gap-2">
          <Card title="Pipeline / data truth (separate from investment signal)">
            {/* counts are presentation tallies of producer-owned lists — nothing invented */}
            <div data-testid="health-counters" className="flex gap-2">
              <div className={`flex-1 rounded border px-3 py-2 ${OVERALL_CLASSES[dh.overall] ?? OVERALL_CLASSES.PARTIAL}`}>
                <div className="text-lg font-bold tabular-nums">{dh.overall}</div>
                <div className="text-[10px] uppercase tracking-wider opacity-80">overall</div>
              </div>
              <div className="flex-1 rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-amber-300">
                <div className="text-lg font-bold tabular-nums">{dh.stale_components.length}</div>
                <div className="text-[10px] uppercase tracking-wider opacity-80">stale components</div>
              </div>
              <div className="flex-1 rounded border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-amber-300">
                <div className="text-lg font-bold tabular-nums">{dh.missing_components.length}</div>
                <div className="text-[10px] uppercase tracking-wider opacity-80">missing components</div>
              </div>
              <div className="flex-1 rounded border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-amber-300">
                <div className="text-lg font-bold tabular-nums">{dh.blockers.length}</div>
                <div className="text-[10px] uppercase tracking-wider opacity-80">blockers</div>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
              <div className="rounded border border-ink-700 bg-ink-850 px-2 py-1.5">
                <div className="text-[10px] uppercase tracking-wider text-ink-500">Evidence lane</div>
                <div className="mt-0.5 font-semibold text-violet-300">{snapshot.metadata.lane}</div>
              </div>
              <div className="rounded border border-ink-700 bg-ink-850 px-2 py-1.5">
                <div className="text-[10px] uppercase tracking-wider text-ink-500">FORMAL_OOS eligibility</div>
                <div className="mt-0.5 text-ink-400">not disclosed by producer V0</div>
              </div>
            </div>
            <p className="mt-2 text-[10px] leading-snug text-ink-500">
              Amber badges describe pipeline health only — they must never be read as a bearish market signal.
              MONITORING views on this snapshot are not FORMAL_OOS evidence.
            </p>
          </Card>
          <Card title="Blockers / stale / missing (producer-emitted lists)">
            <ul className="space-y-1.5 text-[11px]">
              {dh.blockers.map((b) => (
                <li key={b} className="rounded border border-amber-500/50 bg-amber-500/10 px-2 py-1.5 text-amber-200">{b}</li>
              ))}
              {dh.stale_components.map((s) => (
                <li key={s} className="flex items-center gap-2 rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1.5 text-amber-200/90">
                  <FreshnessChip status="STALE" /> {s}
                </li>
              ))}
              {dh.missing_components
                .filter((m) => !dh.stale_components.includes(m))
                .map((m) => (
                  <li key={m} className="flex items-center gap-2 rounded border border-amber-500/30 border-dashed bg-amber-500/5 px-2 py-1.5 text-amber-200/90">
                    <FreshnessChip status="MISSING" /> {m}
                  </li>
                ))}
              {dh.blockers.length === 0 && dh.stale_components.length === 0 && dh.missing_components.length === 0 && (
                <li className="text-ink-500">No stale/missing/blockers disclosed in this snapshot.</li>
              )}
            </ul>
          </Card>
        </div>

        <Card title="Per-family information status (producer `details.family_information_status`)">
          <FamilyStatusTable familyInformationStatus={dh.family_information_status} />
        </Card>

        {snapshot.details?.lineage_note && (
          <Card title="Lineage / method notes (drill-down)">
            <ul className="list-inside list-disc text-[11px] text-ink-300">
              <li>{snapshot.details.lineage_note}</li>
              <li>taxonomy_version: {String(snapshot.details.taxonomy_version)} · parameter_status: {String(snapshot.details.parameter_status)}</li>
              {snapshot.details.parameter_status && (
                <li>
                  The UI renders producer fields via a presentation-only adapter; it performs no economic or signal computation.
                </li>
              )}
            </ul>
          </Card>
        )}
      </div>
    </div>
  )
}
