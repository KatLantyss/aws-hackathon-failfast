export function formatUsd(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

export function formatNumber(value: number, digits = 1): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value)
}

/**
 * The dataset has no real calendar date — only a sequential day-index
 * (NOON_UTC / event_day, 0-based). Show that honestly as "Day N" rather
 * than inventing a calendar date off an arbitrary anchor.
 */
export function formatDay(day: number | null | undefined): string {
  if (day == null) return '—'
  return `Day ${Math.round(day)}`
}

export function formatPct(value: number, digits = 1): string {
  return `${value >= 0 ? '' : ''}${formatNumber(value, digits)}%`
}

/**
 * Speed-loss color grading (v2.1 §4) — draws the eye to vessels that need
 * attention first. > 8% is a critical decision threshold (signal-red).
 */
export function speedLossColor(pct: number): string {
  if (pct >= 8) return 'var(--color-signal-red)'
  if (pct >= 5) return 'var(--color-brass-amber)'
  return 'var(--color-fathom-teal)'
}

export const URGENCY_LABEL: Record<string, string> = {
  LOW: '低',
  MEDIUM: '中',
  HIGH: '高',
}

export const URGENCY_COLOR: Record<string, string> = {
  LOW: 'var(--color-fathom-teal)',
  MEDIUM: 'var(--color-brass-amber)',
  HIGH: 'var(--color-signal-red)',
}

export const CONFIDENCE_LABEL: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

export const STATUS_LABEL: Record<string, string> = {
  underway: '航行中',
  moored: '靠泊中',
  anchored: '錨泊中',
}

export const STATUS_COLOR: Record<string, string> = {
  underway: 'var(--color-fathom-teal)',
  moored: 'var(--color-brass-amber)',
  anchored: 'var(--color-ink-slate)',
}


export const MAINTENANCE_STATUS_LABEL: Record<string, string> = {
  normal: '正常',
  needs_request: '需申請維修',
  requested: '已申請維修',
  in_progress: '維修中',
}

export const MAINTENANCE_STATUS_COLOR: Record<string, string> = {
  normal: 'var(--color-fathom-teal)',
  needs_request: 'var(--color-signal-red)',
  requested: 'var(--color-brass-amber)',
  in_progress: 'var(--color-brass-amber)',
}
