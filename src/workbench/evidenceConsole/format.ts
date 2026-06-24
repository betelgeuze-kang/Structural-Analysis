// Pure formatting/verdict helpers shared by the Evidence Console components.
// The verdict logic intentionally never defaults to PASS.

import type { ReviewerDecisionKey } from './types'

export const DECISION_LABELS: Record<ReviewerDecisionKey, string> = {
  PASS: 'Pass',
  REVIEW: 'Review',
  FAIL: 'Fail',
}

export const DECISION_CLASS: Record<ReviewerDecisionKey, string> = {
  PASS: 'ec-pill--pass',
  REVIEW: 'ec-pill--review',
  FAIL: 'ec-pill--fail',
}

export function hasValue(value: unknown): boolean {
  if (value == null) return false
  if (typeof value === 'string') return value.trim() !== ''
  if (Array.isArray(value)) return value.length > 0
  return true
}

/** Returns PASS/REVIEW/FAIL only when explicitly present; otherwise null. */
export function normalizeDecision(raw: unknown): ReviewerDecisionKey | null {
  if (!hasValue(raw)) return null
  const key = String(raw).trim().toUpperCase()
  return key === 'PASS' || key === 'REVIEW' || key === 'FAIL' ? (key as ReviewerDecisionKey) : null
}

export function decisionAnnouncement(raw: unknown): string {
  const key = normalizeDecision(raw)
  return key ? DECISION_LABELS[key] : 'verdict unavailable'
}

export function formatNumber(value: unknown): string | null {
  if (typeof value !== 'number' || Number.isNaN(value)) return null
  if (value !== 0 && (Math.abs(value) < 1e-3 || Math.abs(value) >= 1e6)) {
    return value.toExponential(3)
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
}
