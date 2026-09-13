import { AlertTriangle, ArrowDown, ArrowRight, ArrowUp, CalendarClock, CircleSlash, Lock } from 'lucide-react'

/* ---------- direction (red/green RESERVED for market/stance direction) ---------- */

export function DirectionArrow({ sign, className = '' }) {
  if (sign === 'UP') return <ArrowUp aria-label="up" className={`inline h-3.5 w-3.5 text-emerald-400 ${className}`} />
  if (sign === 'DOWN') return <ArrowDown aria-label="down" className={`inline h-3.5 w-3.5 text-rose-400 ${className}`} />
  return <ArrowRight aria-label="flat" className={`inline h-3.5 w-3.5 text-zinc-500 ${className}`} />
}

/* ---------- stance (-2..+2): directional, so red/green allowed ---------- */

const STANCE_CLASSES = {
  2: 'bg-emerald-500/25 text-emerald-300 border-emerald-400/40',
  1: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  0: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/30',
  [-1]: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
  [-2]: 'bg-rose-500/20 text-rose-300 border-rose-400/40',
}

export function StanceChip({ stance, label, className = '' }) {
  const key = stance > 0 ? Math.ceil(stance) : stance < 0 ? Math.floor(stance) : 0
  return (
    <span
      data-testid="stance-chip"
      data-stance={stance}
      className={`inline-flex min-w-[3.4rem] items-center justify-center rounded border px-1.5 py-0.5 text-[11px] font-semibold tabular-nums ${STANCE_CLASSES[key] ?? STANCE_CLASSES[0]} ${className}`}
    >
      {label ?? (stance > 0 ? `+${stance}` : `${stance}`)}
    </span>
  )
}

/* ---------- freshness / data-health: NEVER bearish red.
 * amber = warning, gray = unavailable / no new information, blue = fresh OK ---------- */

const FRESHNESS_CLASSES = {
  FRESH: 'bg-sky-500/10 text-sky-300 border-sky-500/30',
  NO_NEW_INFORMATION: 'bg-zinc-500/10 text-zinc-400 border-zinc-600/40 border-dashed',
  STALE: 'bg-amber-500/10 text-amber-300 border-amber-500/40',
  MISSING: 'bg-amber-500/5 text-amber-400/90 border-amber-500/30 border-dashed',
  BLOCKED: 'bg-amber-500/10 text-amber-300 border-amber-500/50',
}

const FRESHNESS_ICONS = {
  FRESH: null,
  NO_NEW_INFORMATION: CalendarClock,
  STALE: AlertTriangle,
  MISSING: CircleSlash,
  BLOCKED: Lock,
}

const FRESHNESS_LABELS = {
  FRESH: 'FRESH',
  NO_NEW_INFORMATION: 'NO NEW INFO',
  STALE: 'STALE',
  MISSING: 'MISSING',
  BLOCKED: 'BLOCKED',
}

export function FreshnessChip({ status, className = '' }) {
  const Icon = FRESHNESS_ICONS[status]
  return (
    <span
      data-testid="freshness-chip"
      data-status={status}
      title={`Data status: ${status}`}
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium tracking-wide ${FRESHNESS_CLASSES[status] ?? FRESHNESS_CLASSES.MISSING} ${className}`}
    >
      {Icon ? <Icon className="h-3 w-3" aria-hidden /> : null}
      {FRESHNESS_LABELS[status] ?? status}
    </span>
  )
}

/* ---------- confidence: LOW is amber (warning), never bearish ---------- */

export function ConfidenceBadge({ confidence, className = '' }) {
  const pct = Math.round(confidence * 100)
  const level = confidence >= 0.65 ? 'HIGH' : confidence >= 0.45 ? 'MEDIUM' : 'LOW'
  const cls =
    level === 'HIGH'
      ? 'text-sky-300 border-sky-500/30 bg-sky-500/10'
      : level === 'MEDIUM'
        ? 'text-zinc-300 border-zinc-600/50 bg-zinc-500/10'
        : 'text-amber-300 border-amber-500/40 bg-amber-500/10'
  return (
    <span data-testid="confidence-badge" data-level={level} title={`Confidence ${pct}%`}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium tabular-nums ${cls} ${className}`}>
      {level} {pct}%
    </span>
  )
}

/* ---------- market confirmation gate ---------- */

const CONFIRMATION_CLASSES = {
  CONFIRMED: 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10',
  DIVERGENT: 'text-sky-300 border-sky-500/30 bg-sky-500/10',
  COUNTER_TREND: 'text-amber-300 border-amber-500/40 bg-amber-500/10',
}

export function ConfirmationChip({ value, className = '' }) {
  return (
    <span data-testid="confirmation-chip" data-confirmation={value}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium ${CONFIRMATION_CLASSES[value] ?? CONFIRMATION_CLASSES.DIVERGENT} ${className}`}>
      {value.replace('_', ' ')}
    </span>
  )
}

/* ---------- lane badge ---------- */

export function LaneBadge({ lane, className = '' }) {
  return (
    <span data-testid="lane-badge"
      className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-semibold tracking-wider text-violet-300 border-violet-400/40 bg-violet-500/10 ${className}`}>
      {lane}
    </span>
  )
}

/* ---------- panel card ---------- */

export function Card({ title, right, children, className = '', bodyClassName = '' }) {
  return (
    <section className={`flex min-h-0 flex-col rounded-lg border border-ink-700 bg-ink-900 ${className}`}>
      {title ? (
        <header className="flex shrink-0 items-center justify-between border-b border-ink-700 px-3 py-1.5">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-ink-300">{title}</h2>
          {right}
        </header>
      ) : null}
      <div className={`min-h-0 flex-1 px-3 py-2 ${bodyClassName}`}>{children}</div>
    </section>
  )
}
