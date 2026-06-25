// Interprets a loaded evidence envelope into readiness facts, WITHOUT laundering
// failures into passes. Rules enforced here:
// - a missing/unreadable artifact is `missing`, never ready;
// - any blocker, status=blocked, launch_ready=false, or release_ready=false is
//   surfaced as `blocked`;
// - `ready` requires zero blockers AND an explicit positive signal;
// - contract_pass is NOT promoted to release_ready (kept as a separate field);
// - source_commit_sha is always surfaced (mismatches are reported, never hidden);
// - staleness is reported independently of the gate, so a fresh-looking but
//   blocked artifact still shows its blockers.

import type { EvidenceEnvelope } from './evidenceEnvelope'

export type GateState = 'ready' | 'blocked' | 'missing' | 'unavailable'
export type Freshness = 'fresh' | 'stale' | 'unknown'

export const MAX_EVIDENCE_AGE_MS = 21 * 24 * 60 * 60 * 1000

export interface ReadinessFacts {
  gateState: GateState
  freshness: Freshness
  staleReason: string | null
  status: string | null
  launchReady: boolean | null
  releaseReady: boolean | null
  contractPass: boolean | null
  reasonCode: string | null
  blockers: string[]
  blockerCount: number
  generatedAt: string | null
  sourceCommitSha: string | null
  sourceCommitShort: string | null
  summaryLine: string | null
  claimBoundary: string | null
  error: string | null
}

function str(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

function boolOrNull(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function shortCommit(sha: string | null): string | null {
  if (!sha) return null
  return sha.length > 8 ? sha.slice(0, 8) : sha
}

function extractBlockers(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (typeof item === 'string') return item.trim() || null
      if (item && typeof item === 'object') {
        const r = item as Record<string, unknown>
        return str(r.id) ?? str(r.code) ?? str(r.message) ?? str(r.reason) ?? JSON.stringify(item)
      }
      return null
    })
    .filter((v): v is string => v != null)
}

function evaluateFreshness(generatedAt: string | null, status: string | null, reasonCode: string | null, evidenceFresh: boolean | null, now: number): { freshness: Freshness; staleReason: string | null } {
  if (status === 'stale_or_inconsistent' || (reasonCode && reasonCode.toUpperCase().includes('STALE'))) {
    return { freshness: 'stale', staleReason: 'Source reports a stale / inconsistent status.' }
  }
  if (evidenceFresh === false) {
    return { freshness: 'stale', staleReason: 'Source reports evidence_fresh = false.' }
  }
  if (!generatedAt) return { freshness: 'unknown', staleReason: 'No generated_at timestamp.' }
  const parsed = Date.parse(generatedAt)
  if (Number.isNaN(parsed)) return { freshness: 'unknown', staleReason: 'Unparseable generated_at.' }
  const ageMs = now - parsed
  if (ageMs > MAX_EVIDENCE_AGE_MS) {
    const days = Math.floor(ageMs / (24 * 60 * 60 * 1000))
    return { freshness: 'stale', staleReason: `Generated ${days} day(s) ago.` }
  }
  return { freshness: 'fresh', staleReason: null }
}

export function interpretReadiness<T>(envelope: EvidenceEnvelope<T>, options: { now?: number } = {}): ReadinessFacts {
  const now = options.now ?? Date.now()

  if (envelope.state === 'missing' || !envelope.data || typeof envelope.data !== 'object') {
    return {
      gateState: 'missing',
      freshness: 'unknown',
      staleReason: null,
      status: null,
      launchReady: null,
      releaseReady: null,
      contractPass: null,
      reasonCode: null,
      blockers: [],
      blockerCount: 0,
      generatedAt: null,
      sourceCommitSha: envelope.sourceCommitSha ?? null,
      sourceCommitShort: shortCommit(envelope.sourceCommitSha ?? null),
      summaryLine: null,
      claimBoundary: null,
      error: envelope.error ?? 'Evidence unavailable.',
    }
  }

  const d = envelope.data as Record<string, unknown>
  const status = str(d.status)
  const launchReady = boolOrNull(d.launch_ready)
  const releaseReady = boolOrNull(d.release_ready)
  const contractPass = boolOrNull(d.contract_pass)
  const reasonCode = str(d.reason_code)
  const evidenceFresh = boolOrNull(d.evidence_fresh)
  const blockers = extractBlockers(d.blockers)
  const generatedAt = str(d.generated_at)
  const sourceCommitSha = str(d.source_commit_sha) ?? envelope.sourceCommitSha ?? null

  const { freshness, staleReason } = evaluateFreshness(generatedAt, status, reasonCode, evidenceFresh, now)

  let gateState: GateState
  if (status === 'blocked' || launchReady === false || releaseReady === false || blockers.length > 0) {
    gateState = 'blocked'
  } else if (blockers.length === 0 && (reasonCode === 'PASS' || contractPass === true) && status !== 'blocked') {
    gateState = 'ready'
  } else {
    // No explicit positive signal -> never assume pass.
    gateState = 'unavailable'
  }

  return {
    gateState,
    freshness,
    staleReason,
    status,
    launchReady,
    releaseReady,
    contractPass,
    reasonCode,
    blockers,
    blockerCount: blockers.length,
    generatedAt,
    sourceCommitSha,
    sourceCommitShort: shortCommit(sourceCommitSha),
    summaryLine: str(d.summary_line),
    claimBoundary: str(d.claim_boundary),
    error: null,
  }
}

/** Detect source-commit mismatch across several interpreted facts (never hidden). */
export function detectCommitMismatch(facts: ReadinessFacts[]): { mismatch: boolean; commits: string[] } {
  const commits = Array.from(
    new Set(facts.map((f) => f.sourceCommitSha).filter((c): c is string => c != null)),
  )
  return { mismatch: commits.length > 1, commits }
}
