import type { ReactElement } from 'react'
import type { DataMode } from '../model/workbenchState'

export type ChipState = 'DEMO' | 'LIVE' | 'STALE' | 'BLOCKED' | 'MISSING' | 'UNAVAILABLE'

export const STATE_META: Record<ChipState, { label: string; hint: string }> = {
  DEMO: { label: 'DEMO', hint: 'Demonstration data' },
  LIVE: { label: 'LIVE', hint: 'Live evidence attached' },
  STALE: { label: 'STALE', hint: 'Evidence is out of date' },
  BLOCKED: { label: 'BLOCKED', hint: 'Gated / not connected' },
  MISSING: { label: 'MISSING', hint: 'Not present' },
  UNAVAILABLE: { label: 'UNAVAILABLE', hint: 'No value' },
}

/** Map a status/check value to a chip state. Never yields a positive verdict. */
export function mapCheckState(value: unknown): ChipState {
  if (value === true) return 'LIVE'
  if (value === false) return 'BLOCKED'
  const token = String(value == null ? '' : value).trim().toUpperCase()
  switch (token) {
    case 'NOT_CONNECTED':
    case 'DISCONNECTED':
      return 'MISSING'
    case 'NOT_EVALUATED':
    case 'PENDING':
    case '':
      return 'UNAVAILABLE'
    case 'BLOCKED':
      return 'BLOCKED'
    case 'STALE':
      return 'STALE'
    case 'CONNECTED':
    case 'READY':
    case 'CONVERGED':
      return 'LIVE'
    default:
      return 'UNAVAILABLE'
  }
}

export function dataModeChipState(mode: DataMode): ChipState {
  switch (mode) {
    case 'demo':
      return 'DEMO'
    case 'live':
      return 'LIVE'
    case 'stale':
      return 'STALE'
    default:
      return 'UNAVAILABLE'
  }
}

export function StateChip({ state, srLabel }: { state: ChipState; srLabel?: string }): ReactElement {
  const meta = STATE_META[state]
  const aria = srLabel ? `${srLabel}: ${meta.label} — ${meta.hint}` : `${meta.label} — ${meta.hint}`
  return (
    <span className={`wb2-chip wb2-chip--${state.toLowerCase()}`} data-state={state} title={meta.hint} aria-label={aria}>
      {meta.label}
    </span>
  )
}
