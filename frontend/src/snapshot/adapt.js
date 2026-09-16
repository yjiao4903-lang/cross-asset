/**
 * Presentation-only adapter: authoritative #117 DashboardSnapshotV0 payload →
 * UI view model. Rules (WEB-CONTROL #116 comment 5654314322):
 *  - render backend states/directions/confidence directly;
 *  - selection, renaming and display formatting only;
 *  - NO client-side sign/economic inference, NO contribution recomputation,
 *    NO invention of fields the producer does not emit.
 */

const ASSET_LABELS = {
  CN_EQ: 'CN Equity',
  HK_EQ: 'HK Equity',
  US_EQ: 'US Equity',
  CN_BOND: 'CN Bonds',
  GOLD: 'Gold',
  COPPER: 'Copper / Commodities',
  USD_CNY: 'USD/CNY / Dollar',
  CASH: 'Cash',
}

export function assetLabel(asset) {
  return ASSET_LABELS[asset] ?? asset
}

const FAMILY_LABELS = {
  GROWTH_ACTIVITY: 'Growth & Activity',
  INFLATION_COST: 'Inflation & Cost Pressure',
  POLICY_LIQUIDITY: 'Policy & Liquidity',
  CHINA_CYCLE: 'China Cycle / Credit-Demand',
  FINANCIAL_CONDITIONS: 'Financial Conditions & Stress',
  MARKET_CONFIRMATION: 'Market Confirmation & Momentum',
  RISK_APPETITE: 'Risk Appetite / Positioning',
  VALUATION_RISK_PREMIUM: 'Valuation & Risk Premium',
}

export function familyLabel(family) {
  return FAMILY_LABELS[family] ?? family
}

/* freshness_status → display data-state. Pure vocabulary mapping.
 * PARTIAL is a producer-owned coverage state and stays PARTIAL — it must not
 * collapse into STALE (WEB-CONTROL R3, #116 comment 5654468573). */
const FRESHNESS_MAP = {
  OK: 'FRESH',
  PARTIAL: 'PARTIAL',
  STALE: 'STALE',
  NO_NEW_INFORMATION: 'NO_NEW_INFORMATION',
  MISSING: 'MISSING',
  BLOCKED: 'BLOCKED',
}

export function mapFreshness(status) {
  return FRESHNESS_MAP[status] ?? 'MISSING'
}

const DATA_HEALTH_MAP = {
  OK: 'FRESH',
  PARTIAL: 'PARTIAL',
  STALE: 'STALE',
  MISSING: 'MISSING',
  BLOCKED: 'BLOCKED',
}

/* Backend market-confirmation vocabulary includes UNKNOWN (#117 R1).
 * UNKNOWN/UNAVAILABLE render as data-state semantics, never as direction. */
const CONFIRMATION_KNOWN = ['CONFIRMED', 'DIVERGENT', 'COUNTER_TREND']

export function mapConfirmation(value) {
  if (CONFIRMATION_KNOWN.includes(value)) return value
  return 'UNKNOWN'
}

/*
 * Backend driver strings: "FAMILY:+0.16" (numeric, plottable) or
 * "market_confirmed:FACTOR" (qualitative). Parsing is presentation only —
 * the numeric contribution is displayed exactly as emitted, never recomputed.
 */
export function parseDriver(driverString) {
  const idx = driverString.lastIndexOf(':')
  if (idx === -1) return { label: driverString, contribution: null }
  const label = driverString.slice(0, idx)
  const raw = driverString.slice(idx + 1)
  const value = Number.parseFloat(raw)
  return {
    label,
    contribution: Number.isFinite(value) ? value : null,
  }
}

function climateMap(climateComponents) {
  const map = {}
  for (const c of climateComponents ?? []) map[c.component] = c
  return map
}

export function adaptSnapshot(payload) {
  const climate = climateMap(payload.climate_components)
  const dataHealth = payload.data_health_summary ?? {}
  const details = payload.details ?? {}

  const clusters = (payload.clusters ?? []).map((c) => ({
    id: c.cluster_id,
    family: c.family,
    label: `${familyLabel(c.family)} · ${c.horizon}`,
    familyLabel: familyLabel(c.family),
    horizon: c.horizon,
    direction: c.direction,
    score: c.score,
    weekly_delta: c.weekly_delta,
    confidence: c.confidence,
    coverage: c.coverage,
    freshness: mapFreshness(c.freshness_status),
    freshness_status: c.freshness_status,
    top_positive: c.top_positive ?? [],
    top_negative: c.top_negative ?? [],
    missing_factors: c.missing_factors ?? [],
    stale_factors: c.stale_factors ?? [],
  }))

  const info = payload.weekly_change?.information_set_delta ?? {}
  const events = (info.events ?? []).map((e) => ({
    ...e,
    status: e.event_type === 'OVERDUE' ? 'STALE' : 'UPDATED',
  }))

  const assetViews = (payload.asset_views ?? []).map((v) => ({
    asset: v.asset,
    label: assetLabel(v.asset),
    stance: v.stance,
    prior_stance: v.prior_stance,
    stance_delta: v.stance - v.prior_stance,
    confidence: v.confidence,
    macro_bias: v.macro_bias,
    market_confirmation: v.market_confirmation,
    confirmation_display: mapConfirmation(v.market_confirmation),
    valuation_tag: v.valuation_tag,
    drivers: (v.drivers ?? []).map(parseDriver),
    counter_signals: v.counter_signals ?? [],
    invalidator: v.invalidator,
    data_health: DATA_HEALTH_MAP[v.data_health] ?? 'MISSING',
    data_health_status: v.data_health,
  }))

  return {
    metadata: {
      ...payload.metadata,
      data_overall: dataHealth.overall ?? null,
    },
    macro_climate: payload.macro_climate,
    investment_climate: payload.investment_climate,
    climate,
    clusters,
    weekly_change: {
      information_status: info.status ?? null,
      events,
      stale_factors: info.stale_factors ?? [],
      macro_state_delta: payload.weekly_change?.macro_state_delta?.entries ?? [],
      market_moves: payload.weekly_change?.market_condition_delta?.moves ?? [],
      asset_view_delta: payload.weekly_change?.asset_view_delta?.entries ?? [],
    },
    regime: {
      quadrant_label: payload.regime?.quadrant_label ?? null,
      growth_state: payload.regime?.growth_state ?? null,
      growth_direction: payload.regime?.growth_direction ?? null,
      inflation_state: payload.regime?.inflation_state ?? null,
      inflation_direction: payload.regime?.inflation_direction ?? null,
      dwell_weeks: payload.regime?.dwell_weeks ?? null,
      transition: payload.regime?.transition_flag ?? false,
      confidence: payload.regime?.confidence ?? null,
      coverage: payload.regime?.coverage ?? null,
      lens_disagreement: payload.regime?.lens_disagreement ?? { flag: false, summary: '' },
    },
    asset_views: assetViews,
    cross_asset_pulse: {
      entries: (payload.cross_asset_pulse?.entries ?? []).map((e) => ({
        asset: e.asset,
        label: assetLabel(e.asset),
        r1w: e.ret_1w,
        r1m: e.ret_1m,
        r3m: e.ret_3m,
        momentum_label: e.momentum_label ?? null,
      })),
      // producer V0 does not emit YTD; UI must not invent it
      ytd_provided: false,
    },
    executive_brief: {
      what_changed: payload.executive_brief?.what_changed ?? '',
      why_it_matters: payload.executive_brief?.why_it_matters ?? '',
      what_to_watch: payload.executive_brief?.what_to_watch ?? [],
    },
    data_health_summary: {
      overall: dataHealth.overall ?? null,
      stale_components: dataHealth.stale_components ?? [],
      missing_components: dataHealth.missing_components ?? [],
      blockers: dataHealth.blockers ?? [],
      family_information_status: details.family_information_status ?? {},
    },
    details,
  }
}
