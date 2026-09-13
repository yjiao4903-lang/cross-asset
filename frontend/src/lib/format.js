export function fmtPct(value, { sign = true } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const s = value > 0 && sign ? '+' : ''
  return `${s}${value.toFixed(1)}%`
}

export function fmtBps(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const s = value > 0 ? '+' : ''
  return `${s}${Math.round(value)}bps`
}

export function fmtMove(item) {
  if (!item || item.move === null || item.move === undefined) return '—'
  return item.unit === 'bps' ? fmtBps(item.move) : fmtPct(item.move)
}

/* Backend market_condition_delta.moves unit vocabulary: PCT | BPS | POINT */
export function fmtBackendMove(move) {
  if (!move || move.weekly_change === null || move.weekly_change === undefined) return '—'
  const v = move.weekly_change
  const s = v > 0 ? '+' : ''
  if (move.unit === 'BPS') return `${s}${v.toFixed(0)}bps`
  if (move.unit === 'POINT') return `${s}${v.toFixed(1)}pt`
  return `${s}${v.toFixed(2)}%`
}

export function stanceLabel(stance) {
  return { 2: 'STRONG BUY', 1: 'OVERWEIGHT', 0: 'NEUTRAL', [-1]: 'UNDERWEIGHT', [-2]: 'STRONG SELL' }[stance]
}

export function stanceDelta(prior, current) {
  return current - prior
}

export function confidenceLabel(confidence) {
  if (confidence >= 0.65) return 'HIGH'
  if (confidence >= 0.45) return 'MEDIUM'
  return 'LOW'
}

export function directionSign(direction) {
  if (['UP', 'IMPROVING', 'EASING', 'ACCELERATING', 'RISING'].includes(direction)) return 'UP'
  if (['DOWN', 'DETERIORATING', 'TIGHTENING', 'DECELERATING', 'FALLING'].includes(direction)) return 'DOWN'
  return 'FLAT'
}

export function shortDate(iso) {
  if (!iso) return '—'
  return String(iso).slice(0, 10)
}
