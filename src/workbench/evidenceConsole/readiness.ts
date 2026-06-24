// Read-only readiness normalization for the React Evidence Console.
//
// This mirrors the vanilla readiness-adapter.js contract in TypeScript so the
// React surface shares the same guarantees: a missing/stale artifact is
// surfaced explicitly and a ready/PASS state is never fabricated.

import type {
  ReadinessFreshness,
  ReadinessGate,
  ReadinessState,
} from './types'

export const MAX_READINESS_AGE_MS = 21 * 24 * 60 * 60 * 1000

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((v) => asString(v)).filter((v): v is string => v != null)
}

export function shortCommit(sha: unknown): string | null {
  const s = asString(sha)
  if (!s) return null
  return s.length > 8 ? s.slice(0, 8) : s
}

export function deriveGate(status: string | null, launchReady: boolean | null): ReadinessGate {
  if (status === 'blocked' || launchReady === false) return 'BLOCKED'
  if (launchReady === true && status !== 'blocked') return 'READY'
  if (status) return status.toUpperCase()
  return 'UNKNOWN'
}

export function evaluateFreshness(
  generatedAt: unknown,
  now: number,
  maxAgeMs: number = MAX_READINESS_AGE_MS,
): { freshness: ReadinessFreshness; staleReason: string | null } {
  const iso = asString(generatedAt)
  if (!iso) return { freshness: 'unknown', staleReason: 'No generated_at timestamp present.' }
  const parsed = Date.parse(iso)
  if (Number.isNaN(parsed)) {
    return { freshness: 'unknown', staleReason: 'Unparseable generated_at timestamp.' }
  }
  const ageMs = now - parsed
  if (ageMs > maxAgeMs) {
    const ageDays = Math.floor(ageMs / (24 * 60 * 60 * 1000))
    const maxDays = Math.floor(maxAgeMs / (24 * 60 * 60 * 1000))
    return { freshness: 'stale', staleReason: `Generated ${ageDays} day(s) ago (max ${maxDays}).` }
  }
  return { freshness: 'fresh', staleReason: null }
}

export function missingReadiness(error: string | null, source: string | null = null): ReadinessState {
  return {
    availability: 'missing',
    error,
    source,
    status: 'unknown',
    launchReady: null,
    gate: 'UNKNOWN',
    freshness: 'unknown',
    staleReason: null,
    sourceCommit: null,
    sourceCommitShort: null,
    generatedAt: null,
    summaryLine: null,
    blockers: [],
    claimBoundary: null,
    nextAction: null,
  }
}

export function normalizeReadiness(
  raw: unknown,
  options: { now?: number; source?: string | null } = {},
): ReadinessState {
  const now = options.now ?? Date.now()
  const source = options.source ?? null
  if (!raw || typeof raw !== 'object') {
    return missingReadiness('Readiness payload was not an object.', source)
  }
  const record = raw as Record<string, unknown>
  const status = asString(record.status) ?? 'unknown'
  const launchReady = typeof record.launch_ready === 'boolean' ? record.launch_ready : null
  const { freshness, staleReason } = evaluateFreshness(record.generated_at, now)
  const sourceCommit = asString(record.source_commit_sha)
  const summary = (record.summary && typeof record.summary === 'object'
    ? (record.summary as Record<string, unknown>)
    : {}) as Record<string, unknown>

  return {
    availability: 'available',
    error: null,
    source,
    status,
    launchReady,
    gate: deriveGate(status, launchReady),
    freshness,
    staleReason,
    sourceCommit,
    sourceCommitShort: shortCommit(sourceCommit),
    generatedAt: asString(record.generated_at),
    summaryLine: asString(record.summary_line),
    blockers: asStringArray(record.blockers),
    claimBoundary: asString(record.claim_boundary),
    nextAction: asString(summary.next_action),
  }
}
